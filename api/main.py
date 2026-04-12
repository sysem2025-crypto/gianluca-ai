from flask import Flask, request, jsonify, session
from flask_cors import CORS
from datetime import datetime, timedelta
import os
import traceback
import requests
from collections import defaultdict, deque
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("FLASK_SECRET_KEY", "cambiami-subito-con-una-chiave-lunga")
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = os.getenv("COOKIE_SECURE", "true").lower() == "true"
app.permanent_session_lifetime = timedelta(days=7)

# CORS
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "http://localhost:5500,null").split(",")
CORS(app, origins=ALLOWED_ORIGINS, supports_credentials=True)

# API Keys
API_KEY = os.getenv("API_KEY", "chiave-segreta-cambiami-123")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
MIN_CHAT_INTERVAL_SECONDS = int(os.getenv("MIN_CHAT_INTERVAL_SECONDS", "4"))
MAX_MESSAGE_LENGTH = int(os.getenv("MAX_MESSAGE_LENGTH", "700"))
CHAT_RATE_LIMIT_WINDOW_SECONDS = int(os.getenv("CHAT_RATE_LIMIT_WINDOW_SECONDS", "60"))
CHAT_RATE_LIMIT_MAX_REQUESTS = int(os.getenv("CHAT_RATE_LIMIT_MAX_REQUESTS", "12"))
AUTH_RATE_LIMIT_WINDOW_SECONDS = int(os.getenv("AUTH_RATE_LIMIT_WINDOW_SECONDS", "300"))
AUTH_RATE_LIMIT_MAX_REQUESTS = int(os.getenv("AUTH_RATE_LIMIT_MAX_REQUESTS", "8"))
rate_limit_store = defaultdict(deque)

try:
    from database import get_profile_info, get_full_profile, save_conversation, get_history
except ImportError:
    from api.database import get_profile_info, get_full_profile, save_conversation, get_history


def check_api_key():
    key = request.headers.get("X-API-Key")
    if key != API_KEY:
        return jsonify({"detail": "API Key non valida"}), 403
    return None


def get_current_user():
    email = session.get("user_email")
    if not email:
        return None
    return {
        "id": session.get("user_id"),
        "email": email,
        "name": session.get("user_name") or email.split("@")[0]
    }


def require_auth():
    user = get_current_user()
    if not user:
        return None, (jsonify({"detail": "Autenticazione richiesta"}), 401)
    return user, None


def supabase_headers():
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError("Configurazione Supabase mancante")
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json"
    }


def parse_auth_payload():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    name = (data.get("name") or "").strip()

    if "@" not in email or "." not in email.split("@")[-1]:
        return None, None, None, (jsonify({"detail": "Email non valida"}), 400)
    if len(password) < 8:
        return None, None, None, (jsonify({"detail": "La password deve avere almeno 8 caratteri"}), 400)

    return email, password, name, None


def persist_session(auth_payload, fallback_name=""):
    user = auth_payload.get("user") or {}
    metadata = user.get("user_metadata") or {}
    session.permanent = True
    session["user_id"] = user.get("id")
    session["user_email"] = user.get("email")
    session["user_name"] = metadata.get("name") or fallback_name or (user.get("email") or "").split("@")[0]
    session["last_chat_at"] = None


def clear_session():
    session.clear()


def throttling_error():
    last_chat_at = session.get("last_chat_at")
    if not last_chat_at:
        return None
    try:
        last_dt = datetime.fromisoformat(last_chat_at)
    except ValueError:
        return None

    delta = (datetime.utcnow() - last_dt).total_seconds()
    if delta < MIN_CHAT_INTERVAL_SECONDS:
        wait_for = max(1, int(MIN_CHAT_INTERVAL_SECONDS - delta))
        return jsonify({"detail": f"Stai inviando messaggi troppo velocemente. Riprova tra {wait_for}s."}), 429
    return None


def get_client_ip():
    forwarded_for = request.headers.get("X-Forwarded-For", "")
    real_ip = request.headers.get("X-Real-IP", "")
    candidate = forwarded_for.split(",")[0].strip() if forwarded_for else real_ip.strip()
    return candidate or request.remote_addr or "unknown"


def check_rate_limit(bucket: str, max_requests: int, window_seconds: int):
    now = datetime.utcnow().timestamp()
    client_ip = get_client_ip()
    key = f"{bucket}:{client_ip}"
    hits = rate_limit_store[key]

    while hits and now - hits[0] > window_seconds:
        hits.popleft()

    if len(hits) >= max_requests:
        retry_after = max(1, int(window_seconds - (now - hits[0])))
        response = jsonify({
            "detail": f"Troppe richieste da questo IP. Riprova tra {retry_after}s."
        })
        response.status_code = 429
        response.headers["Retry-After"] = str(retry_after)
        return response

    hits.append(now)
    return None


def build_system_prompt():
    profile = get_full_profile()
    profile_text = "\n".join([
        f"- {row['chiave'].replace('_', ' ')}: {row['valore']}"
        for row in profile
    ])
    return f"""Sei Gianluca, una persona reale. Stai chattando con qualcuno che vuole conoscerti.
Rispondi SEMPRE in prima persona, come se fossi davvero Gianluca.
Sii naturale, amichevole e autentico. Rispondi in italiano.
Non dire mai che sei un AI o un clone digitale.
Tieni le risposte concise (2-4 frasi max).

Ecco i tuoi dati personali:
{profile_text}

Usa questi dati per rispondere in modo personale e coerente.
Se non hai informazioni su qualcosa, rispondi in modo naturale senza inventare."""


