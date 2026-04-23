"""
Scraping listing JobStreet menggunakan Playwright
Versi SUPER STABIL + FORCE MODE 32 (anti pagination chaos)
+ JSON logging + human-readable logs
"""

import random
import re
import time
import logging
from Support.logger import setup_logger
import Support.deteksi_waktu as detek
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout


# =========================
# LOGGER SETUP
# =========================
logger = setup_logger(
    "scraper_listing",
    log_file="logs/pipeline/scraper_listing.log"
)

BASE_URL = "https://id.jobstreet.com"
LISTING_URL = "https://id.jobstreet.com/id/jobs-in-information-communication-technology?page={page}&sortmode=ListedDate"

MAX_RETRY_PAGE = 2
MAX_SESSION_RETRY = 3
TARGET_JOBS_PER_PAGE = 32


def ekstrak_job_id_dari_url(url: str) -> str | None:
    match = re.search(r"/job/(\d+)", url)
    return match.group(1) if match else None


def get_semua_job_id(max_page_limit: int = 100) -> list[dict]:

    # =========================
    # INIT LOG
    # =========================
    logger.info("scrape_start", extra={
        "event": "SCRAPE_START",
        "max_page_limit": max_page_limit,
        "target_jobs_per_page": TARGET_JOBS_PER_PAGE
    })

    print(f"\n[EXTRACT] Mulai scraping (FORCE MODE 32)")
    print(f"[CONFIG] max_page_limit = {max_page_limit}")

    semua = []
    seen_ids = set()

    no_new_counter = 0
    MAX_NO_NEW_PAGE = 3

    with sync_playwright() as p:

        session_retry = 0

        while session_retry < MAX_SESSION_RETRY:

            logger.info("session_start", extra={
                "attempt": session_retry + 1
            })

            print(f"\n[SESSION] Percobaan ke-{session_retry + 1}")

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
            )

            page = context.new_page()

            # =========================
            # INIT HOME
            # =========================
            print(" >> [Listing] Inisialisasi homepage")
            logger.info("init_homepage")

            page.goto(BASE_URL, wait_until="domcontentloaded", timeout=30000)
            time.sleep(random.uniform(0.8, 1.2))

            # =========================
            # VALIDASI PAGE 1
            # =========================
            print(" >> [CHECK] Validasi halaman 1")
            logger.info("validate_page_1")

            try:
                page.goto(LISTING_URL.format(page=1), wait_until="domcontentloaded", timeout=30000)
                time.sleep(random.uniform(0.8, 1.2))

                page.wait_for_selector('article[data-automation="normalJob"]', timeout=8000)

                articles = page.query_selector_all('article[data-automation="normalJob"]')
                job_count = len(articles)

                logger.info("page1_check", extra={"job_count": job_count})

                print(f"   - [Listing] Ditemukan {job_count} loker di halaman 1")

                # MODE 50 DETECTED
                if job_count >= 45:
                    logger.warning("mode_50_detected")
                    print("   - [REJECT] Mode 50 terdeteksi → restart session")
                    browser.close()
                    session_retry += 1
                    continue

                if job_count != TARGET_JOBS_PER_PAGE:
                    logger.warning("page1_not_ideal", extra={"job_count": job_count})
                    print(f"   - [WARNING] Jumlah tidak ideal ({job_count})")

                print("   - [OK] Mode valid → lanjut scraping")

            except Exception as e:
                logger.error("page1_validation_failed", extra={"error": str(e)}, exc_info=True)
                print(f"   - [ERROR] Validasi halaman 1 gagal: {e}")

                browser.close()
                session_retry += 1
                continue

            # =========================
            # SCRAPING LOOP
            # =========================
            page_num = 1
            no_new_counter = 0

            while True:

                print(f" >> [Listing] Halaman {page_num}")
                logger.info("page_fetch", extra={"page": page_num})

                try:
                    page.goto(LISTING_URL.format(page=page_num), wait_until="domcontentloaded", timeout=30000)
                    time.sleep(random.uniform(0.8, 1.2))
                except Exception as e:
                    logger.error("page_load_failed", extra={"page": page_num, "error": str(e)})
                    break

                retry_count = 0
                success_load = False

                while retry_count <= MAX_RETRY_PAGE:
                    try:
                        page.wait_for_selector('article[data-automation="normalJob"]', timeout=8000)
                        success_load = True
                        break

                    except PlaywrightTimeout:
                        retry_count += 1
                        logger.warning("retry_selector", extra={
                            "page": page_num,
                            "attempt": retry_count
                        })

                        if retry_count > MAX_RETRY_PAGE:
                            logger.warning("page_failed")
                            no_new_counter += 1
                            break

                        time.sleep(random.uniform(1.0, 1.5))
                        page.reload()

                if not success_load:
                    if no_new_counter >= MAX_NO_NEW_PAGE:
                        logger.warning("stop_no_response")
                        print("   - [STOP] terlalu banyak halaman gagal")
                        break

                    page_num += 1
                    continue

                articles = page.query_selector_all('article[data-automation="normalJob"]')

                print(f"   - [Listing] Halaman {page_num} → {len(articles)} loker")
                logger.info("page_result", extra={
                    "page": page_num,
                    "job_count": len(articles)
                })

                if len(articles) >= 45:
                    logger.warning("mode_changed_to_50")
                    print("   - [STOP] Mode berubah ke 50 di tengah scraping")
                    break

                new_count = 0

                for article in articles:
                    try:
                        overlay = article.query_selector('a[data-automation="job-list-item-link-overlay"]')
                        if not overlay:
                            continue

                        href = overlay.get_attribute("href")
                        job_id = ekstrak_job_id_dari_url(href) if href else None

                        if job_id and job_id not in seen_ids:
                            seen_ids.add(job_id)

                            semua.append({
                                "job_id": job_id,
                                "url_loker": BASE_URL + href,
                                "waktuScrapLoker": detek.waktuSaatIni(),
                            })

                            new_count += 1

                    except Exception as e:
                        logger.warning("skip_article_error", extra={"error": str(e)})

                # =========================
                # RESTORED HUMAN LOGS
                # =========================
                print(f"   - [Listing] Job baru ditemukan: {new_count}")
                print(f"   - [Listing] Total unik sementara: {len(seen_ids)}")

                logger.info("page_delta", extra={
                    "page": page_num,
                    "new_jobs": new_count,
                    "total_unique": len(seen_ids)
                })

                if new_count == 0:
                    no_new_counter += 1
                    print(f"   - [Listing] Tidak ada job baru ({no_new_counter}/{MAX_NO_NEW_PAGE})")
                else:
                    no_new_counter = 0

                if no_new_counter >= MAX_NO_NEW_PAGE:
                    print("   - [STOP] Tidak ada job baru dalam beberapa halaman")
                    logger.warning("stop_no_new_jobs")
                    break

                if page_num >= max_page_limit:
                    print("   - [STOP] Mencapai max page limit")
                    logger.warning("stop_max_page_limit")
                    break

                page_num += 1
                time.sleep(random.uniform(0.8, 1.5))

            browser.close()
            break

    logger.info("scrape_done", extra={
        "total_unique_jobs": len(semua)
    })

    print(f"\n[EXTRACT] TOTAL UNIQUE JOB: {len(semua)}")

    return semua