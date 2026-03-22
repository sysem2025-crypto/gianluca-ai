from flask import Flask, request, jsonify
from flask_cors import CORS
from datetime import datetime
import os
import random
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# CORS
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "http://localhost:5500,null").split(",")
CORS(app, origins=ALLOWED_ORIGINS)

# API Key
API_KEY = os.getenv("API_KEY", "chiave-segreta-cambiami-123")

try:
    from database import get_profile_info, get_full_profile, save_conversation, get_history
except ImportError:
    from api.database import get_profile_info, get_full_profile, save_conversation, get_history

def check_api_key():
    key = request.headers.get("X-API-Key")
    if key != API_KEY:
        return jsonify({"detail": "API Key non valida"}), 403
    return None

KEYWORD_MAP = {
    "nome":           ["nome", "chiami", "sei gianluca"],
    "eta":            ["età", "anni", "quanti anni"],
    "citta":          ["città", "abiti", "vivi"],
    "lavoro":         ["lavoro", "professione", "fai nella vita", "mestiere"],
    "linguaggi":      ["linguaggi", "programmi", "coding", "codice"],
    "hobby":          ["hobby", "tempo libero", "passioni", "interessi"],
    "sport":          ["sport", "palestra", "allenamento"],
    "musica":         ["musica", "ascolti", "cantante"],
    "cibo_preferito": ["cibo", "mangi", "piatto"],
    "film_preferito": ["film", "cinema"],
    "serie_preferita":["serie", "tv", "netflix"],
    "carattere":      ["carattere", "personalità"],
    "valori":         ["valori", "credi"],
    "obiettivo":      ["obiettivo", "sogno"],
}

LABELS = {
    "nome":           "Mi chiamo",
    "eta":            "Ho",
    "citta":          "Abito a",
    "lavoro":         "Lavoro come",
    "linguaggi":      "I linguaggi che uso sono",
    "hobby":          "Nel tempo libero mi piace",
    "sport":          "Faccio",
    "musica":         "Ascolto",
    "cibo_preferito": "Il mio cibo preferito è",
    "film_preferito": "Il mio film preferito è",
    "serie_preferita":"La mia serie preferita è",
    "carattere":      "Sono",
    "valori":         "Per me sono importanti",
    "obiettivo":      "Il mio obiettivo è",
}

FALLBACK = [
    "Interessante! Puoi dirmi qualcosa in più?",
    "Non ho capito bene, prova a riformulare.",
    "Bella domanda! Sto ancora imparando.",
]

def get_response(message):
    msg_lower = message.lower()
    for key, keywords in KEYWORD_MAP.items():
        if any(kw in msg_lower for kw in keywords):
            value = get_profile_info(key)
            if value:
                return f"{LABELS.get(key, key)} {value}."
    return random.choice(FALLBACK)

@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "timestamp": datetime.now().isoformat()})

@app.route("/api/chat", methods=["POST"])
def chat():
    err = check_api_key()
    if err: return err
    data = request.get_json()
    text = data.get("text", "")
    user = data.get("user", "Anonimo")
    response = get_response(text)
    save_conversation(user, text, response)
    return jsonify({"response": response, "timestamp": datetime.now().isoformat()})

@app.route("/api/profile", methods=["GET"])
def profile():
    err = check_api_key()
    if err: return err
    return jsonify({"profile": get_full_profile()})

@app.route("/api/history/<user>", methods=["GET"])
def history(user):
    err = check_api_key()
    if err: return err
    return jsonify({"history": get_history(user)})