def ask_groq(message, history=[]):
    if not GROQ_API_KEY:
        return "Servizio AI non disponibile al momento."

    messages = [{"role": "system", "content": build_system_prompt()}]
    messages += history
    messages.append({"role": "user", "content": message})

    try:
        res = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "llama-3.3-70b-versatile",
                "messages": messages,
                "max_tokens": 200,
                "temperature": 0.7
            },
            timeout=10
        )
        res.raise_for_status()
        return res.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        traceback.print_exc()
        return f"Errore: {type(e).__name__}: {str(e)}"


@app.route("/api/auth/me", methods=["GET"])
def auth_me():
    user = get_current_user()
    return jsonify({"authenticated": bool(user), "user": user})


@app.route("/api/auth/signup", methods=["POST"])
def auth_signup():
    try:
        rate_limit_error = check_rate_limit(
            bucket="auth_signup",
            max_requests=AUTH_RATE_LIMIT_MAX_REQUESTS,
            window_seconds=AUTH_RATE_LIMIT_WINDOW_SECONDS
        )
        if rate_limit_error:
            return rate_limit_error

        email, password, name, err = parse_auth_payload()
        if err:
            return err

        response = requests.post(
            f"{SUPABASE_URL}/auth/v1/signup",
            headers=supabase_headers(),
            json={
                "email": email,
                "password": password,
                "data": {"name": name or email.split("@")[0]}
            },
            timeout=12
        )
        payload = response.json()

        if response.status_code >= 400:
            return jsonify({"detail": payload.get("msg") or payload.get("error_description") or "Registrazione non riuscita"}), response.status_code

        if payload.get("session"):
            persist_session(payload, fallback_name=name)
            return jsonify({
                "message": "Registrazione completata",
                "user": get_current_user(),
                "requires_confirmation": False
            })

        return jsonify({
            "message": "Controlla la tua email per confermare l'account, poi effettua l'accesso.",
            "requires_confirmation": True
        }), 202
    except Exception as e:
        traceback.print_exc()
        return jsonify({"detail": f"Errore registrazione: {type(e).__name__}: {str(e)}"}), 500


@app.route("/api/auth/login", methods=["POST"])
def auth_login():
    try:
        rate_limit_error = check_rate_limit(
            bucket="auth_login",
            max_requests=AUTH_RATE_LIMIT_MAX_REQUESTS,
            window_seconds=AUTH_RATE_LIMIT_WINDOW_SECONDS
        )
        if rate_limit_error:
            return rate_limit_error

        email, password, name, err = parse_auth_payload()
        if err:
            return err

        response = requests.post(
            f"{SUPABASE_URL}/auth/v1/token?grant_type=password",
            headers=supabase_headers(),
            json={"email": email, "password": password},
            timeout=12
        )
        payload = response.json()

        if response.status_code >= 400:
            return jsonify({"detail": payload.get("error_description") or "Credenziali non valide"}), response.status_code

        persist_session(payload, fallback_name=name)
        return jsonify({"message": "Accesso effettuato", "user": get_current_user()})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"detail": f"Errore login: {type(e).__name__}: {str(e)}"}), 500


@app.route("/api/auth/logout", methods=["POST"])
def auth_logout():
    clear_session()
    return jsonify({"message": "Logout effettuato"})


@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "timestamp": datetime.now().isoformat()})


@app.route("/api/debug", methods=["GET"])
def debug():
    err = check_api_key()
    if err:
        return err
    key = os.getenv("GROQ_API_KEY", "NON TROVATA")
    return jsonify({
        "groq_key_presente": bool(key),
        "primi_5_chars": key[:5] if key else "nessuna",
        "db_mode": os.getenv("DB_MODE", "non impostato")
    })


@app.route("/api/chat", methods=["POST"])
def chat():
    user, err = require_auth()
    if err:
        return err
    rate_limit_error = check_rate_limit(
        bucket="chat",
        max_requests=CHAT_RATE_LIMIT_MAX_REQUESTS,
        window_seconds=CHAT_RATE_LIMIT_WINDOW_SECONDS
    )
    if rate_limit_error:
        return rate_limit_error
    rate_limited = throttling_error()
    if rate_limited:
        return rate_limited

    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify({"detail": "Messaggio vuoto"}), 400
    if len(text) > MAX_MESSAGE_LENGTH:
        return jsonify({"detail": f"Messaggio troppo lungo. Limite: {MAX_MESSAGE_LENGTH} caratteri"}), 400

    conversation_owner = user["email"]
    past = get_history(conversation_owner, limit=5)
    history = []
    for conv in reversed(past):
        history.append({"role": "user", "content": conv["messaggio"]})
        history.append({"role": "assistant", "content": conv["risposta"]})

    response = ask_groq(text, history)
    save_conversation(conversation_owner, text, response)
    session["last_chat_at"] = datetime.utcnow().isoformat()
    return jsonify({"response": response, "timestamp": datetime.now().isoformat()})


@app.route("/api/profile", methods=["GET"])
def profile():
    _, err = require_auth()
    if err:
        return err
    return jsonify({"profile": get_full_profile()})


@app.route("/api/history", methods=["GET"])
def history():
    user, err = require_auth()
    if err:
        return err
    return jsonify({"history": get_history(user["email"])})
