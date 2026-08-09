import sys, os, time, random
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, parent_dir)

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium_stealth import stealth
from bs4 import BeautifulSoup
import pandas as pd

SEARCH_URL = "https://donasionline.id/search?q=zakat"
BASE_URL   = "https://donasionline.id"

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
    campaigns = []
    seen = set()
    for card in soup.find_all('div', attrs={'data-pg-name': 'card'}):
        a = card.find('a', class_=lambda c: c and 'absolute' in c and 'inset-0' in c)
        if not a:
            continue
        href = a.get('href', '')
        if not href or href in seen:
            continue
        seen.add(href)

        url  = href if href.startswith('http') else BASE_URL + href
        slug = url.rstrip('/').split('/')[-1]

        h3    = card.find('h3')
        title = h3.get_text(strip=True) if h3 else ''

        # collected & donor 
        spans = card.find_all('span', class_=lambda c: c and
                               'font-semibold' in c and 'text-black' in c)
        collected = spans[0].get_text(strip=True) if len(spans) > 0 else ''
        donor     = spans[1].get_text(strip=True) if len(spans) > 1 else ''

        campaigns.append({
            'url'              : url,
            'slug'             : slug,
            'title'            : title,
            'collected_preview': collected,
            'donor_preview'    : donor,
            'platform'         : 'donasionline',
        })
    return campaigns

def main():
    print("=" * 65)
    print("  DONASI ONLINE — Kumpulkan URL Kampanye Zakat")
    print("=" * 65)

    driver = init_driver()

    try:
        print(f"\n[1] Membuka: {SEARCH_URL}")
        driver.get(SEARCH_URL)
        time.sleep(6)

        print("[2] Mulai scroll infinite...")
        prev_count    = 0
        no_change     = 0
        MAX_NO_CHANGE = 4

        while True:
            soup  = BeautifulSoup(driver.page_source, 'html.parser')
            items = extract_links(soup)
            curr  = len(items)

            print(f"    Items ditemukan: {curr}", end='')
            if curr > prev_count:
                print(f"  (+{curr - prev_count})")
                prev_count = curr
                no_change  = 0
            else:
                no_change += 1
                print(f"  (tidak bertambah — {no_change}/{MAX_NO_CHANGE})")
                if no_change >= MAX_NO_CHANGE:
                    print("  ✓ Tidak ada item baru — scroll selesai.")
                    break

            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(random.uniform(2.5, 4.0))

        soup  = BeautifulSoup(driver.page_source, 'html.parser')
        items = extract_links(soup)

    finally:
        driver.quit()

    if not items:
        print("\n Tidak ada kampanye ditemukan.")
        return

    df = pd.DataFrame(items)
    before = len(df)
    df = df.drop_duplicates(subset='url').reset_index(drop=True)
    df.insert(0, 'no', df.index + 1)

    print(f"\n{'='*65}")
    print(f"Total URL terkumpul : {len(df)} kampanye (sebelum dedup: {before})")
    print(f"{'='*65}")

    out_path = os.path.join(parent_dir, 'data', 'raw', 'donasionline_zakat_urls.csv')
    df.to_csv(out_path, index=False, encoding='utf-8')
    print(f"✓ Disimpan ke: {out_path}")
    print(df[['no', 'slug', 'title']].to_string(index=False))

if __name__ == '__main__':
    main()