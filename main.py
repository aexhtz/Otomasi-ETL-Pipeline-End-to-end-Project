# ------------------- PENGEMBANGAN -------------------- #
# 1. Buat setiap potongan kode menjadi function agar kode menjadi lebih rapi dan lebih mudah untuk di maintenance

import requests as req
import pandas as pd
import config.konfigurasi_sql as konfigurasi
from bs4 import BeautifulSoup as bs
import deteksi_waktu as detek

targetScrap = "https://id.jobstreet.com/id/jobs-in-information-communication-technology?page=1&sortmode=ListedDate"
response = req.get(targetScrap)
soup = bs(response.text, "html.parser")

cursor = konfigurasi.sql.cursor()

if response.status_code == 200:
    print("\n>> RESPONSE STATUS: Sukses (200).")
else:
    print(">> RESPONSE STATUS: Gagal")

# -- Tahap pertama untuk scan jumlah loker pada suatu URL --
lokerLoker = soup.find_all("article", {"data-automation": "normalJob"})

# -- Print total loker pada suatu URL --
print("\n>> Loker Tersedia: ",len(lokerLoker),"\n")

# -- Variabel tempat simpan hasil scrap --
hasilscrap = []
# -- Iterasi --
for loker in lokerLoker:
    posisiLoker = loker.find("a", {"data-automation": "jobTitle"}).text.strip()
    perusahaanLoker = loker.find(attrs = {"data-automation": "jobCompany"}).text.strip()
    lokasiLoker = loker.find("span", {"data-automation": "jobLocation"}).text.strip()
    deskripsiSingkatLoker = loker.find("span", {"data-automation": "jobShortDescription"}).text.strip()
    klasifikasiLoker = loker.find("div", {"data-testid": "job-classification"}).text.strip()
    waktuLoker = loker.find("span", {"data-automation": "jobListingDate"}).text.strip()
    waktuPostingLoker = detek.scanwaktu((waktuLoker))

    # -- Input ke dalam variabel hasilscrap --
    hasilscrap.append({
        "posisi": posisiLoker,
        "perusahaan": perusahaanLoker,
        "lokasi": lokasiLoker,
        "deskripsi": deskripsiSingkatLoker,
        "klasifikasi": klasifikasiLoker,
        "waktuPostingLoker": waktuPostingLoker,
        "waktuScrapLoker": detek.waktuSaatIni()
    })

    # -- Bentuk dataframe dari hasilscrap --
    dataFrame = pd.DataFrame(hasilscrap)
    # -- Ubah dataframe jadi format csv --
    dataFrame.to_csv("hasil_scrap.csv", index=False, encoding="utf-8-sig")

query = """
INSERT INTO lowongan (posisi, perusahaan, lokasi, deskripsi, klasifikasi, waktuPostingLoker, waktuScrapLoker)
VALUES (%s, %s, %s, %s, %s, %s, %s)
"""
values = [
    (
        data["posisi"],
        data["perusahaan"],
        data["lokasi"],
        data["deskripsi"],
        data["klasifikasi"],
        data["waktuPostingLoker"],
        data["waktuScrapLoker"]
    )
    for data in hasilscrap
]

try:
    cursor.executemany(query,values)
    konfigurasi.sql.commit()
finally:
    cursor.close()
    konfigurasi.sql.close()