"""
transformer.py
Tahap Transform pada ETL Pipeline JobStreet.
Mengubah data mentah JSON menjadi data terstruktur siap visualisasi Looker Studio.

Transformasi yang dilakukan:
  1. Waktu  — pecah ISO timestamp ke komponen (tahun, bulan, hari, jam, hari_minggu)
  2. Gaji   — parse teks bebas ke gaji_min, gaji_max, gaji_midpoint, gaji_disclosed
  3. Skill  — ekstrak keyword teknologi dari deskripsi_lengkap
  4. Lokasi — normalisasi nama kota/provinsi ke bentuk standar
  5. Enum   — isi nilai null pada tipe_kerja & work_arrangement
  6. Durasi — hitung hari_tayang dan flag is_active dari expired date
  7. Klasifikasi — grouping sub-klasifikasi ke kategori besar
"""

import re
from datetime import datetime, timezone


# ══════════════════════════════════════════════════════════════════════════════
# 1. TRANSFORM WAKTU
# ══════════════════════════════════════════════════════════════════════════════

NAMA_HARI = {
    0: "Senin", 1: "Selasa", 2: "Rabu", 3: "Kamis",
    4: "Jumat", 5: "Sabtu", 6: "Minggu"
}

NAMA_BULAN = {
    1: "Januari", 2: "Februari", 3: "Maret", 4: "April",
    5: "Mei", 6: "Juni", 7: "Juli", 8: "Agustus",
    9: "September", 10: "Oktober", 11: "November", 12: "Desember"
}

def transform_waktu(iso_string: str | None) -> dict:
    """
    Pecah ISO 8601 timestamp ke komponen-komponen waktu.

    Input : "2026-04-06T18:54:13.000Z"
    Output: dict berisi tahun, bulan, nama_bulan, hari, jam,
            hari_minggu, nama_hari, kuartal, tanggal_posting (DATE)
    """
    if not iso_string:
        return {
            "tahun": None, "bulan": None, "nama_bulan": None,
            "hari": None, "jam": None, "hari_minggu": None,
            "nama_hari": None, "kuartal": None, "tanggal_posting": None,
        }

    try:
        # Handle format dengan atau tanpa milliseconds
        iso_clean = iso_string.replace("Z", "+00:00")
        dt = datetime.fromisoformat(iso_clean)

        return {
            "tahun"          : dt.year,
            "bulan"          : dt.month,
            "nama_bulan"     : NAMA_BULAN[dt.month],
            "hari"           : dt.day,
            "jam"            : dt.hour,
            "hari_minggu"    : dt.weekday(),        # 0=Senin, 6=Minggu
            "nama_hari"      : NAMA_HARI[dt.weekday()],
            "kuartal"        : f"Q{(dt.month - 1) // 3 + 1}",
            "tanggal_posting": dt.date().isoformat(), # "2026-04-06"
        }
    except (ValueError, KeyError) as e:
        print(f"  [transform_waktu] Gagal parse '{iso_string}': {e}")
        return {k: None for k in [
            "tahun","bulan","nama_bulan","hari","jam",
            "hari_minggu","nama_hari","kuartal","tanggal_posting"
        ]}


# ══════════════════════════════════════════════════════════════════════════════
# 2. TRANSFORM GAJI
# ══════════════════════════════════════════════════════════════════════════════

# Kata-kata yang menandakan gaji tidak disebutkan secara numerik
GAJI_NON_NUMERIK = [
    "kompetitif", "negotiable", "negosiasi", "attractive",
    "sesuai pengalaman", "tergantung pengalaman", "market rate",
    "to be discussed", "tbd", "competitive"
]

def _bersihkan_angka_gaji(teks: str) -> int | None:
    """Hapus karakter non-angka dan konversi ke integer."""
    angka = re.sub(r"[^\d]", "", teks)
    return int(angka) if angka else None

def _konversi_satuan(nilai: int, satuan: str) -> int:
    """Konversi satuan 'jt'/'juta'/'rb'/'ribu' ke nilai penuh."""
    satuan = satuan.lower().strip()
    if satuan in ("jt", "juta", "m"):
        return nilai * 1_000_000
    if satuan in ("rb", "ribu", "k"):
        return nilai * 1_000
    return nilai

