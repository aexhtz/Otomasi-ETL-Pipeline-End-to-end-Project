"""
reconciler.py
=============================================================
Rekonsiliasi data dengan dua strategi:

STRATEGI 1 — Expired by date (selalu jalan):
  Tandai nonaktif berdasarkan waktuExpiredLoker < NOW()
  Akurat 100%, berdasarkan data JobStreet sendiri.

STRATEGI 2 — Konsensus 3x (jalan tiap rekonsiliasi):
  Loker ditandai nonaktif hanya jika tidak muncul dalam
  3 kali rekonsiliasi berturut-turut.
  Counter reset ke 0 jika loker muncul kembali.
=============================================================
"""

import os
from datetime import datetime, timezone
import config.konfigurasi_supabase as konfigurasi

# 2x tidak terlihat, otomatis di tandai tidak ada
THRESHOLD_TIDAK_TERLIHAT = int(os.getenv("RECONCILE_THRESHOLD", "2"))
THRESHOLD_HALAMAN = int(os.getenv("THRESHOLD_HALAMAN", "999"))

def pastikan_kolom_ada():
    """Pastikan kolom jumlah_tidak_terlihat sudah ada di fact_lowongan."""
    cur = konfigurasi.sql.cursor()
    try:
        cur.execute("""
            ALTER TABLE fact_lowongan
            ADD COLUMN IF NOT EXISTS jumlah_tidak_terlihat SMALLINT DEFAULT 0;
        """)
        konfigurasi.sql.commit()
    except Exception:
        konfigurasi.sql.rollback()
    finally:
        cur.close()

# ─── STRATEGI 1: EXPIRED BY DATE ────────────────────────────────

def tandai_expired() -> int:
    """Tandai nonaktif berdasarkan waktuExpiredLoker yang sudah lewat."""
    sekarang = datetime.now(timezone.utc)
    cur = konfigurasi.sql.cursor()
    try:
        cur.execute("""
            UPDATE fact_lowongan
            SET
                is_active        = false,
                status_loker     = 'nonaktif',
                pertama_hilang   = COALESCE(pertama_hilang, %s),
                alasan_nonaktif  = 'expired_by_date',
                "waktuScrapLoker" = %s
            WHERE is_active           = true
              AND status_loker        = 'aktif'
              AND "waktuExpiredLoker" IS NOT NULL
              AND "waktuExpiredLoker" < %s;
        """, (sekarang, sekarang, sekarang))

        jumlah = cur.rowcount

        if jumlah > 0:
            cur.execute("""
                INSERT INTO riwayat_status_loker
                    (job_id, status_lama, status_baru, waktu_perubahan, keterangan)
                SELECT job_id, 'aktif', 'nonaktif', %s, 'expired_by_date'
                FROM fact_lowongan
                WHERE alasan_nonaktif = 'expired_by_date'
                  AND pertama_hilang >= %s - INTERVAL '1 minute';
            """, (sekarang, sekarang))

        konfigurasi.sql.commit()
        print(f"  [S1] Expired by date : {jumlah} loker ditandai nonaktif.")
        return jumlah

    except Exception as e:
        konfigurasi.sql.rollback()
        print(f"  [S1] ERROR: {e}")
        raise
    finally:
        cur.close()

# ─── STRATEGI 2: KONSENSUS ───────────────────────────────────────

def get_job_ids_aktif_di_db() -> set[str]:
    """Ambil semua job_id yang masih aktif di database."""
    cur = konfigurasi.sql.cursor()
    try:
        cur.execute("""
            SELECT job_id FROM fact_lowongan
            WHERE is_active    = true
              AND status_loker = 'aktif'
              AND job_id IS NOT NULL;
        """)
        hasil = {row[0] for row in cur.fetchall()}
        print(f"  [S2] Job aktif di DB          : {len(hasil)}")
        return hasil
    finally:
        cur.close()

