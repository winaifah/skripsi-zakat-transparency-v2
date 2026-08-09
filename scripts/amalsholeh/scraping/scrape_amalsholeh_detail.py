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
    """Scrape main campaign page"""
    
    print(f"\n Main page...")
    driver.get(url)
    time.sleep(5)
    
    try:
        selengkapnya_stats = driver.find_element(By.XPATH, "//button[contains(text(), 'Selengkapnya')]")
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", selengkapnya_stats)
        time.sleep(0.5)
        selengkapnya_stats.click()
        time.sleep(2)
    except:
        pass
    
    soup = BeautifulSoup(driver.page_source, 'html.parser')
    
    data = {
        'url': url,
        'slug': slug,
        'scraped_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }
    
    stats_div = soup.find('div', class_=lambda x: x and 'bg-slate-50' in str(x))
    
    if stats_div:
        # Collected amount
        collected_div = stats_div.find('div', class_=lambda x: x and 'text-lg' in str(x))
        if collected_div:
            text_lg = collected_div.get_text()
            
            if 'dari' in text_lg:
                parts = text_lg.split('dari')
                collected_part = parts[0]
                target_part = parts[1] if len(parts) > 1 else ""
                
                collected_match = re.search(r'Rp\s*([\d.,]+)', collected_part)
                target_match = re.search(r'Rp\s*([\d.,]+)', target_part)
                
                data['collected_amount'] = collected_match.group(1) if collected_match else ""
                data['target_amount'] = target_match.group(1) if target_match else ""
            else:
                collected_match = re.search(r'Rp\s*([\d.,]+)', text_lg)
                data['collected_amount'] = collected_match.group(1) if collected_match else ""
                data['target_amount'] = "no_target"
        
        # Donor count
        stats_html = str(stats_div)
        donor_match = re.search(r'<strong>(\d+(?:\.\d+)?)</strong>\s*Donatur', stats_html, re.IGNORECASE)
        if donor_match:
            data['donor_count'] = donor_match.group(1)
        else:
            donatur_text = stats_div.find(string=re.compile(r'Donatur', re.I))
            if donatur_text:
                parent = donatur_text.find_parent('div')
                if parent:
                    strong = parent.find('strong')
                    if strong:
                        donor_text = strong.get_text(strip=True)
                        if 'rp' not in donor_text.lower() and len(donor_text) < 10:
                            data['donor_count'] = donor_text
        
        # Days left
        days_div = stats_div.find('div', class_='flex-shrink-0')
        if days_div:
            days_text = days_div.get_text(strip=True)
            if '∞' in days_text:
                data['days_left'] = "unlimited"
            elif 'hari' in days_text.lower():
                days_match = re.search(r'(\d+)', days_text)
                data['days_left'] = days_match.group(1) if days_match else days_text
            else:
                data['days_left'] = days_text
    
    print(f"    Stats: Collected={data.get('collected_amount', '?')} | Target={data.get('target_amount', '?')} | Donors={data.get('donor_count', '?')} | Days={data.get('days_left', '?')}")
    
    # 2. Organizer info
    info_lembaga_h3 = soup.find('h3', string=re.compile(r'Info Lembaga'))
    
    if info_lembaga_h3:
        parent_section = info_lembaga_h3.find_parent('div')
        if parent_section:
            organizer_div = parent_section.find('div', class_='flex items-center cursor-pointer')
            
            if organizer_div:
                org_h3 = organizer_div.find('h3', class_=lambda x: x and 'font-semibold' in str(x))
                data['organizer'] = org_h3.get_text(strip=True) if org_h3 else ""
                
                verification = organizer_div.find('div', string=re.compile(r'Akun Terverifikasi'))
                data['ind1_has_legal'] = verification is not None
        
        # Click to get profile URL
        try:
            info_lembaga_clickable = driver.find_element(By.XPATH, "//h3[contains(text(), 'Info Lembaga')]/following-sibling::div[contains(@class, 'cursor-pointer')]")
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", info_lembaga_clickable)
            time.sleep(0.5)
            info_lembaga_clickable.click()
            time.sleep(2)
            
            current_url = driver.current_url
            if '/lembaga/' in current_url:
                data['profile_url'] = current_url
                print(f"    Profile URL: {current_url}")
            
        except Exception as e:
            print(f"    ⚠️ Could not click Info Lembaga: {str(e)[:50]}")
    
    print(f"    Organizer: {data.get('organizer', '?')} | Legal: {data.get('ind1_has_legal', False)}")
    
    # 3. Go back for description
    driver.get(url)
    time.sleep(3)
    
    try:
        story_btn = driver.find_element(By.XPATH, "//h3[contains(text(), 'Tentang program')]/following-sibling::div//button[contains(text(), 'Selengkapnya')]")
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", story_btn)
        time.sleep(0.5)
        story_btn.click()
        time.sleep(2)
    except:
        pass
    
    soup = BeautifulSoup(driver.page_source, 'html.parser')
    
    story_section = soup.find('h3', string=re.compile(r'Tentang program'))
    if story_section:
        content_div = story_section.find_next('div', class_='content')
        if content_div:
            for img in content_div.find_all('img'):
                img.decompose()
            
            description = content_div.get_text(strip=True, separator=' ')
            data['description'] = description
            data['ind2_word_count'] = len(description.split())
            data['ind2_has_mission'] = len(description) > 100
    
    print(f"    Description: {data.get('ind2_word_count', 0)} words")
    
    # 4. Admin fee
    admin_fee = soup.find('span', string=re.compile(r'Rincian penggunaan dana'))
    data['ind6_has_admin_fee'] = admin_fee is not None
    
    # 5. News URL
    news_section = soup.find('div', id='news')
    if news_section:
        lihat_semua = news_section.find('a', href=re.compile(r'/news'))
        if lihat_semua:
            news_href = lihat_semua.get('href')
            data['news_url'] = 'https://www.amalsholeh.com' + news_href
    
    # 6. Always available
    data['ind3_has_fund_report'] = True
    data['ind7_has_anonymity'] = True
    data['ind8_has_transaction_id'] = False
    
    return data

def scrape_organizer(driver, profile_url):
    """Scrape organizer profile"""
    
    print(f"    👥 Organizer profile...")
    driver.get(profile_url)
    time.sleep(4)
    
    soup = BeautifulSoup(driver.page_source, 'html.parser')
    
    data = {}
    
    # Description
    tentang_section = soup.find('div', string=re.compile(r'Tentang'))
    if tentang_section:
        desc_div = tentang_section.find_next('div', class_=lambda x: x and 'text-center' in str(x))
        if desc_div:
            data['organizer_description'] = desc_div.get_text(strip=True)
    
    # LOWERED THRESHOLD: 30 chars instead of 50
    data['ind1_has_profile'] = len(data.get('organizer_description', '')) > 30
    
    # Social media platforms
    social_links = soup.find_all('a', href=True, target='_blank')
    platforms = []
    
    for link in social_links:
        href = link.get('href', '').lower()
        
        if 'facebook.com' in href:
            platforms.append('Facebook')
        elif 'instagram.com' in href:
            platforms.append('Instagram')
        elif 'twitter.com' in href or 'x.com' in href:
            platforms.append('Twitter')
        elif 'tiktok.com' in href:
            platforms.append('TikTok')
        elif 'youtube.com' in href:
            platforms.append('YouTube')
        elif 'linkedin.com' in href:
            platforms.append('LinkedIn')
    
    platforms = list(set(platforms))
    
    data['contact_platforms'] = ', '.join(platforms) if platforms else ""
    data['ind1_has_contact_direct'] = len(platforms) > 0
    
    print(f"      Profile: {data['ind1_has_profile']} | Platforms: {data.get('contact_platforms', 'none')}")
    
    return data

def scrape_news(driver, news_url):
    
    print(f" News + Disbursement...")
    driver.get(news_url)
    time.sleep(4)
    
    soup = BeautifulSoup(driver.page_source, 'html.parser')
    news_items = soup.find_all('div', class_='news-item')
    
    print(f"Found {len(news_items)} items")
    
    if len(news_items) == 0:
        return {
            'latest_news_json': json.dumps([], ensure_ascii=False),
            'update_count': 0,
            'ind4_has_updates': False,
            'disbursement_json': json.dumps([], ensure_ascii=False),
            'disbursement_count': 0,
            'ind5_has_disbursement': False
        }

    clicked = 0
    for idx in range(min(len(news_items), 20)):
        try:
            buttons = driver.find_elements(By.XPATH, "//button[contains(text(), 'Baca Selengkapnya')]")
            if idx < len(buttons):
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", buttons[idx])
                time.sleep(0.2)
                buttons[idx].click()
                clicked += 1
                time.sleep(0.3)
        except:
            pass
    
    time.sleep(2)
    soup = BeautifulSoup(driver.page_source, 'html.parser')
    news_items = soup.find_all('div', class_='news-item')
    
    all_news = []
    disbursements = []
    
    for item in news_items:
        date_elem = item.find('p', class_=lambda x: x and 'text-gray-600' in str(x))
        date_text = date_elem.get_text(strip=True) if date_elem else ""
        
        title_elem = item.find('p', class_=lambda x: x and 'font-semibold' in str(x))
        title = title_elem.get_text(strip=True) if title_elem else ""
        
        content_div = item.find('div', class_='content')
        content = ""
        if content_div:
            for img in content_div.find_all('img'):
                img.decompose()
            content = content_div.get_text(strip=True, separator=' ')
        
        amount = ""
        is_disbursement = False
        
        if 'pencairan dana' in title.lower():
            is_disbursement = True
            amount_match = re.search(r'Rp\s*([\d.,]+)', title)
            amount = amount_match.group(1) if amount_match else ""
        
        if content:
            news_item = {
                'date': date_text,
                'title': title,
                'amount': amount,
                'content': content[:1000]
            }
            
            all_news.append(news_item)
            
            if is_disbursement:
                disbursements.append(news_item)
    
    print(f"      Updates: {len(all_news)} | Disbursement: {len(disbursements)}")
    
    return {
        'latest_news_json': json.dumps(all_news, ensure_ascii=False),
        'update_count': len(all_news),
        'ind4_has_updates': len(all_news) > 0,
        'disbursement_json': json.dumps(disbursements, ensure_ascii=False),
        'disbursement_count': len(disbursements),
        'ind5_has_disbursement': len(disbursements) > 0
    }

def main():
    print("="*80)
    print("AMALSHOLEH DETAILED SCRAPER")
    print("="*80)

    import os, sys
    parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    default_urls = os.path.join(parent_dir, 'data', 'raw', 'amalsholeh_zakat_urls.csv')
    print(f"\nURL file: {default_urls}")
    custom = input("Pakai file URL lain? (Enter = default, atau ketik path): ").strip()
    url_file = custom if custom else default_urls
    df_urls = pd.read_csv(url_file)
    print(f"✓ Total URLs: {len(df_urls)}\n")

    print(f"  Kampanye tersedia: 1 - {len(df_urls)}")
    start = int(input("Mulai dari kampanye no. (1-based, contoh: 11): ").strip())
    count = int(input("Scrape berapa kampanye?: ").strip())
    start_idx = start - 1 
    end_idx   = min(start_idx + count, len(df_urls))
    batch = df_urls.iloc[start_idx:end_idx]
    print(f"\n✓ Akan scrape {len(batch)} kampanye (no. {start} s/d {start_idx + len(batch)})\n")

    driver = init_driver()
    results = []

    for i, (idx, row) in enumerate(batch.iterrows()):
        campaign_no = start_idx + i + 1
        title_display = str(row.get('title', row.get('slug', 'N/A')))[:50]
        print(f"[{i+1}/{len(batch)}] No.{campaign_no} | {title_display}")

        try:
            main_data = scrape_main_campaign(driver, row['url'], row['slug'])
            main_data['no'] = campaign_no
            main_data['title'] = row.get('title', '')
            main_data['platform'] = 'amalsholeh.com'

            if main_data.get('profile_url'):
                org_data = scrape_organizer(driver, main_data['profile_url'])
                main_data.update(org_data)

            if main_data.get('news_url'):
                news_data = scrape_news(driver, main_data['news_url'])
                main_data.update(news_data)

            indicator_cols = [col for col in main_data.keys() if col.startswith('ind')]
            total_detected = sum(1 for col in indicator_cols if main_data.get(col) == True)
            main_data['total_indicators_detected'] = total_detected

            results.append(main_data)
            print(f"  ✓ {total_detected} indikator\n")

            time.sleep(2)

        except Exception as e:
            print(f" Error: {str(e)[:100]}\n")

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
        'contact_platforms'
    ]

    df = pd.DataFrame(results)
    for col in column_order:
        if col not in df.columns:
            df[col] = None
    df = df[[c for c in column_order if c in df.columns]]

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    out_dir = os.path.join(parent_dir, 'data', 'processed')
    output_file = os.path.join(out_dir, f'amalsholeh_details_{start}_{start_idx+len(results)}_{timestamp}.csv')
    df.to_csv(output_file, index=False, encoding='utf-8')

    print("\n" + "="*80)
    print("SCRAPING COMPLETE!")
    print("="*80)
    print(f"Berhasil : {len(results)}/{len(batch)}")
    print(f"Output   : {output_file}")

    print("\n INDICATOR COVERAGE:")
    for col in column_order:
        if col.startswith('ind') and col in df.columns:
            count = df[col].sum() if df[col].dtype == bool else df[col].astype(str).isin(['True','true','1']).sum()
            print(f"  {col}: {count}/{len(df)}")

    print("="*80)

if __name__ == "__main__":
    main()