def transform_gaji(gaji_raw: str | None) -> dict:
    """
    Parse string gaji bebas ke komponen numerik terstruktur.

    Contoh input yang ditangani:
      "IDR 8.000.000 – 15.000.000 per bulan"
      "Rp 8jt - 15jt/bulan"
      "8,000,000"
      "Kompetitif"
      None

    Output:
      gaji_min        : int   | None
      gaji_max        : int   | None
      gaji_midpoint   : int   | None   (rata-rata min+max)
      gaji_disclosed  : bool          (True jika ada angka)
      gaji_periode    : str   | None  ("bulan", "tahun", dll)
      gaji_teks_asli  : str   | None  (nilai asli untuk referensi)
    """
    default = {
        "gaji_min": None, "gaji_max": None, "gaji_midpoint": None,
        "gaji_disclosed": False, "gaji_periode": None, "gaji_teks_asli": None,
    }

    if not gaji_raw:
        return default

    teks = gaji_raw.strip()
    default["gaji_teks_asli"] = teks

    # Cek apakah gaji non-numerik (kompetitif, dll)
    teks_lower = teks.lower()
    for kata in GAJI_NON_NUMERIK:
        if kata in teks_lower:
            return default

    # Deteksi periode
    periode = None
    if re.search(r"per\s*bulan|/bulan|monthly", teks_lower):
        periode = "bulan"
    elif re.search(r"per\s*tahun|/tahun|per\s*year|annual", teks_lower):
        periode = "tahun"
    elif re.search(r"per\s*hari|/hari|daily", teks_lower):
        periode = "hari"

    # Pattern: angka dengan satuan jt/juta/rb/ribu
    # Contoh: "8jt", "8 juta", "15jt", "8.5jt"
    pattern_satuan = r"([\d.,]+)\s*(jt|juta|rb|ribu|m|k)\b"
    matches_satuan = re.findall(pattern_satuan, teks_lower)

    if matches_satuan:
        angka_list = []
        for angka_str, satuan in matches_satuan:
            angka_str = angka_str.replace(",", ".").replace(".", "")
            try:
                nilai = _konversi_satuan(int(float(angka_str.replace(",",".")
                                              if "." in angka_str else angka_str) * 1), satuan)
                # Re-parse lebih aman
                angka_bersih = re.sub(r"[^\d.]", "", angka_str)
                nilai = _konversi_satuan(int(float(angka_bersih)), satuan)
                angka_list.append(nilai)
            except (ValueError, TypeError):
                continue

        if angka_list:
            gaji_min = min(angka_list)
            gaji_max = max(angka_list) if len(angka_list) > 1 else None
            midpoint = int((gaji_min + gaji_max) / 2) if gaji_max else gaji_min
            return {
                "gaji_min"      : gaji_min,
                "gaji_max"      : gaji_max,
                "gaji_midpoint" : midpoint,
                "gaji_disclosed": True,
                "gaji_periode"  : periode,
                "gaji_teks_asli": teks,
            }

    # Pattern: angka besar langsung (misal: 8.000.000 atau 8,000,000)
    pattern_angka = r"[\d]{1,3}(?:[.,][\d]{3})+"
    matches_angka = re.findall(pattern_angka, teks)

    if matches_angka:
        angka_list = []
        for m in matches_angka:
            val = _bersihkan_angka_gaji(m)
            if val and val > 100_000:  # filter angka kecil yang bukan gaji
                angka_list.append(val)

        if angka_list:
            gaji_min = min(angka_list)
            gaji_max = max(angka_list) if len(angka_list) > 1 else None
            midpoint = int((gaji_min + gaji_max) / 2) if gaji_max else gaji_min
            return {
                "gaji_min"      : gaji_min,
                "gaji_max"      : gaji_max,
                "gaji_midpoint" : midpoint,
                "gaji_disclosed": True,
                "gaji_periode"  : periode,
                "gaji_teks_asli": teks,
            }

    # Tidak ada angka yang bisa diparsing
    return default


# ══════════════════════════════════════════════════════════════════════════════
# 3. EKSTRAK SKILL
# ══════════════════════════════════════════════════════════════════════════════

