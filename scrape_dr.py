"""
CI-ready / no GitHub / merge from Firestore

MODIFICHE PRINCIPALI:
1. ChromeOptions configurato per headless Linux (--headless=new, --no-sandbox, --disable-dev-shm-usage, --window-size=1920,1080)
2. Rimosso CHROMEDRIVER_PATH hardcoded, ora usa webdriver-manager per gestire chromedriver automaticamente
3. Eliminate tutte le variabili e funzioni GitHub: REPO_OWNER, REPO_NAME, BRANCH, TOKEN_FILE, GITHUB_AVATAR_BASE, github_upload_file()
4. Rimossa sezione "UPLOAD GITHUB" completa
5. Rimossa lettura token.txt
6. Merge ora usa Firestore come stato precedente: legge drivers/{psn} prima di processare
7. Se API non disponibile o valori 0 => pilota NON aggiornato, mantiene valori vecchi da Firestore
8. avatarUrl ora è stringa vuota "" (preparato per Storage futuro)
9. dr.json e anomalies.json scritti localmente solo per debug/output
10. Logging chiaro quando pilota viene skippato o usa valori vecchi
11. Gestione errori Firestore: se init fallisce, script continua e crea file locali
12. Dipendenza requests rimossa (non più necessaria senza GitHub)
"""

import os
import time
import re
import json
from datetime import datetime, timezone

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

import firebase_admin
from firebase_admin import credentials, firestore

# ============================================================
#   LISTA PILOTI
# ============================================================

PILOTI_LIST = [
    "RKE_MaxEpico1979",
    "RKE_Ekin",
    "RKE__Giuls",
    "RKE_Bazzo",
    "RKE_Cjcerbola",
    "RKE_Pepyx29",
    "RKE_MWalter",
    "RKE__Carra7",
    "RKE_Micky30",
    "RKE_Monty",
    "Daviderom_91",
    "RKE_BALDO44",
    "RKE_JigenBiker",
    "brummybulldog",
]

ALL_PILOTI = PILOTI_LIST[:]
piloti = PILOTI_LIST[:]

# ============================================================
#   CONFIG
# ============================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

AVATAR_DIR = os.path.join(BASE_DIR, "avatars")
os.makedirs(AVATAR_DIR, exist_ok=True)

CSS_SELECTOR_AVATAR = "img.driver-photo"

FIREBASE_SERVICE_ACCOUNT_FILE = os.path.join(BASE_DIR, "firebase_key.json")
FIRESTORE_COLLECTION = "drivers"
APP_META_COLLECTION = "app_meta"
APP_META_DOC = "latest"

DEBUG_WINS = False

# ============================================================
#   ALIAS LABEL
# ============================================================

STAT_ALIASES = {
    "drPoints": ["dr points"],
    "wins": ["wins"],
    "races": ["races"],
    "top5": ["top 5", "top5"],
    "poles": ["pole positions", "pole position"],
}

# ============================================================
#   HELPERS
# ============================================================

def estrai_numero(text):
    if not text:
        return 0
    clean = str(text).replace(",", "").replace(".", "")
    m = re.search(r"(\d+)", clean)
    return int(m.group(1)) if m else 0

def norm_label(s):
    if not s:
        return ""
    s = s.strip().lower()
    s = s.replace(":", "")
    s = re.sub(r"\s+", " ", s)
    return s

def pick_stat(stats_dict, aliases):
    for a in aliases:
        k = norm_label(a)
        if k in stats_dict:
            return stats_dict[k]
    return ""

# ============================================================
#   DEBUG
# ============================================================

def debug_all_wins(driver, psn):
    els = driver.find_elements(By.XPATH, "//span[contains(@class,'stat-label') and normalize-space()='Wins:']")
    print(f"[{psn}] Wins trovati: {len(els)}")
    for i, lab in enumerate(els, 1):
        try:
            val = lab.find_element(By.XPATH, "following-sibling::span[contains(@class,'stat-value')]").text.strip()
        except Exception:
            val = "?"
        try:
            h3 = lab.find_element(By.XPATH, "preceding::h3[1]").text.strip()
        except Exception:
            h3 = "(no h3)"
        print(f"[{psn}] Wins #{i} = {val} | sezione = {h3}")

# ============================================================
#   PARSE STATS
# ============================================================

def read_stats_daily_only(driver):
    out = {}
    labels = driver.find_elements(By.CSS_SELECTOR, "span.stat-label")

    for lab in labels:
        try:
            heading = lab.find_element(By.XPATH, "preceding::h3[1]").text
        except Exception:
            heading = ""

        if "daily race stats" not in (heading or "").strip().lower():
            continue

        try:
            lab_txt = norm_label(lab.text)
            if not lab_txt:
                continue

            val_span = lab.find_element(
                By.XPATH,
                "following-sibling::span[contains(@class,'stat-value')]",
            )
            out[lab_txt] = val_span.text.strip()
        except Exception:
            continue

    return out

