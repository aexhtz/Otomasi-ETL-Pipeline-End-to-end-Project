"""
scraper_detail.py
Tahap Extract kedua: ambil detail lengkap setiap loker via GraphQL endpoint JobStreet.
Jauh lebih cepat dan stabil dibanding HTML scraping karena langsung dari API JSON.
"""

import re
import time
import requests
from bs4 import BeautifulSoup

GRAPHQL_URL = "https://id.jobstreet.com/graphql"

HEADERS = {
    "content-type"        : "application/json",
    "accept"              : "*/*",
    "origin"              : "https://id.jobstreet.com",
    "seek-request-brand"  : "jobstreet",
    "seek-request-country": "ID",
    "x-seek-site"         : "chalice",
    "user-agent"          : (
        "Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/146.0.0.0 Mobile Safari/537.36 Edg/146.0.0.0"
    ),
}

# GraphQL query exact copy dari Network tab browser (JANGAN diubah formatnya)
GRAPHQL_QUERY = "query jobDetails($jobId: ID!, $jobDetailsViewedCorrelationId: String!, $sessionId: String!, $zone: Zone!, $locale: Locale!, $languageCode: LanguageCodeIso!, $countryCode: CountryCodeIso2!, $timezone: Timezone!, $visitorId: UUID!, $isAuthenticated: Boolean!, $enableJdvBadge: Boolean!) {\n  jobDetails(\n    id: $jobId\n    tracking: {channel: \"WEB\", jobDetailsViewedCorrelationId: $jobDetailsViewedCorrelationId, sessionId: $sessionId}\n  ) {\n    ...job\n    insights @include(if: $isAuthenticated) {\n      ... on ApplicantCount {\n        volumeLabel(locale: $locale)\n        count\n        __typename\n      }\n      __typename\n    }\n    learningInsights(platform: WEB, zone: $zone, locale: $locale) {\n      analytics\n      content\n      __typename\n    }\n    gfjInfo {\n      location {\n        countryCode\n        country(locale: $locale)\n        suburb(locale: $locale)\n        region(locale: $locale)\n        state(locale: $locale)\n        postcode\n        __typename\n      }\n      workTypes {\n        label\n        __typename\n      }\n      company {\n        url(locale: $locale, zone: $zone)\n        __typename\n      }\n      __typename\n    }\n    workArrangements(visitorId: $visitorId, channel: \"JDV\", platform: WEB) {\n      arrangements {\n        type\n        label(locale: $locale)\n        __typename\n      }\n      label(locale: $locale)\n      __typename\n    }\n    seoInfo {\n      normalisedRoleTitle\n      workType\n      classification\n      subClassification\n      where(zone: $zone)\n      broaderLocationName(locale: $locale)\n      normalisedOrganisationName\n      __typename\n    }\n    __typename\n  }\n}\n\nfragment badges on JobDetails {\n  badges(visitorId: $visitorId, platform: WEB, locale: $locale) @include(if: $enableJdvBadge) {\n    badges {\n      badge\n      displayText(locale: $locale)\n      ... on JobDetailsInteractiveBadge {\n        message(locale: $locale, zone: $zone)\n        __typename\n      }\n      ... on JobDetailsResponsiveHirerBadge {\n        message(locale: $locale, zone: $zone)\n        badgeScore\n        __typename\n      }\n      __typename\n    }\n    __typename\n  }\n  __typename\n}\n\nfragment job on JobDetails {\n  job {\n    sourceZone\n    tracking {\n      adProductType\n      classificationInfo {\n        classificationId\n        classification\n        subClassificationId\n        subClassification\n        __typename\n      }\n      hasRoleRequirements\n      isPrivateAdvertiser\n      locationInfo {\n        area\n        location\n        locationIds\n        __typename\n      }\n      workTypeIds\n      postedTime\n      __typename\n    }\n    id\n    title\n    phoneNumber\n    isExpired\n    expiresAt {\n      dateTimeUtc\n      __typename\n    }\n    isLinkOut\n    contactMatches {\n      type\n      value\n      __typename\n    }\n    isVerified\n    abstract\n    content(platform: WEB)\n    status\n    listedAt {\n      label(context: JOB_POSTED, length: SHORT, timezone: $timezone, locale: $locale)\n      dateTimeUtc\n      __typename\n    }\n    salary {\n      currencyLabel(zone: $zone)\n      label\n      __typename\n    }\n    shareLink(platform: WEB, zone: $zone, locale: $locale)\n    workTypes {\n      label(locale: $locale)\n      __typename\n    }\n    advertiser {\n      id\n      name(locale: $locale)\n      isVerified\n      registrationDate {\n        dateTimeUtc\n        __typename\n      }\n      __typename\n    }\n    location {\n      label(locale: $locale, type: LONG)\n      __typename\n    }\n    classifications {\n      label(languageCode: $languageCode)\n      __typename\n    }\n    products {\n      branding {\n        id\n        cover {\n          url\n          __typename\n        }\n        thumbnailCover: cover(isThumbnail: true) {\n          url\n          __typename\n        }\n        logo {\n          url\n          __typename\n        }\n        __typename\n      }\n      bullets\n      questionnaire {\n        questions\n        __typename\n      }\n      video {\n        url\n        position\n        __typename\n      }\n      __typename\n    }\n    __typename\n  }\n  ...badges\n  companyProfile(zone: $zone) {\n    id\n    name\n    companyNameSlug\n    shouldDisplayReviews\n    branding {\n      logo\n      __typename\n    }\n    overview {\n      description {\n        paragraphs\n        __typename\n      }\n      industry\n      size {\n        description\n        __typename\n      }\n      website {\n        url\n        __typename\n      }\n      __typename\n    }\n    reviewsSummary {\n      overallRating {\n        numberOfReviews {\n          value\n          __typename\n        }\n        value\n        __typename\n      }\n      __typename\n    }\n    perksAndBenefits {\n      title\n      __typename\n    }\n    __typename\n  }\n  companySearchUrl(zone: $zone, languageCode: $languageCode)\n  companyTags {\n    key(languageCode: $languageCode)\n    value\n    __typename\n  }\n  restrictedApplication(countryCode: $countryCode) {\n    label(locale: $locale)\n    __typename\n  }\n  sourcr {\n    image\n    imageMobile\n    link\n    __typename\n  }\n  __typename\n}"

