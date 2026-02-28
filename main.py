# ------------------- PENGEMBANGAN --------------------
# 1. Buat setiap potongan kode menjadi function agar kode menjadi lebih rapi dan lebih mudah untuk di maintenance

import requests as req
import pandas as panda
import mysql.connector
from bs4 import BeautifulSoup
import deteksi_waktu as dw

targetScrap = "https://id.jobstreet.com/id/jobs-in-information-communication-technology?page=1&sortmode=ListedDate"
response = req.get(targetScrap)
soup = BeautifulSoup(response.text, "html.parser")

# ----- Konfigurasi MySQL ----- #
sql = mysql.connector.connect(
    host = "localhost",
    user = "root",
    password = "",
    database = "webscrap"
)
cursor = sql.cursor()

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
    posisi_loker = loker.find("a", {"data-automation": "jobTitle"}).text.strip()
    perusahaan_loker = loker.find("a", {"data-automation": "jobCompany"}).text.strip()
    lokasi_loker = loker.find("a", {"data-automation": "jobLocation"}).text.strip()
    deskripsi_singkat = loker.find("span", {"data-automation": "jobShortDescription"}).text.strip()
    klasfikasi_loker = loker.find("div", {"data-testid": "job-classification"}).text.strip()
    # -- Input ke dalam variabel hasilscrap --
    hasilscrap.append({
        "posisi": posisi_loker,
        "perusahaan": perusahaan_loker,
        "lokasi": lokasi_loker,
        "deskripsi": deskripsi_singkat,
        "klasifikasi": klasfikasi_loker
    })

    # -- Bentuk dataframe dari hasilscrap --
    dataFrame = panda.DataFrame(hasilscrap)
    # -- Ubah dataframe jadi format csv --
    dataFrame.to_csv("hasil_scrap.csv", index=False, encoding="utf-8-sig")

query = """
INSERT INTO lowongan (posisi, perusahaan, lokasi, deskripsi, klasifikasi)
VALUES (%s, %s, %s, %s, %s)
"""
values = [
    (
        data["posisi"],
        data["perusahaan"],
        data["lokasi"],
        data["deskripsi"],
        data["klasifikasi"],
    )
    for data in hasilscrap
]
try:
    cursor.executemany(query,values)
    sql.commit()
finally:
    cursor.close()
    sql.close()