def fallback_from_text(result_text):
    vals = {
        "drPoints": 0,
        "wins": 0,
        "races": 0,
        "top5": 0,
        "poles": 0,
    }

    patterns = {
        "drPoints": [r"DR\s*Points?[:：]?\s*([0-9\.,]+)"],
        "wins": [r"Wins?[:：]?\s*([0-9\.,]+)"],
        "races": [r"Races?[:：]?\s*([0-9\.,]+)"],
        "top5": [r"Top\s*5[:：]?\s*([0-9\.,]+)"],
        "poles": [r"Pole\s*Positions?[:：]?\s*([0-9\.,]+)"],
    }

    for k, pats in patterns.items():
        for pat in pats:
            m = re.search(pat, result_text or "", re.IGNORECASE)
            if m:
                vals[k] = estrai_numero(m.group(1))
                break

    return vals

def get_values_with_fallback(driver, psn):
    result_el = driver.find_element(By.ID, "result")
    result_text = result_el.text or ""

    stats = read_stats_daily_only(driver)

    dr_txt = pick_stat(stats, STAT_ALIASES["drPoints"])
    wins_txt = pick_stat(stats, STAT_ALIASES["wins"])
    races_txt = pick_stat(stats, STAT_ALIASES["races"])
    top5_txt = pick_stat(stats, STAT_ALIASES["top5"])
    poles_txt = pick_stat(stats, STAT_ALIASES["poles"])

    dr_points = estrai_numero(dr_txt)
    wins = estrai_numero(wins_txt)
    races = estrai_numero(races_txt)
    top5 = estrai_numero(top5_txt)
    poles = estrai_numero(poles_txt)

    print(f"  [{psn}] daily raw -> DR:'{dr_txt}' Wins:'{wins_txt}' Races:'{races_txt}' Top5:'{top5_txt}' Poles:'{poles_txt}'")
    print(f"  [{psn}] daily num -> DR={dr_points} Wins={wins} Races={races} Top5={top5} Poles={poles}")

    fb = fallback_from_text(result_text)

    if dr_points == 0 and fb["drPoints"] > 0:
        dr_points = fb["drPoints"]
    if wins == 0 and fb["wins"] > 0:
        wins = fb["wins"]
    if races == 0 and fb["races"] > 0:
        races = fb["races"]
    if top5 == 0 and fb["top5"] > 0:
        top5 = fb["top5"]
    if poles == 0 and fb["poles"] > 0:
        poles = fb["poles"]

    print(f"  [{psn}] final -> DR={dr_points} Wins={wins} Races={races} Top5={top5} Poles={poles}")

    return dr_points, wins, races, top5, poles, result_text

# ============================================================
#   FIREBASE
# ============================================================

def init_firestore():
    """Inizializza Firestore. Ritorna None se fallisce."""
    if not os.path.exists(FIREBASE_SERVICE_ACCOUNT_FILE):
        print(f"ATTENZIONE: manca {FIREBASE_SERVICE_ACCOUNT_FILE}. Salto Firebase.")
        return None
    try:
        if not firebase_admin._apps:
            cred = credentials.Certificate(FIREBASE_SERVICE_ACCOUNT_FILE)
            firebase_admin.initialize_app(cred)
        return firestore.client()
    except Exception as e:
        print(f"ATTENZIONE: init Firebase fallita: {e}")
        return None

def load_old_data_from_firestore(db, psn_list):
    """
    Legge da Firestore la collection 'drivers' per tutti i PSN in psn_list.
    Ritorna dict: {psn: {dr, drPoints, wins, races, top5, poles, winrate}}
    """
    old_by_psn = {}
    if db is None:
        print("Firestore non disponibile, nessun dato vecchio caricato.")
        return old_by_psn

    try:
        for psn in psn_list:
            doc_ref = db.collection(FIRESTORE_COLLECTION).document(psn)
            doc = doc_ref.get()
            if doc.exists:
                data = doc.to_dict()
                old_by_psn[psn] = {
                    "dr": int(data.get("dr", data.get("drPoints", 0)) or 0),
                    "drPoints": int(data.get("drPoints", data.get("dr", 0)) or 0),
                    "wins": int(data.get("wins", 0) or 0),
                    "races": int(data.get("races", 0) or 0),
                    "top5": int(data.get("top5", 0) or 0),
                    "poles": int(data.get("poles", 0) or 0),
                    "winrate": str(data.get("winrate", "-")),
                }
                print(f"[FIRESTORE] Caricati dati vecchi per {psn}: DR={old_by_psn[psn]['drPoints']}, Wins={old_by_psn[psn]['wins']}, Races={old_by_psn[psn]['races']}")
            else:
                print(f"[FIRESTORE] Nessun dato vecchio per {psn}")
    except Exception as e:
        print(f"Errore lettura dati vecchi da Firestore: {e}")

    return old_by_psn

