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
    cloudflare_keywords = [
        "Melakukan verifikasi keamanan",
        "Enable JavaScript and cookies to continue",
        "Checking your browser",
        "Just a moment",
        "Please wait"
    ]
    
    for keyword in cloudflare_keywords:
        if keyword in page_source:
            return True
    return False
    
def init_stealth_driver():
    
    options = Options()
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    options.add_argument("--start-maximized")
    
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
    
    return driver

def scrape_campaign_story(driver, campaign_url, max_retries=3):
    
    for attempt in range(max_retries):
        try:
            story_url = f"{campaign_url}/story"
            driver.get(story_url)
            time.sleep(5)
            
            # CHECK FOR CLOUDFLARE
            if is_cloudflare_blocked(driver.page_source):
                print(f" Cloudflare detected (attempt {attempt + 1}/{max_retries})")
                
                if attempt < max_retries - 1:
                    wait_time = random.uniform(30, 60)
                    print(f" Waiting {wait_time:.0f}s before retry...")
                    time.sleep(wait_time)
                    continue
                else:
                    print(f" Cloudflare blocked after {max_retries} attempts")
                    return "CLOUDFLARE_BLOCKED"
            
            soup = BeautifulSoup(driver.page_source, 'html.parser')
            story_div = soup.find('div', {'data-testid': 'campaign-section-fundraising-story'})
            
            if not story_div:
                story_div = soup.find('div', class_=re.compile(r'story|narrative|content'))
            
            if story_div:
                for img in story_div.find_all('img'):
                    img.decompose()
                
                story_text = story_div.get_text(strip=True, separator=' ')
                
                # Double-check story is not Cloudflare message
                if is_cloudflare_blocked(story_text):
                    print(f" Story contains Cloudflare text")
                    if attempt < max_retries - 1:
                        time.sleep(random.uniform(30, 60))
                        continue
                    return "CLOUDFLARE_BLOCKED"
                
                return story_text[:5000]
            else:
                return ""
                
        except Exception as e:
            print(f"      Error: {str(e)[:50]}")
            if attempt < max_retries - 1:
                time.sleep(10)
                continue
            return f"ERROR: {str(e)[:50]}"
    
    return "CLOUDFLARE_BLOCKED"

def scrape_latest_news(driver, campaign_url, update_count):
   
    try:
        if not update_count or str(update_count) == "0":
            return "[]"
        
        # Parse update count
        try:
            count_int = int(str(update_count))
        except:
            count_int = 0
        
        # SKIP very large campaigns
        if count_int > 20:
            print(f" SKIPPED: {count_int} updates (>20)")
            return json.dumps([{"note": f"Skipped: {count_int} updates, handle separately"}], ensure_ascii=False)
        
        news_url = f"{campaign_url}/latest-news"
        driver.get(news_url)
        time.sleep(5)
        
        updates = []
        
        try:

            print(f"      Scrolling to load all {count_int} updates...")
            for scroll in range(3):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
            
            buttons = driver.find_elements(By.XPATH, "//button[.//span[contains(text(), 'Selengkapnya')]]")
            print(f"      Found {len(buttons)} 'Selengkapnya' buttons")
            
            for idx in range(len(buttons)):
                try:
                    buttons = driver.find_elements(By.XPATH, "//button[.//span[contains(text(), 'Selengkapnya')]]")
                    
                    if idx >= len(buttons):
                        break
                    
                    button = buttons[idx]
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", button)
                    time.sleep(0.5)
                    button.click()
                    print(f"        Opened modal {idx+1}/{len(buttons)}")
                    time.sleep(2)
                    
                    soup = BeautifulSoup(driver.page_source, 'html.parser')
                    
                    modal_body = soup.find('div', {'data-testid': 'latest-news-body-text'})
                    
                    if modal_body:
                        for img in modal_body.find_all('img'):
                            img.decompose()
                        
                        content = modal_body.get_text(strip=True, separator=' ')

                        import re
                        parent = modal_body.find_parent('div', class_=re.compile(r'flex.*flex-col'))
                        title = ""
                        if parent:
                            title_elem = parent.find('h1')
                            title = title_elem.get_text(strip=True) if title_elem else ""
                        
                        if content and len(content) > 50:
                            updates.append({
                                'title': title,
                                'content': content[:3000]
                            })
                            print(f"          ✓ Extracted: {title[:40]}")
                    
                    try:
                        close_buttons = driver.find_elements(By.XPATH, "//button[contains(text(), 'Tutup')]")
                        if close_buttons:
                            close_buttons[0].click()
                            time.sleep(1)
                            print(f"          Closed modal")
                    except:
                        # If can't close, press ESC key
                        from selenium.webdriver.common.keys import Keys
                        driver.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
                        time.sleep(1)
                
                except Exception as e:
                    print(f" Error on update {idx+1}: {str(e)[:50]}")
                    try:
                        from selenium.webdriver.common.keys import Keys
                        driver.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
                        time.sleep(1)
                    except:
                        pass
            
            print(f"      Total extracted: {len(updates)} news items")
            
        except Exception as e:
            print(f" Error: {str(e)[:80]}")
        
        return json.dumps(updates, ensure_ascii=False)
        
    except Exception as e:
        return json.dumps([{"error": str(e)}], ensure_ascii=False)

