"""
=============================================================
Modul rekonsiliasi data — mendeteksi loker yang sudah tidak
ada di JobStreet dan menandainya sebagai nonaktif di database.

Cara kerja:
  1. Ambil semua job_id yang terlihat di listing hari ini
  2. Bandingkan dengan job_id yang masih berstatus 'aktif' di DB
  3. Yang tidak muncul lagi → tandai nonaktif (SOFT DELETE)
  4. Catat perubahan di tabel riwayat_status_loker
  5. Data TIDAK dihapus — tetap ada untuk analisis historis

Dipanggil dari pipeline.py setelah scraping selesai.
=============================================================
"""

import os
from datetime import datetime, timezone
import psycopg2
import config.konfigurasi_supabase as konfigurasi

def get_job_ids_aktif_di_db() -> set[str]:
    """Ambil semua job_id yang masih berstatus aktif di database."""
    cur = konfigurasi.sql.cursor()
    try:
        cur.execute("""
            SELECT job_id
            FROM fact_lowongan
            WHERE is_active = true
              AND status_loker = 'aktif'
              AND job_id IS NOT NULL;
        """)
        hasil = {row[0] for row in cur.fetchall()}
        print(f"  [RECONCILE] Job aktif di DB    : {len(hasil)}")
        return hasil
    finally:
        cur.close()


def deteksi_loker_hilang(
    job_ids_di_db: set[str],
    job_ids_scraped: set[str]
) -> set[str]:
    """
    Bandingkan job ID di DB vs hasil scraping hari ini.
    Yang ada di DB tapi tidak ada di scraping = kemungkinan sudah hilang.
    """
    hilang = job_ids_di_db - job_ids_scraped
    print(f"  [RECONCILE] Job terlihat hari ini: {len(job_ids_scraped)}")
    print(f"  [RECONCILE] Job diduga hilang     : {len(hilang)}")
    return hilang


def tandai_nonaktif(job_ids_hilang: set[str], alasan: str = "tidak_muncul_di_listing") -> int:
    """
    Soft delete — tandai loker yang hilang sebagai nonaktif.
    Data TIDAK dihapus dari database.

    Return: jumlah loker yang berhasil ditandai
    """
    if not job_ids_hilang:
        print("  [RECONCILE] Tidak ada loker yang perlu ditandai nonaktif.")
        return 0

    sekarang    = datetime.now(timezone.utc)
    job_id_list = list(job_ids_hilang)

    cur = konfigurasi.sql.cursor()
    try:
        # Update status di fact_lowongan
        cur.execute("""
            UPDATE fact_lowongan
            SET
                is_active        = false,
                status_loker     = 'nonaktif',
                pertama_hilang   = CASE
                                       WHEN pertama_hilang IS NULL
                                       THEN %s
                                       ELSE pertama_hilang
                                   END,
                alasan_nonaktif  = %s,
                "waktuScrapLoker" = %s
            WHERE job_id = ANY(%s)
              AND status_loker = 'aktif';
        """, (sekarang, alasan, sekarang, job_id_list))

        jumlah_update = cur.rowcount

        # Catat di tabel riwayat
        riwayat_values = [
            (job_id, 'aktif', 'nonaktif', sekarang, alasan)
            for job_id in job_ids_hilang
        ]
        cur.executemany("""
            INSERT INTO riwayat_status_loker
                (job_id, status_lama, status_baru, waktu_perubahan, keterangan)
            VALUES (%s, %s, %s, %s, %s);
        """, riwayat_values)

        konfigurasi.sql.commit()
        print(f"  [RECONCILE] {jumlah_update} loker ditandai nonaktif.")
        return jumlah_update

    except Exception as e:
        konfigurasi.sql.rollback()
        print(f"  [RECONCILE] ERROR: {e}")
        raise
    finally:
        cur.close()


def update_terakhir_terlihat(job_ids_masih_ada: set[str]) -> None:
    """
    Update kolom terakhir_terlihat untuk loker yang masih muncul
    di listing — sebagai bukti loker ini masih aktif hari ini.
    """
    if not job_ids_masih_ada:
        return

    sekarang = datetime.now(timezone.utc)
    cur = konfigurasi.sql.cursor()
    try:
        cur.execute("""
            UPDATE fact_lowongan
            SET terakhir_terlihat = %s
            WHERE job_id = ANY(%s)
              AND status_loker = 'aktif';
        """, (sekarang, list(job_ids_masih_ada)))

        konfigurasi.sql.commit()
        print(f"  [RECONCILE] {cur.rowcount} loker diperbarui waktu terakhir terlihat.")
    except Exception as e:
        konfigurasi.sql.rollback()
        print(f"  [RECONCILE] ERROR update terakhir_terlihat: {e}")
    finally:
        cur.close()


def rekonsiliasi(scraped_list: list[dict]) -> dict:
    """
    Entry point — jalankan rekonsiliasi penuh.

    Parameter:
        scraped_list : hasil dari scraper_listing.get_semua_job_id()
                       (semua job_id yang terlihat di listing hari ini)

    Return:
        dict berisi ringkasan hasil rekonsiliasi
    """
    print("\n[RECONCILE] Memulai rekonsiliasi data...")

    # Set job_id dari hasil scraping hari ini
    job_ids_scraped = {item["job_id"] for item in scraped_list}

    # Set job_id yang aktif di DB
    job_ids_aktif_db = get_job_ids_aktif_di_db()

    # Deteksi yang hilang
    job_ids_hilang    = deteksi_loker_hilang(job_ids_aktif_db, job_ids_scraped)
    job_ids_masih_ada = job_ids_aktif_db & job_ids_scraped

    # Tandai yang hilang sebagai nonaktif
    jumlah_nonaktif = tandai_nonaktif(job_ids_hilang)

    # Update timestamp loker yang masih ada
    update_terakhir_terlihat(job_ids_masih_ada)

    ringkasan = {
        "total_aktif_db"   : len(job_ids_aktif_db),
        "total_scraped"    : len(job_ids_scraped),
        "masih_aktif"      : len(job_ids_masih_ada),
        "baru_nonaktif"    : jumlah_nonaktif,
    }

    print(f"  [RECONCILE] Selesai.")
    return ringkasan