# Kamus skill yang dikelompokkan per kategori
SKILL_DICT = {
    # Bahasa pemrograman
    "Python"        : r"\bpython\b",
    "SQL"           : r"\bsql\b",
    "Java"          : r"\bjava\b(?!script)",
    "JavaScript"    : r"\bjavascript\b|\bjs\b",
    "TypeScript"    : r"\btypescript\b|\bts\b",
    "PHP"           : r"\bphp\b",
    "Kotlin"        : r"\bkotlin\b",
    "Swift"         : r"\bswift\b",
    "Go"            : r"\bgolang\b|\bgo\b",
    "R"             : r"\br\s+programming\b|\blanguage\s+r\b",
    "Scala"         : r"\bscala\b",
    "C++"           : r"\bc\+\+\b|\bcpp\b",
    "Rust"          : r"\brust\b",

    # Framework & library
    "React"         : r"\breact\.?js\b|\breact\b",
    "Vue"           : r"\bvue\.?js\b|\bvue\b",
    "Angular"       : r"\bangular\b",
    "Django"        : r"\bdjango\b",
    "FastAPI"       : r"\bfastapi\b",
    "Flask"         : r"\bflask\b",
    "Spring Boot"   : r"\bspring\s*boot\b",
    "Laravel"       : r"\blaravel\b",
    "Node.js"       : r"\bnode\.?js\b",
    "Next.js"       : r"\bnext\.?js\b",

    # Data & ML
    "Pandas"        : r"\bpandas\b",
    "NumPy"         : r"\bnumpy\b",
    "TensorFlow"    : r"\btensorflow\b",
    "PyTorch"       : r"\bpytorch\b",
    "Scikit-learn"  : r"\bscikit[\s-]?learn\b|\bsklearn\b",
    "Machine Learning": r"\bmachine\s+learning\b|\bml\b",
    "Deep Learning" : r"\bdeep\s+learning\b",
    "NLP"           : r"\bnlp\b|\bnatural\s+language\s+processing\b",
    "Computer Vision": r"\bcomputer\s+vision\b",
    "Data Analysis" : r"\bdata\s+anal[iy]sis\b|\banalitik\s+data\b",
    "Power BI"      : r"\bpower\s*bi\b",
    "Tableau"       : r"\btableau\b",
    "Looker"        : r"\blooker\b",

    # Database
    "PostgreSQL"    : r"\bpostgresql\b|\bpostgres\b",
    "MySQL"         : r"\bmysql\b",
    "MongoDB"       : r"\bmongodb\b|\bmongo\b",
    "Redis"         : r"\bredis\b",
    "Elasticsearch" : r"\belasticsearch\b|\belastic\b",
    "BigQuery"      : r"\bbigquery\b",
    "Snowflake"     : r"\bsnowflake\b",
    "Supabase"      : r"\bsupabase\b",

    # Cloud & DevOps
    "AWS"           : r"\baws\b|\bamazon\s+web\s+services\b",
    "GCP"           : r"\bgcp\b|\bgoogle\s+cloud\b",
    "Azure"         : r"\bazure\b|\bmicrosoft\s+azure\b",
    "Docker"        : r"\bdocker\b",
    "Kubernetes"    : r"\bkubernetes\b|\bk8s\b",
    "Terraform"     : r"\bterraform\b",
    "CI/CD"         : r"\bci[/\s]?cd\b|\bcontinuous\s+integration\b",
    "Git"           : r"\bgit\b(?!hub|lab)",
    "GitHub"        : r"\bgithub\b",
    "Linux"         : r"\blinux\b|\bubuntu\b|\bdebian\b",

    # Data Engineering
    "Apache Spark"  : r"\bapache\s+spark\b|\bpyspark\b",
    "Apache Kafka"  : r"\bkafka\b",
    "Airflow"       : r"\bairflow\b",
    "dbt"           : r"\bdbt\b",
    "ETL"           : r"\betl\b|\bextract\s+transform\s+load\b",
    "Data Warehouse": r"\bdata\s+warehouse\b|\bdwh\b",
    "Data Lake"     : r"\bdata\s+lake\b",

    # Networking & Sysadmin
    "Linux Admin"   : r"\blinux\s+admin\b|\bsysadmin\b",
    "Networking"    : r"\bnetworking\b|\bjaringan\b",
    "Cisco"         : r"\bcisco\b",
    "VMware"        : r"\bvmware\b",
    "Ansible"       : r"\bansible\b",
}

