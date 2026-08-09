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

def scroll_to_load_all(driver):
    
    print("\nScrolling to load all campaigns...")
    
    last_height = driver.execute_script("return document.body.scrollHeight")
    scroll_count = 0
    no_change_count = 0
    
    while True:
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2)
        
        new_height = driver.execute_script("return document.body.scrollHeight")
        
        scroll_count += 1
        if scroll_count % 5 == 0:
            print(f"  Scrolled {scroll_count} times...")
        
        if new_height == last_height:
            no_change_count += 1
            if no_change_count >= 3:
                print(f"  ✓ All loaded ({scroll_count} scrolls)")
                break
        else:
            no_change_count = 0
        
        last_height = new_height
        
        if scroll_count > 100:
            print(f"  ⚠️ Stopped at 100 scrolls")
            break

def collect_bersedekah_urls(driver):

    print("="*80)
    print("BERSEDEKAH.COM - ZAKAT CAMPAIGN URL COLLECTION")
    print("="*80)
    
    url = "https://bersedekah.com/zakat"
    
    driver.get(url)
    time.sleep(5)
    
    scroll_to_load_all(driver)
    
    print(f"\nExtracting campaign URLs...")
    
    soup = BeautifulSoup(driver.page_source, 'html.parser')
    
    # Find all box-program divs
    boxes = soup.find_all('div', class_='box-program')
    
    print(f"  Found {len(boxes)} campaign boxes")
    
    campaigns = []
    seen_urls = set()
    
    for box in boxes:
        # Find parent <a> tag
        link = box.find_parent('a', href=True)
        
        if not link:
            continue
        
        href = link.get('href', '')
        
        if not href or href in seen_urls:
            continue
        
        seen_urls.add(href)
        
        # Get title
        judul = box.find('span', class_='judul')
        title = judul.get_text(strip=True) if judul else ""
        
        # Get organizer
        lembaga = box.find('span', class_='lembaga')
        organizer = ""
        if lembaga:
            # Remove img tag and icon, get text only
            lembaga_copy = lembaga.__copy__()
            for img in lembaga_copy.find_all('img'):
                img.decompose()
            for icon in lembaga_copy.find_all('i'):
                icon.decompose()
            organizer = lembaga_copy.get_text(strip=True)
        
        # Extract slug from URL
        slug = href.split('/')[-1] if '/' in href else href
        
        campaigns.append({
            'no': len(campaigns) + 1,
            'title': title,
            'organizer': organizer,
            'url': href,
            'slug': slug,
            'platform': 'bersedekah.com'
        })
    
    print(f"  Extracted {len(campaigns)} unique campaigns")
    
    return campaigns

def main():
    driver = init_driver()
    
    campaigns = collect_bersedekah_urls(driver)
    
    driver.quit()
    
    if not campaigns:
        print("\n❌ No campaigns found!")
        return
    
    df = pd.DataFrame(campaigns)
    output_file = 'bersedekah_zakat_urls.csv'
    df.to_csv(output_file, index=False, encoding='utf-8')
    
    print("\n" + "="*80)
    print("URL COLLECTION COMPLETE!")
    print("="*80)
    print(f"\nTotal campaigns: {len(campaigns)}")
    print(f"Output file: {output_file}")
    
    print("\nSample campaigns:")
    for idx, row in df.head(10).iterrows():
        print(f"  {row['no']}. {row['title'][:40]} - {row['organizer'][:30]}")
    
    print("\n" + "="*80)
    print("NEXT STEP:")
    print("  Use 'bersedekah_zakat_urls.csv' for detailed scraping")
    print("="*80)

if __name__ == "__main__":
    main()