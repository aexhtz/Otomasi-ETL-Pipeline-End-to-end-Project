from datetime import datetime, timedelta
import re

def parse_relative_time(text):
    now = datetime.now()

    if "menit" in text:
        minutes = int(re.search(r"\d+", text).group())
        return now - timedelta(minutes=minutes)

    elif "jam" in text:
        hours = int(re.search(r"\d+", text).group())
        return now - timedelta(hours=hours)

    elif "hari" in text:
        days = int(re.search(r"\d+", text).group())
        return now - timedelta(days=days)

    else:
        return now