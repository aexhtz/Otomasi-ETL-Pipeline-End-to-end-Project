"""
pipeline.py
Orchestrator utama ETL Pipeline JobStreet.

Alur:
  [E1] Extract listing   → scraper_listing.py  (HTML → job ID list)
  [E2] Extract detail    → scraper_detail.py   (GraphQL JSON → data mentah)
  [T]  Transform         → transformer.py      (data mentah → data terstruktur)
  [L]  Load              → Supabase (tabel lowongan_transformed) + CSV
"""

import pandas as pd
import config.konfigurasi_supabase as konfigurasi
import scraper_listing as listing
import scraper_detail  as detail
import transformer     as transform

# ─── Konfigurasi Pipeline ────────────────────────────────────────────────────

MAX_HALAMAN   = 1      # Jumlah halaman listing yang di-scrape
REQUEST_DELAY = 0.5    # Jeda antar request detail (detik)
OUTPUT_CSV    = "hasil_scrap_transformed.csv"

QUERY_INSERT = """
    INSERT INTO lowongan_transformed (
        job_id, url, posisi, perusahaan, perusahaan_verified,
        lokasi, klasifikasi, sub_klasifikasi, tipe_kerja, work_arrangement,
        gaji, deskripsi_singkat,
        "waktuPostingLoker", "waktuExpiredLoker", "waktuScrapLoker",
        status, "isExpired", "isPrivateAdvertiser",
        company_industry, company_size, company_website,
        company_rating, company_total_review,
        tahun, bulan, nama_bulan, hari, jam_posting,
        hari_minggu, nama_hari, kuartal, tanggal_posting,
        gaji_min, gaji_max, gaji_midpoint, gaji_disclosed, gaji_periode,
        jumlah_skill, skill_string,
        kota_standar, provinsi_standar, is_remote,
        tipe_kerja_std, work_arrangement_std,
        hari_tayang, is_active, hari_tersisa, hari_sejak_post,
        kategori_besar, sub_klasifikasi_std
    )
    VALUES (
        %s,%s,%s,%s,%s, %s,%s,%s,%s,%s, %s,%s,
        %s,%s,%s, %s,%s,%s, %s,%s,%s, %s,%s,
        %s,%s,%s,%s,%s, %s,%s,%s,%s,
        %s,%s,%s,%s,%s,
        %s,%s,
        %s,%s,%s,
        %s,%s,
        %s,%s,%s,%s,
        %s,%s
    )
    ON CONFLICT (url)
    DO UPDATE SET
        "waktuScrapLoker" = EXCLUDED."waktuScrapLoker",
        status            = EXCLUDED.status,
        "isExpired"       = EXCLUDED."isExpired",
        is_active         = EXCLUDED.is_active,
        hari_tersisa      = EXCLUDED.hari_tersisa,
        hari_sejak_post   = EXCLUDED.hari_sejak_post;
"""


# ─── Load Functions ──────────────────────────────────────────────────────────

def simpan_ke_csv(data: list[dict], output_path: str) -> None:
    """Simpan hasil transform ke CSV — kolom list/dict di-drop."""
    df = pd.DataFrame(data)
    for col in ["skills_ditemukan", "skills_kategori"]:
        if col in df.columns:
            df.drop(columns=[col], inplace=True)
    df.to_csv(output_path, index=False, encoding="utf-8-sig")
    print(f"\n[LOAD] CSV tersimpan: {output_path} ({len(data)} baris)")


def simpan_ke_database(data: list[dict]) -> None:
    """Batch insert hasil transform ke tabel lowongan_transformed di Supabase."""

    def v(d, key):
        val = d.get(key)
        return None if isinstance(val, (list, dict)) else val

    values = [
        (
            v(d,"job_id"), v(d,"url"), v(d,"posisi"), v(d,"perusahaan"), v(d,"perusahaan_verified"),
            v(d,"lokasi"), v(d,"klasifikasi"), v(d,"sub_klasifikasi"), v(d,"tipe_kerja"), v(d,"work_arrangement"),
            v(d,"gaji"), v(d,"deskripsi_singkat"),
            v(d,"waktuPostingLoker"), v(d,"waktuExpiredLoker"), v(d,"waktuScrapLoker"),
            v(d,"status"), v(d,"isExpired"), v(d,"isPrivateAdvertiser"),
            v(d,"company_industry"), v(d,"company_size"), v(d,"company_website"),
            v(d,"company_rating"), v(d,"company_total_review"),
            v(d,"tahun"), v(d,"bulan"), v(d,"nama_bulan"), v(d,"hari"), v(d,"jam_posting"),
            v(d,"hari_minggu"), v(d,"nama_hari"), v(d,"kuartal"), v(d,"tanggal_posting"),
            v(d,"gaji_min"), v(d,"gaji_max"), v(d,"gaji_midpoint"), v(d,"gaji_disclosed"), v(d,"gaji_periode"),
            v(d,"jumlah_skill"), v(d,"skill_string"),
            v(d,"kota_standar"), v(d,"provinsi_standar"), v(d,"is_remote"),
            v(d,"tipe_kerja_std"), v(d,"work_arrangement_std"),
            v(d,"hari_tayang"), v(d,"is_active"), v(d,"hari_tersisa"), v(d,"hari_sejak_post"),
            v(d,"kategori_besar"), v(d,"sub_klasifikasi_std"),
        )
        for d in data
    ]

    cursor = konfigurasi.sql.cursor()
    try:
        cursor.executemany(QUERY_INSERT, values)
        konfigurasi.sql.commit()
        print(f"[LOAD] {len(values)} data berhasil disimpan ke database.")
    except Exception as e:
        konfigurasi.sql.rollback()
        print(f"[LOAD] ERROR saat insert database: {e}")
        raise
    finally:
        cursor.close()
        konfigurasi.sql.close()


# ─── Main Pipeline ───────────────────────────────────────────────────────────

def main():
    print("=" * 55)
    print("  ETL PIPELINE — JobStreet (GraphQL + Transform)")
    print("=" * 55)

    # [E1] Extract listing → job ID
    job_id_list = listing.get_semua_job_id(max_halaman=MAX_HALAMAN)
    if not job_id_list:
        print("\n[PIPELINE] Tidak ada job ID ditemukan. Pipeline dihentikan.")
        return

    # [E2] Extract detail via GraphQL
    hasil_mentah = detail.get_semua_detail(job_id_list, delay=REQUEST_DELAY)
    if not hasil_mentah:
        print("\n[PIPELINE] Tidak ada detail berhasil di-fetch. Pipeline dihentikan.")
        return

    # [T] Transform
    hasil_transformed = transform.transform_semua(hasil_mentah)
    if not hasil_transformed:
        print("\n[PIPELINE] Transform gagal semua. Pipeline dihentikan.")
        return

    # [L] Load → CSV + Database
    print("\n[LOAD] Menyimpan hasil transform...")
    simpan_ke_csv(hasil_transformed, OUTPUT_CSV)
    simpan_ke_database(hasil_transformed)

    print("\n" + "=" * 55)
    print(f"  Pipeline selesai.")
    print(f"  Loker di-extract  : {len(hasil_mentah)}")
    print(f"  Loker di-transform: {len(hasil_transformed)}")
    print("=" * 55 + "\n")


if __name__ == "__main__":
    main()