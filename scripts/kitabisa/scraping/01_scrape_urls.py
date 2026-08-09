
import sys
import os

script_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(script_dir)
sys.path.insert(0, parent_dir)

import config

from selenium import webdriver
from selenium.webdriver.safari.service import Service
from selenium.webdriver.common.by import By
from bs4 import BeautifulSoup
import pandas as pd
import time
import random
from datetime import datetime


def init_driver():
    try:
        service = Service(executable_path=config.SAFARI_DRIVER_PATH)
        driver = webdriver.Safari(service=service)
        print("Safari WebDriver initialized")
        return driver
    except:
        driver = webdriver.Safari()
        print("Safari WebDriver initialized (default)")
        return driver

def scrape_campaign_urls(max_scrolls=150):
    
    print("\n" + "="*80)
    print("SCRAPING CAMPAIGN URLs FROM KITABISA.COM")
    print("="*80)
    
    # Initialize browser
    print("\n[1/4] Starting browser...")
    driver = init_driver()
    driver.set_window_size(414, 896)  # Mobile viewport
    
    try:
        # Load page
        print(f"\n[2/4] Loading {config.KITABISA_EXPLORE_ZAKAT}...")
        driver.get(config.KITABISA_EXPLORE_ZAKAT)
        time.sleep(7)
        print("✓ Page loaded\n")
        
        # Scroll and collect URLs
        print(f"[3/4] Scrolling to collect URLs (max {max_scrolls} scrolls)...")
        print("-" * 80)
        
        all_urls = set()
        last_count = 0
        no_change_count = 0
        
        for scroll_num in range(max_scrolls):
            # Get current position
            current_pos = driver.execute_script("return window.pageYOffset")
            total_height = driver.execute_script("return document.body.scrollHeight")
            
            # Scroll down
            new_pos = min(current_pos + config.SCROLL_INCREMENT, total_height)
            driver.execute_script(f"window.scrollTo(0, {new_pos});")
            time.sleep(config.SCROLL_DELAY + random.uniform(0.3, 0.8))
            
            # Extract URLs
            cards = driver.find_elements(By.CSS_SELECTOR, config.SELECTORS['campaign_link'])
            
            for card in cards:
                try:
                    href = card.get_attribute("href")
                    if href and "/campaign/" in href:
                        clean_url = href.split('?')[0]
                        if 'zakat' in clean_url.lower():
                            all_urls.add(clean_url)
                except:
                    continue
            
            current_count = len(all_urls)
            added = current_count - last_count
            
            # Progress
            print(f"  Scroll {scroll_num+1:3d}/{max_scrolls}: {current_count:4d} URLs", end="")
            
            if added > 0:
                print(f" (+{added}) ✓")
                no_change_count = 0
            else:
                no_change_count += 1
                print(f" (no change x{no_change_count})")
            
            # Check if reached end
            if new_pos >= total_height - 100:
                print(f" Reached page bottom")
                time.sleep(3)
            
            # Stop if no new URLs
            if no_change_count >= config.NO_CHANGE_THRESHOLD:
                print(f"\n  ✓ No new URLs after {config.NO_CHANGE_THRESHOLD} scrolls - stopping!")
                break
            
            last_count = current_count
        
        print("-" * 80)
        print(f"\n✓ Total unique URLs collected: {len(all_urls)}\n")
        
        return sorted(all_urls)
        
    finally:
        print("Closing browser...")
        driver.quit()
        print("✓ Browser closed\n")

def save_urls(urls):
    

    print("[4/4] Saving URLs to CSV...")
    
    # Prepare data
    campaigns = []
    for i, url in enumerate(urls, 1):
        slug = url.split('/campaign/')[-1]
        campaigns.append({
            'no': i,
            'url': url,
            'slug': slug,
            'platform': 'kitabisa.com',
            'category': 'zakat',
            'scraped_at': datetime.now().isoformat()
        })
    
    # Save to CSV
    df = pd.DataFrame(campaigns)
    output_path = config.RAW_DATA_PATH + 'kitabisa_urls_fresh.csv'
    df.to_csv(output_path, index=False, encoding='utf-8')
    
    print(f"✓ Saved {len(df)} URLs to: {output_path}\n")
    
    # Summary
    print("="*80)
    print("SUMMARY")
    print("="*80)
    print(f"Total URLs collected: {len(df)}")
    print(f"Source: {config.KITABISA_EXPLORE_ZAKAT}")
    print(f"Category: Zakat")
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("\n URL COLLECTION COMPLETE!")
    print("="*80)
    
    # Sample
    print(f"\nSample URLs (first 5):")
    for i in range(min(5, len(df))):
        print(f"  {i+1}. {df.iloc[i]['slug'][:60]}")
    
    return df

def main():
    input("Tekan ENTER untuk mulai scraping")
    
    # Scrape URLs
    urls = scrape_campaign_urls(max_scrolls=config.MAX_SCROLLS)
    
    if urls:
        # Save results
        df = save_urls(urls)
        
        print(f"\n url saved!:")
    else:
        print("\n No URLs collected\n")

if __name__ == "__main__":
    main()