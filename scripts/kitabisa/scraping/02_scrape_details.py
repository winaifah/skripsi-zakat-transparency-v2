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

def is_cloudflare_blocked(page_source):
    if not page_source:
        return True

    keywords = [
        "Melakukan verifikasi keamanan",
        "Enable JavaScript and cookies to continue",
        "Checking your browser",
        "Just a moment",
        "Please wait",
        "cf-browser-verification",
        "challenge-platform",
        "cf-challenge",
        "cf-turnstile",
    ]

    page_lower = page_source.lower()
    return any(k.lower() in page_lower for k in keywords)


def debug_page(driver, label):
    try:
        print(f"    [debug:{label}] title      : {driver.title}")
        print(f"    [debug:{label}] current_url: {driver.current_url}")
        print(f"    [debug:{label}] html_len   : {len(driver.page_source)}")
    except Exception as e:
        print(f"    [debug:{label}] gagal debug: {str(e)[:80]}")


def init_stealth_driver():
    try:
        import undetected_chromedriver as uc
        options = uc.ChromeOptions()
        options.add_argument("--start-maximized")
        options.add_argument("--lang=id-ID")
        options.add_argument("--disable-notifications")
        driver = uc.Chrome(options=options, version_main=None)
        print("✓ undetected-chromedriver initialized")
        return driver
    except ImportError:
        pass

    options = Options()
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    options.add_argument("--start-maximized")
    options.add_argument("--lang=id-ID")
    options.add_argument("--disable-notifications")

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)

    stealth(driver,
        languages=["id-ID", "id", "en-US", "en"],
        vendor="Google Inc.",
        platform="MacIntel",
        webgl_vendor="Intel Inc.",
        renderer="Intel Iris OpenGL Engine",
        fix_hairline=True,
    )

    print("✓ selenium-stealth Chrome initialized")
    return driver


def wait_page_ready(driver, url, label="halaman", max_retries=5, min_html_len=12000):
    for attempt in range(max_retries):
        try:
            driver.get(url)
            time.sleep(8)
            html = driver.page_source
            debug_page(driver, label)

            if is_cloudflare_blocked(html):
                wait = random.uniform(35, 70)
                print(f" Cloudflare di {label} (attempt {attempt+1}/{max_retries}) — tunggu {wait:.0f}s...")
                time.sleep(wait)
                continue

            if len(html.strip()) < min_html_len:
                wait = random.uniform(8, 15)
                print(f"    ⏳ {label}: render belum siap (attempt {attempt+1}/{max_retries}) — tunggu {wait:.0f}s...")
                time.sleep(wait)
                continue

            return True

        except Exception as e:
            wait = random.uniform(10, 20)
            print(f"    ⚠️ Error load {label}: {str(e)[:80]} — retry {wait:.0f}s")
            time.sleep(wait)

    return False


def safe_return_to_campaign(driver, campaign_url):
    return wait_page_ready(driver, campaign_url, "kembali-campaign", max_retries=4)


def scrape_organizer_profile(driver, profile_url, campaign_url):

    try:
        ok = wait_page_ready(driver, profile_url, "organizer-profile", max_retries=5, min_html_len=8000)
        if not ok:
            print("Profile gagal dimuat, tandai untuk retry")
            safe_return_to_campaign(driver, campaign_url)
            return "PROFILE_BLOCKED_OR_NOT_RENDERED"

        soup = BeautifulSoup(driver.page_source, 'html.parser')

        desc_div = soup.find('div', class_=re.compile(r'text-\[14px\].*leading-\[21px\]'))

        if not desc_div:
            desc_div = soup.find('div', class_=re.compile(r'bio|description|about', re.I))

        if desc_div:
            for tag in desc_div.find_all(['img', 'figure', 'figcaption', 'svg', 'video']):
                tag.decompose()
            description = desc_div.get_text(strip=True, separator=' ')
            description = re.sub(r'\s{2,}', ' ', description).strip()
        else:
            description = ""

        safe_return_to_campaign(driver, campaign_url)
        return description

    except Exception as e:
        print(f" Profile scraping error: {str(e)[:80]}")
        safe_return_to_campaign(driver, campaign_url)
        return "PROFILE_ERROR"


