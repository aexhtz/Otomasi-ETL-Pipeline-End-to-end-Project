"""
Alur per run:
  [E1] Scrape listing HTML      → job_id list
  [CHECK] Query fact_lowongan   → existing job_id
  [FILTER] Pisah baru vs lama
  [E2] GraphQL detail           → data mentah (hanya job baru)
  [T]  Transform 7 dimensi
  [L]  Load ke star schema:
         dim_perusahaan  (upsert)
         dim_lokasi      (upsert)
         dim_waktu       (upsert)
         dim_klasifikasi (upsert)
         fact_lowongan   (insert)
         bridge_skill    (insert)
  [UPDATE] Update waktuScrap loker lama
"""

import os
import sys
import pandas as pd
import config.konfigurasi_supabase as konfigurasi
import ETL.Extract.scraper_listing as listing
import ETL.Extract.scraper_detail  as detail
import ETL.Transform.transformer     as transform
from Support.logger import setup_logger

MAX_HALAMAN   = int(os.getenv("MAX_HALAMAN", "2"))
REQUEST_DELAY = float(os.getenv("REQUEST_DELAY", "0.5"))
OUTPUT_CSV    = os.getenv("OUTPUT_CSV", "hasil_scrap.csv")
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
DISCORD_ERROR_WEBHOOK_URL = os.getenv("DISCORD_ERROR_WEBHOOK_URL")
DISCORD_WARNING_WEBHOOK_URL = os.getenv("DISCORD_WARNING_WEBHOOK_URL")

os.makedirs("logs/pipeline", exist_ok=True)
logger = setup_logger(
    "pipeline",
    log_file="logs/pipeline/pipeline.log",
    discord_webhook_url=DISCORD_WEBHOOK_URL,
    discord_error_webhook_url=DISCORD_ERROR_WEBHOOK_URL,
    discord_warning_webhook_url=DISCORD_WARNING_WEBHOOK_URL,
)

# ---- Incremental

def get_existing_job_ids() -> set[str]:
    """Ambil semua job_id yang sudah ada di fact_lowongan."""
    cur = konfigurasi.sql.cursor()
    try:
        cur.execute("SELECT job_id FROM fact_lowongan WHERE job_id IS NOT NULL;")
        existing = {row[0] for row in cur.fetchall()}
        print(f" - [Incremental] Sudah ada di database: {len(existing)} loker")
        return existing
    except Exception as e:
        print(f" - [Incremental] Error: {e}")
        return set()
    finally:
        cur.close()

def filter_job_baru(scraped_list, existing_ids):
    job_baru = [x for x in scraped_list if x["job_id"] not in existing_ids]
    job_lama = [x for x in scraped_list if x["job_id"] in existing_ids]
    print(f" - [Incremental] Job Baru: {len(job_baru)} | Job Lama: {len(job_lama)}")
    return job_baru, job_lama

def update_waktu_scrap_lama(job_lama: list[dict]) -> None:
    """Perbarui waktuScrapLoker untuk loker lama yang masih muncul di listing."""
    if not job_lama:
        return
    from datetime import datetime, timezone
    sekarang = datetime.now(timezone.utc)
    values = [(sekarang, item["job_id"]) for item in job_lama]
    cur = konfigurasi.sql.cursor()
    try:
        cur.executemany(
            'UPDATE fact_lowongan SET "waktuScrapLoker" = %s WHERE job_id = %s;',
            values
        )
        konfigurasi.sql.commit()
        print(f" - [Incremental] {len(values)} loker lama waktu scrap diperbarui")
    except Exception as e:
        konfigurasi.sql.rollback()
        print(f" - [Incremental] ERROR update lama: {e}")
    finally:
        cur.close()


