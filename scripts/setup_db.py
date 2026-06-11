import sys
import os
import json
from datetime import datetime
from dotenv import load_dotenv

# Aggiunge la cartella /api al PYTHONPATH
BASE_DIR = os.path.dirname(os.path.dirname(__file__))
API_DIR = os.path.join(BASE_DIR, "api")
sys.path.append(API_DIR)

load_dotenv()

from database import (
    init_sqlite,
    get_sqlite_connection,
    get_supabase,
    DB_MODE
)

# ─────────────────────────────────────────
# CARICAMENTO JSON
# ─────────────────────────────────────────

def load_json_data(path="data/gianluca_profile.json"):
    if not os.path.exists(path):
        raise FileNotFoundError(f"❌ File JSON non trovato: {path}")

    with open(path, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
            print("📄 JSON caricato correttamente")
            return data
        except Exception as e:
            raise ValueError(f"❌ Errore parsing JSON: {e}")


# ─────────────────────────────────────────
# POPOLAMENTO SQLITE
# ─────────────────────────────────────────

def populate_sqlite(data):
    print("🔧 Popolamento SQLite...")

    conn = get_sqlite_connection()
    cur = conn.cursor()

    for item in data.get("gianluca_profile", []):
        cur.execute("""
            INSERT OR REPLACE INTO gianluca_profile (chiave, valore, categoria, updated_at)
            VALUES (?, ?, ?, ?)
        """, (
            item["chiave"],
            item.get("valore"),
            item.get("categoria"),
            datetime.now().isoformat()
        ))

    conn.commit()
    conn.close()
    print("✅ SQLite popolato correttamente")


# ─────────────────────────────────────────
# POPOLAMENTO SUPABASE (REST API)
# ─────────────────────────────────────────

def populate_supabase(data):
    print("🔧 Popolamento Supabase (REST API)...")

    sb = get_supabase()
    if sb is None:
        print("❌ Errore: impossibile creare client Supabase")
        return

    for item in data.get("gianluca_profile", []):
        sb.table("gianluca_profile").upsert({
            "chiave": item["chiave"],
            "valore": item.get("valore"),
            "categoria": item.get("categoria"),
            "updated_at": datetime.now().isoformat()
        }).execute()

    print("✅ Supabase popolato correttamente")


# ─────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────

if __name__ == "__main__":
    print(f"🚀 Avvio setup database (modalità: {DB_MODE})")

    data = load_json_data()

    if DB_MODE == "local":
        init_sqlite()
        populate_sqlite(data)
    else:
        populate_supabase(data)

    print("🎉 Setup completato!")

