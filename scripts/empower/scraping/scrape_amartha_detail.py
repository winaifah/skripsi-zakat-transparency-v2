from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
from selenium_stealth import stealth
from bs4 import BeautifulSoup
import pandas as pd
import time
import re
import json
from datetime import datetime

def init_driver():
    options = Options()
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    
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

def scrape_main_campaign(driver, url, slug):  
    print(f"\n Main page...")
    driver.get(url)
    time.sleep(5)
    
    soup = BeautifulSoup(driver.page_source, 'html.parser')
    
    data = {
        'url': url,
        'slug': slug,
        'scraped_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }
    
    # 1. Title
    title_h1 = soup.find('h1', class_='title')
    data['title'] = title_h1.get_text(strip=True) if title_h1 else ""
    
    # 2. Verification
    verified = soup.find('span', string=re.compile(r'Campaign ini sudah terverifikasi'))
    data['ind1_has_legal'] = verified is not None
    
    # 3. Organizer name
    medicator = soup.find('span', class_='medicator')
    data['organizer'] = medicator.get_text(strip=True) if medicator else ""
    
    # 4. Donor count
    donors_item = soup.find('div', class_='item donors')
    if donors_item:
        donor_span = donors_item.find('span', class_='font-700')
        if donor_span:
            data['donor_count'] = donor_span.get_text(strip=True)
    
    # 5. Days left
    time_item = soup.find('div', class_=lambda x: x and 'item' in x and 'time' in x)
    if time_item:
        digit = time_item.find('span', class_='font-700')
        if digit:
            data['days_left'] = digit.get_text(strip=True)
    
    # 6. Collected & Target 
    # Find by searching for "Terdanai" text
    terdanai_label = soup.find('span', string=re.compile(r'Terdanai'))
    if terdanai_label:
        funded_div = terdanai_label.find_parent('div', class_='funded')
        if funded_div:
            digit_span = funded_div.find('span', class_='digit')
            if digit_span:
                collected_text = digit_span.get_text(strip=True)
                collected_match = re.search(r'Rp\s*([\d.,]+)', collected_text)
                if collected_match:
                    data['collected_amount'] = collected_match.group(1)
    
    # Find "Kekurangan" text
    kekurangan_label = soup.find('span', string=re.compile(r'Kekurangan'))
    if kekurangan_label:
        remaining_div = kekurangan_label.find_parent('div', class_=lambda x: x and 'remaining' in x)
        if remaining_div:
            digit_span = remaining_div.find('span', class_='digit')
            if digit_span:
                remaining_text = digit_span.get_text(strip=True)
                remaining_match = re.search(r'Rp\s*([\d.,]+)', remaining_text)
                if remaining_match:
                    remaining_amount = remaining_match.group(1)
                    
                    # Calculate target
                    if data.get('collected_amount') and remaining_amount:
                        try:
                            collected = float(data['collected_amount'].replace('.', '').replace(',', '.'))
                            remaining = float(remaining_amount.replace('.', '').replace(',', '.'))
                            target = collected + remaining
                            data['target_amount'] = f"{int(target):,}".replace(',', '.')
                        except Exception as e:
                            print(f"      ⚠️ Could not calculate target: {str(e)[:40]}")
    
    print(f"    Stats: Collected={data.get('collected_amount', '?')} | Target={data.get('target_amount', '?')} | Donors={data.get('donor_count', '?')} | Days={data.get('days_left', '?')}")
    
    # 7. Organizer Profile URL
    try:
        medicator_elem = driver.find_element(By.XPATH, "//span[@class='medicator']")
        parent_wrapper = medicator_elem.find_element(By.XPATH, "./ancestor::div[contains(@class, 'wrapper-medicator')][1]")
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", parent_wrapper)
        time.sleep(0.5)
        driver.execute_script("arguments[0].click();", parent_wrapper)
        time.sleep(2)
        
        profile_url = driver.current_url
        if '/campaigner/' in profile_url:
            data['profile_url'] = profile_url
            print(f"    Profile URL: {profile_url}")
    except Exception as e:
        print(f"    ⚠️ Could not get profile URL: {str(e)[:50]}")
    
    # 8. Go back
    driver.get(url)
    time.sleep(3)
    
    # 9. Description (Kisah)
    try:
        lihat_lebih = driver.find_element(By.XPATH, "//div[contains(text(), 'Lihat Lebih Banyak')]")
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", lihat_lebih)
        time.sleep(0.5)
        lihat_lebih.click()
        time.sleep(2)
    except:
        pass
    
    soup = BeautifulSoup(driver.page_source, 'html.parser')
    
    kisah_section = soup.find('h2', string=re.compile(r'Kisah'))
    if kisah_section:
        content_div = kisah_section.find_next('div', class_='content markdown')
        if content_div:
            for img in content_div.find_all('img'):
                img.decompose()
            
            description = content_div.get_text(strip=True, separator=' ')
            data['description'] = description
            data['ind2_word_count'] = len(description.split())
            data['ind2_has_mission'] = len(description) > 100
    
    print(f"    Description: {data.get('ind2_word_count', 0)} words")
    
    # 10. Admin fee
    alokasi = soup.find('h2', string=re.compile(r'Alokasi anggaran'))
    data['ind6_has_admin_fee'] = alokasi is not None
    
    # 11. Always available
    data['ind3_has_fund_report'] = True
    data['ind7_has_anonymity'] = True
    data['ind8_has_transaction_id'] = False
    
    return data

def scrape_organizer(driver, profile_url):
 
    print(f"    👥 Organizer profile...")
    driver.get(profile_url)
    time.sleep(4)
    
    soup = BeautifulSoup(driver.page_source, 'html.parser')
    
    data = {}
    
    # Biodata
    biodata_h2 = soup.find('h2', string=re.compile(r'Biodata'))
    if biodata_h2:
        desc_p = biodata_h2.find_next('p', class_='nobio')
        if desc_p:
            data['organizer_description'] = desc_p.get_text(strip=True)
    
    data['ind1_has_profile'] = len(data.get('organizer_description', '')) > 20
    
    data['ind1_has_contact_direct'] = False
    
    
    print(f"      Profile: {data['ind1_has_profile']} ({len(data.get('organizer_description', ''))} chars)")
    
    return data

def scrape_updates_and_disbursement(driver, url):

    print(f" Updates + Disbursement...")
    
    driver.get(url)
    time.sleep(3)
    
    # Click Update Campaign tab
    try:
        update_tab = driver.find_element(By.XPATH, "//li[contains(text(), 'Update Campaign')]")
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", update_tab)
        time.sleep(0.5)
        update_tab.click()
        time.sleep(3)
    except Exception as e:
        print(f"      ⚠️ Could not click Update tab: {str(e)[:50]}")
    
    # Click "Lihat lebih banyak" for updates
    for i in range(3):
        try:
            lihat_btn = driver.find_element(By.XPATH, "//button[contains(text(), 'Lihat lebih banyak')]")
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", lihat_btn)
            time.sleep(0.5)
            lihat_btn.click()
            time.sleep(2)
        except:
            break
    
    soup = BeautifulSoup(driver.page_source, 'html.parser')
    
    # Updates
    update_timelines = soup.find_all('div', class_='timeline')
    all_updates = []
    
    for timeline in update_timelines:
        date_div = timeline.find('div', class_='date')
        date_text = date_div.get_text(strip=True) if date_div else ""
        
        card = timeline.find('div', class_='card')
        if card:
            title_div = card.find('div', class_='title')
            title = title_div.get_text(strip=True) if title_div else ""
            
            desc_div = card.find('div', class_='desc markdown')
            content = ""
            if desc_div:
                for img in desc_div.find_all('img'):
                    img.decompose()
                content = desc_div.get_text(strip=True, separator=' ')[:1000]
            
            if content:
                all_updates.append({
                    'date': date_text,
                    'title': title,
                    'content': content
                })
    
    print(f"      Updates: {len(all_updates)}")
    
    # Disbursement - Click "Rincian Dana" tab
    try:
        rincian_tab = driver.find_element(By.XPATH, "//li[contains(text(), 'Rincian Dana')]")
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", rincian_tab)
        time.sleep(0.5)
        rincian_tab.click()
        time.sleep(3)
    except Exception as e:
        print(f"      ⚠️ Could not click Rincian tab: {str(e)[:50]}")
    
    # Click "Lihat lebih banyak" for disbursement
    for i in range(3):
        try:
            lihat_btn = driver.find_element(By.XPATH, "//button[contains(text(), 'Lihat lebih banyak')]")
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", lihat_btn)
            time.sleep(0.5)
            lihat_btn.click()
            time.sleep(2)
        except:
            break
    
    soup = BeautifulSoup(driver.page_source, 'html.parser')
    
    disbursement_timelines = soup.find_all('div', class_='timeline')
    all_disbursements = []
    
    for timeline in disbursement_timelines:
        date_div = timeline.find('div', class_='date')
        date_text = date_div.get_text(strip=True) if date_div else ""
        
        card = timeline.find('div', class_='card')
        if card:
            desc_div = card.find('div', class_='desc')
            description = desc_div.get_text(strip=True) if desc_div else ""
            
            amount_div = card.find('div', class_='amount')
            amount = ""
            if amount_div:
                green_amount = amount_div.find('div', class_='green-amount')
                if green_amount:
                    amount_text = green_amount.get_text()
                    amount_match = re.search(r'Rp\.([\d.,]+)', amount_text)
                    amount = amount_match.group(1) if amount_match else ""
            
            if description:
                all_disbursements.append({
                    'date': date_text,
                    'amount': amount,
                    'content': description[:1000]
                })
    
    print(f"      Disbursement: {len(all_disbursements)}")
    
    return {
        'latest_news_json': json.dumps(all_updates, ensure_ascii=False),
        'update_count': len(all_updates),
        'ind4_has_updates': len(all_updates) > 0,
        'disbursement_json': json.dumps(all_disbursements, ensure_ascii=False),
        'disbursement_count': len(all_disbursements),
        'ind5_has_disbursement': len(all_disbursements) > 0
    }

def main():
    print("="*80)
    print("AMARTHA EMPOWER DETAILED SCRAPER - FINAL")
    print("="*80)
    
    df_urls = pd.read_csv('amartha_zakat_urls.csv')
    
    print(f"\nTotal URLs: {len(df_urls)}")
    print(f"Scraping all {len(df_urls)} campaigns...\n")
    
    driver = init_driver()
    
    results = []
    
    for idx, row in df_urls.iterrows():
        print(f"[{idx+1}/{len(df_urls)}] {row['title'][:50]}")
        
        try:
            main_data = scrape_main_campaign(driver, row['url'], row['slug'])
            main_data['no'] = idx + 1
            main_data['title'] = row['title']
            main_data['platform'] = 'amartha.com'
            
            if main_data.get('profile_url'):
                org_data = scrape_organizer(driver, main_data['profile_url'])
                main_data.update(org_data)
            
            updates_data = scrape_updates_and_disbursement(driver, row['url'])
            main_data.update(updates_data)
            
            indicator_cols = [col for col in main_data.keys() if col.startswith('ind')]
            total_detected = sum(1 for col in indicator_cols if main_data.get(col) == True)
            main_data['total_indicators_detected'] = total_detected
            
            results.append(main_data)
            
            time.sleep(2)
            
        except Exception as e:
            print(f"  ❌ Error: {str(e)[:100]}")
    
    driver.quit()
    
    column_order = [
        'no', 'url', 'slug', 'platform', 'scraped_at', 'title', 'organizer',
        'collected_amount', 'target_amount', 'days_left', 
        'profile_url', 'organizer_description',
        'ind1_has_profile', 'ind1_has_contact_direct', 'ind1_has_legal',
        'ind2_has_mission', 'ind2_word_count', 'description',
        'ind3_has_fund_report', 'donor_count',
        'ind4_has_updates', 'update_count',
        'ind5_has_disbursement', 'disbursement_count',
        'ind6_has_admin_fee',
        'ind7_has_anonymity',
        'ind8_has_transaction_id',
        'total_indicators_detected',
        'latest_news_json', 'disbursement_json',
    ]
    
    df = pd.DataFrame(results)
    
    for col in column_order:
        if col not in df.columns:
            df[col] = None
    
    df = df[column_order]
    
    output_file = 'amartha_details.csv'
    df.to_csv(output_file, index=False, encoding='utf-8')
    
    print("\n" + "="*80)
    print("SCRAPING COMPLETE!")
    print("="*80)
    print(f"\nOutput: {output_file}")
    
    print("\n INDICATOR COVERAGE:")
    for col in column_order:
        if col.startswith('ind'):
            count = df[col].sum() if col in df.columns else 0
            print(f"  {col}: {count}/{len(df)}")
    
    print("\n" + "="*80)

if __name__ == "__main__":
    main()