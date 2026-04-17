import psycopg2
from dotenv import load_dotenv
import os

load_dotenv()

USER = os.getenv("USER")
PASSWORD = os.getenv("PASSWORD")
HOST = os.getenv("HOST")
PORT = os.getenv("PORT")
DBNAME = os.getenv("DBNAME")

# print(USER, PASSWORD, HOST, PORT, DBNAME)

try:
    sql = psycopg2.connect(
        user=USER,
        password=PASSWORD,
        host=HOST,
        port=PORT,
        dbname=DBNAME
    )
    print("[Supabase] Berhasil terhubung")

except Exception as e:
    print(f"[Supabase] Gagal terhubung {e}")