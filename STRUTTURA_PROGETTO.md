# Struttura del progetto `gianluca-ai`

Questo repository contiene un clone digitale personale con:

- frontend statico in `index.html`
- backend Python/Flask nella cartella `api`
- dati profilo in JSON e database SQLite locale
- script di supporto per inizializzare il database

## Vista rapida

```text
gianluca-ai/
├── .git/                     # repository Git
├── api/                      # backend API
├── data/                     # dati sorgente del profilo
├── scripts/                  # script di setup/supporto
├── venv/                     # ambiente virtuale Python
├── .env                      # variabili ambiente e chiavi
├── .gitignore                # file ignorati da Git
├── gianluca.db               # database SQLite locale
├── index.html                # frontend della chat
├── README.md                 # descrizione minima del progetto
├── requirements.txt          # dipendenze Python principali
├── vercel.json               # configurazione deploy
├── vercel - Copia.json       # copie di configurazione
├── vercel - Copia (2).json   # copie di configurazione
└── STRUTTURA_PROGETTO.md     # questo documento
```

## Dettaglio cartelle

### `api/`

Contiene il backend del clone digitale.

- `main.py`
  Espone le API principali con Flask:
  - `GET /api/health`
  - `GET /api/debug`
  - `POST /api/chat`
  - `GET /api/profile`
  - `GET /api/history/<user>`
- `database.py`
  Gestisce accesso ai dati in due modalità:
  - SQLite locale tramite `gianluca.db`
  - Supabase tramite API client
- `index.py`
  Probabile entrypoint alternativo per deploy/serverless.
- `requirements.txt`
  Dipendenze specifiche del backend.
- `main - Copia.py`
  Copia di backup del file principale.
- `Supbasekey.txt`
  File collegato a credenziali/configurazione Supabase.
  Attenzione: conviene evitare di mantenerlo in chiaro nel repo.
- `__pycache__/`
  File compilati Python generati automaticamente.

### `data/`

Contiene i dati strutturati usati per costruire il profilo del clone.

- `gianluca_profile.json`
  Archivio principale delle informazioni personali, professionali e familiari
  che alimentano il prompt e il database.

### `scripts/`

Contiene utilità operative.

- `setup_db.py`
  Inizializza il database e importa i dati da `data/gianluca_profile.json`.
- `gianluca_profile.csv`
  Versione tabellare dei dati profilo, utile per editing o import/export.
- `Nuovo Documento di testo.txt`
  File generico di appoggio, probabilmente non essenziale al funzionamento.

### `venv/`

Ambiente virtuale locale Python. Serve per installare le dipendenze senza
sporcare l'installazione globale del sistema.

## File principali in root

### `index.html`

Frontend statico della chat:

- contiene HTML, CSS e JavaScript nello stesso file
- mostra interfaccia conversazionale con avatar, messaggi e stato online
- chiama l'API remota `https://gianluca-ai-ten.vercel.app/api`

### `gianluca.db`

Database SQLite locale. In base al codice di `api/database.py`, contiene almeno:

- `gianluca_profile`
- `conversazioni`
- `preferenze`

### `.env`

Contiene la configurazione runtime, ad esempio:

- `API_KEY`
- `GROQ_API_KEY`
- `DB_MODE`
- origini CORS
- eventuali credenziali Supabase

Attenzione: è un file sensibile e non dovrebbe essere esposto.

### `requirements.txt`

Dipendenze Python del progetto. Da confrontare con `api/requirements.txt`
per capire se ci sono duplicazioni o differenze tra ambiente locale e deploy.

### `vercel.json` e copie

Configurazione per deploy su Vercel. Le versioni con "Copia" sembrano backup o
tentativi precedenti di configurazione.

## Flusso logico del progetto

1. I dati personali vengono definiti in `data/gianluca_profile.json`.
2. Lo script `scripts/setup_db.py` popola SQLite o Supabase.
3. Il backend in `api/main.py` legge profilo e cronologia conversazioni.
4. Il backend invia il prompt al modello tramite Groq API.
5. `index.html` invia i messaggi utente alle API e mostra le risposte.

## Note utili

- Il progetto oggi usa Flask nel backend, anche se in alcuni dati compare la
  descrizione "FastAPI": quindi la documentazione interna non è del tutto allineata.
- Sono presenti file duplicati o di backup (`main - Copia.py`, file `vercel` copiati).
- Sono presenti file sensibili o potenzialmente sensibili (`.env`, `Supbasekey.txt`).
- `venv/` e `__pycache__/` sono contenuti tecnici locali, non logica applicativa.

## Suggerimenti di pulizia futura

- Rimuovere o archiviare i file di copia non più utili.
- Verificare che i segreti non siano versionati.
- Separare frontend, backend e configurazioni in modo più ordinato.
- Aggiungere una documentazione più completa in `README.md`.
