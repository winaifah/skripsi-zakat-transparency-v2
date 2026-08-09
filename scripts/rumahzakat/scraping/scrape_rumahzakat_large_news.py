"""
SCRIPT 11: Scrape ulang latest_news untuk kampanye Rumah Zakat besar.
scrape_rumahzakat_detail.py kadang tidak berhasil memuat SEMUA item berita
saat update_count besar (scroll berhenti lebih awal) — script ini
menangani kampanye tsb secara khusus dengan scroll murni sampai mentok.

Beda dengan Kitabisa: di Rumah Zakat halaman info-penyaluran TIDAK punya
modal popup per item. Setiap item sudah/akan tampil inline di halaman —
cukup klik tombol "Lihat Selengkapnya" (jika ada, untuk expand/load more)
lalu scroll ke bawah terus-menerus sampai konten berhenti bertambah.

Kampanye dimasukkan jika update_count > THRESHOLD dan latest_news_json
masih kosong/error/'no updates' (lihat NEEDS_RE).

Input  : CSV yang punya kolom no, url, slug, update_count, latest_news_json
         (mis. data/processed/rumahzakat_details_*.csv)
Output :
  • data/processed/rumahzakat_json/<no>_<slug>_news.json — list news item lengkap
  • CSV input diupdate:
        latest_news_json  = "FILE:<no>_<slug>_news.json"
        disbursement_json = "FILE:<no>_<slug>_news.json" (turunan, filter "pencairan dana")
                            atau "no disbursement" jika tidak ada

Cara baca FILE: reference saat analisis:
    val = row['latest_news_json']
    if str(val).startswith('FILE:'):
        data = json.load(open(f"data/processed/rumahzakat_json/{val[5:]}"))

Author: Arifah Deswina (D121221030)
"""

import sys, os, time, random, re, json
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
from datetime import datetime

BASE_URL  = "https://www.rumahzakat.org"
ENTRY_URL = "https://www.rumahzakat.org/donasi"

NEWS_JSON_DIR = os.path.join(parent_dir, 'data', 'processed', 'rumahzakat_json')
os.makedirs(NEWS_JSON_DIR, exist_ok=True)

THRESHOLD     = 40   # kampanye dengan update_count > ini ditangani script ini
RESTART_EVERY = 5    # restart driver tiap N kampanye

ITEM_FILTER = lambda c: (c and 'order-1' in c and 'bg-gray-50' in c
                         and 'rounded-lg' in c and 'shadow' in c)

# ─────────────────────────────────────────────────────────────────
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

def clean_text(element):
    if not element:
        return ""
    for tag in element.find_all(['img','figure','figcaption','svg','video','picture']):
        tag.decompose()
    text = element.get_text(strip=True, separator=' ')
    return re.sub(r'\s{2,}', ' ', text).strip()

# ─────────────────────────────────────────────────────────────────
def find_news_url(driver, soup):
    """Cari URL halaman info-penyaluran dari halaman kampanye."""
    a = soup.find('a', href=re.compile(r'/care/info-penyaluran/'))
    if a:
        href = a['href']
        return href if href.startswith('http') else BASE_URL + href

    try:
        buttons = driver.find_elements(
            By.XPATH,
            "//button[.//div[contains(normalize-space(text()),'Lihat Selengkapnya')]]"
        )
        for btn in buttons:
            try:
                parent_html = btn.find_element(
                    By.XPATH, './ancestor::div[contains(@class,"px-4")][1]'
                ).get_attribute('innerHTML')
                if 'Info Terbaru' in parent_html:
                    current_url = driver.current_url
                    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
                    time.sleep(0.5)
                    driver.execute_script("arguments[0].click();", btn)
                    time.sleep(4)
                    new_url = driver.current_url
                    if new_url != current_url and 'info-penyaluran' in new_url:
                        return new_url
                    driver.back()
                    time.sleep(3)
                    break
            except Exception:
                continue
    except Exception:
        pass
    return None

def _click_load_more(driver):
    """Klik tombol 'Lihat Selengkapnya'/'Muat lebih banyak' di halaman berita jika ada."""
    try:
        btn = driver.find_element(
            By.XPATH,
            "//button[.//div[contains(normalize-space(text()),'Lihat Selengkapnya')]"
            " or contains(normalize-space(.),'Lihat Selengkapnya')"
            " or contains(normalize-space(.),'Muat')]"
        )
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
        time.sleep(0.4)
        driver.execute_script("arguments[0].click();", btn)
        time.sleep(2)
        return True
    except Exception:
        return False

