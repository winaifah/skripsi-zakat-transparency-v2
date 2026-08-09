import sys
import os
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, parent_dir)

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
from webdriver_manager.chrome import ChromeDriverManager
from selenium_stealth import stealth
from bs4 import BeautifulSoup
import pandas as pd
import time
import re
from datetime import datetime, timedelta
import random
import json

import config

PLATFORM = "rumahyatim.org"
DISBURSEMENT_PATTERNS = [
    r'pencairan dana dengan total',
    r'pencairan dana sebesar',
]


def init_driver():
    options = Options()
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    options.add_argument("--start-maximized")

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)

    driver.set_page_load_timeout(60)
    driver.set_script_timeout(30)

    stealth(driver,
        languages=["id-ID", "id", "en-US", "en"],
        vendor="Google Inc.",
        platform="MacIntel",
        webgl_vendor="Intel Inc.",
        renderer="Intel Iris OpenGL Engine",
        fix_hairline=True,
    )

    print("✓ Chrome stealth siap")
    return driver

def is_cloudflare(page_source):
    for kw in ["Just a moment", "Checking your browser", "Enable JavaScript and cookies",
               "Melakukan verifikasi keamanan", "Please wait"]:
        if kw in page_source:
            return True
    return False


def safe_get(driver, url, wait=6, retries=3):
    for attempt in range(retries):
        try:
            driver.get(url)
        except Exception as e:
            if 'timeout' in str(e).lower():
                print(f"    ⏱ Page load timeout (konten mungkin sudah muat), lanjut...")
            else:
                print(f"    ⚠️ get() error: {str(e)[:60]}")
        time.sleep(wait)
        if not is_cloudflare(driver.page_source):
            return True
        wait_cf = random.uniform(50, 70)
        print(f"    ⚠️  Cloudflare di {url.split('/')[-1]} (attempt {attempt+1}/{retries}) — tunggu {wait_cf:.0f}s...")
        time.sleep(wait_cf)
    return False


def scroll_to_bottom(driver, max_rounds=30, pause=2):
    last_height = driver.execute_script("return document.body.scrollHeight")
    for _ in range(max_rounds):
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(pause)
        new_height = driver.execute_script("return document.body.scrollHeight")
        if new_height == last_height:
            break
        last_height = new_height


def is_disbursement_news(text):
    text_lower = text.lower()
    return any(re.search(p, text_lower) for p in DISBURSEMENT_PATTERNS)


def scrape_organizer_profile(driver, profile_url, back_url):

    try:
        ok = safe_get(driver, profile_url, wait=4)
        if not ok:
            return ""

        soup = BeautifulSoup(driver.page_source, 'html.parser')

        selectors = [
            {'class': re.compile(r'text-\[14px\]')},
            {'class': re.compile(r'bio|description|about', re.I)},
        ]
        desc = ""
        for sel in selectors:
            el = soup.find('div', sel)
            if el:
                desc = el.get_text(strip=True, separator=' ')
                if len(desc) > 30:
                    break

        return desc[:1000]

    except Exception as e:
        print(f"    ⚠️ Profile error: {str(e)[:60]}")
        return ""
    finally:
        try:
            driver.get(back_url)
            time.sleep(3)
        except:
            pass

def scrape_campaign_story(driver, soup_initial):
    """
    Ambil teks dari seksi Deskripsi.
    Klik tombol "Selengkapnya" terlebih dulu agar konten penuh muncul.
    """
    try:
        # Klik "Selengkapnya" di seksi Deskripsi
        btns = driver.find_elements(By.XPATH,
            "//button[.//span[contains(text(),'Selengkapnya')] or contains(text(),'Selengkapnya')]")
        for btn in btns:
            try:
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
                time.sleep(0.3)
                btn.click()
                time.sleep(1)
                break 
            except:
                pass

        soup = BeautifulSoup(driver.page_source, 'html.parser')

        # Cari div Deskripsi
        story_div = soup.find('div', class_=re.compile(r'prose.*prose-sm|prose-sm.*prose'))
        if not story_div:
            story_div = soup.find('div', class_=re.compile(r'text-universa-font-color'))

        if story_div:
            for img in story_div.find_all('img'):
                img.decompose()
            text = story_div.get_text(strip=True, separator=' ')
            return text[:5000]

        return ""

    except Exception as e:
        return f"ERROR: {str(e)[:60]}"

