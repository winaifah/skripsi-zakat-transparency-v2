import sys, os, time, re
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, parent_dir)

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from webdriver_manager.chrome import ChromeDriverManager
from selenium_stealth import stealth
from bs4 import BeautifulSoup
import pandas as pd
from datetime import datetime

SEARCH_URL = "https://rumahyatim.org/search"
BASE_URL   = "https://rumahyatim.org"
KEYWORD    = "zakat"

def init_driver():
    options = Options()
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    options.add_argument("--start-maximized")
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    stealth(driver,
        languages=["id-ID","id","en-US","en"],
        vendor="Google Inc.", platform="MacIntel",
        webgl_vendor="Intel Inc.", renderer="Intel Iris OpenGL Engine",
        fix_hairline=True,
    )
    return driver

def find_search_input(driver):
    """Cari elemen input search — coba beberapa selector."""
    selectors = [
        "input[type='search']",
        "input[placeholder*='Cari']",
        "input[placeholder*='Search']",
        "input[placeholder*='cari']",
        "input[name='q']",
        "input[name='search']",
        "input[name='keyword']",
        "input",
    ]
    for sel in selectors:
        try:
            elems = driver.find_elements(By.CSS_SELECTOR, sel)
            if elems:
                return elems[0]
        except Exception:
            pass
    return None

def do_search(driver, keyword):
 
    driver.get(SEARCH_URL)
    time.sleep(4)

    inp = find_search_input(driver)
    if not inp:
        print("  ⚠️  Input search tidak ditemukan!")
        return False

    inp.click()
    inp.clear()
    time.sleep(0.3)
    inp.send_keys(keyword)
    time.sleep(3.5) 

    soup = BeautifulSoup(driver.page_source, 'html.parser')
    found = soup.find_all('span', class_='text-universa-font-color')
    return len(found) > 0

def scroll_load_all(driver):
    prev = 0
    no_change = 0
    while no_change < 4:
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2.0)
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        curr = len(soup.find_all('span', class_='text-universa-font-color'))
        if curr > prev:
            print(f"       {curr} card termuat (+{curr-prev})")
            prev = curr
            no_change = 0
        else:
            no_change += 1
    driver.execute_script("window.scrollTo(0, 0);")
    time.sleep(0.5)
    return prev

def parse_cards(driver):
    soup = BeautifulSoup(driver.page_source, 'html.parser')

    container = soup.find('div', class_=lambda c: c and
                           'divide-y' in c and 'divide-gray-100' in c)
    if not container:
        cards_html = soup.find_all('div', class_=lambda c: c and
                                    'hover:bg-gray-50' in c and
                                    'transition-colors' in c)
    else:
        cards_html = container.find_all('div', class_=lambda c: c and
                                         'hover:bg-gray-50' in c and
                                         'transition-colors' in c)

    cards = []
    for i, card in enumerate(cards_html):
        title_span = card.find('span', class_='text-universa-font-color')
        title = title_span.get_text(strip=True) if title_span else ''

        badge = card.find('div', class_=lambda c: c and 'bg-red-500' in c)
        status = badge.get_text(strip=True) if badge else 'Aktif'
        if title:
            cards.append({'index': i, 'title': title, 'status': status})

    return cards

def click_card_by_index(driver, target_index, title_hint=""):

    try:
        cards = driver.find_elements(
            By.XPATH,
            "//div[contains(@class,'hover:bg-gray-50') and contains(@class,'transition-colors')]"
            "//div[contains(@style,'cursor: pointer')]"
        )
        if target_index >= len(cards):
            print(f" Index {target_index} melebihi jumlah card ({len(cards)})")
            return False

        card = cards[target_index]
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", card)
        time.sleep(0.5)
        before_url = driver.current_url
        driver.execute_script("arguments[0].click();", card)
        time.sleep(4)
        after_url = driver.current_url
        return after_url != before_url and 'search' not in after_url
    except Exception as e:
        print(f" Klik gagal: {str(e)[:70]}")
        return False