def _parse_items(soup):
    items = []
    for div in soup.find_all('div', class_=ITEM_FILTER):
        date_p    = div.find('p', class_=lambda c: c and 'text-gray-400' in c)
        title_h3  = div.find('h3', class_=lambda c: c and 'text-gray-800' in c)
        content_p = div.find('p', class_=lambda c: c and 'tracking-wide' in c)

        date    = date_p.get_text(strip=True)   if date_p    else ''
        title   = title_h3.get_text(strip=True) if title_h3  else ''
        content = clean_text(content_p)         if content_p else ''

        if title or content:
            items.append({'date': date, 'title': title, 'content': content})
    return items

# ─────────────────────────────────────────────────────────────────
def scrape_latest_news(driver, campaign_url, expected_count):
    """
    Buka halaman info-penyaluran, klik 'Lihat Selengkapnya' (jika ada,
    untuk expand inline — bukan modal), lalu scroll murni ke bawah
    sampai jumlah item berhenti bertambah.
    """
    print(f"    📰 Latest news ({expected_count} expected)")

    driver.get(campaign_url)
    time.sleep(6)
    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
    time.sleep(2)
    driver.execute_script("window.scrollTo(0, 0);")
    time.sleep(1)

    soup = BeautifulSoup(driver.page_source, 'html.parser')
    news_url = find_news_url(driver, soup)
    if not news_url:
        print("       ⚠️  URL info-penyaluran tidak ditemukan")
        return None, "NEWS_URL_NOT_FOUND"

    if 'info-penyaluran' not in driver.current_url:
        print(f"       → {news_url}")
        driver.get(news_url)
        time.sleep(5)

    # Expand inline jika ada tombol "Lihat Selengkapnya"/"Muat lebih banyak"
    for _ in range(5):
        if not _click_load_more(driver):
            break

    # Pure scroll ke bawah sampai jumlah item stabil
    print("       Scroll untuk muat semua berita...")
    prev_count = 0
    no_change  = 0
    while no_change < 5:
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2.5)
        _click_load_more(driver)   # kadang muncul lagi di tengah scroll

        soup_tmp = BeautifulSoup(driver.page_source, 'html.parser')
        curr = len(soup_tmp.find_all('div', class_=ITEM_FILTER))
        if curr > prev_count:
            print(f"       {curr} item ditemukan (+{curr-prev_count})")
            prev_count = curr
            no_change  = 0
        else:
            no_change += 1

    soup  = BeautifulSoup(driver.page_source, 'html.parser')
    items = _parse_items(soup)
    print(f"       ✓ Selesai: {len(items)}/{expected_count} item diekstrak")
    return items, "OK"