def upload_to_firestore(db, final_results):
    """Carica i risultati finali su Firestore (drivers + app_meta/latest)."""
    if db is None:
        print("Firestore non disponibile, salto upload.")
        return

    try:
        now_iso = datetime.now(timezone.utc).isoformat()
        batch = db.batch()

        for item in final_results:
            psn = item.get("psn", "")
            if not psn:
                continue

            dr_points = int(item.get("drPoints", item.get("dr", 0)) or 0)
            wins = int(item.get("wins", 0) or 0)
            races = int(item.get("races", 0) or 0)

            doc_ref = db.collection(FIRESTORE_COLLECTION).document(psn)
            payload = {
                "psn": psn,
                "dr": dr_points,
                "drPoints": dr_points,
                "wins": wins,
                "races": races,
                "top5": int(item.get("top5", 0) or 0),
                "poles": int(item.get("poles", 0) or 0),
                "winrate": str(item.get("winrate", "-")),
                "avatarUrl": "",  # Preparato per Storage futuro
                "updatedAt": now_iso,
            }
            batch.set(doc_ref, payload, merge=True)

        meta_ref = db.collection(APP_META_COLLECTION).document(APP_META_DOC)
        batch.set(meta_ref, {"updatedAt": now_iso}, merge=True)

        batch.commit()
        print("Upload Firestore OK (drivers + app_meta/latest).")
    except Exception as e:
        print(f"Errore upload Firestore: {e}")

# ============================================================
#   ANOMALIE
# ============================================================

def build_anomaly_report(old_by_psn, final_results):
    anomalies = []
    for p in final_results:
        psn = p.get("psn", "")
        if not psn:
            continue

        old = old_by_psn.get(psn, {})
        old_wins = int(old.get("wins", 0) or 0)
        old_races = int(old.get("races", 0) or 0)

        wins = int(p.get("wins", 0) or 0)
        races = int(p.get("races", 0) or 0)
        top5 = int(p.get("top5", 0) or 0)
        poles = int(p.get("poles", 0) or 0)

        reasons = []

        if wins < old_wins:
            reasons.append(f"wins scese: {old_wins} -> {wins}")

        if races > 0 and wins > races:
            reasons.append(f"wins > races: {wins} > {races}")

        if races > 0 and top5 > races:
            reasons.append(f"top5 > races: {top5} > {races}")

        if races > 0 and poles > races:
            reasons.append(f"poles > races: {poles} > {races}")

        if old_races > 0 and races == 0:
            reasons.append(f"races azzerate: {old_races} -> 0")

        if reasons:
            anomalies.append({
                "psn": psn,
                "reasons": reasons,
                "old": {"wins": old_wins, "races": old_races},
                "new": {"wins": wins, "races": races, "top5": top5, "poles": poles},
            })

    return anomalies

# ============================================================
#   RUN
# ============================================================

# Configurazione Chrome per CI headless Linux
options = webdriver.ChromeOptions()
options.add_argument("--headless=new")
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")
options.add_argument("--window-size=1920,1080")
options.add_argument("--disable-gpu")

# Usa webdriver-manager per gestire chromedriver automaticamente
service = Service(ChromeDriverManager().install())
driver = webdriver.Chrome(service=service, options=options)

print("=== AGGIORNAMENTO DR PILOTI (Daily Race Stats) ===\n")
print("Modalità: CI-ready headless, merge da Firestore, no GitHub\n")

# Inizializza Firestore e carica dati vecchi
db = init_firestore()
old_by_psn = load_old_data_from_firestore(db, ALL_PILOTI)

new_results = {}

