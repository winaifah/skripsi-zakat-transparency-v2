import sys, os, time, random, re, json
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, parent_dir)

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from webdriver_manager.chrome import ChromeDriverManager
from selenium_stealth import stealth
from bs4 import BeautifulSoup
import pandas as pd
from datetime import datetime

NEWS_JSON_DIR = os.path.join(parent_dir, 'data', 'processed', 'news_json')
os.makedirs(NEWS_JSON_DIR, exist_ok=True)

THRESHOLD     = 40    # kampanye dengan update/disbursement > ini ditangani script 4
RESTART_EVERY = 3     

# ─────────────────────────────────────────────────────────────────
def is_cloudflare_blocked(page_source):
    keywords = [
        "Melakukan verifikasi keamanan",
        "Enable JavaScript and cookies to continue",
        "Checking your browser", "Just a moment",
        "cf-browser-verification", "challenge-platform",
    ]
    if any(k in page_source for k in keywords):
        return True
    if len(page_source.strip()) < 2000:
        return True
    return False

def init_driver():
    try:
        import undetected_chromedriver as uc
        opts = uc.ChromeOptions()
        opts.add_argument("--start-maximized")
        opts.add_argument("--lang=id-ID")
        driver = uc.Chrome(options=opts, version_main=None)
        print("  [driver] undetected-chromedriver aktif")
        return driver
    except ImportError:
        pass

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
    print("  [driver] selenium-stealth aktif")
    return driver

def wait_cf_clear(driver, url, label="halaman"):
    """Load URL, tunggu sampai Cloudflare clear (max 3 retry)."""
    for attempt in range(3):
        driver.get(url)
        time.sleep(6)
        if not is_cloudflare_blocked(driver.page_source):
            return True
        wait = random.uniform(40, 70)
        print(f"    ⚠️  Cloudflare di {label} (attempt {attempt+1}/3) — tunggu {wait:.0f}s...")
        time.sleep(wait)
    return False   # tetap blocked setelah 3x


