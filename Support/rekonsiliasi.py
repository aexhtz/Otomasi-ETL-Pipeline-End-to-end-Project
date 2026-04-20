"""
=============================================================
Cara kerja:
  1. Scrape listing JobStreet sebanyak MAX_HALAMAN halaman
     (default 5 halaman = ~250 job_id untuk sampel representatif)
  2. Bandingkan dengan job_id aktif di database
  3. Tandai yang tidak muncul lagi sebagai nonaktif
  4. Catat di tabel riwayat_status_loker

Kenapa dipisah dari ETL:
  - ETL berjalan setiap 3 jam, hanya scrape 1 halaman
  - Rekonsiliasi butuh scrape lebih banyak halaman agar akurat
  - Jika digabung, ETL akan jadi lambat setiap 3 jam
  - Dengan dipisah, komputasi berat hanya terjadi sekali seminggu
=============================================================
"""

import os
import ETL.Extract.scraper_listing as listing
import Support.reconciler      as reconcile

MAX_HALAMAN = int(os.getenv("MAX_HALAMAN", "5"))

def main():
    print("=" * 55)
    print("  REKONSILIASI MINGGUAN — JobStreet")
    print(f"  Scraping {MAX_HALAMAN} halaman untuk akurasi optimal")
    print("=" * 55)

    # Scrape listing lebih banyak halaman untuk hasil akurat
    print(f"\n[Scraping] Mengambil job ID dari {MAX_HALAMAN} halaman listing")
    scraped_list = listing.get_semua_job_id(max_halaman=MAX_HALAMAN)

    if not scraped_list:
        print("[Rekonsil] Tidak ada data dari scraping, rekonsiliasi dibatalkan")
        return

    # Jalankan rekonsiliasi
    ringkasan = reconcile.rekonsiliasi(scraped_list)

    # Laporan akhir
    print("\n" + "-" * 55)
    print("  Rekonsiliasi selesai.")
    print(f"  Halaman discrape   : {MAX_HALAMAN}")
    print(f"  Job terlihat       : {ringkasan['total_scraped']}")
    print(f"  Aktif di DB        : {ringkasan['total_aktif_db']}")
    print(f"  Masih aktif        : {ringkasan['masih_aktif']}")
    print(f"  Baru ditandai nonaktif: {ringkasan['baru_nonaktif']}")
    print("-" * 55)


if __name__ == "__main__":
    main()