KATEGORI_SKILL = {
    "Python": "Programming", "SQL": "Programming", "Java": "Programming",
    "JavaScript": "Programming", "TypeScript": "Programming", "PHP": "Programming",
    "Kotlin": "Programming", "Swift": "Programming", "Go": "Programming",
    "R": "Programming", "Scala": "Programming", "C++": "Programming", "Rust": "Programming",
    "React": "Framework", "Vue": "Framework", "Angular": "Framework",
    "Django": "Framework", "FastAPI": "Framework", "Flask": "Framework",
    "Spring Boot": "Framework", "Laravel": "Framework", "Node.js": "Framework",
    "Next.js": "Framework",
    "Pandas": "Data & ML", "NumPy": "Data & ML", "TensorFlow": "Data & ML",
    "PyTorch": "Data & ML", "Scikit-learn": "Data & ML", "Machine Learning": "Data & ML",
    "Deep Learning": "Data & ML", "NLP": "Data & ML", "Computer Vision": "Data & ML",
    "Data Analysis": "Data & ML", "Power BI": "Data & ML", "Tableau": "Data & ML",
    "Looker": "Data & ML",
    "PostgreSQL": "Database", "MySQL": "Database", "MongoDB": "Database",
    "Redis": "Database", "Elasticsearch": "Database", "BigQuery": "Database",
    "Snowflake": "Database", "Supabase": "Database",
    "AWS": "Cloud & DevOps", "GCP": "Cloud & DevOps", "Azure": "Cloud & DevOps",
    "Docker": "Cloud & DevOps", "Kubernetes": "Cloud & DevOps", "Terraform": "Cloud & DevOps",
    "CI/CD": "Cloud & DevOps", "Git": "Cloud & DevOps", "GitHub": "Cloud & DevOps",
    "Linux": "Cloud & DevOps",
    "Apache Spark": "Data Engineering", "Apache Kafka": "Data Engineering",
    "Airflow": "Data Engineering", "dbt": "Data Engineering", "ETL": "Data Engineering",
    "Data Warehouse": "Data Engineering", "Data Lake": "Data Engineering",
    "Linux Admin": "Networking", "Networking": "Networking", "Cisco": "Networking",
    "VMware": "Networking", "Ansible": "Networking",
}

def transform_skill(deskripsi: str | None) -> dict:
    """
    Scan deskripsi loker dan ekstrak skill yang disebutkan.

    Output:
      skills_ditemukan : list[str]   — nama skill yang ada
      skills_kategori  : dict        — {kategori: [skill, ...]}
      jumlah_skill     : int         — total skill unik
      skill_string     : str         — "Python,SQL,Docker" (untuk filter Looker)
    """
    if not deskripsi:
        return {
            "skills_ditemukan": [], "skills_kategori": {},
            "jumlah_skill": 0, "skill_string": "",
        }

    teks_lower = deskripsi.lower()
    ditemukan = []

    for nama_skill, pattern in SKILL_DICT.items():
        if re.search(pattern, teks_lower, re.IGNORECASE):
            ditemukan.append(nama_skill)

    # Kelompokkan per kategori
    per_kategori = {}
    for skill in ditemukan:
        kat = KATEGORI_SKILL.get(skill, "Lainnya")
        per_kategori.setdefault(kat, []).append(skill)

    return {
        "skills_ditemukan": ditemukan,
        "skills_kategori" : per_kategori,
        "jumlah_skill"    : len(ditemukan),
        "skill_string"    : ",".join(ditemukan),  # untuk kolom teks di Looker
    }


# ══════════════════════════════════════════════════════════════════════════════
# 4. NORMALISASI LOKASI
# ══════════════════════════════════════════════════════════════════════════════