def _find_pof_org_link(soup):

    all_links = soup.find_all('a', href=re.compile(r'/orang-baik/'))
    if not all_links:
        return None

    fundraiser_section = (
        soup.find(attrs={'data-testid': 'campaign-fundraiser-information'}) or
        soup.find(attrs={'data-testid': 'campaign-fundraiser-information-organizer'}) or
        soup.find(attrs={'data-testid': 'campaign-pof-organizer'})
    )
    if fundraiser_section:
        link = fundraiser_section.find('a', href=re.compile(r'/orang-baik/'))
        if link:
            return link

    for link in all_links:
        bold = link.find('div', class_='font-bold')
        if bold and len(bold.get_text(strip=True)) >= 2:
            return link

    for link in all_links:
        sp = link.find('span')
        if sp and len(sp.get_text(strip=True)) >= 2:
            return link

    return all_links[0]


def detect_transparency_indicators(soup):

    indicators = {}
    
    organizer = soup.find('span', {'data-testid': 'campaigner-name'})
    pof_org_link = _find_pof_org_link(soup)
    indicators['ind1_has_profile'] = bool(organizer or pof_org_link)
    indicators['ind1_has_contact_direct'] = False

    verified_svg = soup.find('svg', {'data-testid': 'verified-campaigner-badge'})
    org_badge = soup.find('svg', {'data-testid': 'organization-badge'})
    verified_text = soup.find('span', {'data-testid': 'campaigner-identity-verification-status'})
    
    indicators['ind1_has_legal'] = bool(verified_svg or org_badge or verified_text)
    
    #Indikator 2: Misi dan Tujuan Campaign
    desc_div = soup.find('div', class_='cd-story__content')
    if not desc_div:
        section = soup.find(attrs={'data-testid': 'campaign-section-fundraising-story'})
        if section:
            # Ambil konten di dalam section, bukan header-nya
            desc_div = section.find('div', class_=re.compile(r'content|story|text', re.I)) or section
    if not desc_div:
        desc_div = soup.find('div', {'data-testid': 'campaign-story'})

    if desc_div:
        # Hapus gambar dan elemen non-teks sebelum ambil teks
        for tag in desc_div.find_all(['img', 'figure', 'figcaption', 'svg', 'video']):
            tag.decompose()
        desc_text = desc_div.get_text(strip=True, separator=' ')
        desc_text = re.sub(r'\s{2,}', ' ', desc_text).strip()
        word_count = len(desc_text.split())
        indicators['ind2_has_mission'] = word_count > 50
        indicators['ind2_word_count'] = word_count
        indicators['description'] = desc_text
    else:
        indicators['ind2_has_mission'] = False
        indicators['ind2_word_count'] = 0
        indicators['description'] = ""
    
    #Indikator 3: Laporan Penggunaan Dana
    donation_button = soup.find('button', {'data-testid': 'campaign-section-donation'})
    indicators['ind3_has_fund_report'] = donation_button is not None
    
    # Extract donor count
    if donation_button:
        donor_count_elem = donation_button.find('span', class_=re.compile(r'bg-cerulean'))
        indicators['donor_count'] = donor_count_elem.text.strip() if donor_count_elem else "0"
    else:
        indicators['donor_count'] = "0"
    
    #Indikator 4: Update Campaign
    updates_section = soup.find('div', {'id': 'campaign-updates'})
    if updates_section:
        # Gunakan regex lebih luas — class bg-cerulean cukup (count 1 pun tetap cerulean)
        update_badge = updates_section.find('span', class_=re.compile(r'bg-cerulean'))
        indicators['ind4_has_updates'] = update_badge is not None
        indicators['update_count'] = update_badge.get_text(strip=True) if update_badge else "0"
    else:
        indicators['ind4_has_updates'] = False
        indicators['update_count'] = "0"
    
    #Indikator 5: Disbursement
    disbursement_section = soup.find('div', {'id': 'disbursements'})
    if disbursement_section:
        disbursement_badge = disbursement_section.find('span', class_=re.compile(r'bg-cerulean'))
        indicators['ind5_has_disbursement'] = disbursement_badge is not None
        indicators['disbursement_count'] = disbursement_badge.get_text(strip=True) if disbursement_badge else "0"
    else:
        indicators['ind5_has_disbursement'] = False
        indicators['disbursement_count'] = "0"
    
    #Indikator 6: Biaya Admin
    budget_elem = (
        soup.find('button', {'data-testid': 'campaign-fundraiser-information-budget-plan-button'}) or
        soup.find('button', {'data-testid': 'campaign-budget-plan-button'}) or
        soup.find(attrs={'data-testid': 'budget-detail-button'}) or
        soup.find(attrs={'data-testid': 'budget-detail'})
    )
    indicators['ind6_has_admin_fee'] = budget_elem is not None
    
    #Indikator 7: Anonimitas Donatur
    indicators['ind7_has_anonymity'] = True
    
    #Indikator 8: ID Transaksi
    indicators['ind8_has_transaction_id'] = False
    
    return indicators