# SCRAPE LATEST NEWS
def scrape_latest_news(driver, expected_count):
    """
    Latest news ada di halaman kampanye yang SAMA (bukan URL terpisah).
    Alur:
      1. Klik tombol "Selengkapnya" di seksi Kabar Terbaru (expand container)
      2. Scroll ke bawah sampai semua li termuat
      3. Ekstrak setiap <li> langsung dari DOM (konten sudah fully rendered)
    """
    print(f"    📰 Latest news ({expected_count} expected) — halaman yang sama")
    updates = []

    try:
        all_btns = driver.find_elements(By.XPATH,
            "//button[.//span[contains(text(),'Selengkapnya')] "
            "or normalize-space(text())='Selengkapnya']")

        print(f"       Ditemukan {len(all_btns)} tombol Selengkapnya di halaman")
        for btn in all_btns:
            try:
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
                time.sleep(0.4)
                driver.execute_script("arguments[0].click();", btn)
                time.sleep(1)
            except:
                pass

        print(f"       Scroll untuk muat semua item...")
        try:
            exp = int(str(expected_count))
        except:
            exp = 0

        for _ in range(50):
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1.5)
            n_li = len(driver.find_elements(By.CSS_SELECTOR, 'ol li'))
            if exp > 0 and n_li >= exp:
                break

        soup = BeautifulSoup(driver.page_source, 'html.parser')

        news_ol = None
        for h3 in soup.find_all('h3'):
            if 'Kabar Terbaru' in h3.get_text():
                container = h3.find_parent('div', class_=re.compile(r'rounded-2xl'))
                if container:
                    news_ol = container.find('ol')
                break

        if not news_ol:
            news_ol = soup.find('ol', class_=re.compile(r'border-l'))
        if not news_ol:
            news_ol = soup.find('ol')

        all_li = news_ol.find_all('li') if news_ol else []
        print(f"       Total li ditemukan: {len(all_li)}")

        for li in all_li:
            for img in li.find_all('img'):
                img.decompose()

            title_el = li.find(['h4', 'h3', 'h2', 'h1'])
            title = title_el.get_text(strip=True) if title_el else ""

            time_el = li.find('time')
            date = time_el.get_text(strip=True) if time_el else ""

            prose_div = li.find('div', class_=re.compile(r'prose'))
            content = prose_div.get_text(strip=True, separator=' ') if prose_div else \
                      li.get_text(strip=True, separator=' ')

            if content and len(content) > 30:
                updates.append({'date': date, 'title': title, 'content': content[:3000]})

        print(f"       Total diekstrak: {len(updates)} item")

    except Exception as e:
        print(f"      ⚠️ Error news: {str(e)[:80]}")

    return json.dumps(updates, ensure_ascii=False)

# EKSTRAK DISBURSEMENT DARI NEWS
def extract_disbursement_from_news(latest_news_json):
    """
    Cari news item yang mengandung frasa pencairan dana.
    Return (has_disbursement, disbursement_count, disbursement_json)
    """
    if not latest_news_json or latest_news_json in ['[]', 'no updates', '']:
        return False, 0, "[]"

    try:
        items = json.loads(latest_news_json)
    except:
        return False, 0, "[]"

    disb_items = []
    for item in items:
        content = item.get('content', '') + ' ' + item.get('title', '')
        if is_disbursement_news(content):
            disb_items.append(item)

    has_disb = len(disb_items) > 0
    return has_disb, len(disb_items), json.dumps(disb_items, ensure_ascii=False)