def update_konsensus(
    job_ids_aktif_db: set[str],
    job_ids_scraped: set[str]
) -> dict:
    """
    Update counter konsensus per loker:
      - Muncul di scraping  → reset counter = 0
      - Tidak muncul        → counter + 1
      - Counter >= threshold → tandai nonaktif
    """
    sekarang     = datetime.now(timezone.utc)
    masih_muncul = list(job_ids_aktif_db & job_ids_scraped)
    tidak_muncul = list(job_ids_aktif_db - job_ids_scraped)
    alasan       = f"tidak_terlihat_{THRESHOLD_TIDAK_TERLIHAT}x"

    print(f"  [S2] Masih muncul di scraping : {len(masih_muncul)}")
    print(f"  [S2] Tidak muncul hari ini    : {len(tidak_muncul)}")

    cur = konfigurasi.sql.cursor()
    try:
        # Yang masih muncul → reset counter dan update timestamp
        if masih_muncul:
            cur.execute("""
                UPDATE fact_lowongan
                SET
                    jumlah_tidak_terlihat = 0,
                    terakhir_terlihat     = %s
                WHERE job_id = ANY(%s)
                  AND status_loker = 'aktif';
            """, (sekarang, masih_muncul))

        # Yang tidak muncul → tambah counter 1
        if tidak_muncul:
            cur.execute("""
                UPDATE fact_lowongan
                SET jumlah_tidak_terlihat = jumlah_tidak_terlihat + 1
                WHERE job_id = ANY(%s)
                  AND status_loker = 'aktif';
            """, (tidak_muncul,))

        # Tandai nonaktif yang sudah >= threshold
        cur.execute("""
            UPDATE fact_lowongan
            SET
                is_active        = false,
                status_loker     = 'nonaktif',
                pertama_hilang   = COALESCE(pertama_hilang, %s),
                alasan_nonaktif  = %s,
                "waktuScrapLoker" = %s
            WHERE jumlah_tidak_terlihat >= %s
              AND status_loker = 'aktif';
        """, (sekarang, alasan, sekarang, THRESHOLD_TIDAK_TERLIHAT))

        baru_nonaktif = cur.rowcount

        # Catat di riwayat
        if baru_nonaktif > 0:
            cur.execute("""
                INSERT INTO riwayat_status_loker
                    (job_id, status_lama, status_baru, waktu_perubahan, keterangan)
                SELECT job_id, 'aktif', 'nonaktif', %s, %s
                FROM fact_lowongan
                WHERE alasan_nonaktif = %s
                  AND pertama_hilang >= %s - INTERVAL '1 minute';
            """, (sekarang, alasan, alasan, sekarang))

        konfigurasi.sql.commit()

        # Tampilkan distribusi counter saat ini (untuk monitoring)
        cur.execute("""
            SELECT jumlah_tidak_terlihat, COUNT(*) AS jumlah_loker
            FROM fact_lowongan
            WHERE status_loker = 'aktif'
              AND jumlah_tidak_terlihat > 0
            GROUP BY jumlah_tidak_terlihat
            ORDER BY jumlah_tidak_terlihat;
        """)
        distribusi = cur.fetchall()

        print(f"  [S2] Baru ditandai nonaktif   : {baru_nonaktif}")
        if distribusi:
            print(f"  [S2] Distribusi counter (loker yang belum nonaktif):")
            for counter, jml in distribusi:
                bar = "█" * counter
                sisa = THRESHOLD_TIDAK_TERLIHAT - counter
                print(f"       {bar} {counter}x → {jml} loker (perlu {sisa}x lagi)")

        return {
            "masih_muncul"  : len(masih_muncul),
            "tidak_muncul"  : len(tidak_muncul),
            "baru_nonaktif" : baru_nonaktif,
        }

    except Exception as e:
        konfigurasi.sql.rollback()
        print(f"  [S2] ERROR: {e}")
        raise
    finally:
        cur.close()

# ─── ENTRY POINT ─────────────────────────────────────────────────

def rekonsiliasi(scraped_list: list[dict], max_page_limit: int = 1) -> dict:
    """Jalankan rekonsiliasi lengkap dengan kedua strategi."""
    print(f"\n[RECONCILE] Memulai rekonsiliasi...")
    print(f"  Halaman discrape    : {max_page_limit}")
    print(f"  Threshold konsensus : {THRESHOLD_TIDAK_TERLIHAT}x tidak muncul")

    pastikan_kolom_ada()

    job_ids_scraped = {item["job_id"] for item in scraped_list}

    print("\n  --- Strategi 1: Expired by date ---")
    expired_count = tandai_expired()

    print("\n  --- Strategi 2: Konsensus ---")
    job_ids_aktif_db = get_job_ids_aktif_di_db()
    hasil_konsensus  = update_konsensus(job_ids_aktif_db, job_ids_scraped)

    total_nonaktif = expired_count + hasil_konsensus["baru_nonaktif"]
    print(f"\n  [RECONCILE] Total baru nonaktif: {total_nonaktif}")

    return {
        "total_scraped"      : len(job_ids_scraped),
        "expired_count"      : expired_count,
        "tidak_muncul_count" : hasil_konsensus["tidak_muncul"],
        "konsensus_nonaktif" : hasil_konsensus["baru_nonaktif"],
        "total_nonaktif"     : total_nonaktif,
    }