def scrape_latest_news(driver, campaign_url, expected_count):
    """
    Scrape /latest-news dengan dukungan virtual list.
    Satu tombol diklik per iterasi, lalu scroll tepat ke bawah tombol tsb
    sehingga virtual scroll menghapusnya dari DOM.
    Iterasi berikutnya btns[0] = tombol baru.
    """
    news_url = f"{campaign_url}/latest-news"
    print(f"    📰 Latest news ({expected_count} expected) → {news_url}")

    if not wait_cf_clear(driver, news_url, "latest-news"):
        return None, "CF_BLOCKED"

    updates    = []
    seen_keys  = set()
    no_prog    = 0          

    def _key(title, content):
        return title if title else content[:80]

    def _extract_body(soup):
        body = soup.find('div', {'data-testid': 'latest-news-body-text'})
        if not body:
            return '', ''
        for tag in body.find_all(['img', 'figure', 'figcaption', 'svg']):
            tag.decompose()
        content = re.sub(r'\s{2,}', ' ',
                         body.get_text(strip=True, separator=' ')).strip()
        parent_div = body.find_parent('div', class_=re.compile(r'flex.*flex-col'))
        title = ''
        if parent_div:
            h1 = parent_div.find('h1')
            title = h1.get_text(strip=True) if h1 else ''
        return title, content

    def _close_modal():
        try:
            close = driver.find_elements(
                By.XPATH, "//button[contains(text(),'Tutup')]")
            if close:
                close[0].click()
            else:
                driver.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
            time.sleep(0.6)
        except Exception:
            try:
                driver.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
                time.sleep(0.6)
            except Exception:
                pass

    def _try_inline(soup):
 
        for body in soup.find_all('div', {'data-testid': 'latest-news-body-text'}):
            has_btn = False
            node = body
            for _ in range(6):
                node = node.parent
                if node is None:
                    break
                if node.find('span', string=re.compile(r'Selengkapnya', re.I)):
                    has_btn = True
                    break
            if has_btn:
                continue
            for tag in body.find_all(['img', 'figure', 'figcaption', 'svg']):
                tag.decompose()
            content = re.sub(r'\s{2,}', ' ',
                             body.get_text(strip=True, separator=' ')).strip()
            parent_div = body.find_parent('div', class_=re.compile(r'flex.*flex-col'))
            title = ''
            if parent_div:
                h1 = parent_div.find('h1')
                title = h1.get_text(strip=True) if h1 else ''
            k = _key(title, content)
            if k and k not in seen_keys:
                updates.append({'title': title, 'content': content})
                seen_keys.add(k)

    def _find_vp_btn():

        candidates = driver.find_elements(
            By.XPATH,
            "//button[.//span[contains(text(),'Selengkapnya')]"
            " and not(@data-processed)]")
        for b in candidates[:40]:
            try:
                in_vp = driver.execute_script(
                    "var r=arguments[0].getBoundingClientRect();"
                    "return r.top>=-10 && r.bottom<=window.innerHeight+10;", b)
                if in_vp:
                    return b
            except Exception:
                pass
        return None

    print(f"       Scroll + klik per item (1 per iterasi)...")

    while no_prog < 10 and len(updates) < expected_count:
        count_before = len(updates)

        _try_inline(BeautifulSoup(driver.page_source, 'html.parser'))

        btn = _find_vp_btn()

        if btn:
            try:
                scroll_y = driver.execute_script("return window.scrollY;")
                driver.execute_script(
                    "arguments[0].setAttribute('data-processed','1');", btn)
                driver.execute_script("arguments[0].click();", btn)
                time.sleep(1.5)

                title, content = _extract_body(
                    BeautifulSoup(driver.page_source, 'html.parser'))
                k = _key(title, content)
                if k and k not in seen_keys:
                    updates.append({'title': title, 'content': content})
                    seen_keys.add(k)
                    if len(updates) % 10 == 0:
                        print(f"       {len(updates)}/{expected_count}")

                _close_modal()
                time.sleep(0.4)

                driver.execute_script("window.scrollTo(0, arguments[0]);", scroll_y)
                time.sleep(0.4)

                driver.execute_script("window.scrollBy(0, 150);")
                time.sleep(0.3)

            except Exception as e:
                if 'stale' not in str(e).lower():
                    print(f"       ⚠️  {str(e)[:55]}")
                _close_modal()
                driver.execute_script("window.scrollBy(0, 150);")
                time.sleep(0.5)

            had_button = True
        else:
            driver.execute_script(
                "window.scrollBy(0, Math.round(window.innerHeight * 0.5));")
            time.sleep(2.5)
            had_button = False

        if had_button or len(updates) > count_before:
            no_prog = 0
        else:
            if is_cloudflare_blocked(driver.page_source):
                print(f"       ⚠️  CF terdeteksi saat scraping "
                      f"({len(updates)}/{expected_count} sudah) — reload...")
                if wait_cf_clear(driver, news_url, "latest-news (lanjut)"):
                    no_prog = 0
                    print(f"       ✓ CF clear, lanjut ({len(updates)} item tersimpan)")
                else:
                    print(f"       ❌ CF persistent, berhenti di {len(updates)} item")
                    break
            else:
                no_prog += 1

    print(f"       ✓ Selesai: {len(updates)}/{expected_count} item diekstrak")
    return updates, "OK"

