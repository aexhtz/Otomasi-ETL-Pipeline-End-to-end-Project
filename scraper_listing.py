import re
import requests
from bs4 import BeautifulSoup
import deteksi_waktu as detek

BASE_URL    = "https://id.jobstreet.com"
LISTING_URL = "https://id.jobstreet.com/id/jobs-in-information-communication-technology?page={page}&sortmode=ListedDate"

HEADERS = {
    "user-agent": (
        "Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/146.0.0.0 Mobile Safari/537.36 Edg/146.0.0.0"
    ),
    "accept-language": "en-US,en;q=0.9,id;q=0.8",
    "connection": "keep-alive",
    "origin": "https://id.jobstreet.com",
    "referer": "https://id.jobstreet.com/id/jobs-in-information-communication-technology?sortmode=ListedDate",
    "accept": "application/x-clarity-gzip"
}

def fetch_listing_page(page: int = 5) -> BeautifulSoup | None:
    """Fetch halaman listing loker, return BeautifulSoup atau None jika gagal."""
    url = LISTING_URL.format(page=page)
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        if response.status_code == 200:
            print(f"  [listing] Halaman {page} berhasil di-fetch.")
            return BeautifulSoup(response.text, "html.parser")
        else:
            print(f"  [listing] Gagal fetch halaman {page}: status {response.status_code}")
            return None
    except requests.exceptions.RequestException as e:
        print(f"  [listing] ERROR koneksi: {e}")
        return None

def ekstrak_job_id_dari_url(url: str) -> str | None:
    """Ekstrak job ID dari URL loker. Contoh: /id/job/91351476 -> '91351476'"""
    match = re.search(r"/job/(\d+)", url)
    return match.group(1) if match else None

def parse_listing(soup: BeautifulSoup) -> list[dict]:
    """
    Parse semua artikel loker dari halaman listing.
    Return list of dict berisi job_id dan waktu_scrap.
    Hanya mengambil data minimal — detail lengkap diambil via GraphQL.
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
                print("  [listing] SKIP: job ID tidak ditemukan.")
                continue

            hasil.append({
                "job_id"        : job_id,
                "url_loker"     : url_loker,
                "waktuScrapLoker": detek.waktuSaatIni(),
            })
        except Exception as e:
            print(f"  [listing] SKIP artikel karena error: {e}")

    return hasil

def get_semua_job_id(max_halaman: int = 5) -> list[dict]:
    """
    Entry point modul ini.
    Fetch beberapa halaman listing dan kumpulkan semua job ID.
    """
    print(f"\n[EXTRACT] Mulai scraping listing ({max_halaman} halaman)...")
    semua = []
    for page in range(1, max_halaman + 1):
        soup = fetch_listing_page(page)
        if soup:
            semua.extend(parse_listing(soup))
    print(f"[EXTRACT] Total job ID terkumpul: {len(semua)}")
    return semua