from flask import Flask, request, jsonify
from flask_cors import CORS
from datetime import datetime
import os
import json
import traceback
import requests
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# CORS
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "http://localhost:5500,null").split(",")
CORS(app, origins=ALLOWED_ORIGINS)

# API Keys
API_KEY = os.getenv("API_KEY", "chiave-segreta-cambiami-123")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

try:
    from database import get_profile_info, get_full_profile, save_conversation, get_history
except ImportError:
    from api.database import get_profile_info, get_full_profile, save_conversation, get_history


def check_api_key():
    key = request.headers.get("X-API-Key")
    if key != API_KEY:
        return jsonify({"detail": "API Key non valida"}), 403
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


@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "timestamp": datetime.now().isoformat()})


@app.route("/api/debug", methods=["GET"])
def debug():
    key = os.getenv("GROQ_API_KEY", "NON TROVATA")
    return jsonify({
        "groq_key_presente": bool(key),
        "primi_5_chars": key[:5] if key else "nessuna",
        "db_mode": os.getenv("DB_MODE", "non impostato")
    })


@app.route("/api/chat", methods=["POST"])
def chat():
    err = check_api_key()
    if err:
        return err
    data = request.get_json()
    text = data.get("text", "")
    user = data.get("user", "Anonimo")

    past = get_history(user, limit=5)
    history = []
    for conv in reversed(past):
        history.append({"role": "user", "content": conv["messaggio"]})
        history.append({"role": "assistant", "content": conv["risposta"]})

    response = ask_groq(text, history)
    save_conversation(user, text, response)
    return jsonify({"response": response, "timestamp": datetime.now().isoformat()})


@app.route("/api/profile", methods=["GET"])
def profile():
    err = check_api_key()
    if err:
        return err
    return jsonify({"profile": get_full_profile()})


@app.route("/api/history/<user>", methods=["GET"])
def history(user):
    err = check_api_key()
    if err:
        return err
    return jsonify({"history": get_history(user)})