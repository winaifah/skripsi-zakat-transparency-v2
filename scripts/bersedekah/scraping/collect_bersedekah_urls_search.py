"""
Kumpulkan URL kampanye zakat dari halaman search Bersedekah.com.
Sumber  : https://www.bersedekah.com/program?search=zakat
Filter  : href ATAU judul mengandung kata "zakat" (case-insensitive)
Output  : data/raw/bersedekah_search_zakat_urls.csv

Setelah selesai, script membandingkan hasil dengan file existing
data/raw/bersedekah_zakat_urls.csv untuk deteksi duplikat.

Author: Arifah Deswina (D121221030)
"""

import sys, os, time, random, re
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, parent_dir)

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium_stealth import stealth
from bs4 import BeautifulSoup
import pandas as pd

SEARCH_URL = "https://www.bersedekah.com/program?search=zakat"
BASE_URL   = "https://www.bersedekah.com"

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

def extract_links(soup):
    """
    Ekstrak semua link dari div.list-program > a[href].
    Filter: href ATAU span.judul mengandung 'zakat' (case-insensitive).
    Return list of dict.
    """
    campaigns = []
    seen = set()

    container = soup.find('div', class_='list-program')
    if not container:
        return campaigns

    for a in container.find_all('a', href=True):
        href  = a['href'].strip()
        if not href or href in seen:
            continue

        url   = href if href.startswith('http') else BASE_URL + href
        slug  = url.rstrip('/').split('/')[-1]

        # Judul
        judul_span = a.find('span', class_='judul')
        title = judul_span.get_text(strip=True) if judul_span else ''

        # Filter: "zakat" di href ATAU judul
        if 'zakat' not in url.lower() and 'zakat' not in title.lower():
            continue

        seen.add(href)

        # Organizer: span.lembaga (hapus img dan icon, ambil teks)
        lembaga_span = a.find('span', class_='lembaga')
        organizer = ''
        if lembaga_span:
            for tag in lembaga_span.find_all(['img', 'i']):
                tag.decompose()
            organizer = lembaga_span.get_text(strip=True)

        # Dana terkumpul (preview)
        terkumpul_span = a.find('span', class_='terkumpul')
        collected = terkumpul_span.get_text(strip=True) if terkumpul_span else ''

        campaigns.append({
            'url'              : url,
            'slug'             : slug,
            'title'            : title,
            'organizer'        : organizer,
            'collected_preview': collected,
            'platform'         : 'bersedekah.com',
        })

    return campaigns

def main():
    print("=" * 65)
    print("  BERSEDEKAH.COM — Kumpulkan URL Kampanye Zakat (Search)")
    print("=" * 65)
    print(f"\nSumber: {SEARCH_URL}")

    driver = init_driver()

    try:
        print(f"\n[1] Membuka halaman search...")
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

            print(f"    Kampanye zakat: {curr}", end='')
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

        # Parse final
        soup  = BeautifulSoup(driver.page_source, 'html.parser')
        items = extract_links(soup)

    finally:
        driver.quit()

    if not items:
        print("\n⚠️ Tidak ada kampanye zakat ditemukan.")
        return

    df = pd.DataFrame(items)
    before = len(df)
    df = df.drop_duplicates(subset='url').reset_index(drop=True)
    df.insert(0, 'no', df.index + 1)

    print(f"\n{'='*65}")
    print(f"Total URL zakat (search) : {len(df)}  (sebelum dedup: {before})")
    print(f"{'='*65}")

    out_path = os.path.join(parent_dir, 'data', 'raw', 'bersedekah_search_zakat_urls.csv')
    df.to_csv(out_path, index=False, encoding='utf-8')
    print(f"✓ Disimpan ke: {out_path}")

    # ── Bandingkan dengan file existing ──────────────────────────────
    existing_path = os.path.join(parent_dir, 'data', 'raw', 'bersedekah_zakat_urls.csv')
    if os.path.exists(existing_path):
        df_old = pd.read_csv(existing_path)
        old_urls = set(df_old['url'].str.strip())
        new_urls = set(df['url'].str.strip())

        duplikat   = new_urls & old_urls
        hanya_baru = new_urls - old_urls
        hanya_lama = old_urls - new_urls

        print(f"\n{'='*65}")
        print("📊 PERBANDINGAN DENGAN FILE EXISTING")
        print(f"{'='*65}")
        print(f"  File existing ({os.path.basename(existing_path)}) : {len(df_old)} kampanye")
        print(f"  File search baru                              : {len(df)} kampanye")
        print(f"  Duplikat (ada di kedua file)                  : {len(duplikat)}")
        print(f"  Hanya di file baru (belum ada di existing)    : {len(hanya_baru)}")
        print(f"  Hanya di file lama (tidak ada di search)      : {len(hanya_lama)}")

        if hanya_baru:
            print(f"\n  URL BARU (perlu ditambahkan ke existing):")
            df_baru = df[df['url'].isin(hanya_baru)][['no','url','title','organizer']]
            for _, row in df_baru.iterrows():
                print(f"    [{row['no']:3d}] {row['title'][:45]:<45} | {row['organizer'][:30]}")

        if duplikat:
            print(f"\n  DUPLIKAT ({len(duplikat)} URL ada di kedua file) — tidak perlu scrape ulang")

        # Simpan daftar URL baru saja (untuk scraping selanjutnya jika ada)
        if hanya_baru:
            df_new_only = df[df['url'].isin(hanya_baru)].reset_index(drop=True)
            df_new_only['no'] = df_new_only.index + 1
            new_only_path = os.path.join(
                parent_dir, 'data', 'raw', 'bersedekah_new_urls.csv')
            df_new_only.to_csv(new_only_path, index=False, encoding='utf-8')
            print(f"\n  ✓ URL baru saja disimpan ke: {new_only_path}")

        print(f"{'='*65}")
    else:
        print(f"\n⚠️  File existing tidak ditemukan: {existing_path}")

    # Preview
    print(f"\nPreview (10 pertama):")
    print(df[['no','title','organizer']].head(10).to_string(index=False))

if __name__ == '__main__':
    main()
