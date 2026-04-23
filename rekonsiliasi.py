"""
Dijalankan terpisah dari ETL pipeline, cukup sekali seminggu.
"""

import os
from datetime import datetime

import ETL.Extract.scraper_listing as listing
import Support.reconciler as reconcile
from Support.logger import setup_logger


# ==============================
# SETUP LOGGER (SAMA SEPERTI PIPELINE)
# ==============================
logger = setup_logger(
    "reconciler",
    log_file=f"logs/reconciler/rekonsiliasi.log"
)

# ==============================
# CONFIG
# ==============================
MAX_HALAMAN_REKONSILIASI = int(
    os.getenv("MAX_HALAMAN_REKONSILIASI", "55")
)


def main():
    logger.info("reconcile_start", extra={
        "event": "RECONCILE_START",
        "max_halaman": MAX_HALAMAN_REKONSILIASI,
        "threshold_tidak_terlihat": reconcile.THRESHOLD_TIDAK_TERLIHAT,
        "threshold_halaman": reconcile.THRESHOLD_HALAMAN
    })

    # ==============================
    # SCRAPING
    # ==============================
    try:
        scraped_list = listing.get_semua_job_id(
            max_page_limit=MAX_HALAMAN_REKONSILIASI
        )

        logger.info("scrape_done", extra={
            "total_scraped": len(scraped_list)
        })

    except Exception as e:
        logger.error("scrape_error", extra={
            "error": str(e)
        }, exc_info=True)

        scraped_list = []

    # ==============================
    # JIKA SCRAPING GAGAL
    # ==============================
    if not scraped_list:
        logger.warning("scrape_empty_run_strategy_1")

        try:
            expired = reconcile.tandai_expired()

            logger.info("strategy_1_done", extra={
                "expired_count": expired
            })

        except Exception as e:
            logger.error("strategy_1_error", extra={
                "error": str(e)
            }, exc_info=True)

        return

    # ==============================
    # REKONSILIASI
    # ==============================
    try:
        ringkasan = reconcile.rekonsiliasi(
            scraped_list,
            max_page_limit=MAX_HALAMAN_REKONSILIASI
        )

        logger.info("reconcile_done", extra=ringkasan)

    except Exception as e:
        logger.error("reconcile_error", extra={
            "error": str(e)
        }, exc_info=True)

        return

    # ==============================
    # SUMMARY
    # ==============================
    logger.info("reconcile_summary", extra={
        "total_scraped": ringkasan["total_scraped"],
        "expired": ringkasan["expired_count"],
        "konsensus": ringkasan["konsensus_nonaktif"],
        "total_nonaktif": ringkasan["total_nonaktif"]
    })


if __name__ == "__main__":
    main()