def main():
    print("=" * 65)
    print("  RUMAH YATIM — Kumpulkan URL Kampanye Zakat")
    print("=" * 65)

    driver = init_driver()

    # ── Langkah 1: Dapatkan daftar semua kampanye ─────────────────
    print(f"\n[1] Search '{KEYWORD}' di {SEARCH_URL}...")
    ok = do_search(driver, KEYWORD)
    if not ok:
        print("Hasil search tidak muncul. Cek selector input search.")
        input("Tekan Enter untuk lanjut manual (sudah ada hasil di browser?)...")

    print("[2] Scroll untuk muat semua card...")
    total = scroll_load_all(driver)
    cards_info = parse_cards(driver)
    print(f"\n✓ Total: {len(cards_info)} kampanye ditemukan")

    if not cards_info:
        print("Tidak ada card ditemukan. Periksa selector.")
        driver.quit()
        return

    print("\nDaftar kampanye:")
    for c in cards_info:
        badge = f" [{c['status']}]" if c['status'] != 'Aktif' else ''
        print(f"  {c['index']+1:2d}. {c['title'][:55]}{badge}")

    confirm = input("\nLanjut kumpulkan URL satu per satu? (y/n): ").strip().lower()
    if confirm != 'y':
        driver.quit()
        return

    # ── Langkah 2: Klik satu per satu, catat URL ─────────────────
    results = []
    print()
    for i, card_info in enumerate(cards_info):
        title   = card_info['title']
        status  = card_info['status']
        idx     = card_info['index']
        print(f"[{i+1}/{len(cards_info)}] {title[:50]}")

        # Re-search (selalu, karena search state hilang setelah klik)
        ok = do_search(driver, KEYWORD)
        if not ok:
            print(" Search gagal, coba lagi...")
            time.sleep(3)
            ok = do_search(driver, KEYWORD)
        scroll_load_all(driver)

        navigated = click_card_by_index(driver, idx, title)
        if navigated:
            url  = driver.current_url
            slug = url.rstrip('/').split('/')[-1]
            results.append({
                'no'    : i + 1,
                'title' : title,
                'url'   : url,
                'slug'  : slug,
                'status': status,
            })
            print(f"  ✓ {url}")
        else:

            print(f"  ⚠️  Navigasi gagal via index, coba via teks...")
            try:
                escaped = title.replace("'", "\\'")
                span = driver.find_element(
                    By.XPATH,
                    f"//span[contains(@class,'text-universa-font-color')"
                    f" and normalize-space(text())='{escaped}']"
                )
                clickable = span.find_element(
                    By.XPATH, "./ancestor::div[contains(@style,'cursor: pointer')]")
                before = driver.current_url
                driver.execute_script("arguments[0].click();", clickable)
                time.sleep(4)
                url = driver.current_url
                if url != before and 'search' not in url:
                    slug = url.rstrip('/').split('/')[-1]
                    results.append({'no': i+1, 'title': title,
                                    'url': url, 'slug': slug, 'status': status})
                    print(f"  ✓ {url}")
                else:
                    print(f"  ❌ Gagal dapat URL untuk: {title}")
                    results.append({'no': i+1, 'title': title,
                                    'url': '', 'slug': '', 'status': status})
            except Exception as e:
                print(f"  ❌ Error: {str(e)[:70]}")
                results.append({'no': i+1, 'title': title,
                                'url': '', 'slug': '', 'status': status})

        time.sleep(2)

    driver.quit()

    df = pd.DataFrame(results)
    out = os.path.join(parent_dir, 'data', 'raw', 'rumahyatim_zakat_urls.csv')
    df.to_csv(out, index=False, encoding='utf-8')

    print("\n" + "=" * 65)
    print("SELESAI!")
    print("=" * 65)
    ok_count = (df['url'] != '').sum()
    print(f"Berhasil dapat URL : {ok_count}/{len(df)}")
    print(f"Output             : {out}")
    if len(df) > 0:
        print("\nHasil:")
        for _, r in df.iterrows():
            print(f"  {r['no']:2d}. [{r['status']:6s}] {r['title'][:45]}")
            print(f"       {r['url']}")
    print("=" * 65)

if __name__ == '__main__':
    main()
