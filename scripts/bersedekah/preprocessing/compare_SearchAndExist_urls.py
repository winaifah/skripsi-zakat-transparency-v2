import sys
import os
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
import time

EXISTING_CSV = os.path.join(parent_dir, 'data', 'raw', 'bersedekah_zakat_urls.csv')
OUTPUT_CSV   = os.path.join(parent_dir, 'data', 'raw', 'bersedekah_missing_urls.csv')
SEARCH_URL   = 'https://www.bersedekah.com/program?search=zakat'


def init_driver():
    options = Options()
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    options.add_argument("--start-maximized")

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)

    stealth(driver,
        languages=["id-ID", "id"],
        vendor="Google Inc.",
        platform="MacIntel",
        webgl_vendor="Intel Inc.",
        renderer="Intel Iris OpenGL Engine",
        fix_hairline=True,
    )
    return driver


def scroll_to_bottom(driver, pause=2, max_scrolls=100):
    last_h = driver.execute_script("return document.body.scrollHeight")
    no_change = 0
    for i in range(max_scrolls):
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(pause)
        new_h = driver.execute_script("return document.body.scrollHeight")
        if new_h == last_h:
            no_change += 1
            if no_change >= 3:
                print(f"  ✓ Selesai scroll ({i+1} kali)")
                break
        else:
            no_change = 0
        last_h = new_h
        if (i+1) % 10 == 0:
            print(f"  ... {i+1} scroll")


def extract_campaigns(driver):
    """Extract semua kampanye dari halaman saat ini."""
    soup = BeautifulSoup(driver.page_source, 'html.parser')
    campaigns = []
    seen = set()

    links = soup.find_all('a', href=lambda h: h and '/program/' not in h and h.startswith('https://www.bersedekah.com/'))

    for a in links:
        href = a.get('href', '').strip().rstrip('/')
        if not href or href in seen:
            continue

        # Judul
        judul_el = a.find('span', class_='judul') or a.find(class_=lambda c: c and 'judul' in c)
        if not judul_el:
            # fallback: h2/h3/h4 di dalam <a>
            judul_el = a.find(['h2', 'h3', 'h4', 'h5'])
        title = judul_el.get_text(strip=True) if judul_el else a.get_text(strip=True)[:80]

        # Program group label
        group_el = a.find('label', class_='program-group') or \
                   a.find(class_=lambda c: c and 'program-group' in str(c))
        group = group_el.get_text(strip=True) if group_el else ""

        # Filter: judul atau group harus mengandung "zakat"
        if 'zakat' not in title.lower() and 'zakat' not in group.lower():
            continue

        # Organizer dari URL: bersedekah.com/{organizer}/{slug}
        parts = href.replace('https://www.bersedekah.com/', '').split('/')
        organizer_slug = parts[0] if len(parts) >= 1 else ""
        slug = parts[-1] if len(parts) >= 2 else organizer_slug

        # Lembaga (organizer nama)
        lembaga_el = a.find('span', class_='lembaga')
        if lembaga_el:
            for tag in lembaga_el.find_all(['img', 'i']):
                tag.decompose()
            organizer = lembaga_el.get_text(strip=True)
        else:
            organizer = organizer_slug

        seen.add(href)
        campaigns.append({
            'title': title,
            'organizer': organizer,
            'url': href,
            'slug': slug,
            'platform': 'bersedekah.com',
            'program_group': group,
        })

    return campaigns


def main():
    print("="*70)
    print("CEK BERSEDEKAH.COM /program?search=zakat vs CSV yang ada")
    print("="*70)

    # Load existing URLs
    df_existing = pd.read_csv(EXISTING_CSV)
    existing_urls = set(df_existing['url'].str.rstrip('/').str.lower())
    print(f"✓ CSV existing: {len(existing_urls)} URL")

    # Init driver
    driver = init_driver()

    try:
        print(f"\nBuka: {SEARCH_URL}")
        driver.get(SEARCH_URL)
        time.sleep(5)

        print("Scroll untuk muat semua kampanye...")
        scroll_to_bottom(driver)

        print("\nExtract kampanye...")
        campaigns = extract_campaigns(driver)
        print(f"  Ditemukan {len(campaigns)} kampanye zakat di /program?search=zakat")

    finally:
        driver.quit()
        print("✓ Browser ditutup")

    if not campaigns:
        print("\n Tidak ada kampanye ditemukan — cek selector HTML-nya")
        return

    # Bandingkan
    missing = []
    for c in campaigns:
        url_norm = c['url'].rstrip('/').lower()
        if url_norm not in existing_urls:
            missing.append(c)

    print(f"\n{'='*70}")
    print(f"HASIL PERBANDINGAN:")
    print(f"  Total di /program?search=zakat : {len(campaigns)}")
    print(f"  Sudah ada di CSV               : {len(campaigns) - len(missing)}")
    print(f"  ⚡ TERLEWAT (belum di CSV)      : {len(missing)}")
    print(f"{'='*70}")

    if missing:
        df_missing = pd.DataFrame(missing)
        # Tambah nomor urut (lanjutan dari CSV existing)
        start_no = df_existing['no'].max() + 1
        df_missing.insert(0, 'no', range(int(start_no), int(start_no) + len(missing)))

        df_missing.to_csv(OUTPUT_CSV, index=False, encoding='utf-8')
        print(f"\n Disimpan ke: {OUTPUT_CSV}")
        print(f"\nDaftar yang terlewat:")
        for _, row in df_missing.iterrows():
            print(f"  {row['no']}. [{row['program_group']}] {row['title'][:50]} — {row['url']}")
    else:
        print("\n Tidak ada yang terlewat — semua sudah ada di CSV!")


if __name__ == "__main__":
    main()