# ─────────────────────────────────────────────────────────────────
def save_to_file(data, no, slug, suffix):
    """Simpan list ke JSON file, return filename (bukan full path)."""
    fname = f"{no}_{slug}_{suffix}.json"
    fpath = os.path.join(NEWS_JSON_DIR, fname)
    with open(fpath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return fname

# ─────────────────────────────────────────────────────────────────
def main():
    print("=" * 65)
    print("  SCRIPT 11 — Rumah Zakat: Re-scrape Latest News Kampanye Besar")
    print("=" * 65)

    default = os.path.join(parent_dir, 'data', 'processed',
                           'rumahzakat_large_campaigns.csv')
    print(f"\nFile default : {default}")
    custom = input("Pakai file lain? (Enter = default, atau ketik path): ").strip()
    input_file = custom if custom else default

    df = pd.read_csv(input_file)
    print(f"✓ Total baris: {len(df)}")

    NEEDS_RE = ['[]', '', 'nan', 'None', 'CF_BLOCKED', 'CLOUDFLARE_BLOCKED',
                'NEWS_URL_NOT_FOUND']

    def needs_scraping(row):
        val = str(row.get('latest_news_json', ''))
        return val in NEEDS_RE or val.startswith('{"note"') or val == 'no updates'

    def qualifies(row):
        uc = int(str(row.get('update_count', 0) or 0))
        return uc > THRESHOLD and needs_scraping(row)

    mask = df.apply(qualifies, axis=1)
    df_todo = df[mask].reset_index(drop=True)
    print(f"  Perlu scrape : {len(df_todo)} kampanye")

    if df_todo.empty:
        print("Tidak ada kampanye yang perlu di-scrape.")
        return

    print(f"\n  Tersedia: 1 – {len(df_todo)}")
    start = int(input("Mulai dari baris ke- (1-based): ").strip())
    count = int(input("Scrape berapa kampanye    : ").strip())
    batch = df_todo.iloc[start-1 : start-1+count]
    print(f"\n✓ Akan scrape {len(batch)} kampanye (baris {start}–{start-1+len(batch)})\n")

    confirm = input("Proceed? (y/n): ").strip().lower()
    if confirm != 'y':
        print("Cancelled.")
        return

    driver = init_driver()
    print(f"[Init] Membuka entry page: {ENTRY_URL}")
    driver.get(ENTRY_URL)
    time.sleep(5)

    start_time = datetime.now()
    processed  = 0

    for i, (_, row) in enumerate(batch.iterrows()):
        slug = str(row['slug'])
        url  = str(row['url'])
        no   = str(row.get('no', i + 1))
        uc   = int(str(row.get('update_count', 0) or 0))

        print(f"\n[{i+1}/{len(batch)}] #{no} {slug[:50]}")
        print(f"  update_count={uc}")

        delay = random.uniform(6, 11)
        print(f"  ⏳ Delay {delay:.1f}s...")
        time.sleep(delay)

        news_data, status = scrape_latest_news(driver, url, uc)

        if status == "NEWS_URL_NOT_FOUND":
            df.loc[df['slug'] == slug, 'latest_news_json'] = 'NEWS_URL_NOT_FOUND'
            print(f"  ❌ News URL tidak ditemukan")
        elif news_data is not None:
            fname = save_to_file(news_data, no, slug, 'news')
            df.loc[df['slug'] == slug, 'latest_news_json'] = f"FILE:{fname}"
            df.loc[df['slug'] == slug, 'update_count']     = len(news_data)

            # Pencairan dana = subset berita yang menyebut "pencairan dana"
            pencairan = [item for item in news_data
                         if re.search(r'pencairan\s+dana',
                                      item['title'] + ' ' + item['content'], re.I)]
            if pencairan:
                df.loc[df['slug'] == slug, 'disbursement_json']  = f"FILE:{fname}"
                df.loc[df['slug'] == slug, 'disbursement_count'] = len(pencairan)
            else:
                df.loc[df['slug'] == slug, 'disbursement_json']  = 'no disbursement'
                df.loc[df['slug'] == slug, 'disbursement_count'] = 0

            print(f"  ✓ News → FILE:{fname} ({len(news_data)} items, "
                  f"{len(pencairan)} pencairan)")

        processed += 1

        if processed % 3 == 0:
            tmp = os.path.join(parent_dir, 'data', 'processed',
                               f'rumahzakat_large_temp_{processed}.csv')
            df.to_csv(tmp, index=False, encoding='utf-8')
            elapsed = datetime.now() - start_time
            print(f"\n  💾 Auto-save: {tmp} | {processed}/{len(batch)} | {elapsed}\n")

        if processed % RESTART_EVERY == 0 and processed < len(batch):
            print(f"\n  🔄 Restart driver + cooling 20s...")
            try:
                driver.quit()
            except Exception:
                pass
            time.sleep(20)
            driver = init_driver()
            driver.get(ENTRY_URL)
            time.sleep(5)
            print(f"  ✓ Driver baru siap\n")

    driver.quit()

    ts  = datetime.now().strftime('%Y%m%d_%H%M%S')
    out = os.path.join(parent_dir, 'data', 'processed',
                       f'rumahzakat_large_done_{ts}.csv')
    df.to_csv(out, index=False, encoding='utf-8')

    print("\n" + "=" * 65)
    print("✅ SELESAI!")
    print("=" * 65)
    print(f"Output CSV : {out}")
    print(f"JSON files : {NEWS_JSON_DIR}")

    done_news = df['latest_news_json'].str.startswith('FILE:').sum() \
                if 'latest_news_json' in df.columns else 0
    print(f"\nNews → FILE: {done_news}")
    print("=" * 65)

if __name__ == '__main__':
    main()
