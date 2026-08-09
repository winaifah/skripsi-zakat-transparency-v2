from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
from selenium_stealth import stealth
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
        if scroll_count % 3 == 0:
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
    
    print("  Extra scrolls for last items...")
    for i in range(3):
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(1)

def collect_amartha_urls(driver):

    print("="*80)
    print("AMARTHA EMPOWER - URL COLLECTION FINAL")
    print("="*80)
    
    search_url = "https://empower.amartha.com/search?search=zakat"
    
    driver.get(search_url)
    time.sleep(5)
    
    scroll_to_load_all(driver)
    
    print(f"\nExtracting titles...")
    
    title_elements = driver.find_elements(By.XPATH, "//h3[@class='title']")
    
    all_titles = []
    for elem in title_elements:
        title = elem.text.strip()
        if title and title not in all_titles:
            all_titles.append(title)
    
    print(f"  Found {len(all_titles)} campaigns")
    
    print(f"\nCollecting URLs...")
    
    campaigns = []
    failed = []
    
    for idx, target_title in enumerate(all_titles):
        is_last = (idx == len(all_titles) - 1)
        
        try:
            driver.get(search_url)
            time.sleep(2)
            
            scroll_times = 15 if is_last else 10
            
            for i in range(scroll_times):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(0.8)
            
            if is_last:
                print(f"  [{idx+1}/{len(all_titles)}] Last campaign - extra wait...")
                time.sleep(2)
            
            time.sleep(1)
            
            # Find title element
            title_elem = driver.find_element(By.XPATH, f"//h3[@class='title'][normalize-space()='{target_title}']")
            
            # Find wrapper card
            card_wrapper = title_elem.find_element(By.XPATH, "./ancestor::div[contains(@class, 'wrapper-card')][1]")
            
            if is_last:
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(0.5)
            
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", card_wrapper)
            time.sleep(0.8 if is_last else 0.5)
            
            driver.execute_script("arguments[0].click();", card_wrapper)
            
            time.sleep(3 if is_last else 2)
            
            # Get URL
            current_url = driver.current_url
            
            if '/search' not in current_url and 'empower.amartha.com' in current_url:
                slug = current_url.split('/')[-1]
                
                campaigns.append({
                    'no': len(campaigns) + 1,
                    'title': target_title,
                    'url': current_url,
                    'slug': slug,
                    'platform': 'amartha.com'
                })
                
                print(f"  [{idx+1}/{len(all_titles)}] ✓ {target_title[:50]}")
            else:
                failed.append(target_title)
                print(f"  [{idx+1}/{len(all_titles)}] ✗ Still on search: {current_url}")
            
        except Exception as e:
            failed.append(target_title)
            print(f"  [{idx+1}/{len(all_titles)}] ✗ Error: {str(e)[:60]}")

            try:
                driver.get(search_url)
                time.sleep(2)
            except:
                pass
    
    print(f"\n✓ Done! Success: {len(campaigns)}/{len(all_titles)}")
    
    if failed:
        print(f"\n Failed campaigns ({len(failed)}):")
        for title in failed:
            print(f"  - {title[:60]}")
    
    return campaigns

def main():
    driver = init_driver()
    
    campaigns = collect_amartha_urls(driver)
    
    driver.quit()
    
    if not campaigns:
        print("\n No campaigns collected!")
        return
    
    df = pd.DataFrame(campaigns)
    output_file = 'amartha_zakat_urls.csv'
    df.to_csv(output_file, index=False, encoding='utf-8')
    
    print("\n" + "="*80)
    print("URL COLLECTION COMPLETE!")
    print("="*80)
    print(f"\nTotal: {len(campaigns)}")
    print(f"Output: {output_file}")
    
    print("\nAll campaigns:")
    for idx, row in df.iterrows():
        print(f"  {row['no']}. {row['title'][:60]}")
    
    print("\n" + "="*80)
    
    if len(campaigns) < 10:
        print("⚠️ Note: If still missing last campaign, we'll use 9 campaigns")
        print("   (90% success rate is already very good!)")
        print("="*80)

if __name__ == "__main__":
    main()