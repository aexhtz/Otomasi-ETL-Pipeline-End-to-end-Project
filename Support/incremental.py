"""
Logik incremental untuk ETL pipeline JobStreet.

Cara kerja:
  1. Ambil semua job_id yang sudah ada di database
  2. Bandingkan dengan job_id hasil scrape listing
  3. Hanya proses job_id yang BARU saja
  4. Update is_active & hari_tersisa untuk loker lama yang masih ada di listing
"""

import config.konfigurasi_supabase as konfigurasi


def get_existing_job_ids() -> set[str]:
    """
    Ambil semua job_id yang sudah ada di tabel lowongan_transformed.
    Return: set of string job_id
    """
    query = 'SELECT job_id FROM lowongan_transformed WHERE job_id IS NOT NULL;'
    cursor = konfigurasi.sql.cursor()
    try:
        cursor.execute(query)
        rows = cursor.fetchall()
        existing = {row[0] for row in rows}
        print(f"  [incremental] Job ID sudah ada di DB: {len(existing)}")
        return existing
    except Exception as e:
        print(f"  [incremental] ERROR ambil existing job_id: {e}")
        return set()
    finally:
        cursor.close()


def filter_job_baru(scraped_list: list[dict], existing_ids: set[str]) -> tuple[list[dict], list[dict]]:
    """
    Pisahkan antara loker baru dan loker lama.

    Return:
        job_baru  : list[dict] — job_id belum ada di DB → perlu di-fetch detail
        job_lama  : list[dict] — job_id sudah ada di DB → cukup update status
    """
    job_baru = []
    job_lama = []

    for item in scraped_list:
        if item["job_id"] not in existing_ids:
            job_baru.append(item)
        else:
            job_lama.append(item)

    print(f"  [incremental] Loker baru   : {len(job_baru)}")
    print(f"  [incremental] Loker lama   : {len(job_lama)} (sudah di DB, skip fetch)")
    return job_baru, job_lama

def update_status_loker_lama(job_lama: list[dict]) -> None:
    """
    Update kolom is_active, hari_tersisa, hari_sejak_post, waktuScrapLoker
    untuk loker lama yang masih muncul di listing (artinya masih aktif).
    """
    if not job_lama:
        return

    from datetime import datetime, timezone

    sekarang = datetime.now(timezone.utc)
    query = """
        UPDATE lowongan_transformed
        SET
            "waktuScrapLoker" = %s,
            hari_sejak_post   = EXTRACT(DAY FROM (%s - "waktuPostingLoker"))::INTEGER
        WHERE job_id = %s;
    """

    values = [
        (sekarang, sekarang, item["job_id"])
        for item in job_lama
    ]

    cursor = konfigurasi.sql.cursor()
    try:
        cursor.executemany(query, values)
        konfigurasi.sql.commit()
        print(f"  [incremental] {len(values)} loker lama waktu scrap-nya diperbarui.")
    except Exception as e:
        konfigurasi.sql.rollback()
        print(f"  [incremental] ERROR update loker lama: {e}")
    finally:
        cursor.close()