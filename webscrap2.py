import requests
import csv
from bs4 import BeautifulSoup

targetScrap = "https://id.jobstreet.com/id/jobs-in-information-communication-technology?page=1"

response = requests.get(targetScrap)
soup = BeautifulSoup(response.text, "html.parser")
# print(f">> RESPONSE STATUS: {response.status_code}")
if response.status_code == 200:
    print("\n>> RESPONSE STATUS: Sukses (200).")
else:
    print(">> RESPONSE STATUS: Gagal terhubung ke url target.")

# -- Tahap pertama untuk scan jumlah loker pada suatu URL
lokerloker = soup.find_all("article", {"data-automation": "normalJob"})

# -- Print total loker pada suatu URL
print("\n>> Loker Tersedia: ",len(lokerloker),"\n")

# -- Variabel tempat simpan hasil scrap
hasilscrap = []

for loker in lokerloker:
    posisi_loker = loker.find("a", {"data-automation": "jobTitle"}).text.strip()
    perusahaan_loker = loker.find("a", {"data-automation": "jobCompany"}).text.strip()
    lokasi_loker = loker.find("a", {"data-automation": "jobCompany"}).text.strip()
    deskripsi_singkat = loker.find("span", {"data-automation": "jobShortDescription"}).text.strip()
    klasfikasi_loker = loker.find("div", {"data-testid": "job-classification"}).text.strip()

    print (f"{posisi_loker} - {perusahaan_loker} - {lokasi_loker} - {deskripsi_singkat} - {klasfikasi_loker}")
    # -- hasilscrap.append(posisi_loker, perusahaan_loker, lokasi_loker, deskripsi_singkat)