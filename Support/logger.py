import logging
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
import re

import requests

RESERVED_LOG_RECORD_KEYS = {
    "args", "asctime", "created", "exc_info", "exc_text", "filename",
    "funcName", "levelname", "levelno", "lineno", "message", "module",
    "msecs", "msg", "name", "pathname", "process", "processName",
    "relativeCreated", "stack_info", "thread", "threadName",
}

class JsonFormatter(logging.Formatter):
    def format(self, record):
        log_record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "module": record.name,
            "message": record.getMessage(),
        }

        # kalau ada extra fields (opsional)
        if hasattr(record, "extra"):
            log_record.update(record.extra)

        for key, value in record.__dict__.items():
            if key not in RESERVED_LOG_RECORD_KEYS and key not in log_record:
                log_record[key] = value

        if record.exc_info:
            log_record["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_record)


class DiscordWebhookHandler(logging.Handler):
    """Kirim log ke Discord webhook untuk level tertentu."""

    def __init__(self, webhook_url: str, min_level: int, max_level: int | None = None):
        super().__init__(level=min_level)
        self.webhook_url = webhook_url
        self.min_level = min_level
        self.max_level = max_level

    def _friendly_title(self, record) -> str:
        titles = {
            "page1_validation_failed": "Validasi halaman pertama gagal",
            "page_load_failed": "Halaman listing gagal dimuat",
            "page_selector_failed": "Daftar lowongan tidak muncul",
            "mode_50_detected": "Mode listing berubah",
            "page1_not_ideal": "Jumlah lowongan halaman pertama tidak ideal",
            "retry_selector": "Menunggu daftar lowongan lebih lama",
            "stop_no_response": "Scraper berhenti karena halaman tidak merespons",
            "stop_no_new_jobs": "Scraper berhenti karena tidak ada job baru",
            "stop_max_page_limit": "Scraper mencapai batas halaman",
            "mode_changed_to_50": "Mode listing berubah saat scraping",
            "skip_article_error": "Satu item lowongan dilewati",
            "Runtime stop karena error": "Pipeline berhenti karena error",
        }
        return titles.get(record.getMessage(), record.getMessage().replace("_", " ").title())

    def _attachment_paths(self, record) -> list[Path]:
        paths = []
        for attr in ("screenshot_path", "html_path"):
            path = getattr(record, attr, None)
            if path and Path(path).is_file():
                paths.append(Path(path))
        return paths

    def _friendly_summary(self, record) -> str:
        error = getattr(record, "error", None)
        if not error and record.exc_info:
            error = str(record.exc_info[1])

        if not error:
            if record.levelno == logging.WARNING:
                return "Ada kondisi yang perlu dipantau, tetapi pipeline belum tentu berhenti."
            return "Terjadi error saat pipeline berjalan."

        error_text = re.sub(r"\s+", " ", str(error)).strip()

        if "Timeout" in error_text and "wait_for_selector" in error_text:
            return (
                "Scraper sudah membuka halaman, tetapi daftar lowongan tidak muncul "
                "dalam batas waktu tunggu. Kemungkinan halaman lambat, selector berubah, "
                "atau situs menampilkan halaman verifikasi."
            )

        if "Timeout" in error_text:
            return "Halaman membutuhkan waktu terlalu lama untuk merespons."

        if len(error_text) > 220:
            return error_text[:220] + "..."
        return error_text

    def _build_embed(self, record) -> dict:
        color = 0xE74C3C if record.levelno >= logging.ERROR else 0xF1C40F
        fields = [
            {"name": "Module", "value": record.name, "inline": True},
            {"name": "Level", "value": record.levelname, "inline": True},
        ]

        page = getattr(record, "page", None) or getattr(record, "debug_page", None)
        if page is not None:
            fields.append({"name": "Page", "value": str(page), "inline": True})

        session_attempt = getattr(record, "session_attempt", None)
        if session_attempt is not None:
            fields.append({"name": "Session", "value": str(session_attempt), "inline": True})

        current_url = getattr(record, "current_url", None)
        if current_url:
            fields.append({"name": "URL", "value": current_url[:1024], "inline": False})

        screenshot_path = getattr(record, "screenshot_path", None)
        html_path = getattr(record, "html_path", None)
        artifacts = []
        if screenshot_path:
            artifacts.append(f"Screenshot: `{screenshot_path}`")
        if html_path:
            artifacts.append(f"HTML: `{html_path}`")
        if artifacts:
            fields.append({"name": "Debug file", "value": "\n".join(artifacts)[:1024], "inline": False})

        return {
            "title": self._friendly_title(record),
            "description": self._friendly_summary(record),
            "color": color,
            "fields": fields,
            "footer": {"text": "Project TA ETL Pipeline"},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def emit(self, record):
        if record.levelno < self.min_level:
            return
        if self.max_level is not None and record.levelno > self.max_level:
            return

        try:
            attachment_paths = self._attachment_paths(record)
            content = (
                "**Pipeline butuh perhatian**"
                if record.levelno >= logging.ERROR
                else "**Monitoring warning pipeline**"
            )
            payload = {
                "content": content,
                "username": "Pipeline Logger",
                "embeds": [self._build_embed(record)],
            }

            if attachment_paths:
                opened_files = []
                try:
                    files = []
                    for index, path in enumerate(attachment_paths):
                        content_type = "image/png" if path.suffix.lower() == ".png" else "text/html"
                        file_obj = open(path, "rb")
                        opened_files.append(file_obj)
                        files.append((f"files[{index}]", (path.name, file_obj, content_type)))

                    response = requests.post(
                        self.webhook_url,
                        data={"payload_json": json.dumps(payload)},
                        files=files,
                        timeout=20,
                    )
                finally:
                    for file_obj in opened_files:
                        file_obj.close()
            else:
                response = requests.post(self.webhook_url, json=payload, timeout=10)

            response.raise_for_status()

            for path in attachment_paths:
                try:
                    path.unlink()
                except FileNotFoundError:
                    pass
        except Exception:
            self.handleError(record)


def setup_logger(
    name: str,
    log_file: str | None = None,
    discord_webhook_url: str | None = None,
    discord_error_webhook_url: str | None = None,
    discord_warning_webhook_url: str | None = None,
):
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)

    # hindari duplicate handler
    if logger.handlers:
        return logger

    formatter = JsonFormatter()

    # console handler (GitHub Actions / terminal)
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    # file handler (opsional)
    if log_file:
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setFormatter(formatter)
        logger.addHandler(fh)

    error_webhook_url = discord_error_webhook_url or discord_webhook_url
    warning_webhook_url = discord_warning_webhook_url or discord_webhook_url

    if warning_webhook_url:
        warning_handler = DiscordWebhookHandler(
            warning_webhook_url,
            min_level=logging.WARNING,
            max_level=logging.WARNING,
        )
        warning_handler.setFormatter(formatter)
        logger.addHandler(warning_handler)

    if error_webhook_url:
        error_handler = DiscordWebhookHandler(
            error_webhook_url,
            min_level=logging.ERROR,
        )
        error_handler.setFormatter(formatter)
        logger.addHandler(error_handler)

    return logger