# Mapping variasi nama ke nama kota/provinsi standar
MAPPING_KOTA = {
    # Jakarta
    "jakarta selatan"   : "Jakarta", "jakarta utara"     : "Jakarta",
    "jakarta barat"     : "Jakarta", "jakarta timur"     : "Jakarta",
    "jakarta pusat"     : "Jakarta", "jak-sel"           : "Jakarta",
    "jak-bar"           : "Jakarta", "jak-tim"           : "Jakarta",
    "jak-ut"            : "Jakarta", "jak-pus"           : "Jakarta",
    "south jakarta"     : "Jakarta", "north jakarta"     : "Jakarta",
    "west jakarta"      : "Jakarta", "east jakarta"      : "Jakarta",
    "central jakarta"   : "Jakarta", "dki jakarta"       : "Jakarta",
    "jakarta"           : "Jakarta",

    # Jawa Barat
    "bandung"           : "Bandung",  "kota bandung"      : "Bandung",
    "bekasi"            : "Bekasi",   "kota bekasi"       : "Bekasi",
    "depok"             : "Depok",    "kota depok"        : "Depok",
    "bogor"             : "Bogor",    "kota bogor"        : "Bogor",
    "tangerang selatan" : "Tangerang Selatan",
    "tangsel"           : "Tangerang Selatan",
    "tangerang"         : "Tangerang",
    "karawang"          : "Karawang",
    "cimahi"            : "Cimahi",
    "sukabumi"          : "Sukabumi",

    # Jawa Tengah & DIY
    "semarang"          : "Semarang", "kota semarang"     : "Semarang",
    "yogyakarta"        : "Yogyakarta", "jogja"           : "Yogyakarta",
    "jogyakarta"        : "Yogyakarta", "diy"             : "Yogyakarta",
    "solo"              : "Solo",     "surakarta"         : "Solo",

    # Jawa Timur
    "surabaya"          : "Surabaya", "kota surabaya"     : "Surabaya",
    "malang"            : "Malang",   "kota malang"       : "Malang",
    "sidoarjo"          : "Sidoarjo",

    # Sumatera
    "medan"             : "Medan",    "kota medan"        : "Medan",
    "palembang"         : "Palembang",
    "pekanbaru"         : "Pekanbaru",
    "batam"             : "Batam",
    "padang"            : "Padang",
    "bandar lampung"    : "Bandar Lampung",

    # Kalimantan
    "balikpapan"        : "Balikpapan",
    "samarinda"         : "Samarinda",
    "banjarmasin"       : "Banjarmasin",
    "pontianak"         : "Pontianak",

    # Sulawesi
    "makassar"          : "Makassar", "ujung pandang"     : "Makassar",
    "manado"            : "Manado",

    # Bali & NTB
    "bali"              : "Bali",     "denpasar"          : "Bali",
    "mataram"           : "Mataram",

    # Remote
    "remote"            : "Remote",   "work from home"    : "Remote",
    "wfh"               : "Remote",   "anywhere"          : "Remote",
    "indonesia"         : "Indonesia (Nasional)",
}

MAPPING_PROVINSI = {
    "jakarta"           : "DKI Jakarta",
    "bekasi"            : "Jawa Barat",  "depok"       : "Jawa Barat",
    "bogor"             : "Jawa Barat",  "bandung"     : "Jawa Barat",
    "tangerang"         : "Banten",      "tangerang selatan": "Banten",
    "serang"            : "Banten",
    "semarang"          : "Jawa Tengah", "solo"        : "Jawa Tengah",
    "yogyakarta"        : "DI Yogyakarta",
    "surabaya"          : "Jawa Timur",  "malang"      : "Jawa Timur",
    "sidoarjo"          : "Jawa Timur",
    "medan"             : "Sumatera Utara",
    "palembang"         : "Sumatera Selatan",
    "pekanbaru"         : "Riau",
    "batam"             : "Kepulauan Riau",
    "padang"            : "Sumatera Barat",
    "balikpapan"        : "Kalimantan Timur",
    "samarinda"         : "Kalimantan Timur",
    "banjarmasin"       : "Kalimantan Selatan",
    "pontianak"         : "Kalimantan Barat",
    "makassar"          : "Sulawesi Selatan",
    "manado"            : "Sulawesi Utara",
    "bali"              : "Bali",
    "mataram"           : "NTB",
    "remote"            : "Remote",
}

