"""
scraper_listing.py
Tahap Extract pertama: ambil daftar job ID dari halaman listing HTML JobStreet.

Menggunakan requests.Session() dengan cookie harvesting untuk menghindari 403.
Strategi:
  1. Kunjungi homepage dulu untuk dapat cookie sah
  2. Baru request halaman listing dengan cookie tersebut
  3. Retry otomatis jika gagal
"""

import re
import time
import requests
from bs4 import BeautifulSoup
import deteksi_waktu as detek

BASE_URL    = "https://id.jobstreet.com"
LISTING_URL = "https://id.jobstreet.com/id/jobs-in-information-communication-technology?page={page}&sortmode=ListedDate"
HOMEPAGE_URL = "https://id.jobstreet.com/id"

HEADERS = {
    "user-agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "accept": (
        "text/html,application/xhtml+xml,application/xml;"
        "q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8"
    ),
    "accept-language"  : "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
    "accept-encoding"  : "gzip, deflate, br",
    "referer"          : "https://id.jobstreet.com/",
    "sec-fetch-dest"   : "document",
    "sec-fetch-mode"   : "navigate",
    "sec-fetch-site"   : "same-origin",
    "sec-fetch-user"   : "?1",
    "upgrade-insecure-requests": "1",
    "sec-ch-ua"        : '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
    "sec-ch-ua-mobile" : "?0",
    "sec-ch-ua-platform": '"Windows"',
    "cache-control"    : "max-age=0",
    "connection"       : "keep-alive",
}

MAX_RETRY = 3
RETRY_DELAY = 5  # detik antar retry


def buat_session() -> requests.Session:
    """
    Buat session baru dan harvest cookie dengan mengunjungi homepage dulu.
    Ini mensimulasikan browser yang buka JobStreet secara natural.
    """
    session = requests.Session()
    session.headers.update(HEADERS)

    try:
        print("  [listing] Menginisialisasi session (harvest cookie)...")
        # Kunjungi homepage dulu untuk dapat cookie sah
        resp = session.get(HOMEPAGE_URL, timeout=15)
        print(f"  [listing] Homepage status: {resp.status_code} | Cookies: {len(session.cookies)}")
        time.sleep(2)  # jeda natural seperti manusia membaca halaman
    except Exception as e:
        print(f"  [listing] WARNING harvest cookie gagal: {e}")

    return session


def fetch_listing_page(session: requests.Session, page: int = 1) -> BeautifulSoup | None:
    """
    Fetch halaman listing dengan session yang sudah punya cookie.
    Retry otomatis jika gagal.
    """
    url = LISTING_URL.format(page=page)

    for attempt in range(1, MAX_RETRY + 1):
        try:
            # Update referer sesuai halaman sebelumnya
            if page > 1:
                session.headers.update({
                    "referer": LISTING_URL.format(page=page - 1)
                })

            response = session.get(url, timeout=15)

            if response.status_code == 200:
                print(f"  [listing] Halaman {page} berhasil (attempt {attempt})")
                return BeautifulSoup(response.text, "html.parser")

            elif response.status_code == 403:
                print(f"  [listing] 403 pada halaman {page} (attempt {attempt}/{MAX_RETRY})")
                if attempt < MAX_RETRY:
                    print(f"  [listing] Retry dalam {RETRY_DELAY * attempt} detik...")
                    time.sleep(RETRY_DELAY * attempt)
                    # Re-harvest cookie pada retry
                    if attempt == 2:
                        print("  [listing] Re-harvest cookie...")
                        session.get(HOMEPAGE_URL, timeout=15)
                        time.sleep(3)

            else:
                print(f"  [listing] Status {response.status_code} halaman {page}")
                return None

        except requests.exceptions.RequestException as e:
            print(f"  [listing] ERROR koneksi (attempt {attempt}): {e}")
            if attempt < MAX_RETRY:
                time.sleep(RETRY_DELAY)

    print(f"  [listing] Halaman {page} gagal setelah {MAX_RETRY} percobaan.")
    return None


def ekstrak_job_id_dari_url(url: str) -> str | None:
    """Ekstrak job ID dari URL loker. Contoh: /id/job/91351476 -> '91351476'"""
    match = re.search(r"/job/(\d+)", url)
    return match.group(1) if match else None


def parse_listing(soup: BeautifulSoup) -> list[dict]:
    """
    Parse semua artikel loker dari halaman listing.
    Return list of dict berisi job_id dan waktu_scrap.
    """
    artikel_list = soup.find_all("article", {"data-automation": "normalJob"})
    print(f"  [listing] Ditemukan {len(artikel_list)} loker di halaman ini.")

    hasil = []
    for artikel in artikel_list:
        try:
            url_tag  = artikel.find("a", attrs={"data-automation": "job-list-item-link-overlay"})
            href     = url_tag.get("href") if url_tag else None
            job_id   = ekstrak_job_id_dari_url(href) if href else None
            url_loker = BASE_URL + href if href else None

            if not job_id:
                continue

            hasil.append({
                "job_id"         : job_id,
                "url_loker"      : url_loker,
                "waktuScrapLoker": detek.waktuSaatIni(),
            })
        except Exception as e:
            print(f"  [listing] SKIP artikel: {e}")

    return hasil


def get_semua_job_id(max_halaman: int = 1) -> list[dict]:
    """
    Entry point modul ini.
    Fetch beberapa halaman listing dan kumpulkan semua job ID.
    """
    print(f"\n[EXTRACT] Mulai scraping listing ({max_halaman} halaman)...")

    # Satu session untuk semua halaman
    session = buat_session()

    semua = []
    for page in range(1, max_halaman + 1):
        soup = fetch_listing_page(session, page)
        if soup:
            semua.extend(parse_listing(soup))
        # Jeda antar halaman agar tidak terdeteksi sebagai bot
        if page < max_halaman:
            time.sleep(3)

    print(f"[EXTRACT] Total job ID terkumpul: {len(semua)}")
    return semua