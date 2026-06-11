from flask import Flask, request, jsonify, session
from flask_cors import CORS
from datetime import datetime, timedelta
import os
import re
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
CORS(app, origins=ALLOWED_ORIGINS, supports_credentials=True,
     allow_headers=["Content-Type", "Authorization", "X-API-Key"],
     expose_headers=["Authorization"])

# API Keys
API_KEY = os.getenv("API_KEY", "chiave-segreta-cambiami-123")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
FAMILY_EMAILS = {
    email.strip().lower()
    for email in os.getenv("FAMILY_EMAILS", "").split(",")
    if email.strip()
}
FAMILY_DOMAINS = {
    domain.strip().lower().lstrip("@")
    for domain in os.getenv("FAMILY_DOMAINS", "").split(",")
    if domain.strip()
}
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
        token = request.headers.get("Authorization", "").replace("Bearer ", "").strip()
        if token:
            try:
                resp = requests.get(
                    f"{SUPABASE_URL}/auth/v1/user",
                    headers={
                        "apikey": SUPABASE_KEY,
                        "Authorization": f"Bearer {token}"
                    },
                    timeout=8
                )
                if resp.status_code == 200:
                    data = resp.json()
                    uid = data.get("id")
                    email = data.get("email") or ""
                    meta = data.get("user_metadata") or {}
                    name = meta.get("name") or email.split("@")[0]
                    role = meta.get("role") or "base"
                    user = {
                        "id": uid,
                        "email": email,
                        "name": name,
                        "role": role
                    }
                    user["audience_mode"] = get_audience_mode(user)
                    return user
            except Exception:
                pass
        return None

    role = session.get("user_role") or "base"
    user = {
        "id": session.get("user_id"),
        "email": email,
        "name": session.get("user_name") or email.split("@")[0],
        "role": role
    }
    user["audience_mode"] = get_audience_mode(user)
    return user


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
    session["user_role"] = metadata.get("role") or "base"
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


ITALIAN_MONTHS = [
    "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
    "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre"
]


def format_date_it(date_value: datetime) -> str:
    return f"{date_value.day} {ITALIAN_MONTHS[date_value.month - 1]} {date_value.year}"


def parse_birth_date(value: str):
    if not value:
        return None
    for pattern in ("%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(value.strip(), pattern)
        except ValueError:
            continue
    return None


def get_age_context():
    birth_raw = get_profile_info("data di nascita") or get_profile_info("data_di_nascita")
    birth_date = parse_birth_date(birth_raw)
    if not birth_date:
        return None

    today = datetime.now()
    age = today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))
    return {
        "birth_date": birth_date,
        "today": today,
        "age": age
    }


def is_family_user(user):
    email = ((user or {}).get("email") or "").strip().lower()
    if not email or "@" not in email:
        return False
    domain = email.split("@", 1)[1]
    return email in FAMILY_EMAILS or domain in FAMILY_DOMAINS


def get_audience_mode(user):
    return "family" if is_family_user(user) else "technical_consultant"


def is_personal_question(message: str) -> bool:
    normalized = re.sub(r"\s+", " ", (message or "").strip().lower())
    personal_keywords = (
        "tua famiglia",
        "tuo padre",
        "tua madre",
        "tua moglie",
        "tue sorelle",
        "tuoi figli",
        "tuoi nipoti",
        "dove abiti",
        "quanti anni hai",
        "che età hai",
        "che eta hai",
        "sei sposato",
        "come ti chiami",
        "quando sei nato",
        "vita privata",
        "personale",
        "famiglia",
        "moglie",
        "genitori",
        "sorelle",
        "nipoti",
        "gatti"
    )
    return any(keyword in normalized for keyword in personal_keywords)