def transform_lokasi(lokasi_raw: str | None) -> dict:
    """
    Normalisasi string lokasi ke nama kota dan provinsi standar.

    Output:
      kota_standar    : str | None
      provinsi_standar: str | None
      is_remote       : bool
    """
    if not lokasi_raw:
        return {"kota_standar": None, "provinsi_standar": None, "is_remote": False}

    teks_lower = lokasi_raw.lower().strip()

    # Cek remote dulu
    is_remote = any(k in teks_lower for k in ["remote", "wfh", "work from home", "anywhere"])

    # Cari match di mapping kota (dari yang paling spesifik/panjang dulu)
    kota_standar = None
    for key in sorted(MAPPING_KOTA, key=len, reverse=True):
        if key in teks_lower:
            kota_standar = MAPPING_KOTA[key]
            break

    # Tentukan provinsi dari kota
    provinsi_standar = None
    if kota_standar:
        kota_key = kota_standar.lower().split()[0]
        provinsi_standar = MAPPING_PROVINSI.get(kota_key)

    # Fallback: jika tidak ada mapping, gunakan nilai asli (capitalize)
    if not kota_standar and not is_remote:
        kota_standar = lokasi_raw.strip().title()

    return {
        "kota_standar"    : kota_standar,
        "provinsi_standar": provinsi_standar,
        "is_remote"       : is_remote,
    }


# ══════════════════════════════════════════════════════════════════════════════
# 5. STANDARDISASI ENUM (NULL HANDLING)
# ══════════════════════════════════════════════════════════════════════════════

TIPE_KERJA_VALID = {
    "full time": "Full Time", "full-time": "Full Time", "fulltime": "Full Time",
    "part time": "Part Time", "part-time": "Part Time", "parttime": "Part Time",
    "contract" : "Kontrak",   "kontrak"  : "Kontrak",
    "freelance": "Freelance", "intern"   : "Internship",
    "internship": "Internship", "magang" : "Internship",
    "casual"   : "Casual",    "temporary": "Temporer",
    "temporer" : "Temporer",
}

WORK_ARR_VALID = {
    "onsite"  : "Onsite",  "on-site" : "Onsite",  "kantor"  : "Onsite",
    "remote"  : "Remote",  "wfh"     : "Remote",
    "hybrid"  : "Hybrid",  "flexible": "Hybrid",
}

def transform_enum(tipe_kerja: str | None, work_arrangement: str | None) -> dict:
    """
    Standardisasi nilai enum dan isi null dengan label 'Tidak Disebutkan'.

    Output:
      tipe_kerja_std     : str
      work_arrangement_std: str
    """
    # Tipe kerja
    if tipe_kerja:
        key = tipe_kerja.lower().strip()
        tipe_std = TIPE_KERJA_VALID.get(key, tipe_kerja.title())
    else:
        tipe_std = "Tidak Disebutkan"

    # Work arrangement
    if work_arrangement:
        key = work_arrangement.lower().strip()
        # Cek tiap kata dalam string (bisa "Onsite, Hybrid")
        arr_std_list = []
        for bagian in re.split(r"[,;]", work_arrangement):
            bagian_key = bagian.strip().lower()
            arr_std_list.append(WORK_ARR_VALID.get(bagian_key, bagian.strip().title()))
        arr_std = ", ".join(arr_std_list) if arr_std_list else "Tidak Disebutkan"
    else:
        arr_std = "Tidak Disebutkan"

    return {
        "tipe_kerja_std"      : tipe_std,
        "work_arrangement_std": arr_std,
    }


# ══════════════════════════════════════════════════════════════════════════════
# 6. DURASI TAYANG & ACTIVE FLAG
# ══════════════════════════════════════════════════════════════════════════════

