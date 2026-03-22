from fastapi import FastAPI, HTTPException, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security.api_key import APIKeyHeader
from pydantic import BaseModel
from datetime import datetime
import os
import random
from dotenv import load_dotenv

try:
    from database import (
        get_profile_info,
        get_full_profile,
        save_conversation,
        get_history
    )
except ImportError:
    from api.database import (
        get_profile_info,
        get_full_profile,
        save_conversation,
        get_history
    )

load_dotenv()

app = FastAPI(title="Gianluca AI", version="1.0.0")

# ✅ CORS
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "http://localhost:8000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)

# ✅ API Key
API_KEY = os.getenv("API_KEY", "dev-key-locale")
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

def verify_api_key(key: str = Security(api_key_header)):
    if key != API_KEY:
        raise HTTPException(status_code=403, detail="API Key non valida")
    return key

# ─────────────────────────────────────────
# MODELLI
# ─────────────────────────────────────────

class Message(BaseModel):
    text: str
    user: str = "Anonimo"

class ChatResponse(BaseModel):
    response: str
    timestamp: str

# ─────────────────────────────────────────
# LOGICA RISPOSTE
# ─────────────────────────────────────────

KEYWORD_MAP = {
    "nome":             ["nome", "chiami", "sei gianluca"],
    "eta":              ["età", "anni", "quanti anni"],
    "citta":            ["città", "abiti", "vivi", "abiti"],
    "lavoro":           ["lavoro", "professione", "fai nella vita", "mestiere"],
    "linguaggi":        ["linguaggi", "programmi", "coding", "codice"],
    "hobby":            ["hobby", "tempo libero", "passioni", "interessi", "interesse"],
    "sport":            ["sport", "palestra", "allenamento"],
    "musica":           ["musica", "ascolti", "cantante"],
    "cibo_preferito":   ["cibo", "mangi", "piatto", "preferisci mangiare"],
    "film_preferito":   ["film", "cinema", "pellicola"],
    "serie_preferita":  ["serie", "tv", "netflix"],
    "carattere":        ["carattere", "personalità", "tipo di persona"],
    "valori":           ["valori", "credi", "importante per te"],
    "obiettivo":        ["obiettivo", "sogno", "vuoi fare"],
}

FALLBACK_RESPONSES = [
    "Interessante! Puoi dirmi qualcosa in più?",
    "Non ho capito bene, prova a riformulare.",
    "Bella domanda! Sto ancora imparando a rispondere a tutto.",
    "Su questo non ho informazioni, ma puoi aggiornarmi!",
]

def get_personalized_response(message: str) -> str:
    msg_lower = message.lower()

    for profile_key, keywords in KEYWORD_MAP.items():
        if any(kw in msg_lower for kw in keywords):
            value = get_profile_info(profile_key)
            if value:
                labels = {
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
                label = labels.get(profile_key, profile_key.replace("_", " ").capitalize())
                return f"{label} {value}."

    return random.choice(FALLBACK_RESPONSES)

# ─────────────────────────────────────────
# ENDPOINTS
# ─────────────────────────────────────────

@app.post("/api/chat", response_model=ChatResponse)
async def chat(message: Message, _: str = Security(verify_api_key)):
    response = get_personalized_response(message.text)
    save_conversation(message.user, message.text, response)
    return ChatResponse(
        response=response,
        timestamp=datetime.now().isoformat()
    )

@app.get("/api/profile")
async def profile(_: str = Security(verify_api_key)):
    return {"profile": get_full_profile()}

@app.get("/api/history/{user}")
async def history(user: str, _: str = Security(verify_api_key)):
    return {"history": get_history(user)}

@app.get("/api/health")
async def health():
    return {"status": "ok", "timestamp": datetime.now().isoformat()}

from mangum import Mangum
handler = Mangum(app)
    