def scrape_disbursement(driver, campaign_url, expected_count):
    """
    Scrape /pencairan-dana:
    Scroll ke bawah terus menerus sampai semua item termuat — tidak perlu klik apapun.
    """
    disb_url = f"{campaign_url}/pencairan-dana"
    print(f" Disbursement ({expected_count} expected) → {disb_url}")

    if not wait_cf_clear(driver, disb_url, "pencairan-dana"):
        return None, "CF_BLOCKED"

    print(f"       Scroll untuk muat semua disbursement...")
    SELECTOR = 'list-history-disbursement'
    prev_count = 0
    no_change  = 0
    while no_change < 5:
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2.5)
        soup_tmp = BeautifulSoup(driver.page_source, 'html.parser')
        curr = len(soup_tmp.find_all('div', {'data-testid': SELECTOR}))
        if curr > prev_count:
            print(f"       {curr} item ditemukan (+{curr-prev_count})")
            prev_count = curr
            no_change  = 0
        else:
            no_change += 1

    soup = BeautifulSoup(driver.page_source, 'html.parser')
    items = soup.find_all('div', {'data-testid': SELECTOR})
    print(f"       Total: {len(items)} disbursement item")

    disbursements = []
    for item in items:
        date  = item.find('span', {'data-testid': 'text-keterangan-waktu'})
        title = item.find('h1',   {'data-testid': 'text-history-title-disbursement'})
        plan  = item.find('div',  {'data-testid': 'text-history-plan-disbursement'})

        date_txt  = date.get_text(strip=True)  if date  else ''
        title_txt = title.get_text(strip=True) if title else ''
        plan_txt  = plan.get_text(strip=True)  if plan  else ''

        amount = ''
        if title_txt:
            m = re.search(r'Rp\s*[\d.,]+', title_txt)
            amount = m.group() if m else ''

        if title_txt or plan_txt:
            disbursements.append({
                'date': date_txt, 'amount': amount, 'plan': plan_txt
            })

    print(f"       ✓ Selesai: {len(disbursements)} item diekstrak")
    return disbursements, "OK"