def scrape_campaign(driver, url, campaign_no):
    """
    Scrape 1 campaign dengan profile description
    
    Returns complete campaign data ready for NER processing
    """
    
    try:
        delay = random.uniform(6, 12)
        print(f" Delay {delay:.1f}s...")
        time.sleep(delay)
        
        if not wait_page_ready(driver, url, f"campaign-{campaign_no}", max_retries=5, min_html_len=15000):
            print("  ✗ Campaign blocked/render gagal setelah retry")
            return None

        soup = BeautifulSoup(driver.page_source, 'html.parser')
        
        data = {
            'no': campaign_no,
            'url': url,
            'slug': url.split('/campaign/')[-1] if '/campaign/' in url else 'N/A',
            'platform': 'kitabisa.com',
            'scraped_at': datetime.now().isoformat(),
        }

        # Deteksi template: Normal vs POF
        is_pof = soup.find(attrs={'data-testid': 'campaign-pof-title'}) is not None
        data['template'] = 'pof' if is_pof else 'normal'
        if is_pof:
            print(f"    🔖 Template: POF (BisaZakat/Program)")

        # Title
        title = (
            soup.find(attrs={'data-testid': 'campaign-pof-title'}) or
            soup.find('h1', {'data-testid': 'campaign-title'})
        )
        data['title'] = title.text.strip() if title else "N/A"

        # Organizer
        if is_pof:
            org_link = _find_pof_org_link(soup)
            if org_link:
                org_name = (
                    org_link.find('div', class_='font-bold') or
                    org_link.find('span') or
                    org_link
                )
                data['organizer'] = org_name.text.strip() if org_name else "N/A"
            else:
                data['organizer'] = "N/A"
        else:
            organizer = soup.find('span', {'data-testid': 'campaigner-name'})
            data['organizer'] = organizer.text.strip() if organizer else "N/A"
            org_link = soup.find('a', href=re.compile(r'/orang-baik/'))  # untuk profile URL

        # Collected Amount & Target & Days Left
        pof_has_budget = False 
        if is_pof:
            try:
                see_all_btn = driver.find_element(By.CSS_SELECTOR, '[data-testid="campaign-pof-link-see-all"]')
                see_all_btn.click()
                time.sleep(3)
                soup_pof = BeautifulSoup(driver.page_source, 'html.parser')
                collected = soup_pof.find(attrs={'data-testid': 'campaign-pof-donation-received'})

                pof_has_budget = soup_pof.find(attrs={'data-testid': 'budget-detail-button'}) is not None

                driver.back()
                time.sleep(3)
                soup = BeautifulSoup(driver.page_source, 'html.parser')
            except Exception:
                collected = soup.find(attrs={'data-testid': 'campaign-pof-donation-received'})
            data['collected_amount'] = collected.text.strip() if collected else "N/A"
            data['target_amount'] = "no target amount"
            data['days_left'] = "no days_left"
        else:
            collected = soup.find('span', {'data-testid': 'campaign-donation-received'})
            data['collected_amount'] = collected.text.strip() if collected else "N/A"
            target = soup.find('div', {'data-testid': 'campaign-donation-goal'})
            data['target_amount'] = target.text.strip() if target else "N/A"
            days = soup.find('div', {'data-testid': 'campaign-donation-days-to-go'})
            data['days_left'] = days.text.strip() if days else "N/A"

        
        if org_link:
            profile_url = "https://kitabisa.com" + org_link['href']
            data['profile_url'] = profile_url

            print(f" Scraping profile...")
            organizer_desc = scrape_organizer_profile(driver, profile_url, url)
            data['organizer_description'] = organizer_desc

            print(f" Kembali ke halaman kampanye...")
            if not safe_return_to_campaign(driver, url):
                print(" Gagal kembali ke halaman campaign, lanjut pakai HTML terakhir jika ada")
  
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(1)
            soup = BeautifulSoup(driver.page_source, 'html.parser')
        else:
            data['profile_url'] = "N/A"
            data['organizer_description'] = ""

            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(1)
            soup = BeautifulSoup(driver.page_source, 'html.parser')


        indicators = detect_transparency_indicators(soup)
        data.update(indicators)

        if is_pof and pof_has_budget:
            data['ind6_has_admin_fee'] = True
        
        total = sum([
            data.get('ind1_has_profile', False),
            data.get('ind1_has_legal', False),
            data.get('ind2_has_mission', False),
            data.get('ind3_has_fund_report', False),
            data.get('ind4_has_updates', False),
            data.get('ind5_has_disbursement', False),
            data.get('ind6_has_admin_fee', False),
            data.get('ind7_has_anonymity', False),
            data.get('ind8_has_transaction_id', False)
        ])
        data['total_indicators_detected'] = total
        
        return data
        
    except Exception as e:
        print(f"  ✗ Error: {str(e)[:80]}")
        return None

