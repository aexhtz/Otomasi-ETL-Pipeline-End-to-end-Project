"""
Scraping listing JobStreet menggunakan Playwright
Versi SUPER STABIL + FORCE MODE 32 (anti pagination chaos)
"""

import random
import re
import time
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
import Support.deteksi_waktu as detek

BASE_URL    = "https://id.jobstreet.com"
LISTING_URL = "https://id.jobstreet.com/id/jobs-in-information-communication-technology?page={page}&sortmode=ListedDate"

MAX_RETRY_PAGE = 2
MAX_SESSION_RETRY = 3  # 🔥 retry session kalau kena mode 50
TARGET_JOBS_PER_PAGE = 32


def ekstrak_job_id_dari_url(url: str) -> str | None:
    match = re.search(r"/job/(\d+)", url)
    return match.group(1) if match else None


def get_semua_job_id(max_page_limit: int = 100) -> list[dict]:
    print(f"\n[EXTRACT] Mulai scraping (FORCE MODE 32)")

    semua = []
    seen_ids = set()

    no_new_counter = 0
    MAX_NO_NEW_PAGE = 3

    with sync_playwright() as p:

        session_retry = 0

        while session_retry < MAX_SESSION_RETRY:
            print(f"\n[SESSION] Percobaan ke-{session_retry+1}")

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

            context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3]});
                window.chrome = { runtime: {} };
            """)

            page = context.new_page()

            # ---- Init cookie
            print(" >> [Listing] Inisialisasi homepage")
            page.goto(BASE_URL, wait_until="domcontentloaded", timeout=30000)
            time.sleep(random.uniform(0.8, 1.2))

            # =========================================================
            # 🔥 VALIDASI HALAMAN 1 (KUNCI UTAMA)
            # =========================================================
            print(" >> [CHECK] Validasi halaman 1")

            try:
                page.goto(LISTING_URL.format(page=1), wait_until="domcontentloaded", timeout=30000)
                time.sleep(random.uniform(0.8, 1.2))

                page.wait_for_selector(
                    'article[data-automation="normalJob"]',
                    timeout=8000
                )

                articles = page.query_selector_all(
                    'article[data-automation="normalJob"]'
                )

                job_count = len(articles)
                print(f"   - Jumlah job halaman 1: {job_count}")

                # ❌ MODE 50 → RESTART
                if job_count >= 45:
                    print("   - [REJECT] Mode 50 terdeteksi → restart session ❌")
                    browser.close()
                    session_retry += 1
                    continue

                # ⚠️ kalau bukan 32 tapi bukan 50 juga
                if job_count != TARGET_JOBS_PER_PAGE:
                    print("   - [WARNING] Jumlah tidak ideal, lanjut dengan hati-hati")

                print("   - [OK] Mode 32 → lanjut scraping ✅")

            except Exception as e:
                print(f"   - [ERROR] Validasi halaman 1 gagal: {e}")
                browser.close()
                session_retry += 1
                continue

            # =========================================================
            # ✅ LOLOS VALIDASI → MULAI SCRAPING NORMAL
            # =========================================================

            page_num = 1
            no_new_counter = 0

            while True:
                url = LISTING_URL.format(page=page_num)
                print(f" >> [Listing] Halaman {page_num}")

                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=30000)
                    time.sleep(random.uniform(0.8, 1.2))
                except Exception as e:
                    print(f"   - [ERROR] Gagal buka halaman: {e}")
                    break

                # 🔥 RETRY LOGIC
                retry_count = 0
                success_load = False

                while retry_count <= MAX_RETRY_PAGE:
                    try:
                        page.wait_for_selector(
                            'article[data-automation="normalJob"]',
                            timeout=8000
                        )
                        success_load = True
                        break

                    except PlaywrightTimeout:
                        retry_count += 1
                        print(f"   - [RETRY] Selector gagal ({retry_count}/{MAX_RETRY_PAGE})")

                        if retry_count > MAX_RETRY_PAGE:
                            print("   - [WARNING] Gagal ambil halaman setelah retry")
                            no_new_counter += 1
                            break

                        time.sleep(random.uniform(1.0, 1.5))
                        page.reload()

                if not success_load:
                    if no_new_counter >= MAX_NO_NEW_PAGE:
                        print("   - [STOP] Terlalu banyak halaman gagal")
                        break

                    page_num += 1
                    continue

                articles = page.query_selector_all(
                    'article[data-automation="normalJob"]'
                )

                print(f"   - Ditemukan {len(articles)} loker")

                # 🔥 SAFETY GUARD (kalau tiba-tiba berubah jadi 50 di tengah)
                if len(articles) >= 45:
                    print("   - [WARNING] Mode berubah ke 50 di tengah → STOP")
                    break

                if len(articles) < 5:
                    print("   - [WARNING] Jumlah sangat sedikit (indikasi end)")

                new_count = 0

                for article in articles:
                    try:
                        overlay = article.query_selector(
                            'a[data-automation="job-list-item-link-overlay"]'
                        )
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
                        print(f"   - [SKIP] Error parsing artikel: {e}")
                        continue

                print(f"   - Job baru: {new_count}")
                print(f"   - Total unik sementara: {len(seen_ids)}")

                # 🔥 ANTI CHAOS
                if new_count == 0:
                    no_new_counter += 1
                    print(f"   - Tidak ada job baru ({no_new_counter}/{MAX_NO_NEW_PAGE})")
                else:
                    no_new_counter = 0

                if no_new_counter >= MAX_NO_NEW_PAGE:
                    print("   - [STOP] Tidak ada job baru dalam beberapa halaman")
                    break

                if page_num >= max_page_limit:
                    print("   - [STOP] Mencapai batas maksimum page")
                    break

                page_num += 1
                time.sleep(random.uniform(0.8, 1.5))

            browser.close()

            # ✅ kalau sudah sukses scraping → keluar dari session loop
            break

    print(f"\n[EXTRACT] Total unik jobID: {len(semua)}")
    return semua