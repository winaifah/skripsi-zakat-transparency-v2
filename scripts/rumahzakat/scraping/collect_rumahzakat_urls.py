import sys, os, time, random
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, parent_dir)

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium_stealth import stealth
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import pandas as pd

BASE_URL     = "https://www.rumahzakat.org"
ENTRY_URL    = "https://www.rumahzakat.org/donasi"
CATEGORY_URL = "https://www.rumahzakat.org/donasi/category/zakat"

def init_driver():
    options = Options()
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    options.add_argument("--start-maximized")
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    stealth(driver,
        languages=["id-ID", "id", "en-US", "en"],
        vendor="Google Inc.", platform="MacIntel",
        webgl_vendor="Intel Inc.", renderer="Intel Iris OpenGL Engine",
        fix_hairline=True,
    )
    return driver

def extract_links(soup):
    """Ekstrak semua link kampanye dari grid 2 kolom."""
    campaigns = []
    grid = soup.find('div', class_=lambda c: c and 'grid-cols-2' in c)
    if not grid:
        return campaigns

    for a in grid.find_all('a', href=True):
        href = a['href']
        # Resolve URL relatif: ../zakat-xxx → /donasi/zakat-xxx
        full_url = urljoin(CATEGORY_URL + '/', href)

        # Slug = bagian terakhir URL
        slug = full_url.rstrip('/').split('/')[-1]

        # Judul dari figcaption atau alt img
        fig = a.find('figcaption')
        title = fig.get_text(strip=True) if fig else ''
        if not title:
            img = a.find('img')
            title = img.get('alt', '').strip() if img else ''

        if slug and slug not in ('donasi', 'category'):
            campaigns.append({
                'url'     : full_url,
                'slug'    : slug,
                'title'   : title,
                'platform': 'rumahzakat',
            })
    return campaigns

def scroll_to_bottom(driver):
    """Scroll ke bawah lalu return tinggi halaman."""
    return driver.execute_script("""
        window.scrollTo(0, document.body.scrollHeight);
        return document.body.scrollHeight;
    """)

def main():
    print("=" * 65)
    print("  RUMAH ZAKAT — Kumpulkan URL Kampanye Zakat")
    print("=" * 65)

    driver = init_driver()

    try:
        # ── Step 1: Buka /donasi dulu agar SvelteKit session valid ──
        print(f"\n[1] Membuka entry page: {ENTRY_URL}")
        driver.get(ENTRY_URL)
        time.sleep(5)

        # ── Step 2: Navigasi ke category/zakat ───────────────────
        print(f"[2] Navigasi ke: {CATEGORY_URL}")
        driver.get(CATEGORY_URL)
        time.sleep(6)

        # ── Step 3: Scroll sampai tidak ada item baru ─────────────
        print("[3] Mulai scroll infinite...")
        prev_count = 0
        no_change_rounds = 0
        MAX_NO_CHANGE = 4   # berhenti kalau 4 scroll berturut-turut tidak ada item baru

        while True:
            soup = BeautifulSoup(driver.page_source, 'html.parser')
            items = extract_links(soup)
            curr_count = len(items)

            print(f"    Items ditemukan: {curr_count}", end='')

            if curr_count > prev_count:
                print(f"  (+{curr_count - prev_count})")
                prev_count = curr_count
                no_change_rounds = 0
            else:
                no_change_rounds += 1
                print(f"  (tidak bertambah — {no_change_rounds}/{MAX_NO_CHANGE})")
                if no_change_rounds >= MAX_NO_CHANGE:
                    print("  ✓ Tidak ada item baru — scroll selesai.")
                    break

            scroll_to_bottom(driver)
            wait = random.uniform(2.5, 4.5)
            time.sleep(wait)

        # ── Parse final ───────────────────────────────────────────
        soup  = BeautifulSoup(driver.page_source, 'html.parser')
        items = extract_links(soup)

    finally:
        driver.quit()

    if not items:
        print("\n⚠️ Tidak ada kampanye ditemukan.")
        return

    # ── Deduplikasi ───────────────────────────────────────────────
    df = pd.DataFrame(items)
    before = len(df)
    df = df.drop_duplicates(subset='url').reset_index(drop=True)
    df.insert(0, 'no', df.index + 1)

    print(f"\n{'='*65}")
    print(f"Total URL terkumpul : {len(df)} kampanye (sebelum dedup: {before})")
    print(f"{'='*65}")

    # ── Simpan ────────────────────────────────────────────────────
    out_path = os.path.join(parent_dir, 'data', 'raw', 'rumahzakat_zakat_urls.csv')
    df.to_csv(out_path, index=False, encoding='utf-8')
    print(f"✓ Disimpan ke: {out_path}")
    print(df[['no', 'slug', 'title']].to_string(index=False))

if __name__ == '__main__':
    main()