# Variables tetap (tidak bergantung pada job ID)
BASE_VARIABLES = {
    "zone"                          : "asia-4",
    "locale"                        : "id-ID",
    "languageCode"                  : "id",
    "countryCode"                   : "ID",
    "timezone"                      : "Asia/Jakarta",
    "sessionId"                     : "a4db36b3-3094-47e4-b2d8-e245ca8433df",
    "visitorId"                     : "a4db36b3-3094-47e4-b2d8-e245ca8433df",
    "jobDetailsViewedCorrelationId" : "c031bfd5-a03a-4256-8e05-94d42d92771e",
    "isAuthenticated"               : False,
    "enableJdvBadge"                : True,
}


# ─── Helper ──────────────────────────────────────────────────────────────────

def bersihkan_html(html_string: str | None) -> str | None:
    """Hapus tag HTML dari field content, sisakan teks bersih."""
    if not html_string:
        return None
    return BeautifulSoup(html_string, "html.parser").get_text(separator="\n", strip=True)

def safe_get(data: dict, *keys, default=None):
    """Ambil nilai nested dict dengan aman tanpa KeyError."""
    for key in keys:
        if not isinstance(data, dict):
            return default
        data = data.get(key, default)
        if data is None:
            return default
    return data


# ─── Request ─────────────────────────────────────────────────────────────────

def fetch_detail_loker(job_id: str) -> dict | None:
    """
    Kirim POST request GraphQL untuk satu job ID.
    Return: dict raw dari response JSON, atau None jika gagal.
    """
    payload = {
        "operationName": "jobDetails",
        "query"        : GRAPHQL_QUERY,
        "variables"    : {**BASE_VARIABLES, "jobId": job_id},
    }
    try:
        response = requests.post(GRAPHQL_URL, json=payload, headers=HEADERS, timeout=10)
        if response.status_code == 200:
            data = response.json()
            return data.get("data", {}).get("jobDetails")
        else:
            print(f"  [detail] job {job_id}: HTTP {response.status_code}")
            # Debug: print 500 karakter pertama dari response body
            try:
                err_body = response.json()
                print(f"  [debug] response body: {str(err_body)[:500]}")
            except Exception:
                print(f"  [debug] response text: {response.text[:500]}")
            return None
    except requests.exceptions.RequestException as e:
        print(f"  [detail] job {job_id}: ERROR koneksi — {e}")
        return None


# ─── Transform ───────────────────────────────────────────────────────────────