# ---- Load Dimensi
def upsert_dim_perusahaan(data: list[dict]) -> dict[str, int]:
    """
    Insert/update dim_perusahaan.
    Return: dict {nama_perusahaan: id}
    """
    rows = {}
    for d in data:
        nama = d.get("perusahaan")
        if nama and nama not in rows:
            rows[nama] = {
                "nama_perusahaan" : nama,
                "industry"        : d.get("company_industry"),
                "ukuran_perusahaan": d.get("company_size"),
                "website"         : d.get("company_website"),
                "rating"          : d.get("company_rating"),
                "total_review"    : d.get("company_total_review"),
                "is_verified"     : d.get("perusahaan_verified") or False,
            }

    if not rows:
        return {}

    values = list(rows.values())
    cur = konfigurasi.sql.cursor()
    try:
        cur.executemany("""
            INSERT INTO dim_perusahaan
                (nama_perusahaan, industry, ukuran_perusahaan, website, rating, total_review, is_verified)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (nama_perusahaan)
            DO UPDATE SET
                industry          = COALESCE(EXCLUDED.industry, dim_perusahaan.industry),
                ukuran_perusahaan = COALESCE(EXCLUDED.ukuran_perusahaan, dim_perusahaan.ukuran_perusahaan),
                website           = COALESCE(EXCLUDED.website, dim_perusahaan.website),
                rating            = COALESCE(EXCLUDED.rating, dim_perusahaan.rating),
                total_review      = COALESCE(EXCLUDED.total_review, dim_perusahaan.total_review);
        """, [(
            v["nama_perusahaan"], v["industry"], v["ukuran_perusahaan"],
            v["website"], v["rating"], v["total_review"], v["is_verified"]
        ) for v in values])
        konfigurasi.sql.commit()

        # ---- Ambil ID hasil upsert
        nama_list = list(rows.keys())
        cur.execute(
            "SELECT id, nama_perusahaan FROM dim_perusahaan WHERE nama_perusahaan = ANY(%s)",
            (nama_list,)
        )
        return {row[1]: row[0] for row in cur.fetchall()}
    finally:
        cur.close()


def upsert_dim_lokasi(data: list[dict]) -> dict[tuple, int]:
    """
    Insert/update dim_lokasi.
    Return: dict {(kota_standar, is_remote): id}
    """
    rows = {}
    for d in data:
        kota    = d.get("kota_standar") or "Tidak Diketahui"
        remote  = d.get("is_remote") or False
        key     = (kota, remote)
        if key not in rows:
            rows[key] = {
                "kota_standar"    : kota,
                "provinsi_standar": d.get("provinsi_standar"),
                "lokasi_negara"   : "Indonesia",
                "is_remote"       : remote,
            }

    if not rows:
        return {}

    cur = konfigurasi.sql.cursor()
    try:
        cur.executemany("""
            INSERT INTO dim_lokasi (kota_standar, provinsi_standar, lokasi_negara, is_remote)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (kota_standar, is_remote) DO NOTHING;
        """, [(v["kota_standar"], v["provinsi_standar"], v["lokasi_negara"], v["is_remote"])
              for v in rows.values()])
        konfigurasi.sql.commit()

        keys = list(rows.keys())
        kota_list   = [k[0] for k in keys]
        remote_list = [k[1] for k in keys]
        cur.execute("""
            SELECT id, kota_standar, is_remote FROM dim_lokasi
            WHERE (kota_standar, is_remote) IN (
                SELECT unnest(%s::text[]), unnest(%s::bool[])
            )
        """, (kota_list, remote_list))
        return {(row[1], row[2]): row[0] for row in cur.fetchall()}
    finally:
        cur.close()


def upsert_dim_waktu(data: list[dict]) -> dict[str, int]:
    """
    Insert dim_waktu (satu baris per tanggal unik).
    Return: dict {tanggal_posting (str): id}
    """
    rows = {}
    for d in data:
        tgl = d.get("tanggal_posting")
        if tgl and tgl not in rows:
            rows[tgl] = {
                "tanggal_posting": tgl,
                "tahun"          : d.get("tahun"),
                "kuartal"        : d.get("kuartal"),
                "bulan"          : d.get("bulan"),
                "nama_bulan"     : d.get("nama_bulan"),
                "hari"           : d.get("hari"),
                "nama_hari"      : d.get("nama_hari"),
                "hari_minggu"    : d.get("hari_minggu"),
                "jam_posting"    : d.get("jam_posting"),
                "is_weekday"     : (d.get("hari_minggu") or 6) <= 4,
            }

    if not rows:
        return {}

    cur = konfigurasi.sql.cursor()
    try:
        cur.executemany("""
            INSERT INTO dim_waktu
                (tanggal_posting, tahun, kuartal, bulan, nama_bulan,
                 hari, nama_hari, hari_minggu, jam_posting, is_weekday)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (tanggal_posting) DO NOTHING;
        """, [(
            v["tanggal_posting"], v["tahun"], v["kuartal"], v["bulan"], v["nama_bulan"],
            v["hari"], v["nama_hari"], v["hari_minggu"], v["jam_posting"], v["is_weekday"]
        ) for v in rows.values()])
        konfigurasi.sql.commit()

        tgl_list = list(rows.keys())
        cur.execute(
            "SELECT id, tanggal_posting::TEXT FROM dim_waktu WHERE tanggal_posting = ANY(%s::date[])",
            (tgl_list,)
        )
        return {row[1]: row[0] for row in cur.fetchall()}
    finally:
        cur.close()


