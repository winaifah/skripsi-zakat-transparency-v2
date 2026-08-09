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

BASE_URL = "https://digital.dompetdhuafa.org"

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
    if not element:
        return ""
    for tag in element.find_all(['img','figure','figcaption','svg','video','picture']):
        tag.decompose()
    text = element.get_text(strip=True, separator=' ')
    return re.sub(r'\s{2,}', ' ', text).strip()

def get_tab(soup, header_text):

    for tab in soup.find_all('div', class_='tab-content'):
        nav = tab.find('div', class_='res-tab-nav')
        if nav and header_text.lower() in nav.get_text(strip=True).lower():
            return tab
    return None

def get_tab_counter(tab):

    if not tab:
        return 0
    nav = tab.find('div', class_='res-tab-nav')
    if not nav:
        return 0
    counter = nav.find('span', class_='counter')
    if counter:
        txt = counter.get_text(strip=True)
        return int(txt) if txt.isdigit() else 0
    return 0

# ─────────────────────────────────────────────────────────────────
def scrape_organizer_profile(driver, profile_url):

    try:
        driver.get(profile_url)
        time.sleep(5)
        # Scroll untuk trigger lazy-load Vue.js
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2)
        driver.execute_script("window.scrollTo(0, 0);")
        time.sleep(1)
        soup = BeautifulSoup(driver.page_source, 'html.parser')

        tentang_tab = get_tab(soup, 'Tentang Mitra')
        if tentang_tab:
            content = (tentang_tab.find('div', class_='bzg_c') or
                       tentang_tab.find('div', class_='bzg') or
                       tentang_tab)
            return clean_text(content)


        for p in soup.find_all('p'):
            txt = p.get_text(strip=True)
            if len(txt) > 50:
                return txt
    except Exception as e:
        print(f"      ⚠️ Profile error: {str(e)[:60]}")
    return ""

def scrape_campaign(driver, url, slug, campaign_no, title_from_csv=""):
    """Scrape satu halaman kampanye Dompet Dhuafa."""
    try:
        delay = random.uniform(6, 12)
        print(f"  ⏳ Delay {delay:.1f}s...")
        time.sleep(delay)

        driver.get(url)
        time.sleep(6)

        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2)
        driver.execute_script("window.scrollTo(0, 0);")
        time.sleep(1)

        try:
            btn = driver.find_element(
                By.XPATH, "//button[contains(normalize-space(text()), 'SELENGKAPNYA')]")
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
            'platform'  : 'dompetdhuafa',
            'scraped_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        }

        # ── Judul ────────────────────────────────────────────────
        title_tag = (soup.find('h1') or
                     soup.find('h2', class_=re.compile(r'title|campaign', re.I)))
        data['title'] = title_tag.get_text(strip=True) if title_tag else title_from_csv

        # ── Organizer ─────────────────────────────────────────────
        creator = soup.find('a', class_='creator')
        if creator:
            name_span = creator.find('span', class_='creator__name')
            data['organizer'] = name_span.get_text(strip=True) if name_span else ''
            verified = creator.find('span', class_='creator__verified')
            data['ind1_has_legal'] = verified is not None
            href = creator.get('href', '')
            # Mitra eksternal punya halaman /mitra-kami/...
            if href and href.startswith('/mitra-kami/'):
                data['profile_url'] = BASE_URL + href
                # ind1_has_profile True karena ada halaman mitra terpisah
                data['ind1_has_profile'] = True
            else:
                # Dompet Dhuafa sendiri (/donasi) — tidak ada halaman profil terpisah
                data['profile_url'] = ''
                data['ind1_has_profile'] = bool(data['organizer'])
        else:
            data['organizer']        = ''
            data['ind1_has_legal']   = False
            data['profile_url']      = ''
            data['ind1_has_profile'] = False

        data['ind1_has_contact_direct'] = False  # selalu False

        # ── Dana terkumpul & donatur ──────────────────────────────
        collected = soup.find('strong', class_='text-green')
        data['collected_amount'] = collected.get_text(strip=True) if collected else ''

        donor_small = soup.find('small', string=re.compile(r'Donatur', re.I))
        if donor_small:
            m = re.search(r'\d[\d.]*', donor_small.get_text())
            data['donor_count'] = m.group().replace('.', '') if m else '0'
        else:
            data['donor_count'] = '0'

        # ── Target & sisa hari ────────────────────────────────────
        page_text = soup.get_text()
        target_match = re.search(r'Target\s*([\d.,]+|∞)', page_text)
        days_match   = re.search(r'([\d]+|∞)\s*hari lagi', page_text)
        data['target_amount'] = target_match.group(1) if target_match else ''
        data['days_left']     = (days_match.group(1) + ' hari') if days_match else ''

        # ── Campaign story (tab Detail) ───────────────────────────
        detail_tab = get_tab(soup, 'Detail')
        if detail_tab:
            story_div = detail_tab.find('div', class_='text-justify')
            data['campaign_story'] = clean_text(story_div)
        else:
            data['campaign_story'] = ''

        words = data['campaign_story'].split()
        data['ind2_has_mission'] = len(words) > 50
        data['ind2_word_count']  = len(words)

        # ── Fund report (tab Donatur) ─────────────────────────────
        donatur_tab = get_tab(soup, 'Donatur')
        donor_tab_cnt = get_tab_counter(donatur_tab) if donatur_tab else 0
        data['ind3_has_fund_report'] = donor_tab_cnt > 0
        if donor_tab_cnt > 0:
            data['donor_count'] = str(donor_tab_cnt)

        # ── Kabar Terbaru (tab) ───────────────────────────────────
        news_tab    = get_tab(soup, 'Kabar Terbaru')
        update_count = get_tab_counter(news_tab)
        news_items   = []

        if news_tab and update_count > 0:
            for item in news_tab.find_all('div', class_='latest-news__item'):
                time_el  = item.find('time')
                h5_el    = item.find('h5')
                body_div = item.find('div', class_='text-justify')

                date_txt    = time_el.get_text(strip=True) if time_el else ''
                title_txt   = h5_el.get_text(strip=True) if h5_el else ''
                content_txt = clean_text(body_div)

                if title_txt or content_txt:
                    news_items.append({
                        'date'   : date_txt,
                        'title'  : title_txt,
                        'content': content_txt,
                    })

        data['ind4_has_updates'] = update_count > 0
        data['update_count']     = str(update_count)
        data['latest_news_json'] = (json.dumps(news_items, ensure_ascii=False)
                                    if news_items else 'no updates')

        # ── Pencairan Dana (dari konten Kabar Terbaru) ────────────
        pencairan = [
            item for item in news_items
            if re.search(r'pencairan\s+dana', item['title'] + ' ' + item['content'], re.I)
        ]
        data['ind5_has_disbursement'] = len(pencairan) > 0
        data['disbursement_count']    = str(len(pencairan))
        data['disbursement_json']     = (json.dumps(pencairan, ensure_ascii=False)
                                         if pencairan else 'no disbursement')

        # ── Indikator tetap ───────────────────────────────────────
        data['ind6_has_admin_fee']      = False   # tidak ada laporan keuangan
        data['ind7_has_anonymity']      = True
        data['ind8_has_transaction_id'] = False

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

        # ── Organizer profile (mitra eksternal) ──────────────────
        if data['profile_url']:
            print(f"    📄 Scraping mitra profile...")
            data['organizer_description'] = scrape_organizer_profile(
                driver, data['profile_url'])
            print(f"      ✓ {len(data['organizer_description'])} chars")
            # Kembali ke halaman kampanye tidak diperlukan (scrape_organizer sudah selesai)
        else:
            data['organizer_description'] = ''

        return data

    except Exception as e:
        print(f"  ✗ Error: {str(e)[:100]}")
        return None


