"""
Scrape detail kampanye zakat dari Bersedekah.com.
Input : data/raw/bersedekah_zakat_urls.csv  (atau custom path)
Output: data/processed/bersedekah_details_<start>_<end>_<ts>.csv

Kolom output sesuai skema Kitabisa + kolom lokasi khusus Bersedekah.

Author: Arifah Deswina (D121221030)
"""

import sys, os, time, random, re, json, html as htmllib
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

# ── Kolom output ──────────────────────────────────────────────────
COLUMNS = [
    'no','url','slug','platform','scraped_at','title','organizer',
    'collected_amount','target_amount','days_left','location',
    'profile_url','organizer_description',
    'ind1_has_profile','ind1_has_contact_direct','ind1_has_legal',
    'ind2_has_mission','ind2_word_count',
    'ind3_has_fund_report','donor_count',
    'ind4_has_updates','update_count',
    'ind5_has_disbursement','disbursement_count',
    'ind6_has_admin_fee','ind7_has_anonymity','ind8_has_transaction_id',
    'total_indicators_detected',
    'campaign_story','latest_news_json','disbursement_json',
    'contact_info',   # ekstra: kontak terstruktur dari footer
    'notes',          # ekstra: catatan jika updates terlalu banyak
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
    if not element:
        return ""
    for tag in element.find_all(['img','figure','figcaption','svg','video','picture']):
        tag.decompose()
    text = element.get_text(strip=True, separator=' ')
    return re.sub(r'\s{2,}', ' ', text).strip()

def safe_click(driver, element):
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", element)
    time.sleep(0.5)
    driver.execute_script("arguments[0].click();", element)

# ─────────────────────────────────────────────────────────────────
def _parse_kontak_block(block, info):
    """Isi info dict dari satu blok kontak (footer div.box-4 atau navbar)."""
    for div in block.find_all('div'):
        icon  = div.find('i')
        label = div.find('label') or div.find('span')
        if not icon or not label:
            continue
        cls = ' '.join(icon.get('class', []))
        txt = label.get_text(strip=True)
        if 'fa-mobile' in cls:
            if txt and txt not in info['phones']:
                info['phones'].append(txt)
        elif 'fa-phone' in cls:
            if txt and txt not in info['phones']:
                info['phones'].append(txt)
        elif 'fa-envelope' in cls:
            if txt and txt not in info['emails']:
                info['emails'].append(txt)
        elif 'fa-map-marker' in cls:   # matches fa-map-marker and fa-map-marker-alt
            if txt and not info['address']:
                info['address'] = txt

    # Social media: <i class="... link-sosmed" data-url="...">
    sosmed_div = block.find('div', class_='sosmed')
    if sosmed_div:
        for icon in sosmed_div.find_all('i', attrs={'data-url': True}):
            url = icon['data-url']
            if url and url.startswith('http') and url not in info['social']:
                info['social'].append(url)
        for a in sosmed_div.find_all('a', href=True):
            href = a['href']
            if href and href.startswith('http') and href not in info['social']:
                info['social'].append(href)


def extract_contact(soup):
    """
    Ekstrak info kontak dari footer desktop: div.box-4 (kolom 'Kontak').
    Fallback: navbar div.kontak-mobile (template lain).
    Return dict + has_contact bool.
    """
    info = {'phones': [], 'emails': [], 'address': '', 'social': []}

    # ── Sumber utama: footer div.box-4 ──────────────────────────────
    # <section class="footer row"> → <div class="box-4 col-lg-3">
    footer_sec = (soup.find('section', id='flex-footer') or
                  soup.find('section', class_=re.compile(r'\bfooter\b')))
    if footer_sec:
        box4 = footer_sec.find('div', class_=re.compile(r'\bbox-4\b'))
        if box4:
            _parse_kontak_block(box4, info)

    # ── Fallback: navbar kontak-mobile (template mobile) ────────────
    if not (info['phones'] or info['emails']):
        kontak_mobile = soup.find('div', class_=lambda c: c and 'kontak-mobile' in c)
        if kontak_mobile:
            _parse_kontak_block(kontak_mobile, info)

    has_contact = bool(info['phones'] or info['emails'] or info['social'])
    return info, has_contact

def extract_organizer(soup):
    """Nama, deskripsi, profile URL, dan legalitas dari footer + navbar."""
    org_name    = ''
    org_desc    = ''
    profile_url = ''

    # ── Nama & deskripsi: label.nama-lembaga / label.deskripsi-lembaga ──
    # Ada di div.box-1 dalam section.footer.row (id="flex-footer")
    nama_lbl = soup.find('label', class_='nama-lembaga')
    desc_lbl = soup.find('label', class_='deskripsi-lembaga')
    org_name = nama_lbl.get_text(strip=True) if nama_lbl else ''
    org_desc = desc_lbl.get_text(strip=True) if desc_lbl else ''

    # ── Fallback nama: <h1 class="heading-one"> format "OrgName - Title" ──
    # Contoh: "Badan Amil Zakat Nasional - Zakat Maal"
    if not org_name:
        h1 = soup.find('h1', class_='heading-one')
        if h1:
            txt = h1.get_text(strip=True)
            parts = txt.split(' - ', 1)
            if len(parts) == 2:
                org_name = parts[0].strip()

    # ── Fallback nama: <title> format "Title - OrgName" ─────────────────
    if not org_name:
        title_tag = soup.find('title')
        if title_tag:
            txt = title_tag.get_text(strip=True)
            parts = txt.split(' - ', 1)
            if len(parts) == 2:
                org_name = parts[1].strip()

    # ── Profile URL dari navbar: <a> yang wrap <img class="logo_lembaga"> ─
    nav = soup.find('nav', class_=re.compile(r'navbar'))
    if nav:
        logo_img = nav.find('img', class_='logo_lembaga')
        if logo_img:
            parent_a = logo_img.find_parent('a')
            if parent_a and parent_a.get('href'):
                profile_url = parent_a['href']
                if not profile_url.startswith('http'):
                    profile_url = 'https://www.bersedekah.com' + profile_url

    # ── Cek legalitas dari deskripsi ─────────────────────────────────────
    legal_keywords = ['sk ', 'sk\n', 'nomor', 'akta', 'resmi', 'izin',
                      'terdaftar', 'kementerian', 'menag', 'kemenkum',
                      'no.', 'tahun 20']
    desc_lower = org_desc.lower()
    has_legal = any(kw in desc_lower for kw in legal_keywords)

    return org_name, org_desc, profile_url, has_legal

# ─────────────────────────────────────────────────────────────────
def scrape_news(driver, soup):
    """
    Klik tab Info Terbaru → Lihat Selengkapnya → Tampilkan Lainnya.
    Setiap klik Tampilkan Lainnya memunculkan 10 item (Kegiatan ke-10..1).
    Jika tombol masih ada setelah MAX_CLICKS kali → handle terpisah.
    Return list of dict + actual count loaded.
    """
    MAX_CLICKS = 3   # >30 item (tiap klik ~10 item) → simpan ke file terpisah

    # Klik tab Info Terbaru
    try:
        tab = driver.find_element(By.ID, 'tabInfoTerbaru')
        safe_click(driver, tab)
        time.sleep(2)
    except Exception:
        return [], 0, False

    # Klik "Lihat Selengkapnya" untuk unhide div.div-one
    try:
        read_more = driver.find_element(
            By.CSS_SELECTOR, 'a.btn-read-more.read-more-mobile')
        safe_click(driver, read_more)
        time.sleep(2)
    except Exception:
        pass

    # Klik "Tampilkan Lainnya" sampai habis atau MAX_CLICKS
    click_count  = 0
    too_long     = False

    while True:
        try:
            tampil = driver.find_element(By.ID, 'tampilkanLainnya')
            if not tampil.is_displayed():
                break
            if click_count >= MAX_CLICKS:
                # Tombol masih ada setelah MAX_CLICKS klik → handle terpisah
                too_long = True
                break
            safe_click(driver, tampil)
            time.sleep(2)
            click_count += 1
        except Exception:
            break   # Tombol tidak ditemukan → semua sudah termuat

    soup3   = BeautifulSoup(driver.page_source, 'html.parser')
    div_one = soup3.find('div', class_='div-one')
    if not div_one:
        return [], 0, False

    steps = div_one.find_all('div', class_=lambda c: c and 'step' in c and 'active' in c)
    items = []
    for step in steps:
        title_span = step.find('span', class_='text-judul')
        date_label = step.find('label', class_='title-date')
        number_lbl = step.find('label', class_='text-o')
        location_s = step.find('label', class_='text-lokasi')

        title  = title_span.get_text(strip=True)  if title_span else ''
        date   = date_label.get_text(strip=True)   if date_label else ''
        number = number_lbl.get_text(strip=True)   if number_lbl else ''
        loc    = location_s.find('span').get_text(strip=True) if location_s and location_s.find('span') else ''

        # Konten: JS render ke p#kegiatan-{id}
        hidden = step.find('input', type='hidden', id=re.compile(r'^kegiatanID-'))
        content = ''
        if hidden:
            kid = hidden['id'].replace('kegiatanID-', '')
            p_el = step.find('p', id=f'kegiatan-{kid}')
            if p_el:
                content = clean_text(p_el)
            # Fallback: ambil teks setelah hidden input (BeautifulSoup sibling teks)
            if not content:
                lap_div = step.find('div', class_='detail-value-laporan')
                if lap_div:
                    # Kumpulkan teks dari semua tag p, strong, dll. (skip input)
                    for tag in lap_div.find_all(['img','figure','figcaption','svg','video']):
                        tag.decompose()
                    all_text = lap_div.get_text(separator=' ', strip=True)
                    content = re.sub(r'\s{2,}', ' ', all_text).strip()

        if title or content:
            items.append({
                'number'  : number,
                'title'   : title,
                'date'    : date,
                'location': loc,
                'content' : content,
            })

    loaded = len(items)
    if too_long:
        print(f"      ⚠️ >30 updates: sudah {loaded} item dimuat, akan disimpan ke file JSON")

    return items, loaded, too_long

# ─────────────────────────────────────────────────────────────────
def scrape_campaign(driver, url, slug, campaign_no, title_from_csv=""):
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

        # Klik "Selengkapnya" di deskripsi program (expand cerita)
        try:
            sel_lbl = driver.find_element(By.ID, 'selengkapnyaDeskripsi')
            safe_click(driver, sel_lbl)
            time.sleep(1)
        except Exception:
            pass

        # Scroll ke bawah lagi agar footer lazy-load terpicu, lalu kembali ke atas
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(3)
        driver.execute_script("window.scrollTo(0, 0);")
        time.sleep(1)

        soup = BeautifulSoup(driver.page_source, 'html.parser')

        data = {
            'no'        : campaign_no,
            'url'       : url,
            'slug'      : slug,
            'platform'  : 'bersedekah',
            'scraped_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        }

        # ── Judul ────────────────────────────────────────────────
        title_tag = (soup.find('h1') or
                     soup.find('div', class_=re.compile(r'title-program|judul-program')) or
                     soup.find('h2'))
        data['title'] = title_tag.get_text(strip=True) if title_tag else title_from_csv

        # ── Dana terkumpul & target ───────────────────────────────
        # Collected: div#box-program-nominal-1 label.program-donasi
        box1 = soup.find('div', id='box-program-nominal-1')
        collected_lbl = box1.find('label', class_='program-donasi') if box1 else None
        data['collected_amount'] = (collected_lbl.get_text(strip=True)
                                    if collected_lbl else '')

        # Target: div#box-value-yatim label (Tanpa Target atau nilai)
        box2 = soup.find('div', id='box-value-yatim')
        target_lbl = box2.find('label') if box2 else None
        data['target_amount'] = (target_lbl.get_text(strip=True)
                                 if target_lbl else '')

        # Sisa hari / tanggal berakhir: div#subBlockA label.value
        sub_a = soup.find('div', id='subBlockA')
        days_lbl = sub_a.find('label', class_='value') if sub_a else None
        data['days_left'] = (days_lbl.get_text(strip=True)
                             if days_lbl else '')

        # ── Lokasi (unik di Bersedekah) ───────────────────────────
        box_daerah = soup.find('div', class_='box-daerah')
        daerah = box_daerah.find('span', class_='daerah') if box_daerah else None
        data['location'] = daerah.get_text(strip=True) if daerah else ''

        # ── Organizer, deskripsi, profil, legalitas ───────────────
        org_name, org_desc, profile_url, has_legal = extract_organizer(soup)
        data['organizer']             = org_name
        data['organizer_description'] = org_desc
        data['profile_url']           = profile_url
        data['ind1_has_profile']      = bool(profile_url)
        data['ind1_has_legal']        = has_legal

        # ── Kontak ────────────────────────────────────────────────
        contact_info, has_contact = extract_contact(soup)
        data['ind1_has_contact_direct'] = has_contact
        data['contact_info']            = json.dumps(contact_info, ensure_ascii=False)

        # ── Campaign story (tab Detail aktif) ─────────────────────
        box_detail = soup.find('div', id='boxDetail')
        if box_detail:
            desc_div = box_detail.find('div', class_='box-deskripsi')
            if desc_div:
                # Hapus shadow overlay
                shadow = desc_div.find('div', id='box-shadow-deskripsi')
                if shadow:
                    shadow.decompose()
                data['campaign_story'] = clean_text(desc_div)
            else:
                data['campaign_story'] = clean_text(box_detail)
        else:
            data['campaign_story'] = ''

        words = data['campaign_story'].split()
        data['ind2_has_mission'] = len(words) > 50
        data['ind2_word_count']  = len(words)

        # ── Donor count (dari counter tab Muzaki) ─────────────────
        donor_count = 0
        tab_donatur = soup.find('a', id='tabDonatur')
        if tab_donatur:
            counter = tab_donatur.find('label', class_='counter')
            if counter:
                txt = counter.get_text(strip=True).replace('.', '').replace(',', '')
                donor_count = int(txt) if txt.isdigit() else 0
        data['donor_count']          = str(donor_count)
        data['ind3_has_fund_report'] = donor_count > 0

        # ── Info Terbaru (news) ───────────────────────────────────
        news_items, update_count, too_long = scrape_news(driver, soup)

        data['ind4_has_updates'] = update_count > 0
        data['update_count']     = str(update_count)

        if too_long and news_items:
            # Simpan ke file JSON terpisah, isi kolom dengan "FILE:path"
            import config as _cfg
            news_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                    'data', 'processed', 'bersedekah_news_json')
            os.makedirs(news_dir, exist_ok=True)
            json_filename = f"bersedekah_{data['slug']}.json"
            json_path = os.path.join(news_dir, json_filename)
            with open(json_path, 'w', encoding='utf-8') as jf:
                json.dump(news_items, jf, ensure_ascii=False, indent=2)
            rel_path = f"data/processed/bersedekah_news_json/{json_filename}"
            data['latest_news_json'] = f"FILE:{rel_path}"
            data['notes'] = f"latest_news: >30 updates, disimpan ke {rel_path}"
            print(f"      💾 News disimpan ke: {rel_path}")
        elif news_items:
            data['latest_news_json'] = json.dumps(news_items, ensure_ascii=False)
            data['notes'] = ''
        else:
            data['latest_news_json'] = 'no updates'
            data['notes'] = ''

        # ── Pencairan Dana — dari konten berita ───────────────────
        DISB_RE = re.compile(
            r'pencairan\s+dana|penyaluran\s+dana|'
            r'pencairan\s+dana\s+sebesar|'
            r'sebesar\s+Rp[\s\d.,]+|'
            r'Rp[\s\d.,]+\s*(telah\s+)?(disalurkan|diberikan|dibagikan|tersalurkan)',
            re.I
        )
        pencairan = []
        if isinstance(news_items, list):
            pencairan = [
                item for item in news_items
                if 'note' not in item and
                   DISB_RE.search(item.get('title','') + ' ' + item.get('content',''))
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
    print("  BERSEDEKAH.COM — Scrape Detail Kampanye")
    print("=" * 65)

    default_file = os.path.join(parent_dir, 'data', 'raw', 'bersedekah_zakat_urls.csv')
    print(f"\nFile URL default: {default_file}")
    custom = input("Pakai file lain? (Enter = default, atau ketik path): ").strip()
    url_file = custom if custom else default_file
    df_urls = pd.read_csv(url_file)
    print(f"✓ Total URLs: {len(df_urls)}\n")

    print(f"  Tersedia: 1 – {len(df_urls)}")
    start = int(input("Mulai dari kampanye no. (1-based): ").strip())
    count = int(input("Scrape berapa kampanye?: ").strip())
    batch = df_urls.iloc[start-1 : start-1+count]
    print(f"\n✓ Akan scrape {len(batch)} kampanye (no. {start} s/d {start-1+len(batch)})\n")

    driver     = init_driver()
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
            print(f"    Organizer : {data['organizer'][:40]}")
            print(f"    Lokasi    : {data.get('location','')}")
            print(f"    Terkumpul : {data['collected_amount']} / {data['target_amount']}")
            print(f"    Indicators: {total}/9  |  Kontak: {data['ind1_has_contact_direct']}")
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

        # Auto-save tiap 10
        if (i + 1) % 10 == 0 and results:
            tmp_df = pd.DataFrame(results)
            for col in COLUMNS:
                if col not in tmp_df.columns:
                    tmp_df[col] = None
            tmp_path = os.path.join(parent_dir, 'data', 'processed',
                                    f'bersedekah_temp_{i+1}.csv')
            tmp_df[[c for c in COLUMNS if c in tmp_df.columns]].to_csv(
                tmp_path, index=False, encoding='utf-8')
            elapsed = datetime.now() - start_time
            print(f"  💾 Auto-save: {tmp_path}")
            print(f"     {len(results)}/{len(batch)} | Elapsed: {elapsed}\n")

    driver.quit()

    if results:
        df = pd.DataFrame(results)
        for col in COLUMNS:
            if col not in df.columns:
                df[col] = None
        df = df[[c for c in COLUMNS if c in df.columns]]

        ts  = datetime.now().strftime('%Y%m%d_%H%M%S')
        out = os.path.join(parent_dir, 'data', 'processed',
                           f'bersedekah_details_{start}_{start-1+len(results)}_{ts}.csv')
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
