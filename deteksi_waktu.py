from datetime import datetime as dt
from datetime import timedelta as td
import re

def scanwaktu(text):
    now = dt.now()

    if "menit" in text:
        menit = int(re.search(r"\d+", text).group())
        return now - td(minutes=menit)
    elif "jam" in text:
        jam = int(re.search(r"\d+", text).group())
        return now - td(hours=jam)
    elif "hari" in text:
        hari = int(re.search(r"\d+", text).group())
        return now - td(days=hari)
    else:
        return now

def waktuSaatIni():
    return dt.now()