def transform_durasi(waktu_posting: str | None, waktu_expired: str | None,
                     waktu_scrap: str | None = None) -> dict:
    """
    Hitung durasi tayang dan status aktif loker.

    Output:
      hari_tayang     : int | None   (expired - posting)
      is_active       : bool         (expired > sekarang)
      hari_tersisa    : int | None   (expired - sekarang, jika masih aktif)
      hari_sejak_post : int | None   (sekarang - posting)
    """
    default = {
        "hari_tayang": None, "is_active": False,
        "hari_tersisa": None, "hari_sejak_post": None,
    }

    sekarang = datetime.now(timezone.utc)

    def parse_dt(iso_str):
        if not iso_str:
            return None
        try:
            return datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        except ValueError:
            return None

    dt_posting = parse_dt(waktu_posting)
    dt_expired = parse_dt(waktu_expired)

    if dt_posting and dt_expired:
        default["hari_tayang"] = (dt_expired - dt_posting).days

    if dt_expired:
        default["is_active"] = dt_expired > sekarang
        if default["is_active"]:
            default["hari_tersisa"] = (dt_expired - sekarang).days

    if dt_posting:
        default["hari_sejak_post"] = (sekarang - dt_posting).days

    return default


# ══════════════════════════════════════════════════════════════════════════════
# 7. GROUPING KLASIFIKASI
# ══════════════════════════════════════════════════════════════════════════════

# Mapping sub-klasifikasi → kategori besar untuk Looker
MAPPING_KLASIFIKASI = {
    # Infrastructure & Sysadmin
    "Networks & Systems Administration"         : "IT Infrastructure",
    "Administrasi Jaringan & Sistem"            : "IT Infrastructure",
    "System Administration"                     : "IT Infrastructure",
    "IT Support"                                : "IT Infrastructure",
    "Network Engineering"                       : "IT Infrastructure",

    # Software Development
    "Developers/Programmers"                    : "Software Development",
    "Developer/Programmer"                      : "Software Development",
    "Pengembang/Programmer"                     : "Software Development",
    "Software Engineering"                      : "Software Development",
    "Mobile Development"                        : "Software Development",
    "Web Development"                           : "Software Development",
    "Frontend Development"                      : "Software Development",
    "Backend Development"                       : "Software Development",
    "Full Stack Development"                    : "Software Development",

    # Data & Analytics
    "Data/Business Analysis"                    : "Data & Analytics",
    "Analisis Data/Bisnis"                      : "Data & Analytics",
    "Data Science"                              : "Data & Analytics",
    "Business Intelligence"                     : "Data & Analytics",
    "Database Administration"                   : "Data & Analytics",
    "Data Engineering"                          : "Data & Analytics",
    "Machine Learning"                          : "Data & Analytics",
    "Artificial Intelligence"                   : "Data & Analytics",

    # Management & Consulting
    "Management"                                : "IT Management",
    "IT Management"                             : "IT Management",
    "Project Management"                        : "IT Management",
    "IT Consulting"                             : "IT Management",
    "Product Management"                        : "IT Management",

    # Security
    "Cybersecurity"                             : "Cybersecurity",
    "Information Security"                      : "Cybersecurity",
    "Keamanan Siber"                            : "Cybersecurity",

    # Testing & QA
    "Testing & Quality Assurance"               : "QA & Testing",
    "Pengujian & Jaminan Kualitas"              : "QA & Testing",
    "QA Engineering"                            : "QA & Testing",

    # Design & UX
    "Design & UX"                               : "Design & UX",
    "UI/UX"                                     : "Design & UX",
    "Product Design"                            : "Design & UX",
    "User Research"                             : "Design & UX",
}

def transform_klasifikasi(klasifikasi_raw: str | None,
                           sub_klasifikasi_raw: str | None) -> dict:
    """
    Mapping sub-klasifikasi ke kategori besar yang lebih ringkas untuk Looker.

    Output:
      kategori_besar  : str   (kelompok besar, misal "Software Development")
      sub_klasifikasi_std: str (nilai asli yang dibersihkan)
    """
    sub = sub_klasifikasi_raw or klasifikasi_raw or ""
    sub_clean = sub.strip()

    # Cari match di mapping (exact match dulu)
    kategori = MAPPING_KLASIFIKASI.get(sub_clean)

    # Jika tidak ada exact match, coba partial match
    if not kategori:
        sub_lower = sub_clean.lower()
        for key, val in MAPPING_KLASIFIKASI.items():
            if key.lower() in sub_lower or sub_lower in key.lower():
                kategori = val
                break

    # Fallback
    if not kategori:
        kategori = "Lainnya"

    return {
        "kategori_besar"    : kategori,
        "sub_klasifikasi_std": sub_clean or "Tidak Disebutkan",
    }