def scrape_disbursement_details(driver, campaign_url, disbursement_count):

    try:
        disbursement_url = f"{campaign_url}/pencairan-dana"
        driver.get(disbursement_url)
        time.sleep(5)  # tunggu lebih lama untuk JS render

        for _ in range(3):
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)

        last_count = 0
        for _ in range(3):
            soup_temp = BeautifulSoup(driver.page_source, 'html.parser')
            current_count = len(soup_temp.find_all('div', {'data-testid': 'list-history-disbursement'}))
            if current_count == last_count and current_count > 0:
                break
            last_count = current_count
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)

        time.sleep(2)
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        disb_items = soup.find_all('div', {'data-testid': 'list-history-disbursement'})

        if len(disb_items) == 0:
            print(f"      No disbursements found (selector: list-history-disbursement)")
            return "no disbursement"

        print(f"      Found {len(disb_items)} disbursement items")

        disbursements = []
        for item in disb_items:
            date_elem  = item.find('span', {'data-testid': 'text-keterangan-waktu'})
            title_elem = item.find('h1',   {'data-testid': 'text-history-title-disbursement'})
            plan_elem  = item.find('div',  {'data-testid': 'text-history-plan-disbursement'})

            date_text = date_elem.get_text(strip=True)  if date_elem  else ""
            title     = title_elem.get_text(strip=True) if title_elem else ""
            plan      = plan_elem.get_text(strip=True)  if plan_elem  else ""

            amount = ""
            if title:
                amount_match = re.search(r'Rp\s*[\d.,]+', title)
                amount = amount_match.group() if amount_match else ""

            if title or plan:
                disbursements.append({
                    'date': date_text,
                    'amount': amount,
                    'plan': plan[:2000]
                })

        if not disbursements:
            return "no disbursement"

        return json.dumps(disbursements, ensure_ascii=False)

    except Exception as e:
        return json.dumps([{"error": str(e)}], ensure_ascii=False)

def extend_campaign_data(driver, row, skip_story=False, skip_news=False, skip_disb=False):
 
    try:
        url = row['url']
        slug = row['slug']
        update_count = row.get('update_count', '0')
        disbursement_count = row.get('disbursement_count', '0')

        print(f"  Processing: {slug[:50]}")

        delay = random.uniform(10, 20)
        time.sleep(delay)

        new_data = {}

        # 1. Campaign Story
        if skip_story:
            new_data['campaign_story'] = row.get('campaign_story', '')
            print(f"    📖 Story: dilewati (sudah ada)")
        else:
            print(f"    📖 Story...")
            new_data['campaign_story'] = scrape_campaign_story(driver, url)
            print(f"      ✓ {len(new_data['campaign_story'])} chars")

        # 2. Latest News
        if skip_news:
            new_data['latest_news_json'] = row.get('latest_news_json', '[]')
            print(f"    📰 News: dilewati (sudah ada)")
        elif str(update_count) != "0" and update_count:
            print(f"    📰 News ({update_count} updates)...")
            new_data['latest_news_json'] = scrape_latest_news(driver, url, update_count)
        else:
            new_data['latest_news_json'] = "no updates"
            print(f"      - Tidak ada update")

        # 3. Disbursement
        if skip_disb:
            new_data['disbursement_json'] = row.get('disbursement_json', '[]')
            print(f"    💰 Disbursement: dilewati (sudah ada)")
        elif str(disbursement_count) != "0" and disbursement_count:
            print(f"    💰 Disbursements ({disbursement_count})...")
            new_data['disbursement_json'] = scrape_disbursement_details(driver, url, disbursement_count)
        else:
            new_data['disbursement_json'] = "no disbursement"
            print(f"      - Tidak ada disbursement")

        return new_data

    except Exception as e:
        print(f"    ✗ Error: {str(e)[:80]}")
        return {
            'campaign_story': row.get('campaign_story', ''),
            'latest_news_json': row.get('latest_news_json', '[]'),
            'disbursement_json': row.get('disbursement_json', '[]')
        }

