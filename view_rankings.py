
import os
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime

# Config
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FIREBASE_KEY = os.path.join(BASE_DIR, "firebase_key.json")
OUTPUT_HTML = "rankings.html"

def main():
    if not os.path.exists(FIREBASE_KEY):
        print("Errore: firebase_key.json mancante.")
        return

    # Init Firebase
    cred = credentials.Certificate(FIREBASE_KEY)
    firebase_admin.initialize_app(cred)
    db = firestore.client()

    print("Fetching drivers from Firestore...")
    docs = db.collection("drivers").stream()
    
    drivers = []
    for doc in docs:
        drivers.append(doc.to_dict())

    # Sort by DR Points descending
    drivers.sort(key=lambda x: x.get("drPoints", 0), reverse=True)

    print(f"Trovati {len(drivers)} piloti.")

    # Generate HTML
    html_content = f"""
    <!DOCTYPE html>
    <html lang="it">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>GT7 Driver Rankings</title>
        <style>
            body {{ font-family: sans-serif; background: #1a1a1a; color: #fff; padding: 20px; }}
            h1 {{ text-align: center; color: #e50914; }}
            table {{ width: 100%; border-collapse: collapse; margin-top: 20px; background: #333; }}
            th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #444; }}
            th {{ background: #222; text-transform: uppercase; font-size: 0.9em; }}
            tr:hover {{ background: #444; }}
            .avatar {{ width: 50px; height: 50px; border-radius: 50%; object-fit: cover; background: #555; }}
            .dr {{ font-weight: bold; color: #4CAF50; }}
            .rank {{ font-weight: bold; color: #aaa; width: 30px; }}
        </style>
    </head>
    <body>
        <h1>GT7 Driver Rankings</h1>
        <p style="text-align:center; color:#888">Generated at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        
        <table>
            <thead>
                <tr>
                    <th>#</th>
                    <th>Avatar</th>
                    <th>PSN ID</th>
                    <th>DR Points</th>
                    <th>Wins</th>
                    <th>Races</th>
                    <th>Top 5</th>
                    <th>Win Rate</th>
                </tr>
            </thead>
            <tbody>
    """

    for i, d in enumerate(drivers, 1):
        psn = d.get('psn', '')
        avatar_url = d.get("avatarUrl", "")
        
        # Check local file first
        local_path = f"avatars/{psn}.png"
        if os.path.exists(os.path.join(BASE_DIR, local_path)):
            avatar_src = local_path
            # Log for debug
            # print(f"Using local avatar for {psn}")
        else:
            avatar_src = avatar_url or "https://via.placeholder.com/50?text=?"
            
        html_content += f"""
                <tr>
                    <td class="rank">{i}</td>
                    <td><img src="{avatar_src}" class="avatar" alt="Avatar"></td>
                    <td>{psn or 'N/A'}</td>
                    <td class="dr">{d.get('drPoints', 0)}</td>
                    <td>{d.get('wins', 0)}</td>
                    <td>{d.get('races', 0)}</td>
                    <td>{d.get('top5', 0)}</td>
                    <td>{d.get('winrate', '-')}</td>
                </tr>
        """

    html_content += """
            </tbody>
        </table>
    </body>
    </html>
    """

    with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
        f.write(html_content)

    print(f"✅ Report generato: {os.path.abspath(OUTPUT_HTML)}")
    
    # Try to open in browser
    try:
        os.startfile(OUTPUT_HTML)
    except:
        pass

if __name__ == "__main__":
    main()
