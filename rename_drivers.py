import os
import firebase_admin
from firebase_admin import credentials, firestore

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FIREBASE_KEY = os.path.join(BASE_DIR, "firebase_key.json")
COLLECTION = "drivers"

# Mappe: "VecchioNome": "NuovoNome"
RENAMES = {
    "JigenBiker": "RKE_JigenBiker",
    "MontyRidesAgain": "RKE_Monty"
}

def main():
    if not os.path.exists(FIREBASE_KEY):
        print(f"ERRORE: {FIREBASE_KEY} non trovato.")
        return

    cred = credentials.Certificate(FIREBASE_KEY)
    firebase_admin.initialize_app(cred)
    db = firestore.client()

    print("--- INIZIO RINOMINA DRIVER ---")
    batch = db.batch()

    for old_name, new_name in RENAMES.items():
        old_ref = db.collection(COLLECTION).document(old_name)
        new_ref = db.collection(COLLECTION).document(new_name)

        doc = old_ref.get()
        if not doc.exists:
            print(f"[SKIP] {old_name} non esiste in Firestore.")
            continue

        data = doc.to_dict()
        data["psn"] = new_name # Aggiorno anche il campo psn interno
        
        # Copia i dati nel nuovo documento
        batch.set(new_ref, data)
        # Cancella il vecchio documento
        batch.delete(old_ref)
        
        print(f"[OK] Preparato rename: {old_name} -> {new_name}")

    print("Eseguo il batch...")
    batch.commit()
    print("--- COMPLETATO ---")

if __name__ == "__main__":
    main()