# SCRAPE 1 CAMPAIGN
def scrape_campaign(driver, url, campaign_no):
    try:
        delay = random.uniform(5, 10)
        print(f"  ⏳ Delay {delay:.1f}s...")
        time.sleep(delay)

        ok = safe_get(driver, url, wait=7)
        if not ok:
            print(f"  ❌ Cloudflare blocked: {url}")
            return None

        soup = BeautifulSoup(driver.page_source, 'html.parser')
        slug = url.rstrip('/').split('/')[-1]

        data = {
            'no': campaign_no,
            'url': url,
            'slug': slug,
            'platform': PLATFORM,
            'scraped_at': datetime.now().isoformat(),
        }

        # ── JUDUL ──────────────────────────────────────────
        title_el = soup.find('h1', class_=re.compile(r'text-2xl|text-xl'))
        if title_el:
            data['title'] = title_el.get_text(strip=True)
        else:
            topbar = soup.find('div', class_=re.compile(r'program-detail_TopbarSpan'))
            if not topbar:
                topbar = soup.find('div', class_=re.compile(r'TopbarSpan'))
            data['title'] = topbar.get_text(strip=True) if topbar else "N/A"

        # ── COLLECTED AMOUNT ───────────────────────────────
        collected_el = soup.find('span', class_=re.compile(r'text-3xl.*font-bold|font-bold.*text-3xl'))
        data['collected_amount'] = collected_el.get_text(strip=True).replace('\xa0', ' ') if collected_el else "N/A"

        # ── TARGET AMOUNT ──────────────────────────────────
        # Cari span yang berisi "terkumpul dari target" lalu ambil <b>
        target_span = soup.find('span', string=re.compile(r'terkumpul dari target', re.I))
        if not target_span:
            target_span = soup.find('span', class_=re.compile(r'text-sm.*text-gray-500'))
        if target_span:
            b_el = target_span.find('b', class_=re.compile(r'text-gray-700|text-gray'))
            data['target_amount'] = b_el.get_text(strip=True).replace('\xa0', ' ') if b_el else "N/A"
        else:
            data['target_amount'] = "N/A"

        # ── DONOR COUNT & DAYS LEFT ────────────────────────
        donor_count_val = "0"
        days_left_val = "N/A"

        stat_spans = soup.find_all('span', class_=re.compile(r'text-gray-500.*text-sm|text-sm.*text-gray-500'))
        for span in stat_spans:
            text = span.get_text(strip=True)
            b_el = span.find('b')
            if not b_el:
                continue
            val = b_el.get_text(strip=True)
            if 'Donasi' in text or 'donasi' in text:
                donor_count_val = val
            elif 'Hari' in text or 'hari' in text:
                days_left_val = val

        data['days_left'] = days_left_val

        # ── ORGANIZER & PROFILE ────────────────────────────
        organizer_el = soup.find('span', {'data-testid': 'campaigner-name'})
        if not organizer_el:
            profile_link = soup.find('a', href=re.compile(r'/orang-baik/|/profile/|/penggalang/'))
            if profile_link:
                organizer_el = profile_link.find('span') or profile_link
        data['organizer'] = organizer_el.get_text(strip=True) if organizer_el else "N/A"

        profile_link_el = soup.find('a', href=re.compile(r'/orang-baik/|/profile/|/penggalang/'))
        if profile_link_el:
            href = profile_link_el.get('href', '')
            base = re.match(r'https?://[^/]+', url)
            base_url = base.group() if base else ''
            data['profile_url'] = href if href.startswith('http') else base_url + href
        else:
            data['profile_url'] = "N/A"

        if data['profile_url'] != "N/A":
            print(f"    👤 Profil...")
            data['organizer_description'] = scrape_organizer_profile(driver, data['profile_url'], url)

            soup = BeautifulSoup(driver.page_source, 'html.parser')
        else:
            data['organizer_description'] = ""

        # ── INDIKATOR 1: Identifikasi Penggalang ───────────
        data['ind1_has_profile'] = data['organizer'] != "N/A"

        contact_el = soup.find('a', href=re.compile(r'tel:|mailto:|wa\.me|whatsapp', re.I))
        data['ind1_has_contact_direct'] = contact_el is not None

        verified = (
            soup.find('svg', {'data-testid': 'verified-campaigner-badge'}) or
            soup.find('svg', {'data-testid': 'organization-badge'}) or
            soup.find('span', {'data-testid': 'campaigner-identity-verification-status'}) or
            soup.find(class_=re.compile(r'verified|terverifikasi', re.I))
        )
        data['ind1_has_legal'] = bool(verified)

        # ── INDIKATOR 2: Misi & Tujuan ─────────────────────
        desc_div = (
            soup.find('div', class_=re.compile(r'prose.*prose-sm|prose-sm.*prose')) or
            soup.find('div', class_=re.compile(r'text-universa-font-color'))
        )
        if desc_div:
            desc_text = desc_div.get_text(strip=True, separator=' ')
            wc = len(desc_text.split())
            data['ind2_has_mission'] = wc > 50
            data['ind2_word_count'] = wc
        else:
            data['ind2_has_mission'] = False
            data['ind2_word_count'] = 0

        # ── INDIKATOR 3: Laporan Dana Masuk (donor count) ──
        data['ind3_has_fund_report'] = donor_count_val != "0"
        data['donor_count'] = donor_count_val

        # ── INDIKATOR 4: Update / Kabar Terbaru ───────────
        news_section = None
        for h3 in soup.find_all('h3'):
            if 'Kabar Terbaru' in h3.get_text():
                news_section = h3
                break

        news_container = news_section.find_parent('div', class_=re.compile(r'rounded-2xl')) if news_section else None

        update_count_val = 0
        if news_container:
            li_items = news_container.find_all('li')
            update_count_val = len(li_items)

        if update_count_val == 0 and news_container:
            badge = news_container.find('span', class_=re.compile(r'bg-cerulean|rounded-full'))
            if badge:
                try:
                    update_count_val = int(badge.get_text(strip=True))
                except:
                    pass

        if update_count_val == 0:
            ol = soup.find('ol', class_=re.compile(r'border-l'))
            if ol:
                update_count_val = len(ol.find_all('li'))

        data['ind4_has_updates'] = update_count_val > 0
        data['update_count'] = str(update_count_val)

        # ── INDIKATOR 6: Transparansi Biaya Admin ─────────
        budget_btn = (
            soup.find('button', {'data-testid': re.compile(r'budget-plan')}) or
            soup.find('a', string=re.compile(r'biaya|admin|budget|rencana', re.I)) or
            soup.find('button', string=re.compile(r'biaya|admin|budget|rencana', re.I))
        )
        data['ind6_has_admin_fee'] = budget_btn is not None

        # ── INDIKATOR 7 & 8: Tetap ─────────────────────────
        data['ind7_has_anonymity'] = True
        data['ind8_has_transaction_id'] = False

        # ── CAMPAIGN STORY (klik Selengkapnya di Deskripsi) ─
        print(f"    📖 Story...")
        data['campaign_story'] = scrape_campaign_story(driver, soup)
        print(f"       {len(data['campaign_story'])} karakter")

        # ── LATEST NEWS (masih di halaman yang sama) ──────
        if data['ind4_has_updates']:
            data['latest_news_json'] = scrape_latest_news(driver, data['update_count'])
        else:
            data['latest_news_json'] = "no updates"
            print(f"    📰 Tidak ada update")

        # ── INDIKATOR 5: Disbursement (dari news) ─────────
        has_disb, disb_count, disb_json = extract_disbursement_from_news(data['latest_news_json'])
        data['ind5_has_disbursement'] = has_disb
        data['disbursement_count'] = str(disb_count)
        data['disbursement_json'] = disb_json

        # ── TOTAL INDIKATOR ────────────────────────────────
        data['total_indicators_detected'] = sum([
            data['ind1_has_profile'],
            data['ind1_has_contact_direct'],
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
        print(f"  ✗ Error: {str(e)[:80]}")
        return None


COLUMN_ORDER = [
    'no', 'url', 'slug', 'platform', 'scraped_at',
    'title', 'organizer', 'collected_amount', 'target_amount', 'days_left',
    'profile_url', 'organizer_description',
    'ind1_has_profile', 'ind1_has_contact_direct', 'ind1_has_legal',
    'ind2_has_mission', 'ind2_word_count',
    'ind3_has_fund_report', 'donor_count',
    'ind4_has_updates', 'update_count',
    'ind5_has_disbursement', 'disbursement_count',
    'ind6_has_admin_fee', 'ind7_has_anonymity', 'ind8_has_transaction_id',
    'total_indicators_detected',
    'campaign_story', 'latest_news_json', 'disbursement_json',
]


def main():
    print("""
scrape detail rumah yatim
""")

    # ── Input file ──────────────────────────────────────
    default_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'data', 'raw', 'rumahyatim_zakat_urls.csv'
    )
    print(f"Default input: {default_path}")
    custom = input("Path file (Enter = default): ").strip()
    input_file = custom if custom else default_path

    if not os.path.exists(input_file):
        print(f"❌ File tidak ditemukan: {input_file}")
        return

    df_urls = pd.read_csv(input_file)
    print(f"✓ Loaded {len(df_urls)} URLs\n")

    # ── Pilih batch ─────────────────────────────────────
    print("Pilih batch:")
    print("  1.  10 kampanye")
    print("  2.  25 kampanye")
    print("  3.  50 kampanye")
    print("  4. Custom jumlah")
    print("  5. Custom jumlah + start index")
    choice = input("Pilihan (1-5): ").strip()

    if choice == '5':
        start_idx = int(input("Mulai dari index (0-based): "))
        batch_size = int(input("Jumlah kampanye: "))
        campaigns = df_urls.iloc[start_idx:start_idx + batch_size]
    elif choice == '4':
        batch_size = int(input("Jumlah kampanye: "))
        campaigns = df_urls.head(batch_size)
    else:
        sizes = {'1': 10, '2': 25, '3': 50}
        batch_size = sizes.get(choice, 10)
        campaigns = df_urls.head(batch_size)

    print(f"\n✓ Akan scrape {len(campaigns)} kampanye\n")
    confirm = input("Proceed? (y/n): ").strip().lower()
    if confirm != 'y':
        print("Cancelled.")
        return

    driver = init_driver()

    results = []
    failed_nos = []
    start_time = datetime.now()

    print(f"\n[Scraping {len(campaigns)} kampanye...]\n" + "="*80 + "\n")

    for i, (idx, row) in enumerate(campaigns.iterrows()):
        campaign_no = int(row['no']) if 'no' in row and pd.notna(row.get('no')) else i + 1
        slug = str(row.get('slug', row['url'].rstrip('/').split('/')[-1]))
        print(f"[{i+1}/{len(campaigns)}] #{campaign_no} — {slug[:60]}")

        data = scrape_campaign(driver, row['url'], campaign_no)

        if data and data.get('title', 'N/A') != 'N/A':
            results.append(data)
            print(f"  ✓ {data['title'][:55]}")
            print(f"     Donors:{data['donor_count']}  Updates:{data['update_count']}"
                  f"  Disb:{data['disbursement_count']}  Score:{data['total_indicators_detected']}/10")
        else:
            failed_nos.append(campaign_no)
            print(f"  ✗ Gagal (no.{campaign_no})")
        print()

        if (i + 1) % 10 == 0 and results:
            tmp_df = pd.DataFrame(results)
            for col in COLUMN_ORDER:
                if col not in tmp_df.columns:
                    tmp_df[col] = ""
            tmp_df = tmp_df[COLUMN_ORDER]
            tmp_path = config.PROCESSED_DATA_PATH + f'rumahyatim_temp_{i+1}.csv'
            tmp_df.to_csv(tmp_path, index=False, encoding='utf-8')
            elapsed = datetime.now() - start_time
            avg = elapsed.total_seconds() / len(results)
            eta = timedelta(seconds=int((len(campaigns) - len(results)) * avg))
            print(f"  💾 Tersimpan: {tmp_path}")
            print(f"     {len(results)}/{len(campaigns)} | Avg:{avg:.0f}s | ETA:{eta}\n")

    driver.quit()
    print("✓ Browser ditutup")

    if results:
        df = pd.DataFrame(results)
        for col in COLUMN_ORDER:
            if col not in df.columns:
                df[col] = ""
        df = df[COLUMN_ORDER]

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        out = config.PROCESSED_DATA_PATH + f'rumahyatim_complete_{len(results)}_{timestamp}.csv'
        df.to_csv(out, index=False, encoding='utf-8')

        elapsed = datetime.now() - start_time
        print("\n" + "="*80)
        print(f"SELESAI: {len(results)}/{len(campaigns)} berhasil")
        print(f"   Waktu  : {elapsed} | Avg: {elapsed.total_seconds()/len(results):.0f}s/kampanye")
        print(f"   Output : {out}")
        print("="*80)

        print("\n📊 INDIKATOR TRANSPARANSI:")
        ind_cols = {
            'ind1_has_profile':       'Ind 1a Profile',
            'ind1_has_contact_direct':'Ind 1b Kontak langsung',
            'ind1_has_legal':         'Ind 1c Legal/verified',
            'ind2_has_mission':       'Ind 2  Misi & tujuan',
            'ind3_has_fund_report':   'Ind 3  Laporan dana masuk',
            'ind4_has_updates':       'Ind 4  Ada update',
            'ind5_has_disbursement':  'Ind 5  Pencairan dana',
            'ind6_has_admin_fee':     'Ind 6  Biaya admin',
            'ind7_has_anonymity':     'Ind 7  Anonimitas',
            'ind8_has_transaction_id':'Ind 8  ID transaksi',
        }
        n = len(df)
        for col, label in ind_cols.items():
            if col in df.columns:
                cnt = df[col].apply(lambda x: str(x).lower() in ['true','1']).sum()
                print(f"  {label:<30} {cnt:>3}/{n}  {cnt/n*100:>5.1f}%")
        avg_score = df['total_indicators_detected'].mean()
        print(f"\n  Rata-rata score: {avg_score:.2f}/10 ({avg_score/10*100:.1f}%)")

        if failed_nos:
            print(f"\n⚠️  Gagal ({len(failed_nos)}): no. {failed_nos}")
            fail_path = config.PROCESSED_DATA_PATH + f'rumahyatim_failed_{timestamp}.txt'
            with open(fail_path, 'w') as f:
                f.write('\n'.join(str(n) for n in failed_nos))
            print(f"   Tersimpan ke: {fail_path}")

    else:
        print("\n Tidak ada hasil — semua gagal/blocked")


if __name__ == "__main__":
    main()
