"""
Scrape detail kampanye zakat dari Rumah Zakat.
Input : data/raw/linkRumahZakat.csv  (atau custom path)
Output: data/processed/rumahzakat_details_<start>_<end>_<ts>.csv

Kolom output sesuai skema Kitabisa untuk konsistensi analisis.

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

# ── Kolom output (urutan sama dengan Kitabisa) ────────────────────
COLUMNS = [
    'no','url','slug','platform','scraped_at','title','organizer',
    'collected_amount','target_amount','days_left',
    'profile_url','organizer_description',
    'ind1_has_profile','ind1_has_contact_direct','ind1_has_legal',
    'ind2_has_mission','ind2_word_count',
    'ind3_has_fund_report','donor_count',
    'ind4_has_updates','update_count',
    'ind5_has_disbursement','disbursement_count',
    'ind6_has_admin_fee','ind7_has_anonymity','ind8_has_transaction_id',
    'total_indicators_detected',
    'campaign_story','latest_news_json','disbursement_json',
]

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
    """Hapus gambar/svg lalu ambil teks bersih."""
    if not element:
        return ""
    for tag in element.find_all(['img','figure','figcaption','svg','video','picture']):
        tag.decompose()
    text = element.get_text(strip=True, separator=' ')
    return re.sub(r'\s{2,}', ' ', text).strip()

def scroll_until_stable(driver, max_no_change=3, wait=2.5):
    """Scroll ke bawah sampai tidak ada konten baru."""
    prev_h = 0
    no_change = 0
    while True:
        curr_h = driver.execute_script(
            "window.scrollTo(0, document.body.scrollHeight); return document.body.scrollHeight;")
        time.sleep(wait)
        if curr_h == prev_h:
            no_change += 1
            if no_change >= max_no_change:
                break
        else:
            prev_h = curr_h
            no_change = 0

# ─────────────────────────────────────────────────────────────────
def scrape_news_page(driver, news_url):
    """
    Scrape halaman info-penyaluran (scroll infinite).
    Return list of dict: {date, title, content}
    """
    try:
        driver.get(news_url)
        time.sleep(5)
        scroll_until_stable(driver, max_no_change=3, wait=2.5)

        soup = BeautifulSoup(driver.page_source, 'html.parser')

        # Setiap item: div.order-1.bg-gray-50.rounded-lg.shadow
        items = []
        for div in soup.find_all('div', class_=lambda c: c and
                                  'order-1' in c and 'bg-gray-50' in c and
                                  'rounded-lg' in c and 'shadow' in c):
            date_p    = div.find('p', class_=lambda c: c and 'text-gray-400' in c)
            title_h3  = div.find('h3', class_=lambda c: c and 'text-gray-800' in c)
            # Ambil <p> yang bukan tanggal untuk konten
            content_p = div.find('p', class_=lambda c: c and 'tracking-wide' in c)

            date    = date_p.get_text(strip=True)   if date_p    else ''
            title   = title_h3.get_text(strip=True) if title_h3  else ''
            content = clean_text(content_p)         if content_p else ''

            if title or content:
                items.append({'date': date, 'title': title, 'content': content})

        return items

    except Exception as e:
        print(f"      ⚠️ News page error: {str(e)[:80]}")
        return []

# ─────────────────────────────────────────────────────────────────
def find_news_url(driver, soup):
    """
    Cari URL halaman info-penyaluran dari halaman kampanye.
    1. Cari a[href*='/care/info-penyaluran/'] langsung di soup
    2. Klik tombol 'Lihat Selengkapnya' di sekitar 'Info Terbaru' lalu cek URL
    """
    # Cek link langsung
    a = soup.find('a', href=re.compile(r'/care/info-penyaluran/'))
    if a:
        href = a['href']
        return href if href.startswith('http') else BASE_URL + href

    # Temukan semua tombol "Lihat Selengkapnya"
    try:
        buttons = driver.find_elements(
            By.XPATH,
            "//button[.//div[contains(normalize-space(text()),'Lihat Selengkapnya')]]"
        )
        for btn in buttons:
            # Cari h3 "Info Terbaru" terdekat di atas tombol ini (dalam parent yang sama)
            try:
                # Naik ke container luar, lalu cek apakah ada teks "Info Terbaru" di dalamnya
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
                    # Navigasi tidak berhasil — kembali
                    driver.back()
                    time.sleep(3)
                    break
            except Exception:
                continue
    except Exception:
        pass

    return None

# ─────────────────────────────────────────────────────────────────
def scrape_campaign(driver, url, slug, campaign_no, title_from_csv=""):
    """Scrape satu halaman kampanye Rumah Zakat."""
    try:
        delay = random.uniform(6, 11)
        print(f"  ⏳ Delay {delay:.1f}s...")
        time.sleep(delay)

        driver.get(url)
        time.sleep(6)

        # Scroll untuk trigger lazy-load
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2)
        driver.execute_script("window.scrollTo(0, 0);")
        time.sleep(1)

        # Klik "Baca Selengkapnya" untuk expand cerita
        try:
            btn = driver.find_element(
                By.XPATH,
                "//button[.//div[contains(normalize-space(text()),'Baca Selengkapnya')]]"
            )
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
            time.sleep(0.5)
            driver.execute_script("arguments[0].click();", btn)
            time.sleep(2)
        except Exception:
            pass

        soup = BeautifulSoup(driver.page_source, 'html.parser')

        data = {
            'no'        : campaign_no,
            'url'       : url,
            'slug'      : slug,
            'platform'  : 'rumahzakat',
            'scraped_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        }

        # ── Judul ────────────────────────────────────────────────
        title_tag = (soup.find('h1') or
                     soup.find('h2', class_=re.compile(r'text-xl|text-2xl|font-bold', re.I)))
        data['title'] = title_tag.get_text(strip=True) if title_tag else title_from_csv

        # ── Organizer — selalu Rumah Zakat ────────────────────────
        data['organizer']             = 'Rumah Zakat'
        data['profile_url']           = 'https://www.rumahzakat.org'
        data['organizer_description'] = ''
        data['ind1_has_profile']      = True
        data['ind1_has_contact_direct'] = False
        data['ind1_has_legal']        = True   # lembaga zakat resmi bersertifikat

        # ── Dana terkumpul & donatur ──────────────────────────────
        # <strong class="text-base text-primary font-medium">Rp310.732.403</strong>
        # terkumpul dari <strong class="font-semibold text-sm">217</strong> donatur
        collected_tag = soup.find('strong', class_=lambda c: c and 'text-primary' in c)
        data['collected_amount'] = (collected_tag.get_text(strip=True)
                                    if collected_tag else '')

        donor_strong = soup.find('strong', class_=lambda c: c and 'font-semibold' in c
                                  and 'text-sm' in (c if isinstance(c, list) else c.split()))
        if not donor_strong and collected_tag:
            # Coba ambil strong berikutnya dalam <p> yang sama
            p_tag = collected_tag.find_parent('p')
            if p_tag:
                strongs = p_tag.find_all('strong')
                if len(strongs) >= 2:
                    donor_strong = strongs[1]
        donor_txt = donor_strong.get_text(strip=True) if donor_strong else '0'
        # Bersihkan titik ribuan: "1.234" → "1234"
        data['donor_count'] = re.sub(r'[^\d]', '', donor_txt) or '0'

        # ── Target & sisa hari ────────────────────────────────────
        page_text = soup.get_text(' ', strip=True)
        target_m = re.search(
            r'[Tt]arget\s*[:\-]?\s*(Rp[\s\d.,]+|\d[\d.,]+)', page_text)
        days_m = re.search(r'(\d+)\s*hari\s*(lagi|tersisa)', page_text, re.I)
        data['target_amount'] = target_m.group(1).strip() if target_m else ''
        data['days_left']     = (days_m.group(1) + ' hari') if days_m else ''

        # ── Campaign story ────────────────────────────────────────
        # Cari div cerita: elemen dengan paragraf panjang di bawah judul
        story_text = ''
        # Biasanya ada div dengan class text-justify atau prose
        for div in soup.find_all('div', class_=lambda c: c and
                                  ('text-justify' in c or 'prose' in c)):
            txt = clean_text(div)
            if len(txt) > 100:
                story_text = txt
                break
        # Fallback: paragraf pertama yang cukup panjang
        if not story_text:
            for p in soup.find_all('p'):
                txt = p.get_text(strip=True)
                if len(txt) > 150:
                    story_text = txt
                    break
        data['campaign_story'] = story_text

        words = story_text.split()
        data['ind2_has_mission'] = len(words) > 50
        data['ind2_word_count']  = len(words)

        # ── Fund report (ada daftar donatur?) ────────────────────
        donor_count_int = int(data['donor_count']) if data['donor_count'].isdigit() else 0
        data['ind3_has_fund_report'] = donor_count_int > 0

        # ── Info Terbaru (news) ───────────────────────────────────
        # Cek apakah section "Info Terbaru" ada di halaman
        info_section = soup.find(lambda tag: tag.name in ('h3','h2','h4') and
                                  'Info Terbaru' in tag.get_text())
        news_items = []

        if info_section:
            news_url = find_news_url(driver, soup)
            if news_url:
                print(f"    📰 News page: {news_url}")
                news_items = scrape_news_page(driver, news_url)
                print(f"      ✓ {len(news_items)} berita")
                # Tidak perlu kembali ke campaign page — data sudah terkumpul
            else:
                # Ambil konten langsung dari section di halaman kampanye
                parent_div = info_section.find_parent('div')
                if parent_div:
                    # Ambil teks singkat yang sudah tampil
                    preview = clean_text(parent_div)
                    if preview and len(preview) > 20:
                        news_items = [{'date': '', 'title': '', 'content': preview}]

        data['ind4_has_updates'] = len(news_items) > 0
        data['update_count']     = str(len(news_items))
        data['latest_news_json'] = (json.dumps(news_items, ensure_ascii=False)
                                    if news_items else 'no updates')

        # ── Pencairan Dana — dari konten berita ───────────────────
        pencairan = [
            item for item in news_items
            if re.search(r'pencairan\s+dana', item['title'] + ' ' + item['content'], re.I)
        ]
        data['ind5_has_disbursement'] = len(pencairan) > 0
        data['disbursement_count']    = str(len(pencairan))
        data['disbursement_json']     = (json.dumps(pencairan, ensure_ascii=False)
                                         if pencairan else 'no disbursement')

        # ── Indikator tetap ───────────────────────────────────────
        data['ind6_has_admin_fee']      = False
        data['ind7_has_anonymity']      = True
        data['ind8_has_transaction_id'] = False

        # ── Total ─────────────────────────────────────────────────
        data['total_indicators_detected'] = sum([
            data['ind1_has_profile'],
            data['ind1_has_legal'],
            data['ind2_has_mission'],
            data['ind3_has_fund_report'],
            data['ind4_has_updates'],
            data['ind5_has_disbursement'],
            data['ind6_has_admin_fee'],
            data['ind7_has_anonymity'],
            data['ind8_has_transaction_id'],
        ])

        return data

    except Exception as e:
        print(f"  ✗ Error: {str(e)[:100]}")
        return None

# ─────────────────────────────────────────────────────────────────
def main():
    print("=" * 65)
    print("  RUMAH ZAKAT — Scrape Detail Kampanye")
    print("=" * 65)

    # ── Pilih file URL ────────────────────────────────────────────
    default_file = os.path.join(parent_dir, 'data', 'raw', 'linkRumahZakat.csv')
    print(f"\nFile URL default: {default_file}")
    custom = input("Pakai file lain? (Enter = default, atau ketik path): ").strip()
    url_file = custom if custom else default_file
    df_urls = pd.read_csv(url_file)
    print(f"✓ Total URLs: {len(df_urls)}\n")

    # ── Pilih range ───────────────────────────────────────────────
    print(f"  Tersedia: 1 – {len(df_urls)}")
    start = int(input("Mulai dari kampanye no. (1-based): ").strip())
    count = int(input("Scrape berapa kampanye?: ").strip())
    batch = df_urls.iloc[start-1 : start-1+count]
    print(f"\n✓ Akan scrape {len(batch)} kampanye (no. {start} s/d {start-1+len(batch)})\n")

    driver = init_driver()

    # ── Buka /donasi dulu agar SvelteKit session valid ─────────────
    print(f"[Init] Membuka entry page: {ENTRY_URL}")
    driver.get(ENTRY_URL)
    time.sleep(5)

    results    = []
    failed_nos = []
    start_time = datetime.now()

    for i, (_, row) in enumerate(batch.iterrows()):
        campaign_no = start + i
        slug        = str(row.get('slug', row['url'].rstrip('/').split('/')[-1]))
        title_csv   = str(row.get('title', ''))
        print(f"[{i+1}/{len(batch)}] No.{campaign_no} | {slug[:50]}")

        data = scrape_campaign(driver, row['url'], slug, campaign_no, title_csv)

        if data:
            results.append(data)
            total = data['total_indicators_detected']
            print(f"  ✓ {data['title'][:50]}")
            print(f"    Terkumpul : {data['collected_amount']} | Donatur: {data['donor_count']}")
            print(f"    Indicators: {total}/9")
            detail = []
            if data['ind4_has_updates']:
                detail.append(f"News:{data['update_count']}")
            if data['ind5_has_disbursement']:
                detail.append(f"Pencairan:{data['disbursement_count']}")
            if detail:
                print(f"    Detail    : {' | '.join(detail)}")
            print()
        else:
            failed_nos.append(campaign_no)
            print(f"  ✗ Gagal (no.{campaign_no})\n")

        # Auto-save tiap 10 kampanye
        if (i + 1) % 10 == 0 and results:
            tmp_df = pd.DataFrame(results)
            for col in COLUMNS:
                if col not in tmp_df.columns:
                    tmp_df[col] = None
            tmp_path = os.path.join(parent_dir, 'data', 'processed',
                                    f'rumahzakat_temp_{i+1}.csv')
            tmp_df[[c for c in COLUMNS if c in tmp_df.columns]].to_csv(
                tmp_path, index=False, encoding='utf-8')
            elapsed = datetime.now() - start_time
            print(f"  💾 Auto-save: {tmp_path}")
            print(f"     {len(results)}/{len(batch)} | Elapsed: {elapsed}\n")

    driver.quit()

    # ── Simpan final ──────────────────────────────────────────────
    if results:
        df = pd.DataFrame(results)
        for col in COLUMNS:
            if col not in df.columns:
                df[col] = None
        df = df[[c for c in COLUMNS if c in df.columns]]

        ts  = datetime.now().strftime('%Y%m%d_%H%M%S')
        out = os.path.join(parent_dir, 'data', 'processed',
                           f'rumahzakat_details_{start}_{start-1+len(results)}_{ts}.csv')
        df.to_csv(out, index=False, encoding='utf-8')

        print("\n" + "=" * 65)
        print("✅ SELESAI!")
        print("=" * 65)
        print(f"Berhasil : {len(results)}/{len(batch)}")
        print(f"Output   : {out}")

        if failed_nos:
            print(f"\n⚠️  Gagal ({len(failed_nos)}): no. {failed_nos}")

        print("\n📊 INDICATOR COVERAGE:")
        for col in COLUMNS:
            if col.startswith('ind') and col in df.columns:
                n = df[col].astype(str).isin(['True','true','1']).sum()
                print(f"  {col:<35}: {n}/{len(df)}")
        print("=" * 65)
    else:
        print("\n⚠️ Tidak ada hasil — semua gagal.")

if __name__ == '__main__':
    main()
