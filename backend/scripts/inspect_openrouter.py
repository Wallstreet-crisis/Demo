import json
import os
import sqlite3
import sys
import urllib.request
from pathlib import Path

# Add src to sys.path
BACKEND_DIR = Path(r"e:\GitClone\Demo\backend")
SRC_DIR = BACKEND_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

try:
    from ifrontier.services.app_settings import decrypt_json, SECURE_LLM_CONFIG_KEY
except ImportError:
    print("Error: Could not import app_settings")
    sys.exit(1)

def get_api_key():
    db_path = SRC_DIR / "data" / "ledger.db"
    if not db_path.exists():
        return None
    
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT encrypted_payload FROM secure_app_configs WHERE config_key = ?",
            (SECURE_LLM_CONFIG_KEY,)
        ).fetchone()
        conn.close()
        if row:
            cfg = decrypt_json(row["encrypted_payload"])
            return cfg.get("api_key")
    except Exception as e:
        print(f"DB Error: {e}")
    return None

def list_models():
    # Try argument first
    api_key = sys.argv[1] if len(sys.argv) > 1 else None
    
    if not api_key:
        api_key = get_api_key() or os.getenv("OPENROUTER_API_KEY")
    
    if not api_key:
        print("Error: API Key not found. Usage: python scripts/inspect_openrouter.py <YOUR_KEY>")
        return

    print(f"Using Key: {api_key[:8]}...")
    
    url = "https://openrouter.ai/api/v1/models"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "HTTP-Referer": "https://localhost",
        "X-Title": "ifrontier-diag",
    }

    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            models = data.get("data", [])
            print(f"Total models: {len(models)}")
            
            # Filter for 2026 relevant models
            targets = ["gemini-2", "gemini-3", "gpt-5", "qwen", "deepseek", "claude-4"]
            for m in sorted(models, key=lambda x: x['id']):
                mid = m['id']
                if any(t in mid.lower() for t in targets):
                    print(f"ID: {mid}")
    except Exception as e:
        print(f"Request failed: {e}")

if __name__ == "__main__":
    list_models()
