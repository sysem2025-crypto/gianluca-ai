import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from api.database import init_sqlite, get_sqlite_connection

def populate_profile():
    conn = get_sqlite_connection()
    
    # ─────────────────────────────────────────
    # 👤 MODIFICA QUESTI DATI CON I TUOI!
    # ─────────────────────────────────────────
    profilo = [
        # Anagrafica
        ("nome",            "Gianluca",                     "anagrafica"),
        ("eta",             "30",                           "anagrafica"),
        ("citta",           "Milano",                       "anagrafica"),
        ("nazionalita",     "Italiana",                     "anagrafica"),

        # Professione
        ("lavoro",          "Sviluppatore",                 "professione"),
        ("azienda",         "Freelance",                    "professione"),
        ("anni_esperienza", "5",                            "professione"),
        ("linguaggi",       "Python, JavaScript, SQL",      "professione"),

        # Personalità
        ("carattere",       "Curioso, determinato, creativo","personalita"),
        ("valori",          "Famiglia, crescita, libertà",  "personalita"),
        ("obiettivo",       "Costruire prodotti utili",     "personalita"),

        # Hobby e interessi
        ("hobby",           "Programmazione, palestra, musica", "interessi"),
        ("sport",           "Palestra, running",            "interessi"),
        ("musica",          "Rock, elettronica",            "interessi"),
        ("libri",           "Fantascienza, saggi tech",     "interessi"),

        # Gusti
        ("cibo_preferito",  "Pizza margherita",             "gusti"),
        ("bevanda",         "Caffè",                        "gusti"),
        ("film_preferito",  "Interstellar",                 "gusti"),
        ("serie_preferita", "Black Mirror",                 "gusti"),
    ]

    conn.executemany(
        """INSERT INTO gianluca_profile (chiave, valore, categoria)
           VALUES (?, ?, ?)
           ON CONFLICT(chiave) DO UPDATE SET valore=excluded.valore""",
        profilo
    )

    # ─────────────────────────────────────────
    # ❤️ PREFERENZE (cosa ti piace/non piace)
    # ─────────────────────────────────────────
    preferenze = [
        ("tecnologia",  "Intelligenza Artificiale",     9, "Appassionato"),
        ("tecnologia",  "Open Source",                  8, "Supporter"),
        ("cibo",        "Pizza",                        10, "La migliore"),
        ("cibo",        "Sushi",                        7,  "Mi piace"),
        ("sport",       "Palestra",                     8,  "3 volte a settimana"),
        ("musica",      "Rock anni 90",                 9,  "Sempre in cuffia"),
    ]

    conn.executemany(
        "INSERT INTO preferenze (categoria, valore, importanza, note) VALUES (?, ?, ?, ?)",
        preferenze
    )

    conn.commit()
    conn.close()
    print("✅ Profilo popolato con successo!")

if __name__ == "__main__":
    print("🚀 Inizializzazione database locale...")
    init_sqlite()
    populate_profile()
    print("\n✅ Database pronto in: gianluca.db")
    print("📋 Puoi modificare i tuoi dati in scripts/setup_db.py")