def main():
    
    print("""
Ekstrak Story, Latest News, dan Disbursement dari kampanye Kitabisa.
""")
    
    input_path = input("Path file CSV input (kosongkan untuk default: with_profile_temp_100.csv): ").strip()
    if input_path:
        if not os.path.isabs(input_path):
            input_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), input_path)
        input_file = input_path
    else:
        input_file = config.PROCESSED_DATA_PATH + 'with_profile_temp_100.csv'

    print(f"\nLoading: {input_file}")
    df = pd.read_csv(input_file)

    for col in ['latest_news_json', 'disbursement_json', 'campaign_story']:
        if col in df.columns:
            df[col] = df[col].astype(object)

    if 'description' in df.columns:
        if 'campaign_story' not in df.columns:
            df['campaign_story'] = df['description']
        else:
            mask = df['campaign_story'].isna() | (df['campaign_story'] == "")
            df.loc[mask, 'campaign_story'] = df.loc[mask, 'description']
        df.drop(columns=['description'], inplace=True)

    for col, default in [('campaign_story', ""), ('latest_news_json', "[]"), ('disbursement_json', "[]")]:
        if col not in df.columns:
            df[col] = default

    def perlu_scrape(row):
        ind4 = str(row.get('ind4_has_updates', 'False')).lower() in ['true', '1']
        ind5 = str(row.get('ind5_has_disbursement', 'False')).lower() in ['true', '1']
        news = str(row.get('latest_news_json', '[]'))
        disb = str(row.get('disbursement_json', '[]'))
        return (ind4 and news in ['[]', '', 'nan', 'None']) or \
               (ind5 and disb in ['[]', '', 'nan', 'None'])

    n_perlu = df.apply(perlu_scrape, axis=1).sum()
    print(f"✓ Total: {len(df)} kampanye")
    print(f"  Perlu scrape news/disbursement: {n_perlu} kampanye\n")

    start_no = int(input("Mulai dari no kampanye: ").strip())
    jumlah   = int(input("Scrape berapa kampanye : ").strip())
    df_to_process = df[df['no'] >= start_no].head(jumlah)
    print(f"\n✓ Akan scrape {len(df_to_process)} kampanye (no. {df_to_process['no'].min()} - {df_to_process['no'].max()})")

    # Confirm
    confirm = input("\nProceed? (y/n): ").strip().lower()
    if confirm != 'y':
        print("Cancelled.")
        return

    # Init driver
    print("\nInitializing Chrome...")
    driver = init_stealth_driver()
    print("✓ Ready\n")

    # Process
    print(f"Processing {len(df_to_process)} campaigns...")
    print("="*80 + "\n")

    start_time = datetime.now()
    
    processed_count = 0
    
    for idx, row in df_to_process.iterrows():
        print(f"[{idx + 1}/{len(df)}] Campaign #{row['no']}")

        existing_news = str(row.get('latest_news_json', '[]'))
        existing_disb = str(row.get('disbursement_json', '[]'))
        existing_story = str(row.get('campaign_story', ''))

        news_done  = existing_news  not in ['[]', '', 'nan', 'None']
        disb_done  = existing_disb  not in ['[]', '', 'nan', 'None']
        story_done = existing_story not in ['',  'nan', 'None', 'CLOUDFLARE_BLOCKED']

        # Cek apakah kampanye ini perlu di-scrape
        ind4 = str(row.get('ind4_has_updates', 'False')).lower() in ['true', '1']
        ind5 = str(row.get('ind5_has_disbursement', 'False')).lower() in ['true', '1']

        need_news = ind4 and not news_done
        need_disb = ind5 and not disb_done

        # Skip kalau tidak ada yang perlu di-scrape
        if not need_news and not need_disb:
            print(f"  ✓ Tidak ada yang perlu di-scrape, dilewati\n")
            continue

        print(f"     → Perlu: {'news ' if need_news else ''}{'disbursement' if need_disb else ''}")

        new_data = extend_campaign_data(
            driver, row,
            skip_story=True,          # story selalu skip (sudah ada)
            skip_news=not need_news,  # skip news kalau sudah ok
            skip_disb=not need_disb   # skip disb kalau sudah ok
        )

        
        if new_data['campaign_story'] == "CLOUDFLARE_BLOCKED":
            print(f"  🚨 CLOUDFLARE BLOCKED - Marked for later retry\n")
            df.at[idx, 'campaign_story'] = "CLOUDFLARE_BLOCKED"
            df.at[idx, 'latest_news_json'] = "[]"
            df.at[idx, 'disbursement_json'] = "[]"
            with open(config.PROCESSED_DATA_PATH + 'cloudflare_blocked.txt', 'a') as f:
                f.write(f"{row['no']},{row['slug']},{row['url']}\n")
            processed_count += 1
            print()
            continue

        # Normal update
        df.at[idx, 'campaign_story'] = new_data['campaign_story']
        df.at[idx, 'latest_news_json'] = new_data['latest_news_json']
        df.at[idx, 'disbursement_json'] = new_data['disbursement_json']
        
        processed_count += 1
        print()
        
        
        if processed_count % 10 == 0:
            temp_path = config.PROCESSED_DATA_PATH + f'extended_temp_{idx+1}.csv'
            df.to_csv(temp_path, index=False, encoding='utf-8')
            
            elapsed = datetime.now() - start_time
            avg_time = elapsed.total_seconds() / processed_count
            remaining_rows = len(df_to_process) - processed_count
            eta = timedelta(seconds=int(remaining_rows * avg_time))
            
            print(f" Progress saved: {temp_path}")
            print(f"     {processed_count}/{len(df_to_process)} | Avg: {avg_time:.1f}s | ETA: {eta}")
            print()
    
    driver.quit()
    print("\n✓ Browser closed")
    
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    output_file = config.PROCESSED_DATA_PATH + f'kitabisa_complete_FINAL_{len(df)}_{timestamp}.csv'
    df.to_csv(output_file, index=False, encoding='utf-8')
    
    elapsed = datetime.now() - start_time
    
    print("\n" + "="*80)
    print("EXTENSION COMPLETE!")
    print("="*80)
    print(f"Total campaigns in dataset: {len(df)}")
    print(f"Processed in this run: {processed_count}")
    print(f"Time: {elapsed}")
    print(f"\nOutput: {output_file}")
    print("="*80)
    
    print(f"\n CONTENT EXTRACTION RESULTS:")
    print("="*80)
    
    # Story (all campaigns should have)
    story_filled = (df['campaign_story'].str.len() > 0).sum()
    story_not_scraped = (df['campaign_story'] == "").sum()
    print(f"\nCampaign Story:")
    print(f"  Extracted: {story_filled}/{len(df)} ({story_filled/len(df)*100:.1f}%)")
    if story_not_scraped > 0:
        print(f"  Not yet scraped: {story_not_scraped}")
    
    
    has_updates = df['update_count'].apply(lambda x: str(x) != "0" and pd.notna(x)).sum()
    news_extracted = df['latest_news_json'].apply(lambda x: x not in ["[]", "no updates"] and '"note"' not in str(x)).sum()
    news_no_data = (df['latest_news_json'] == "no updates").sum()
    news_not_scraped = (df['latest_news_json'] == "[]").sum()
    news_skipped = df['latest_news_json'].apply(lambda x: '"note"' in str(x)).sum()
    
    print(f"\nLatest News:")
    print(f"  Campaigns with updates expected: {has_updates}")
    if has_updates > 0:
        news_success = news_extracted / has_updates * 100
        print(f"  Successfully extracted: {news_extracted}/{has_updates} ({news_success:.1f}%)")
    print(f"  No updates (as expected): {news_no_data}")
    if news_skipped > 0:
        print(f"  Skipped (>20 updates): {news_skipped}")
    if news_not_scraped > 0:
        print(f"  Not yet scraped: {news_not_scraped}")
    
    
    has_disb = df['disbursement_count'].apply(lambda x: str(x) != "0" and pd.notna(x)).sum()
    disb_extracted = df['disbursement_json'].apply(lambda x: x not in ["[]", "no disbursement"]).sum()
    disb_no_data = (df['disbursement_json'] == "no disbursement").sum()
    disb_not_scraped = (df['disbursement_json'] == "[]").sum()
    
    print(f"\nDisbursement:")
    print(f"  Campaigns with disbursement expected: {has_disb}")
    if has_disb > 0:
        disb_success = disb_extracted / has_disb * 100
        print(f"  Successfully extracted: {disb_extracted}/{has_disb} ({disb_success:.1f}%)")
    print(f"  No disbursement (as expected): {disb_no_data}")
    if disb_not_scraped > 0:
        print(f"  Not yet scraped: {disb_not_scraped}")
    
    blocked = (df['campaign_story'] == "CLOUDFLARE_BLOCKED").sum()
    if blocked > 0:
        print(f"\n🚨 Cloudflare blocked: {blocked} campaigns")
        print(f"     List saved to: cloudflare_blocked.txt")
        print(f"     These need manual retry or different approach")

    print("="*80)
    print("="*80)

if __name__ == "__main__":
    main()