def upsert_dim_klasifikasi(data: list[dict]) -> dict[tuple, int]:
    """
    Insert dim_klasifikasi.
    Return: dict {(sub_klasifikasi, tipe_kerja_std, work_arrangement_std): id}
    """
    rows = {}
    for d in data:
        sub  = d.get("sub_klasifikasi_std") or "Tidak Disebutkan"
        tipe = d.get("tipe_kerja_std")      or "Tidak Disebutkan"
        arr  = d.get("work_arrangement_std") or "Tidak Disebutkan"
        key  = (sub, tipe, arr)
        if key not in rows:
            rows[key] = {
                "kategori_besar"      : d.get("kategori_besar") or "Lainnya",
                "sub_klasifikasi"     : sub,
                "tipe_kerja_std"      : tipe,
                "work_arrangement_std": arr,
            }

    if not rows:
        return {}

    cur = konfigurasi.sql.cursor()
    try:
        cur.executemany("""
            INSERT INTO dim_klasifikasi
                (kategori_besar, sub_klasifikasi, tipe_kerja_std, work_arrangement_std)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (sub_klasifikasi, tipe_kerja_std, work_arrangement_std) DO NOTHING;
        """, [(v["kategori_besar"], v["sub_klasifikasi"], v["tipe_kerja_std"], v["work_arrangement_std"])
              for v in rows.values()])
        konfigurasi.sql.commit()

        cur.execute("""
            SELECT id, sub_klasifikasi, tipe_kerja_std, work_arrangement_std
            FROM dim_klasifikasi
        """)
        return {(row[1], row[2], row[3]): row[0] for row in cur.fetchall()}
    finally:
        cur.close()


# ---- Load Fact & Bridge

def insert_fact_lowongan(data: list[dict], id_perusahaan: dict,
                          id_lokasi: dict, id_waktu: dict,
                          id_klasifikasi: dict) -> None:
    """Insert ke fact_lowongan dengan FK yang sudah di-resolve."""

    def v(d, key):
        val = d.get(key)
        return None if isinstance(val, (list, dict)) else val

    values = []
    for d in data:
        kota    = d.get("kota_standar") or "Tidak Diketahui"
        remote  = d.get("is_remote") or False
        sub     = d.get("sub_klasifikasi_std") or "Tidak Disebutkan"
        tipe    = d.get("tipe_kerja_std")      or "Tidak Disebutkan"
        arr     = d.get("work_arrangement_std") or "Tidak Disebutkan"
        tgl     = str(d.get("tanggal_posting") or "")

        values.append((
            v(d,"job_id"),
            v(d,"url"),
            v(d,"posisi"),
            id_perusahaan.get(d.get("perusahaan")),
            id_lokasi.get((kota, remote)),
            id_waktu.get(tgl),
            id_klasifikasi.get((sub, tipe, arr)),
            v(d,"gaji_min"), v(d,"gaji_max"), v(d,"gaji_midpoint"),
            v(d,"gaji_disclosed") or False,
            v(d,"gaji_periode"),
            v(d,"jumlah_skill") or 0,
            v(d,"skill_string"),
            v(d,"hari_tayang"), v(d,"hari_sejak_post"), v(d,"hari_tersisa"),
            v(d,"is_active") or False,
            v(d,"isPrivateAdvertiser") or False,
            v(d,"waktuPostingLoker"),
            v(d,"waktuExpiredLoker"),
            v(d,"waktuScrapLoker"),
            v(d,"deskripsi_singkat"),
        ))

    cur = konfigurasi.sql.cursor()
    try:
        cur.executemany("""
            INSERT INTO fact_lowongan (
                job_id, url, posisi,
                dim_perusahaan_id, dim_lokasi_id, dim_waktu_id, dim_klasifikasi_id,
                gaji_min, gaji_max, gaji_midpoint, gaji_disclosed, gaji_periode,
                jumlah_skill, skill_string,
                hari_tayang, hari_sejak_post, hari_tersisa,
                is_active, is_private_advertiser,
                "waktuPostingLoker", "waktuExpiredLoker", "waktuScrapLoker",
                deskripsi_singkat
            )
            VALUES (
                %s,%s,%s, %s,%s,%s,%s,
                %s,%s,%s,%s,%s,
                %s,%s,
                %s,%s,%s,
                %s,%s,
                %s,%s,%s,
                %s
            )
            ON CONFLICT (job_id) DO NOTHING;
        """, values)
        konfigurasi.sql.commit()
        print(f" - [Load] {len(values)} loker masuk fact_lowongan")
    except Exception as e:
        konfigurasi.sql.rollback()
        print(f" - [Load] Error fact_lowongan: {e}")
        raise
    finally:
        cur.close()