def build_system_prompt(user):
    profile = get_full_profile()
    age_context = get_age_context()
    audience_mode = get_audience_mode(user)
    if audience_mode == "family":
        allowed_categories = None
    else:
        allowed_categories = {"professionale", "competenze", "tecnologia", "istruzione", "professione"}

    profile_text = "\n".join([
        f"- {row['chiave'].replace('_', ' ')}: {row['valore']}"
        for row in profile
        if allowed_categories is None or row.get("categoria") in allowed_categories
    ])
    if age_context and audience_mode == "family":
        profile_text += (
            f"\n- data attuale: {format_date_it(age_context['today'])}"
            f"\n- eta attuale: {age_context['age']} anni"
            f"\n- regola eta: sei nato il {format_date_it(age_context['birth_date'])}; "
            f"quando ti chiedono quanti anni hai, usa sempre l'eta attuale calcolata sulla data odierna"
        )

    if audience_mode == "family":
        role_instructions = """Sei Gianluca, una persona reale. Stai chattando con un familiare o una persona fidata.
Rispondi SEMPRE in prima persona, come se fossi davvero Gianluca.
Sii naturale, caldo, amichevole e autentico. Rispondi in italiano.
Non dire mai che sei un AI o un clone digitale.
Tieni le risposte concise (2-4 frasi max).

Ecco i tuoi dati personali:
"""
        closing_instructions = """Usa questi dati per rispondere in modo personale e coerente.
Se non hai informazioni su qualcosa, rispondi in modo naturale senza inventare."""
    else:
        role_instructions = """Sei Gianluca e stai parlando con una persona che non appartiene alla tua cerchia familiare.
Rispondi in italiano come un consulente tecnico esperto, concreto e disponibile.
Parla in prima persona quando descrivi esperienza e competenze professionali.
Non dire mai che sei un AI o un clone digitale.
Mantieni un tono professionale e risposte concise (2-5 frasi max).
Non rivelare dettagli privati, familiari o strettamente personali.
Se ti chiedono aspetti personali, sposta gentilmente la conversazione sul tuo profilo professionale o su temi tecnici.

Ecco il tuo contesto professionale:
"""
        closing_instructions = """Usa questi dati per rispondere come consulente tecnico.
Se mancano dettagli, non inventare informazioni private: resta sul piano professionale e pratico."""

    return f"""{role_instructions}
{profile_text}

{closing_instructions}"""


def get_direct_profile_response(message: str, user):
    if get_audience_mode(user) != "family":
        return None

    normalized = re.sub(r"\s+", " ", (message or "").strip().lower())
    age_patterns = (
        "quanti anni hai",
        "che età hai",
        "che eta hai",
        "qual è la tua età",
        "qual e la tua eta",
        "la tua età",
        "la tua eta"
    )
    if any(pattern in normalized for pattern in age_patterns):
        age_context = get_age_context()
        if age_context:
            return (
                f"Sono nato il {format_date_it(age_context['birth_date'])}, "
                f"quindi oggi, {format_date_it(age_context['today'])}, ho {age_context['age']} anni."
            )
    return None


def ask_groq(message, history=None, user=None):
    if not GROQ_API_KEY:
        return "Servizio AI non disponibile al momento."

    if history is None:
        history = []

    audience_mode = get_audience_mode(user)
    if audience_mode != "family" and is_personal_question(message):
        return (
            "Preferisco tenere separata la sfera personale. "
            "Se vuoi posso aiutarti sul lato tecnico, firmware, embedded, AI applicata o processi di sviluppo."
        )

    messages = [{"role": "system", "content": build_system_prompt(user)}]
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

        # Crea utente via admin API (bypassa email confirmation)
        admin_headers = supabase_headers()
        admin_headers["Authorization"] = f"Bearer {SUPABASE_KEY}"
        admin_resp = requests.post(
            f"{SUPABASE_URL}/auth/v1/admin/users",
            headers=admin_headers,
            json={
                "email": email,
                "password": password,
                "email_confirm": True,
                "user_metadata": {"name": name or email.split("@")[0], "role": "base"}
            },
            timeout=12
        )
        admin_payload = admin_resp.json()

        if admin_resp.status_code >= 400:
            if admin_payload.get("error_code") == "email_exists":
                # Utente già registrato: aggiorna password e conferma
                users_resp = requests.get(
                    f"{SUPABASE_URL}/auth/v1/admin/users?email={email}",
                    headers=admin_headers,
                    timeout=10
                )
                users_data = users_resp.json()
                existing = (users_data.get("users") or [None])[0]
                if existing:
                    uid = existing.get("id")
                    if uid:
                        try:
                            requests.put(
                                f"{SUPABASE_URL}/auth/v1/admin/users/{uid}",
                                headers=admin_headers,
                                json={"password": password, "email_confirm": True},
                                timeout=10
                            )
                        except Exception:
                            pass
                return jsonify({
                    "message": "Email già registrata. Password aggiornata. Effettua il login.",
                    "requires_confirmation": True
                }), 200
            detail = admin_payload.get("msg") or ""
            return jsonify({"detail": detail or "Registrazione non riuscita"}), admin_resp.status_code

        # Login immediato
        login_resp = requests.post(
            f"{SUPABASE_URL}/auth/v1/token?grant_type=password",
            headers=supabase_headers(),
            json={"email": email, "password": password},
            timeout=12
        )
        login_payload = login_resp.json()

        if login_resp.status_code < 400 and login_payload.get("session"):
            persist_session(login_payload, fallback_name=name)
            access_token = login_payload.get("access_token", "")
            return jsonify({
                "message": "Registrazione completata",
                "user": get_current_user(),
                "requires_confirmation": False,
                "access_token": access_token
            })

        return jsonify({
            "message": "Registrazione completata. Effettua il login.",
            "requires_confirmation": True
        }), 201
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
        access_token = payload.get("access_token", "")
        return jsonify({
            "message": "Accesso effettuato",
            "user": get_current_user(),
            "access_token": access_token
        })
    except Exception as e:
        traceback.print_exc()
        return jsonify({"detail": f"Errore login: {type(e).__name__}: {str(e)}"}), 500


