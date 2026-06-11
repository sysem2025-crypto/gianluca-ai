import os
import sqlite3
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

DB_MODE = os.getenv("DB_MODE", "local")

# ─────────────────────────────────────────
# SQLITE - Database locale
# ─────────────────────────────────────────

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "gianluca.db")

def get_sqlite_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_sqlite():
    conn = get_sqlite_connection()
    cursor = conn.cursor()

    cursor.executescript("""
        CREATE TABLE IF NOT EXISTS gianluca_profile (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chiave TEXT UNIQUE NOT NULL,
            valore TEXT,
            categoria TEXT,
            updated_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS conversazioni (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            utente TEXT,
            messaggio TEXT,
            risposta TEXT,
            timestamp TEXT DEFAULT (datetime('now')),
            sentiment TEXT
        );

        CREATE TABLE IF NOT EXISTS preferenze (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            categoria TEXT,
            valore TEXT,
            importanza INTEGER DEFAULT 5,
            note TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_conv_utente ON conversazioni(utente);
        CREATE INDEX IF NOT EXISTS idx_conv_timestamp ON conversazioni(timestamp);
        CREATE INDEX IF NOT EXISTS idx_profile_chiave ON gianluca_profile(chiave);
    """)

    conn.commit()
    conn.close()
    print("✅ SQLite inizializzato correttamente")

# ─────────────────────────────────────────
# SUPABASE - REST API (supabase-py)
# ─────────────────────────────────────────

def get_supabase():
    from supabase import create_client
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")

    if not url or not key:
        raise RuntimeError("❌ Credenziali Supabase mancanti nel file .env")

    try:
        return create_client(url, key)
    except Exception as e:
        print(f"❌ Errore creazione client Supabase REST: {e}")
        return None

# ─────────────────────────────────────────
# INTERFACCIA UNIFICATA
# ─────────────────────────────────────────

def get_profile_info(chiave: str):
    try:
        if DB_MODE == "local":
            conn = get_sqlite_connection()
            row = conn.execute(
                "SELECT valore FROM gianluca_profile WHERE chiave = ?", (chiave,)
            ).fetchone()
            conn.close()
            return row["valore"] if row else None

        else:
            sb = get_supabase()
            if sb is None:
                return None

            result = sb.table("gianluca_profile") \
                .select("valore").eq("chiave", chiave).execute()

            return result.data[0]["valore"] if result.data else None

    except Exception as e:
        print(f"❌ Errore get_profile_info({chiave}): {e}")
        return None


def get_full_profile():
    try:
        if DB_MODE == "local":
            conn = get_sqlite_connection()
            rows = conn.execute("SELECT * FROM gianluca_profile").fetchall()
            conn.close()
            return [dict(row) for row in rows]

        else:
            sb = get_supabase()
            if sb is None:
                return []

            result = sb.table("gianluca_profile").select("*").execute()
            return result.data or []

    except Exception as e:
        print(f"❌ Errore get_full_profile: {e}")
        return []


def save_conversation(utente: str, messaggio: str, risposta: str):
    try:
        timestamp = datetime.now().isoformat()

        if DB_MODE == "local":
            conn = get_sqlite_connection()
            conn.execute(
                "INSERT INTO conversazioni (utente, messaggio, risposta, timestamp) VALUES (?, ?, ?, ?)",
                (utente, messaggio, risposta, timestamp)
            )
            conn.commit()
            conn.close()

        else:
            sb = get_supabase()
            if sb is None:
                return

            sb.table("conversazioni").insert({
                "utente": utente,
                "messaggio": messaggio,
                "risposta": risposta,
                "timestamp": timestamp
            }).execute()

    except Exception as e:
        print(f"❌ Errore save_conversation: {e}")


def get_history(utente: str, limit: int = 50):
    try:
        if DB_MODE == "local":
            conn = get_sqlite_connection()
            rows = conn.execute(
                "SELECT * FROM conversazioni WHERE utente = ? ORDER BY timestamp DESC LIMIT ?",
                (utente, limit)
            ).fetchall()
            conn.close()
            return [dict(row) for row in rows]

        else:
            sb = get_supabase()
            if sb is None:
                return []

            result = sb.table("conversazioni") \
                .select("*").eq("utente", utente) \
                .order("timestamp", desc=True).limit(limit).execute()

            return result.data or []

    except Exception as e:
        print(f"❌ Errore get_history: {e}")
        return []
