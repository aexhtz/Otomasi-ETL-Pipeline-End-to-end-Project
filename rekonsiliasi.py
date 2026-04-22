"""
Dijalankan terpisah dari ETL pipeline, cukup sekali seminggu.
"""

import os
import ETL.Extract.scraper_listing as listing
import Support.reconciler      as reconcile

MAX_HALAMAN_REKONSILIASI = int(os.getenv("MAX_HALAMAN_REKONSILIASI", "55"))

def main():
    print("-" * 55)
    print("  REKONSILIASI — JobStreet")
    print(f"  MAX_HALAMAN_REKONSILIASI = {MAX_HALAMAN_REKONSILIASI}")
    print(f"  Threshold strategi 2 = {reconcile.THRESHOLD_HALAMAN} halaman")
    print("-" * 55)

    # Strategi 1 (expired-based) bisa jalan tanpa scraping
    # Tapi scraping tetap dibutuhkan untuk strategi 2 dan update timestamp
    print(f"\n[SCRAPE] Mengambil job ID dari {MAX_HALAMAN_REKONSILIASI} halaman...")
    scraped_list = listing.get_semua_job_id(max_page_limit=MAX_HALAMAN_REKONSILIASI)

    if not scraped_list:
        print("[RECONCILE] Scraping gagal — jalankan hanya strategi 1 (expired-based)...")
        # Tetap jalankan strategi 1 meski scraping gagal
        expired = reconcile.tandai_expired()
        print(f"  Expired ditandai: {expired}")
        return

    ringkasan = reconcile.rekonsiliasi(scraped_list, max_page_limit=MAX_HALAMAN_REKONSILIASI)

    print("\n" + "-" * 55)
    print("  Rekonsiliasi selesai.")
    print(f"  Job terlihat hari ini : {ringkasan['total_scraped']}")
    print(f"  Nonaktif by expired   : {ringkasan['expired_count']}")
    print(f"  Nonaktif by konsensus  : {ringkasan['konsensus_nonaktif']}")
    print(f"  Total baru nonaktif   : {ringkasan['total_nonaktif']}")
    print("-" * 55)

if __name__ == "__main__":
    main()