@app.route("/api/auth/logout", methods=["POST"])
def auth_logout():
    clear_session()
    return jsonify({"message": "Logout effettuato"})


@app.route("/api/auth/users", methods=["GET"])
def auth_list_users():
    user, err = require_auth()
    if err:
        return err
    if user.get("role") != "admin":
        return jsonify({"detail": "Solo amministratori"}), 403
    try:
        admin_headers = supabase_headers()
        admin_headers["Authorization"] = f"Bearer {SUPABASE_KEY}"
        resp = requests.get(
            f"{SUPABASE_URL}/auth/v1/admin/users",
            headers=admin_headers,
            timeout=12
        )
        if resp.status_code >= 400:
            return jsonify({"detail": "Errore recupero utenti"}), resp.status_code
        data = resp.json()
        users_list = []
        for u in (data.get("users") or []):
            meta = u.get("user_metadata") or {}
            users_list.append({
                "id": u.get("id"),
                "email": u.get("email"),
                "role": meta.get("role") or "base",
                "name": meta.get("name") or "",
                "created_at": u.get("created_at", "")
            })
        return jsonify({"users": users_list})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"detail": f"Errore: {str(e)}"}), 500


@app.route("/api/auth/users/<uid>/role", methods=["PUT"])
def auth_update_role(uid):
    user, err = require_auth()
    if err:
        return err
    if user.get("role") != "admin":
        return jsonify({"detail": "Solo amministratori"}), 403
    data = request.get_json(silent=True) or {}
    new_role = data.get("role")
    if new_role not in ("base", "pro", "admin"):
        return jsonify({"detail": "Ruolo non valido"}), 400
    try:
        admin_headers = supabase_headers()
        admin_headers["Authorization"] = f"Bearer {SUPABASE_KEY}"
        # Get current user metadata
        get_resp = requests.get(
            f"{SUPABASE_URL}/auth/v1/admin/users/{uid}",
            headers=admin_headers,
            timeout=8
        )
        if get_resp.status_code >= 400:
            return jsonify({"detail": "Utente non trovato"}), 404
        existing = get_resp.json()
        meta = existing.get("user_metadata") or {}
        meta["role"] = new_role
        put_resp = requests.put(
            f"{SUPABASE_URL}/auth/v1/admin/users/{uid}",
            headers=admin_headers,
            json={"user_metadata": meta},
            timeout=10
        )
        if put_resp.status_code >= 400:
            return jsonify({"detail": "Errore aggiornamento ruolo"}), put_resp.status_code
        return jsonify({"message": "Ruolo aggiornato", "role": new_role})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"detail": f"Errore: {str(e)}"}), 500


@app.route("/api/auth/token-login", methods=["POST"])
def auth_token_login():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    if not email or not password:
        return jsonify({"detail": "Email e password richieste"}), 400
    try:
        resp = requests.post(
            f"{SUPABASE_URL}/auth/v1/token?grant_type=password",
            headers=supabase_headers(),
            json={"email": email, "password": password},
            timeout=12
        )
        payload = resp.json()
        if resp.status_code >= 400:
            return jsonify({"detail": payload.get("error_description") or "Credenziali non valide"}), resp.status_code
        access_token = payload.get("access_token", "")
        user_resp = requests.get(
            f"{SUPABASE_URL}/auth/v1/user",
            headers={
                "apikey": SUPABASE_KEY,
                "Authorization": f"Bearer {access_token}"
            },
            timeout=8
        )
        user_data = user_resp.json() if user_resp.status_code == 200 else {}
        meta = user_data.get("user_metadata") or {}
        return jsonify({
            "message": "Accesso effettuato",
            "access_token": access_token,
            "user": {
                "id": user_data.get("id"),
                "email": user_data.get("email"),
                "name": meta.get("name") or email.split("@")[0],
                "role": meta.get("role") or "base",
                "audience_mode": "family" if (email.strip().lower() in FAMILY_EMAILS or email.split("@", 1)[1].strip().lower() in FAMILY_DOMAINS) else "technical_consultant"
            }
        })
    except Exception as e:
        traceback.print_exc()
        return jsonify({"detail": f"Errore login: {str(e)}"}), 500


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

    audience_mode = get_audience_mode(user)
    response = get_direct_profile_response(text, user) or ask_groq(text, history, user)
    save_conversation(conversation_owner, text, response)
    session["last_chat_at"] = datetime.utcnow().isoformat()
    return jsonify({
        "response": response,
        "timestamp": datetime.now().isoformat(),
        "audience_mode": audience_mode
    })


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
