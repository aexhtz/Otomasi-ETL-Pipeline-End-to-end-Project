import logging
import json
import sys
from datetime import datetime, timezone

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

        return json.dumps(log_record)


def setup_logger(name: str, log_file: str | None = None):
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

    return logger