def save_to_file(data, no, slug, suffix):
    """Simpan list ke JSON file, return filename (bukan full path)."""
    fname = f"{no}_{slug}_{suffix}.json"
    fpath = os.path.join(NEWS_JSON_DIR, fname)
    with open(fpath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return fname

def main():
    print("=" * 65)
    print("  SCRIPT 4 — Scrape Large Campaigns (>40 news OR disbursement)")
    print("=" * 65)

    default = os.path.join(parent_dir, 'data', 'processed',
                           'kitabisa_large_campaigns.csv')
    print(f"\nFile default : {default}")
    custom = input("Pakai file lain? (Enter = default, atau ketik path): ").strip()
    input_file = custom if custom else default

    df = pd.read_csv(input_file)
    print(f"✓ Total baris: {len(df)}")

    NEEDS_RE = ['[]', '', 'nan', 'None',
                'CF_BLOCKED', 'CLOUDFLARE_BLOCKED']

    def val_needs_scraping_news(row):
        val = str(row.get('latest_news_json', ''))
        return val in NEEDS_RE or val.startswith('{"note"') or val == 'no updates'

    def val_needs_scraping_disb(row):
        val = str(row.get('disbursement_json', ''))
        return val in NEEDS_RE or val.startswith('{"note"') or val == 'no disbursement'

    def qualifies(row):
        uc = int(str(row.get('update_count', 0) or 0))
        dc = int(str(row.get('disbursement_count', 0) or 0))
        return (uc > THRESHOLD or dc > THRESHOLD) and \
               (val_needs_scraping_news(row) or val_needs_scraping_disb(row))

    mask = df.apply(qualifies, axis=1)
    df_todo = df[mask].reset_index(drop=True)
    print(f"  Perlu scrape : {len(df_todo)} kampanye")

    if df_todo.empty:
        print("Tidak ada kampanye yang perlu di-scrape.")
        return

    print(f"\n  Tersedia: 1 – {len(df_todo)}")
    start = int(input("Mulai dari baris ke- (1-based): ").strip())
    count = int(input("Scrape berapa kampanye    : ").strip())
    batch = df_todo.iloc[start-1 : start-1+count]
    print(f"\n✓ Akan scrape {len(batch)} kampanye (baris {start}–{start-1+len(batch)})\n")

    confirm = input("Proceed? (y/n): ").strip().lower()
    if confirm != 'y':
        print("Cancelled.")
        return

    driver = init_driver()
    start_time = datetime.now()
    processed  = 0

    for i, (_, row) in enumerate(batch.iterrows()):
        slug = str(row['slug'])
        url  = str(row['url'])
        no   = str(row.get('no', i + 1))
        uc   = int(str(row.get('update_count',       0) or 0))
        dc   = int(str(row.get('disbursement_count', 0) or 0))

        print(f"\n[{i+1}/{len(batch)}] #{no} {slug[:50]}")
        print(f"  update_count={uc}  disbursement_count={dc}")

        do_news = val_needs_scraping_news(row)
        do_disb = val_needs_scraping_disb(row)

        delay = random.uniform(8, 15)
        print(f"  ⏳ Delay {delay:.1f}s...")
        time.sleep(delay)

        # ── Latest News ───────────────────────────────────────────
        if do_news:
            news_data, status = scrape_latest_news(driver, url, uc)
            if status == "CF_BLOCKED":
                df.loc[df['slug'] == slug, 'latest_news_json'] = 'CF_BLOCKED'
                print(f"  ❌ News CF_BLOCKED")
            elif news_data is not None:
                fname = save_to_file(news_data, no, slug, 'news')
                df.loc[df['slug'] == slug, 'latest_news_json'] = f"FILE:{fname}"
                print(f"  ✓ News → FILE:{fname} ({len(news_data)} items)")
        else:
            print(f"  ↷ News: skip (sudah ada / sudah FILE:)")

        # ── Disbursement ──────────────────────────────────────────
        if do_disb:
            disb_data, status = scrape_disbursement(driver, url, dc)
            if status == "CF_BLOCKED":
                df.loc[df['slug'] == slug, 'disbursement_json'] = 'CF_BLOCKED'
                print(f"  ❌ Disbursement CF_BLOCKED")
            elif disb_data is not None:
                fname = save_to_file(disb_data, no, slug, 'disb')
                df.loc[df['slug'] == slug, 'disbursement_json'] = f"FILE:{fname}"
                print(f"  ✓ Disbursement → FILE:{fname} ({len(disb_data)} items)")
        else:
            print(f"  ↷ Disbursement: skip (sudah ada / sudah FILE:)")

        processed += 1

        if processed % 3 == 0:
            tmp = os.path.join(parent_dir, 'data', 'processed',
                               f'large_temp_{processed}.csv')
            df.to_csv(tmp, index=False, encoding='utf-8')
            elapsed = datetime.now() - start_time
            print(f"\n Auto-save: {tmp} | {processed}/{len(batch)} | {elapsed}\n")

        if processed % RESTART_EVERY == 0 and processed < len(batch):
            print(f"\n Restart driver + cooling 30s...")
            try:
                driver.quit()
            except Exception:
                pass
            time.sleep(30)
            driver = init_driver()
            print(f"  ✓ Driver baru siap\n")

    driver.quit()

    ts  = datetime.now().strftime('%Y%m%d_%H%M%S')
    out = os.path.join(parent_dir, 'data', 'processed',
                       f'kitabisa_large_done_{ts}.csv')
    df.to_csv(out, index=False, encoding='utf-8')

    print("\n" + "=" * 65)
    print("SELESAI!")
    print("=" * 65)
    print(f"Output CSV : {out}")
    print(f"JSON files : {NEWS_JSON_DIR}")

    # Ringkasan
    done_news = df['latest_news_json'].str.startswith('FILE:').sum() \
                if 'latest_news_json' in df.columns else 0
    done_disb = df['disbursement_json'].str.startswith('FILE:').sum() \
                if 'disbursement_json' in df.columns else 0
    cf_news   = (df['latest_news_json'] == 'CF_BLOCKED').sum() \
                if 'latest_news_json' in df.columns else 0
    cf_disb   = (df['disbursement_json'] == 'CF_BLOCKED').sum() \
                if 'disbursement_json' in df.columns else 0

    print(f"\nNews  → FILE: {done_news}  |  CF_BLOCKED: {cf_news}")
    print(f"Disb  → FILE: {done_disb}  |  CF_BLOCKED: {cf_disb}")
    print("=" * 65)

if __name__ == '__main__':
    main()
