import psycopg2
from dotenv import load_dotenv
import os

load_dotenv()

SUPABASE_USER = os.getenv("SUPABASE_USER")
SUPABASE_PASSWORD = os.getenv("SUPABASE_PASSWORD")
SUPABASE_HOST = os.getenv("SUPABASE_HOST")
SUPABASE_PORT = os.getenv("SUPABASE_PORT")
SUPABASE_DB = os.getenv("SUPABASE_DB")

# print(USER, PASSWORD, HOST, PORT, DBNAME)

try:
    sql = psycopg2.connect(
        user=SUPABASE_USER,
        password=SUPABASE_PASSWORD,
        host=SUPABASE_HOST,
        port=SUPABASE_PORT,
        dbname=SUPABASE_DB
    )
    print("\n[Supabase] Berhasil terhubung ke database\n")

except Exception as e:
    print(f"[Supabase] Gagal terhubung {e}")