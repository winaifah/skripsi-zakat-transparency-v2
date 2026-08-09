from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
from selenium_stealth import stealth
from bs4 import BeautifulSoup
import pandas as pd
import time

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

def collect_zakat_urls(driver):
    print("="*80)
    print("AMALSHOLEH - ZAKAT CATEGORY URL COLLECTION")
    print("="*80)
    
    zakat_url = "https://www.amalsholeh.com/zakat"
    
    driver.get(zakat_url)
    time.sleep(5)
    
    print("\nStep 1: Loading ALL campaigns...")
    
    clicked = 0
    while True:
        try:
            button = driver.find_element(By.XPATH, "//button[contains(text(), 'Tampilkan Lebih Banyak')]")
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", button)
            time.sleep(0.5)
            button.click()
            clicked += 1
            
            if clicked % 5 == 0:
                print(f"  Clicked {clicked} times...")
            
            time.sleep(2)
        except:
            print(f"  ✓ All campaigns loaded ({clicked} clicks)")
            break
 
    print(f"\nStep 2: Extracting campaign URLs...")
    
    soup = BeautifulSoup(driver.page_source, 'html.parser')
    
    campaign_links = soup.find_all('a', class_='absolute inset-0', href=True)
    
    print(f"  Found {len(campaign_links)} campaign links")
    
    campaigns = []
    seen_slugs = set()
    
    for link in campaign_links:
        href = link.get('href', '')
        
        clean_href = href.split('?')[0]
        slug = clean_href.strip('/')

        if slug in seen_slugs:
            continue
        seen_slugs.add(slug)
        
        title_span = link.find('span', class_='screen-reader-text')
        if title_span:
            title = title_span.get_text(strip=True)
        else:
            title = slug.replace('-', ' ').title()
        
        full_url = 'https://www.amalsholeh.com' + clean_href
        
        campaigns.append({
            'no': len(campaigns) + 1,
            'title': title,
            'url': full_url,
            'slug': slug,
            'platform': 'amalsholeh.com',
            'category': 'zakat'
        })
    
    print(f"  Extracted {len(campaigns)} unique campaigns")
    
    return campaigns

def main():
    driver = init_driver()
    
    campaigns = collect_zakat_urls(driver)
    
    driver.quit()
    
    if not campaigns:
        print("\n No campaigns found!")
        return
    
    df = pd.DataFrame(campaigns)
    output_file = 'amalsholeh_zakat_urls.csv'
    df.to_csv(output_file, index=False, encoding='utf-8')
    
    print("\n" + "="*80)
    print("ZAKAT URL COLLECTION COMPLETE!")
    print("="*80)
    print(f"\nTotal campaigns: {len(campaigns)}")
    print(f"Output file: {output_file}")
    
    print("\nAll campaigns:")
    for idx, row in df.iterrows():
        print(f"  {row['no']}. {row['title'][:60]}")
    
    print("\n" + "="*80)
    print("NEXT STEP:")
    print("  Use 'amalsholeh_zakat_urls.csv' for detailed scraping")
    print("="*80)

if __name__ == "__main__":
    main()