import sys, os, time, random
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, parent_dir)

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
from selenium_stealth import stealth
from bs4 import BeautifulSoup
import pandas as pd

BASE_URL   = "https://digital.dompetdhuafa.org"
SEARCH_URL = "https://digital.dompetdhuafa.org/hasil-pencarian?keyword=zakat&page={page}"

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

def get_last_page(soup):

    page_buttons = soup.find_all('button', class_='btn-page')
    nums = []
    for btn in page_buttons:
        txt = btn.get_text(strip=True)
        if txt.isdigit():
            nums.append(int(txt))
    return max(nums) if nums else 1

def is_next_disabled(soup):

    next_btn = soup.find('button', {'aria-label': 'Go to next page'})
    return next_btn is not None and next_btn.get('disabled') is not None

def scrape_page(soup):

    cards = soup.find_all('div', class_='card-campaign')
    campaigns = []
    for card in cards:
        # Link & slug
        link_tag = card.find('a', class_='card-img')
        if not link_tag:
            continue
        href = link_tag.get('href', '')
        url  = BASE_URL + href if href.startswith('/') else href
        slug = href.strip('/').split('/')[-1]

        # Title
        title_tag = card.find('h5', class_='title')
        title = title_tag.get_text(strip=True) if title_tag else ''

        # Organizer
        org_tag = card.find('span', class_='creator__name')
        organizer = org_tag.get_text(strip=True) if org_tag else ''

        # Collected amount
        collected_tag = card.find('strong', class_='text-green')
        collected = collected_tag.get_text(strip=True) if collected_tag else ''

        campaigns.append({
            'url'      : url,
            'slug'     : slug,
            'title'    : title,
            'organizer': organizer,
            'collected_preview': collected,
            'platform' : 'dompetdhuafa',
        })
    return campaigns

def main():
    print("=" * 65)
    print("  DOMPET DHUAFA — Kumpulkan URL Kampanye Zakat")
    print("=" * 65)

    driver = init_driver()
    all_campaigns = []
    page = 1

    try:
        while True:
            delay = random.uniform(3, 6) if page > 1 else 0
            if delay:
                print(f"\n[Page {page}] Delay {delay:.1f}s...")
                time.sleep(delay)
            else:
                print(f"\n[Page {page}] Loading...")

            driver.get(SEARCH_URL.format(page=page))
            time.sleep(5)

            soup = BeautifulSoup(driver.page_source, 'html.parser')
            campaigns = scrape_page(soup)

            if not campaigns:
                print(f"  ⚠️ Tidak ada kampanye di halaman {page} — berhenti.")
                break

            all_campaigns.extend(campaigns)
            print(f"  Kampanye: {len(campaigns)} | Total: {len(all_campaigns)}")

            if is_next_disabled(soup):
                print(f"  ✓ Tombol Next disabled — halaman terakhir tercapai.")
                break

            page += 1

    finally:
        driver.quit()


    df = pd.DataFrame(all_campaigns)
    before = len(df)
    df = df.drop_duplicates(subset='url')
    df = df.reset_index(drop=True)
    df.insert(0, 'no', df.index + 1)

    print(f"\n{'='*65}")
    print(f"Total URL terkumpul : {len(df)} kampanye (sebelum dedup: {before})")
    print(f"{'='*65}")

    out_path = os.path.join(parent_dir, 'data', 'raw', 'dompetdhuafa_zakat_urls.csv')
    df.to_csv(out_path, index=False, encoding='utf-8')
    print(f"✓ Disimpan ke: {out_path}")
    print(df[['no', 'slug', 'title']].to_string(index=False))

if __name__ == '__main__':
    main()