def main():
    
    print("""
Ekstraksi detail kampanye + profile organizer dari kitabisa.com
""")
    
    # Pilih mode input
    print("Pilih mode input:")
    print("  1. Dari kitabisa_urls_final_merged.csv (default)")
    print("  2. Dari file custom CSV")

    mode_choice = input("\nMode (1-2): ").strip()

    if mode_choice == "2":
        custom_path = input("Masukkan path file (relatif dari root project atau absolut): ").strip()
        import os
        if not os.path.isabs(custom_path):
            custom_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), custom_path)
        print(f"\n✓ Menggunakan file: {custom_path}")
        df_urls = pd.read_csv(custom_path)
        print(f"✓ Loaded {len(df_urls)} URLs (no. {df_urls['no'].min()} - {df_urls['no'].max()})\n")

        print("Pilih batch:")
        print("  1.  10 campaigns")
        print("  2.  20 campaigns")
        print("  3.  25 campaigns")
        print("  4.  50 campaigns")
        print("  5. Semua")
        print("  6. Custom jumlah")
        print("  7. Custom jumlah + start dari baris tertentu (1-based)")
        batch_choice = input("\nPilihan (1-7): ").strip()
        batch_map = {'1': 10, '2': 20, '3': 25, '4': 50}
        if batch_choice == '7':
            start_1 = int(input("Mulai dari baris ke berapa? (1-based): "))
            batch_size = int(input("Scrape berapa kampanye? "))
            campaigns = df_urls.iloc[start_1-1 : start_1-1+batch_size]
        elif batch_choice == '6':
            batch_size = int(input("Masukkan jumlah: "))
            campaigns = df_urls.head(batch_size)
        elif batch_choice == '5':
            campaigns = df_urls
        else:
            batch_size = batch_map.get(batch_choice, 20)
            campaigns = df_urls.head(batch_size)
        print(f"✓ Akan scrape {len(campaigns)} kampanye (no. {campaigns['no'].min()} - {campaigns['no'].max()})\n")
    else:
        print("\nPilih batch size:")
        print("  1.  10 campaigns  (~10 menit)")
        print("  2.  25 campaigns  (~25 menit)")
        print("  3.  50 campaigns  (~50 menit)")
        print("  4. 100 campaigns  (~1.5 jam)")
        print("  5. Custom jumlah saja")
        print("  6. Custom jumlah + start dari index tertentu")

        choice = input("\nPilihan (1-6): ").strip()

        batch_sizes = {'1': 10, '2': 25, '3': 50, '4': 100}

        print("[1/3] Loading URLs...")
        df_urls = pd.read_csv(config.RAW_DATA_PATH + 'kitabisa_urls_final_merged.csv')

        if choice == '6':
            start_idx = int(input("Mulai dari index ke berapa? (0-based, contoh: 100 → mulai dari no.101): "))
            batch_size = int(input("Scrape berapa kampanye? "))
            campaigns = df_urls.iloc[start_idx:start_idx + batch_size]
        elif choice == '5':
            batch_size = int(input("Masukkan jumlah: "))
            campaigns = df_urls.head(batch_size)
        else:
            batch_size = batch_sizes.get(choice, 10)
            campaigns = df_urls.head(batch_size)

        print(f"✓ Loaded {len(campaigns)} URLs (no. {campaigns['no'].min()} - {campaigns['no'].max()})\n")

    print(f"\n✓ Will scrape {len(campaigns)} campaigns (with organizer profiles)\n")

    print("[1/3] URLs ready...")
    

    print("[2/3] Starting Chrome stealth mode...")
    driver = init_stealth_driver()
    print()

 
    print(f"[3/3] Scraping {len(campaigns)} campaigns + profiles...")
    print("="*80 + "\n")
    
    results = []
    failed_nos = []
    start_time = datetime.now()

    for idx, row in campaigns.iterrows():
        raw_url = row.get('url', '')
        url = str(raw_url).strip() if pd.notna(raw_url) else ''
        if url.lower() == 'nan':
            url = ''

        if pd.notna(row.get('slug')):
            slug_display = str(row['slug'])[:50]
        elif url:
            slug_display = url.split('/campaign/')[-1][:50]
        else:
            slug_display = f"missing-url-{idx+1}"

        print(f"[{idx+1}/{len(campaigns)}] {slug_display}")


        campaign_no = int(row['no']) if 'no' in row and pd.notna(row['no']) else idx + 1

        if not url:
            print(f"  ✗ Skipping row {idx+1} because URL is missing or invalid\n")
            failed_nos.append(campaign_no)
            continue

        data = scrape_campaign(driver, url, campaign_no)
        
        if data and data['title'] != "N/A":
            results.append(data)
            print(f"  ✓ {data['title'][:50]}")
            print(f"    Organizer: {data['organizer'][:30]}")
            print(f"    Profile: {len(data.get('organizer_description', ''))} chars")
            print(f"    Indicators: {data['total_indicators_detected']}/8 (pre-NER)")

            detail = []
            if data.get('ind4_has_updates'):
                detail.append(f"Updates:{data.get('update_count', '?')}")
            if data.get('ind5_has_disbursement'):
                detail.append(f"Disbursement:{data.get('disbursement_count', '?')}")
            if data.get('ind1_has_legal'):
                detail.append("Verified")
            if detail:
                print(f"    Detail: {' | '.join(detail)}")
            print()
        else:
            failed_nos.append(campaign_no)
            print(f"  ✗ Gagal (no.{campaign_no})\n")

        if results:
            temp = pd.DataFrame(results)
            temp_path = config.PROCESSED_DATA_PATH + f'with_profile_autosave_latest.csv'
            temp.to_csv(temp_path, index=False, encoding='utf-8')
            print(f" Autosave latest: {temp_path}")

        processed_so_far = len(results) + len(failed_nos)
        if processed_so_far > 0 and processed_so_far % 5 == 0 and processed_so_far < len(campaigns):
            print(" Restart driver + cooling 30s...")
            try:
                driver.quit()
            except Exception:
                pass
            time.sleep(30)
            driver = init_stealth_driver()
            print("  ✓ Driver baru siap\n")

        if (idx + 1) % 10 == 0 and results:
            temp = pd.DataFrame(results)
            temp_path = config.PROCESSED_DATA_PATH + f'with_profile_temp_{idx+1}.csv'
            temp.to_csv(temp_path, index=False, encoding='utf-8')
            
            elapsed = datetime.now() - start_time
            avg_time = elapsed.total_seconds() / len(results)
            remaining = (len(campaigns) - len(results)) * avg_time
            
            print(f" Progress saved: {temp_path}")
            print(f"     {len(results)}/{len(campaigns)} | Avg: {avg_time:.1f}s/campaign")
            print(f"     Elapsed: {elapsed} | ETA: {timedelta(seconds=int(remaining))}")
            print()
    
    driver.quit()
    print("\n✓ Browser closed")

    if results:
        df = pd.DataFrame(results)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output = config.PROCESSED_DATA_PATH + f'kitabisa_with_profile_{len(results)}_{timestamp}.csv'
        df.to_csv(output, index=False, encoding='utf-8')
        
        elapsed = datetime.now() - start_time
        
        print("\n" + "="*80)
        print("SCRAPING COMPLETE!")
        print("="*80)
        print(f"Success: {len(results)}/{len(campaigns)} ({len(results)/len(campaigns)*100:.0f}%)")
        print(f"Time: {elapsed}")
        print(f"Avg: {elapsed.total_seconds()/len(results):.1f}s per campaign")
        print(f"\nOutput: {output}")
        print("="*80)
        
        # Detailed stats
        print(f"\n TRANSPARENCY INDICATORS (Pre-NER):")
        print(f"{'Indicator':<30} {'Count':<8} {'Percentage':<10}")
        print("-" * 50)
        
        ind_stats = {
            'Ind 1a (Profile)': df['ind1_has_profile'].sum(),
            'Ind 1b (Contact - Direct)': df['ind1_has_contact_direct'].sum(),
            'Ind 1c (Legal Verification)': df['ind1_has_legal'].sum(),
            'Ind 2 (Mission)': df['ind2_has_mission'].sum(),
            'Ind 3 (Fund Report)': df['ind3_has_fund_report'].sum(),
            'Ind 4 (Updates)': df['ind4_has_updates'].sum(),
            'Ind 5 (Disbursement)': df['ind5_has_disbursement'].sum(),
            'Ind 6 (Admin Fee)': df['ind6_has_admin_fee'].sum(),
            'Ind 7 (Anonymity)': df['ind7_has_anonymity'].sum(),
            'Ind 8 (Transaction ID)': df['ind8_has_transaction_id'].sum(),
        }
        
        for name, count in ind_stats.items():
            pct = (count / len(results)) * 100
            print(f"{name:<30} {count:<8} {pct:>6.1f}%")
        
        print("-" * 50)
        print(f"{'AVERAGE (Pre-NER)':<30} {df['total_indicators_detected'].mean():<8.1f} {df['total_indicators_detected'].mean()/8*100:>6.1f}%")
  
        print(f"\n Profile Description Stats:")
        desc_lengths = df['organizer_description'].str.len()
        has_desc = (desc_lengths > 0).sum()
        print(f"  Has description: {has_desc}/{len(df)} ({has_desc/len(df)*100:.1f}%)")
        print(f"  Avg length: {desc_lengths.mean():.0f} chars")
        print(f"  Max length: {desc_lengths.max():.0f} chars")
        
        if failed_nos:
            print(f"\n  Gagal ({len(failed_nos)} kampanye): no. {failed_nos}")
            failed_path = config.PROCESSED_DATA_PATH + f'scrape_failed_{timestamp}.txt'
            with open(failed_path, 'w') as f:
                f.write('\n'.join(str(n) for n in failed_nos))
            print(f"   → Simpan ke: {failed_path}")
            print(f"   → Jalankan ulang 08 dengan file custom yang hanya berisi URL yang gagal ini")

        print("\n" + "="*80)
        print("="*80)
        
    else:
        print("\n  No results - semua blocked/failed")

if __name__ == "__main__":
    main()