def transform_detail(raw: dict, job_id: str, url_loker: str, waktu_scrap: str) -> dict | None:
    """
    Ekstrak dan normalisasi field yang diperlukan dari raw GraphQL response.
    Return: dict siap simpan ke database.
    """
    if not raw:
        return None

    job             = raw.get("job") or {}
    work_arr        = raw.get("workArrangements") or {}   # null-safe: GraphQL bisa kirim null
    gfj             = raw.get("gfjInfo") or {}
    company         = raw.get("companyProfile") or {}
    company_overview = company.get("overview") or {}
    rating          = safe_get(company, "reviewsSummary", "overallRating")

    # Klasifikasi
    tracking        = job.get("tracking") or {}
    clf_info        = tracking.get("classificationInfo") or {}

    # Work arrangements (bisa multiple: Hybrid, Remote, Onsite)
    arrangements    = [a.get("label") for a in (work_arr.get("arrangements") or [])]

    # Salary
    salary          = job.get("salary")
    salary_label    = salary.get("label") if salary else None

    # Classifications
    classifications = job.get("classifications") or []
    klasifikasi_label = classifications[0].get("label") if classifications else None

    return {
        # Identitas
        "job_id"              : job_id,
        "url"                 : url_loker,

        # Info utama
        "posisi"              : job.get("title"),
        "perusahaan"          : safe_get(job, "advertiser", "name"),
        "perusahaan_verified" : safe_get(job, "advertiser", "isVerified"),
        "lokasi"              : safe_get(job, "location", "label"),
        "lokasi_negara"       : safe_get(gfj, "location", "country"),
        "lokasi_kota"         : safe_get(gfj, "location", "suburb"),
        "lokasi_provinsi"     : safe_get(gfj, "location", "state"),

        # Klasifikasi & tipe kerja
        "klasifikasi"         : klasifikasi_label,
        "sub_klasifikasi"     : clf_info.get("subClassification"),
        "tipe_kerja"          : safe_get(job, "workTypes", "label"),
        "work_arrangement"    : ", ".join(arrangements) if arrangements else None,

        # Gaji
        "gaji"                : salary_label,

        # Deskripsi
        "deskripsi_singkat"   : job.get("abstract"),
        "deskripsi_lengkap"   : bersihkan_html(job.get("content")),

        # Waktu
        "waktuPostingLoker"   : safe_get(job, "listedAt", "dateTimeUtc"),
        "waktuExpiredLoker"   : safe_get(job, "expiresAt", "dateTimeUtc"),
        "waktuScrapLoker"     : waktu_scrap,

        # Status
        "status"              : job.get("status"),
        "isExpired"           : job.get("isExpired"),
        "isPrivateAdvertiser" : tracking.get("isPrivateAdvertiser"),

        # Info perusahaan
        "company_industry"    : company_overview.get("industry") or "Tidak diketahui",
        "company_size"        : safe_get(company_overview, "size", "description"),
        "company_website"     : safe_get(company_overview, "website", "url"),
        "company_rating"      : safe_get(rating, "value") if rating else None,
        "company_total_review": safe_get(rating, "numberOfReviews", "value") if rating else None,
    }

# ─── Entry Point ─────────────────────────────────────────────────────────────

def get_semua_detail(job_list: list[dict], delay: float = 0.3) -> list[dict]:
    """
    Fetch dan transform detail untuk semua job ID dalam list.
    
    Args:
        job_list : output dari scraper_listing.get_semua_job_id()
        delay    : jeda antar request (detik) agar tidak di-rate-limit
    
    Return: list of dict siap masuk ke database.
    """
    print(f"\n>> [EXTRACT] Mulai fetch detail untuk {len(job_list)} loker via GraphQL")
    hasil = []

    for i, item in enumerate(job_list, 1):
        job_id      = item["job_id"]
        url_loker   = item["url_loker"]
        waktu_scrap = item["waktuScrapLoker"]

        print(f"  [{i}/{len(job_list)}] Fetching job ID: {job_id}")
        raw = fetch_detail_loker(job_id)

        if raw:
            detail = transform_detail(raw, job_id, url_loker, waktu_scrap)
            if detail:
                hasil.append(detail)
        else:
            print(f" - [Detail] job {job_id}: response kosong, dilewati.")

        if i < len(job_list):
            time.sleep(delay)

    print(f">> [EXTRACT] Detail berhasil di-fetch: {len(hasil)}/{len(job_list)}")
    return hasil