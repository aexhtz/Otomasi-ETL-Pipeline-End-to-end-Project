import psycopg2
from dotenv import load_dotenv
import os

load_dotenv()

USER = os.getenv("user")
PASSWORD = os.getenv("password")
HOST = os.getenv("host")
PORT = os.getenv("port")
DBNAME = os.getenv("dbname")

print(USER, PASSWORD, HOST, PORT, DBNAME)

try:
    sql = psycopg2.connect(
        user=USER,
        password=PASSWORD,
        host=HOST,
        port=PORT,
        dbname=DBNAME
    )
    print("[OK] Berhasil terhubung Supabase.")

except Exception as e:
    print(f"[BAD] Gagal koneksi {e}")