def main():
    print("=" * 65)
    print("  DOMPET DHUAFA — Scrape Detail Kampanye")
    print("=" * 65)

    # ── Pilih file URL ────────────────────────────────────────────
    default_file = os.path.join(parent_dir, 'data', 'raw', 'linkDompet.csv')
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
    results = []
    failed_nos = []
    start_time = datetime.now()

    for i, (_, row) in enumerate(batch.iterrows()):
        campaign_no = start + i
        slug = str(row.get('slug', row['url'].split('/')[-1]))
        title_csv = str(row.get('title', ''))
        print(f"[{i+1}/{len(batch)}] No.{campaign_no} | {slug[:50]}")

        data = scrape_campaign(driver, row['url'], slug, campaign_no, title_csv)

        if data:
            results.append(data)
            total = data['total_indicators_detected']
            print(f"  ✓ {data['title'][:50]}")
            print(f"    Organizer : {data['organizer'][:40]}")
            print(f"    Indicators: {total}/9")
            detail = []
            if data['ind4_has_updates']:
                detail.append(f"Updates:{data['update_count']}")
            if data['ind5_has_disbursement']:
                detail.append(f"Pencairan:{data['disbursement_count']}")
            if data['ind1_has_legal']:
                detail.append("Verified")
            if detail:
                print(f"    Detail    : {' | '.join(detail)}")
            print()
        else:
            failed_nos.append(campaign_no)
            print(f"  ✗ Gagal (no.{campaign_no})\n")

        if (i + 1) % 10 == 0 and results:
            tmp_df = pd.DataFrame(results)
            for col in COLUMNS:
                if col not in tmp_df.columns:
                    tmp_df[col] = None
            tmp_path = os.path.join(parent_dir, 'data', 'processed',
                                    f'dompetdhuafa_temp_{i+1}.csv')
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

        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        out = os.path.join(parent_dir, 'data', 'processed',
                           f'dompetdhuafa_details_{start}_{start-1+len(results)}_{ts}.csv')
        df.to_csv(out, index=False, encoding='utf-8')

        print("\n" + "=" * 65)
        print("SELESAI!")
        print("=" * 65)
        print(f"Berhasil : {len(results)}/{len(batch)}")
        print(f"Output   : {out}")

        if failed_nos:
            print(f"\n Gagal ({len(failed_nos)}): no. {failed_nos}")

        print("\n📊 INDICATOR COVERAGE:")
        for col in COLUMNS:
            if col.startswith('ind') and col in df.columns:
                n = df[col].astype(str).isin(['True','true','1']).sum()
                print(f"  {col:<35}: {n}/{len(df)}")
        print("=" * 65)
    else:
        print("\n Tidak ada hasil — semua gagal.")

if __name__ == '__main__':
    main()
