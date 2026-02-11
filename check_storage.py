import os
import firebase_admin
from firebase_admin import credentials, storage

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FIREBASE_KEY = os.path.join(BASE_DIR, "firebase_key.json")

def main():
    if not os.path.exists(FIREBASE_KEY):
        print(f"ERRORE: {FIREBASE_KEY} non trovato.")
        return

    cred = credentials.Certificate(FIREBASE_KEY)
    firebase_admin.initialize_app(cred)

    print("--- Cerco Bucket Storage ---")
    try:
        # Senza specificare nome, prova a listare o chiede quello di default se configurato
        # In admin sdk python, storage.bucket() senza argomenti richiede 'storageBucket' in options
        # Ma noi vogliamo SCOPRIRLO.
        
        # Purtroppo firebase-admin non ha un metodo diretto "list_buckets" facile senza Google Cloud Client
        # Proviamo ad usare google-cloud-storage direttamente usando le credenziali
        from google.cloud import storage as gcs
        
        client = gcs.Client.from_service_account_json(FIREBASE_KEY)
        buckets = list(client.list_buckets())
        
        if not buckets:
            print("Nessun bucket trovato. Hai abilitato Storage nella console Firebase?")
        else:
            print(f"Trovati {len(buckets)} bucket:")
            for b in buckets:
                print(f"  - {b.name}")

    except Exception as e:
        print(f"Errore: {e}")
        print("\nNOTA: Potrebbe essere necessario abilitare 'Firebase Storage' nella console.")

if __name__ == "__main__":
    main()
