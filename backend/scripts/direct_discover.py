import json
import os
import sqlite3
import sys
import urllib.request
from pathlib import Path

# Add src to sys.path
ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ifrontier.services.app_settings import decrypt_json

def get_api_key():
    # Try env first
    api_key = os.getenv("OPENROUTER_API_KEY") or os.getenv("IF_OPENROUTER_API_KEY")
    if api_key:
        return api_key
    
    # Try DB - Found at e:\GitClone\Demo\backend\src\data\ledger.db
    # Script is in e:\GitClone\Demo\backend\scripts
    db_path = ROOT / "src" / "data" / "ledger.db"
    if db_path.exists():
        try:
            import sqlite3
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT encrypted_payload FROM secure_app_configs WHERE config_key = 'llm_provider_config'"
            ).fetchone()
            conn.close()
            if row:
                from ifrontier.services.app_settings import decrypt_json
                cfg = decrypt_json(row["encrypted_payload"])
                return cfg.get("api_key")
        except Exception as e:
            print(f"DB Error at {db_path}: {e}")
    else:
        print(f"DB not found at {db_path}")
    return None

def main():
    api_key = get_api_key()
    if not api_key:
        print("Error: Could not find API key in env or DB.")
        return

    print(f"Using API Key: {api_key[:8]}...{api_key[-4:]}")
    
    url = "https://openrouter.ai/api/v1/models"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "HTTP-Referer": "https://localhost",
        "X-Title": "ifrontier-model-discovery",
    }

    print("Fetching models...")
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            models = data.get("data", [])
            print(f"Found {len(models)} models.")
            
            # Print some interesting ones
            targets = ["gemini", "qwen", "deepseek", "gpt-5", "claude-4"]
            found = []
            for m in models:
                mid = m['id']
                if any(t in mid.lower() for t in targets):
                    found.append(m)
            
            print("\n--- Model List ---")
            for m in sorted(found, key=lambda x: x['id']):
                print(f"{m['id']}")
    except Exception as e:
        print(f"Request failed: {e}")

if __name__ == "__main__":
    main()