# ══════════════════════════════════════════════════════════════════════════════
# MASTER TRANSFORM — gabungkan semua transformasi
# ══════════════════════════════════════════════════════════════════════════════

def transform_satu_loker(data: dict) -> dict:
    """
    Jalankan semua transformasi pada satu dict loker hasil scraping.
    Input  : dict dari scraper_detail.transform_detail()
    Output : dict yang diperkaya, siap masuk tabel lowongan_transformed
    """
    hasil = dict(data)  # copy data asli

    # 1. Waktu
    w = transform_waktu(data.get("waktuPostingLoker"))
    hasil.update({
        "tahun"          : w["tahun"],
        "bulan"          : w["bulan"],
        "nama_bulan"     : w["nama_bulan"],
        "hari"           : w["hari"],
        "jam_posting"    : w["jam"],
        "hari_minggu"    : w["hari_minggu"],
        "nama_hari"      : w["nama_hari"],
        "kuartal"        : w["kuartal"],
        "tanggal_posting": w["tanggal_posting"],
    })

    # 2. Gaji
    g = transform_gaji(data.get("gaji"))
    hasil.update({
        "gaji_min"      : g["gaji_min"],
        "gaji_max"      : g["gaji_max"],
        "gaji_midpoint" : g["gaji_midpoint"],
        "gaji_disclosed": g["gaji_disclosed"],
        "gaji_periode"  : g["gaji_periode"],
    })

    # 3. Skill
    teks_gabung = " ".join(filter(None, [
        data.get("deskripsi_singkat", ""),
        data.get("deskripsi_lengkap", ""),
        data.get("posisi", ""),
    ]))
    s = transform_skill(teks_gabung)
    hasil.update({
        "skills_ditemukan": s["skills_ditemukan"],
        "jumlah_skill"    : s["jumlah_skill"],
        "skill_string"    : s["skill_string"],
    })

    # 4. Lokasi
    l = transform_lokasi(data.get("lokasi"))
    hasil.update({
        "kota_standar"    : l["kota_standar"],
        "provinsi_standar": l["provinsi_standar"],
        "is_remote"       : l["is_remote"],
    })

    # 5. Enum
    e = transform_enum(data.get("tipe_kerja"), data.get("work_arrangement"))
    hasil.update({
        "tipe_kerja_std"      : e["tipe_kerja_std"],
        "work_arrangement_std": e["work_arrangement_std"],
    })

    # 6. Durasi
    d = transform_durasi(
        data.get("waktuPostingLoker"),
        data.get("waktuExpiredLoker"),
        data.get("waktuScrapLoker"),
    )
    hasil.update({
        "hari_tayang"   : d["hari_tayang"],
        "is_active"     : d["is_active"],
        "hari_tersisa"  : d["hari_tersisa"],
        "hari_sejak_post": d["hari_sejak_post"],
    })

    # 7. Klasifikasi
    k = transform_klasifikasi(
        data.get("klasifikasi"),
        data.get("sub_klasifikasi"),
    )
    hasil.update({
        "kategori_besar"    : k["kategori_besar"],
        "sub_klasifikasi_std": k["sub_klasifikasi_std"],
    })

    return hasil

def transform_semua(data_list: list[dict]) -> list[dict]:
    """
    Jalankan transform_satu_loker() untuk seluruh list hasil scraping.
    Input  : output dari scraper_detail.get_semua_detail()
    Output : list dict yang sudah ditransform, siap di-load ke database
    """
    print(f"\n[TRANSFORM] Memproses {len(data_list)} loker...")
    hasil = []
    gagal = 0

    for i, item in enumerate(data_list, 1):
        try:
            transformed = transform_satu_loker(item)
            hasil.append(transformed)
        except Exception as e:
            print(f"  [transform] SKIP job {item.get('job_id','?')}: {e}")
            gagal += 1

    print(f"[TRANSFORM] Selesai. Berhasil: {len(hasil)}, Gagal: {gagal}")
    return hasil