def insert_bridge_skill(data: list[dict]) -> None:
    """Pecah skill_string ke baris terpisah di bridge_skill."""
    from ETL.Transform.transformer import KATEGORI_SKILL

    values = []
    for d in data:
        job_id = d.get("job_id")
        skill_string = d.get("skill_string") or ""
        if not job_id or not skill_string:
            continue
        for skill in skill_string.split(","):
            skill = skill.strip()
            if skill:
                values.append((job_id, skill, KATEGORI_SKILL.get(skill, "Lainnya")))

    if not values:
        print("  [Load] Tidak ada skill baru.")
        return

    cur = konfigurasi.sql.cursor()
    try:
        cur.executemany("""
            INSERT INTO bridge_skill (job_id, skill_name, kategori_skill)
            VALUES (%s, %s, %s)
            ON CONFLICT (job_id, skill_name) DO NOTHING;
        """, values)
        konfigurasi.sql.commit()
        print(f"  [Load] {len(values)} baris masuk bridge_skill.")
    except Exception as e:
        konfigurasi.sql.rollback()
        print(f"  [Load] ERROR bridge_skill: {e}")
    finally:
        cur.close()


def simpan_ke_csv(data: list[dict], output_path: str) -> None:
    df = pd.DataFrame(data)
    for col in ["skills_ditemukan", "skills_kategori"]:
        if col in df.columns:
            df.drop(columns=[col], inplace=True)
    df.to_csv(output_path, index=False, encoding="utf-8-sig")
    print(f"  [Load] CSV tersimpan: {output_path} ({len(data)} baris)")

# ---- Main pipeline

def main():
    print("-" * 50)
    print("  Project TA Otomasi ETL Pipeline")
    print(f"  Total page di scraping: {MAX_HALAMAN}")
    print(f"  Delay per scraping: {REQUEST_DELAY}s")
    print("-" * 50)

    # [E1] Scrape listing
    scraped_list = listing.get_semua_job_id(max_page_limit=MAX_HALAMAN)
    if not scraped_list:
        print("[Pipeline] Tidak ada job ID. Pipeline dihentikan.")
        return

    # [CHECK + FILTER] Incremental
    print("\n[Incremental] Mengecek JobID yang sudah ada")
    existing_ids = get_existing_job_ids()
    job_baru, job_lama = filter_job_baru(scraped_list, existing_ids)

    if job_lama:
        update_waktu_scrap_lama(job_lama)

    if not job_baru:
        print("\n[Pipeline] Tidak ada loker baru, Pipeline selesai lebih awal")
        return

    # [E2] Fetch detail GraphQL
    hasil_mentah = detail.get_semua_detail(job_baru, delay=REQUEST_DELAY)
    if not hasil_mentah:
        print("[Pipeline] Fetch detail gagal, Pipeline dihentikan")
        return

    # [T] Transform
    hasil = transform.transform_semua(hasil_mentah)
    if not hasil:
        return

    # [L] Load ke star schema
    print("\n[Load] Menyimpan ke star schema")

    print(" - [Load] Upsert dim_perusahaan")
    id_perusahaan = upsert_dim_perusahaan(hasil)

    print(" - [Load] Upsert dim_lokasi")
    id_lokasi = upsert_dim_lokasi(hasil)

    print(" - [Load] Upsert dim_waktu")
    id_waktu = upsert_dim_waktu(hasil)

    print(" - [Load] Upsert dim_klasifikasi")
    id_klasifikasi = upsert_dim_klasifikasi(hasil)

    print(" - [Load] Insert fact_lowongan")
    insert_fact_lowongan(hasil, id_perusahaan, id_lokasi, id_waktu, id_klasifikasi)

    print(" - [Load] Insert bridge_skill")
    insert_bridge_skill(hasil)

    # simpan_ke_csv(hasil, OUTPUT_CSV)

    print("\n" + "-" * 50)
    print(f"  Pipeline selesai")
    print(f"  Total listing  : {len(scraped_list)}")
    print(f"  Sudah ada di DB    : {len(job_lama)}")
    print(f"  Baru diproses  : {len(hasil)}")
    print("-" * 50 + "\n")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[Pipeline] Dihentikan manual oleh user.")
        sys.exit(130)
    except Exception:
        logger.exception("[Pipeline] Runtime stop karena error")
        raise