for psn in piloti:
    print("=================================")
    print(f"Lettura dati per: {psn}")
    skip_update = False

    try:
        driver.get("https://gtsh-rank.com/profile/")

        WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.ID, "psnid")))

        input_field = driver.find_element(By.ID, "psnid")
        input_field.clear()
        input_field.send_keys(psn)

        get_button = driver.find_element(By.XPATH, '//button[text()="GET"]')
        get_button.click()

        WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.ID, "result")))
        WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.CSS_SELECTOR, "span.stat-label")))

        result_el = driver.find_element(By.ID, "result")
        result_text_raw = (result_el.text or "").strip()

        if (not result_text_raw) or ("API not available" in result_text_raw) or ("API unavailable" in result_text_raw):
            print(f"  ⚠️  API non disponibile o result vuoto per {psn}")
            print(f"  ⏭️  SKIP: NON aggiorno questo pilota, mantengo dati vecchi da Firestore")
            skip_update = True
        else:
            time.sleep(1)

            if DEBUG_WINS:
                debug_all_wins(driver, psn)

            dr_points, wins, races, top5, poles, _ = get_values_with_fallback(driver, psn)

            if dr_points == 0 and wins == 0 and races == 0 and top5 == 0 and poles == 0:
                print(f"  ⚠️  Tutti valori 0 per {psn}, lettura fallita")
                print(f"  ⏭️  SKIP: NON aggiorno questo pilota, mantengo dati vecchi da Firestore")
                skip_update = True
            else:
                winrate = f"{(wins / races * 100):.1f}%" if races > 0 else "-"

        # Salva avatar (sempre, anche se skip_update)
        try:
            avatar_el = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, CSS_SELECTOR_AVATAR))
            )
            avatar_target = os.path.join(AVATAR_DIR, f"{psn}.png")
            avatar_el.screenshot(avatar_target)
            print("  📸 Avatar salvato localmente (per debug)")
        except Exception as e_avatar:
            print(f"  ⚠️  Impossibile salvare avatar per {psn}: {e_avatar}")

        if not skip_update:
            new_results[psn] = {
                "psn": psn,
                "dr": int(dr_points),
                "drPoints": int(dr_points),
                "wins": int(wins),
                "races": int(races),
                "top5": int(top5),
                "poles": int(poles),
                "winrate": winrate,
            }
            print(f"  ✅ AGGIORNATO {psn}: DR={dr_points} Wins={wins} Races={races} Top5={top5} Poles={poles} Win%={winrate}")
        else:
            print(f"  🔄 Uso dati vecchi da Firestore per {psn}")

    except Exception as e:
        print(f"  ❌ Errore per {psn}: {e}")
        print(f"  🔄 Uso dati vecchi da Firestore per {psn}")

    print("  ⏸️  Pausa 3 secondi...\n")
    time.sleep(3)

driver.quit()

# ============================================================
#   MERGE con dati vecchi da Firestore
# ============================================================

final_results = []

for psn in ALL_PILOTI:
    if psn in new_results:
        # Dati freschi dall'API
        final_results.append(new_results[psn])
        continue

    if psn in old_by_psn:
        # Usa dati vecchi da Firestore
        old = old_by_psn[psn]
        final_results.append({
            "psn": psn,
            "dr": old["dr"],
            "drPoints": old["drPoints"],
            "wins": old["wins"],
            "races": old["races"],
            "top5": old["top5"],
            "poles": old["poles"],
            "winrate": old["winrate"],
        })
        print(f"[MERGE] {psn}: usati dati vecchi da Firestore")
        continue

    # Nessun dato vecchio né nuovo => default 0
    final_results.append({
        "psn": psn,
        "dr": 0,
        "drPoints": 0,
        "wins": 0,
        "races": 0,
        "top5": 0,
        "poles": 0,
        "winrate": "-",
    })
    print(f"[MERGE] {psn}: nessun dato disponibile, uso default 0")

# ============================================================
#   OUTPUT LOCALE (debug)
# ============================================================

with open("dr.json", "w", encoding="utf-8") as f:
    json.dump(final_results, f, indent=2, ensure_ascii=False)

print("\n📄 Creato dr.json locale (output debug)")

# ============================================================
#   ANOMALIES REPORT
# ============================================================

anomalies = build_anomaly_report(old_by_psn, final_results)

with open("anomalies.json", "w", encoding="utf-8") as f:
    json.dump(anomalies, f, indent=2, ensure_ascii=False)

print(f"📄 Creato anomalies.json locale (output debug)")
print(f"⚠️  Anomalie trovate: {len(anomalies)}")
for a in anomalies[:20]:
    print(f"   {a['psn']} | {' ; '.join(a['reasons'])}")

# ============================================================
#   UPLOAD FIRESTORE
# ============================================================

upload_to_firestore(db, final_results)

print("\n✅ Operazione completata.")
print("📌 Note:")
print("   - dr.json e anomalies.json sono solo output locali per debug")
print("   - In CI questi file possono essere salvati come artifacts")
print("   - avatarUrl è vuoto (sarà implementato con Storage in futuro)")
