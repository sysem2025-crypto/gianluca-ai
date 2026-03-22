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
    conn.row_factory = sqlite3.Row  # restituisce dict invece di tuple
    return conn

def init_sqlite():
    """Crea le tabelle SQLite se non esistono"""
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
# SUPABASE - Database cloud
# ─────────────────────────────────────────

def get_supabase():
    from supabase import create_client
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    if not url or not key:
        raise Exception("Credenziali Supabase mancanti nel file .env")
    return create_client(url, key)

# ─────────────────────────────────────────
# INTERFACCIA UNIFICATA
# ─────────────────────────────────────────

def get_profile_info(chiave: str):
    """Recupera un valore dal profilo"""
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
            result = sb.table("gianluca_profile")\
                .select("valore").eq("chiave", chiave).execute()
            return result.data[0]["valore"] if result.data else None
    except Exception as e:
        print(f"Errore get_profile_info({chiave}): {e}")
        return None

def get_full_profile():
    """Recupera tutto il profilo"""
    try:
        if DB_MODE == "local":
            conn = get_sqlite_connection()
            rows = conn.execute("SELECT * FROM gianluca_profile").fetchall()
            conn.close()
            return [dict(row) for row in rows]
        else:
            sb = get_supabase()
            return sb.table("gianluca_profile").select("*").execute().data
    except Exception as e:
        print(f"Errore get_full_profile: {e}")
        return []

def save_conversation(utente: str, messaggio: str, risposta: str):
    """Salva una conversazione"""
    try:
        if DB_MODE == "local":
            conn = get_sqlite_connection()
            conn.execute(
                "INSERT INTO conversazioni (utente, messaggio, risposta, timestamp) VALUES (?, ?, ?, ?)",
                (utente, messaggio, risposta, datetime.now().isoformat())
            )
            conn.commit()
            conn.close()
        else:
            sb = get_supabase()
            sb.table("conversazioni").insert({
                "utente": utente,
                "messaggio": messaggio,
                "risposta": risposta,
                "timestamp": datetime.now().isoformat()
            }).execute()
    except Exception as e:
        print(f"Errore save_conversation: {e}")

def get_history(utente: str, limit: int = 50):
    """Recupera la cronologia di un utente"""
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
            return sb.table("conversazioni")\
                .select("*").eq("utente", utente)\
                .order("timestamp", desc=True).limit(limit).execute().data
    except Exception as e:
        print(f"Errore get_history: {e}")
        return []