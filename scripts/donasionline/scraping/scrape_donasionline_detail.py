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

# ── Kolom output 
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

def scrape_campaign(driver, url, slug, campaign_no, title_from_csv=""):
    try:
        delay = random.uniform(6, 11)
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
                By.XPATH,
                "//div[contains(@class,'cursor-pointer')][./div[normalize-space(text())='Selengkapnya']]"
            )
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
            time.sleep(0.5)
            driver.execute_script("arguments[0].click();", btn)
            time.sleep(1)
        except Exception:
            pass

        soup = BeautifulSoup(driver.page_source, 'html.parser')

        data = {
            'no'        : campaign_no,
            'url'       : url,
            'slug'      : slug,
            'platform'  : 'donasionline',
            'scraped_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        }

        # ── Judul ────────────────────────────────────────────────
        title_tag = soup.find('h1') or soup.find('h2', class_=re.compile(r'font-bold|font-semibold'))
        data['title'] = title_tag.get_text(strip=True) if title_tag else title_from_csv

        # ── Organizer — selalu Yayasan Rumah Yatim Arrohman Indonesia ──
        data['organizer']             = 'Yayasan Rumah Yatim Arrohman Indonesia'
        data['profile_url']           = ''
        data['organizer_description'] = (
            'Yayasan Rumah Yatim Arrohman Indonesia berkomitmen untuk menggunakan '
            'dana donasi sesuai dengan peruntukan yang dipilih oleh donatur, dan '
            'akan memberikan laporan penggunaan dana tersebut secara transparan. '
            'Dana digunakan untuk bantuan kemanusiaan, pendidikan, kesehatan, dan '
            'pemberdayaan masyarakat.'
        )
        data['ind1_has_profile']        = True  
        data['ind1_has_contact_direct'] = False
        data['ind1_has_legal']          = True 

        # ── Dana terkumpul & target ───────────────────────────────
        collected_span = soup.find('span', class_=lambda c: c and
                                    'text-primary' in c and 'font-bold' in c and 'text-base' in c)
        data['collected_amount'] = (collected_span.get_text(strip=True)
                                    if collected_span else '')

        target_amount = ''
        if collected_span:
            parent_span = collected_span.find_next_sibling('span')
            if parent_span:
                black_div = parent_span.find('div', class_=lambda c: c and 'text-black' in c)
                if black_div:
                    target_amount = black_div.get_text(strip=True)
        data['target_amount'] = target_amount

        # ── Sisa hari ────────────────────────────────────────────
        page_text = soup.get_text(' ', strip=True)
        days_m = re.search(r'(\d+)\s*hari\s*(lagi|tersisa)', page_text, re.I)
        data['days_left'] = (days_m.group(1) + ' hari') if days_m else ''

        # ── Campaign story (Cerita Penggalangan Dana) ─────────────
        story_text = ''
        for h3 in soup.find_all('h3'):
            if 'Cerita Penggalangan' in h3.get_text():
                
                container = h3.find_parent('div', attrs={'x-data': True})
                if container:
             
                    content_div = container.find('div', class_=lambda c: c and 'overflow-y-hidden' in c)
                    if not content_div:
                        content_div = container.find('div', class_=lambda c: c and 'space-y-3' in c)
                    if content_div:
                        story_text = clean_text(content_div)
                break
        data['campaign_story'] = story_text

        words = story_text.split()
        data['ind2_has_mission'] = len(words) > 50
        data['ind2_word_count']  = len(words)

        # ── Donor count & fund report ─────────────────────────────
        donor_count = 0
        for h3 in soup.find_all('h3'):
            if 'PejuangKebaikan' in h3.get_text() or 'Donatur' in h3.get_text():
                parent = h3.find_parent('div')
                if parent:
                    count_div = parent.find('div', class_=lambda c: c and
                                             'font-bold' in c and 'text-xs' in c and 'text-primary' in c)
                    if count_div:
                        txt = count_div.get_text(strip=True)
                        donor_count = int(txt) if txt.isdigit() else 0
                break
        data['donor_count']       = str(donor_count)
        data['ind3_has_fund_report'] = donor_count > 0

        # ── Berita Penyaluran (news) ──────────────────────────────
        news_section = soup.find('div', id='news')
        news_items   = []

        if news_section:
            list_news = news_section.find('div', id='list-news')
            if list_news:
                for item in list_news.find_all('div', class_=lambda c: c and 'berita-item' in c):
                    title_h2 = item.find('h2')
                    date_span = item.find('span', class_=lambda c: c and 'text-gray-600' in c)
                    content_div = item.find('div', class_=lambda c: c and 'content' in c)

                    item_title   = title_h2.get_text(strip=True)   if title_h2   else ''
                    item_date    = date_span.get_text(strip=True)   if date_span  else ''
                    item_content = clean_text(content_div)          if content_div else ''

                    if item_title or item_content:
                        news_items.append({
                            'date'   : item_date,
                            'title'  : item_title,
                            'content': item_content,
                        })

        data['ind4_has_updates'] = len(news_items) > 0
        data['update_count']     = str(len(news_items))
        data['latest_news_json'] = (json.dumps(news_items, ensure_ascii=False)
                                    if news_items else 'no updates')

        # ── Pencairan Dana — dari konten berita ───────────────────
        pencairan = [
            item for item in news_items
            if re.search(r'pencairan\s+dana|penyaluran\s+dana',
                         item['title'] + ' ' + item['content'], re.I)
        ]
        data['ind5_has_disbursement'] = len(pencairan) > 0
        data['disbursement_count']    = str(len(pencairan))
        data['disbursement_json']     = (json.dumps(pencairan, ensure_ascii=False)
                                         if pencairan else 'no disbursement')

        # ── Indikator tetap ───────────────────────────────────────
        data['ind6_has_admin_fee']      = False
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

        return data

    except Exception as e:
        print(f"  ✗ Error: {str(e)[:100]}")
        return None


def main():
    print("=" * 65)
    print("  DONASI ONLINE — Scrape Detail Kampanye")
    print("=" * 65)

    # ── Pilih file URL ────────────────────────────────────────────
    default_file = os.path.join(parent_dir, 'data', 'raw', 'donasionline_zakat_urls.csv')
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

    driver = init_driver()
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
            print(f"    Terkumpul : {data['collected_amount']} / {data['target_amount']}")
            print(f"    Donatur   : {data['donor_count']} | Indicators: {total}/9")
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

        if (i + 1) % 10 == 0 and results:
            tmp_df = pd.DataFrame(results)
            for col in COLUMNS:
                if col not in tmp_df.columns:
                    tmp_df[col] = None
            tmp_path = os.path.join(parent_dir, 'data', 'processed',
                                    f'donasionline_temp_{i+1}.csv')
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
                           f'donasionline_details_{start}_{start-1+len(results)}_{ts}.csv')
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