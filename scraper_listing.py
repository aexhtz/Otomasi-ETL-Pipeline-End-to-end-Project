"""
scraper_listing.py
Scraping listing JobStreet menggunakan Playwright.
Mensimulasikan browser nyata untuk melewati bot detection.

Install:
  pip install playwright
  playwright install chromium
"""

import re
import time
import asyncio
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
import deteksi_waktu as detek

BASE_URL    = "https://id.jobstreet.com"
LISTING_URL = "https://id.jobstreet.com/id/jobs-in-information-communication-technology?page={page}&sortmode=ListedDate"
MAX_RETRY   = 3


def ekstrak_job_id_dari_url(url: str) -> str | None:
    """Ekstrak job ID dari URL loker."""
    match = re.search(r"/job/(\d+)", url)
    return match.group(1) if match else None

def fetch_listing_page_playwright(page_num: int = 1) -> list[dict] | None:
    """
    Fetch satu halaman listing menggunakan Playwright.
    Membuka browser Chromium headless yang mensimulasikan browser nyata.
    """
    url = LISTING_URL.format(page=page_num)

    for attempt in range(1, MAX_RETRY + 1):
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=True,
                    args=[
                        "--no-sandbox",
                        "--disable-setuid-sandbox",
                        "--disable-blink-features=AutomationControlled",
                    ]
                )

                context = browser.new_context(
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/124.0.0.0 Safari/537.36"
                    ),
                    viewport={"width": 1366, "height": 768},
                    locale="id-ID",
                    timezone_id="Asia/Jakarta",
                    java_script_enabled=True,
                )

                # Sembunyikan tanda-tanda automation
                context.add_init_script("""
                    Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                    Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3]});
                    window.chrome = { runtime: {} };
                """)

                page = context.new_page()

                # Kunjungi homepage dulu untuk dapat cookie
                print(f"  [listing] Membuka homepage...")
                page.goto(BASE_URL, wait_until="domcontentloaded", timeout=30000)
                time.sleep(2)

                # Baru buka halaman listing
                print(f"  [listing] Membuka halaman {page_num}...")
                page.goto(url, wait_until="domcontentloaded", timeout=30000)

                # Tunggu artikel loker muncul
                try:
                    page.wait_for_selector(
                        'article[data-automation="normalJob"]',
                        timeout=15000
                    )
                except PlaywrightTimeout:
                    print(f"  [listing] Selector tidak muncul dalam 15 detik (attempt {attempt})")
                    browser.close()
                    if attempt < MAX_RETRY:
                        time.sleep(5 * attempt)
                        continue
                    return None

                # Ambil semua artikel loker dari DOM
                articles = page.query_selector_all('article[data-automation="normalJob"]')
                print(f"  [listing] Ditemukan {len(articles)} loker di halaman {page_num}")

                hasil = []
                for article in articles:
                    try:
                        overlay = article.query_selector(
                            'a[data-automation="job-list-item-link-overlay"]'
                        )
                        if not overlay:
                            continue

                        href     = overlay.get_attribute("href")
                        job_id   = ekstrak_job_id_dari_url(href) if href else None
                        url_loker = BASE_URL + href if href else None

                        if job_id:
                            hasil.append({
                                "job_id"         : job_id,
                                "url_loker"      : url_loker,
                                "waktuScrapLoker": detek.waktuSaatIni(),
                            })
                    except Exception as e:
                        print(f"  [listing] SKIP artikel: {e}")

                browser.close()
                return hasil

        except Exception as e:
            print(f"  [listing] ERROR attempt {attempt}: {e}")
            if attempt < MAX_RETRY:
                time.sleep(5 * attempt)

    print(f"  [listing] Halaman {page_num} gagal setelah {MAX_RETRY} percobaan.")
    return None


def get_semua_job_id(max_halaman: int = 1) -> list[dict]:
    """
    Entry point — fetch semua halaman listing dan kumpulkan job ID.
    """
    print(f"\n[EXTRACT] Mulai scraping listing ({max_halaman} halaman) via Playwright...")

    semua = []
    for page_num in range(1, max_halaman + 1):
        hasil = fetch_listing_page_playwright(page_num)
        if hasil:
            semua.extend(hasil)
        if page_num < max_halaman:
            time.sleep(3)

    print(f"[EXTRACT] Total job ID terkumpul: {len(semua)}")
    return semua