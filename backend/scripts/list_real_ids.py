import json
import os
import sqlite3
import sys
import urllib.request
from pathlib import Path

# 确保在 backend 目录下运行
BACKEND_DIR = Path(r"e:\GitClone\Demo\backend")
SRC_DIR = BACKEND_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

def get_raw_key():
    # 1. 环境变量
    k = os.getenv("OPENROUTER_API_KEY") or os.getenv("IF_OPENROUTER_API_KEY")
    if k: return k
    
    # 2. 数据库暴力查找
    db_path = SRC_DIR / "data" / "ledger.db"
    if db_path.exists():
        try:
            from ifrontier.services.app_settings import get_runtime_llm_config
            cfg = get_runtime_llm_config()
            return cfg.get("api_key")
        except Exception as e:
            print(f"DEBUG: Runtime config check failed: {e}")
            pass
    return None

def main():
    # 尝试通过参数获取
    key = sys.argv[1] if len(sys.argv) > 1 else get_raw_key()
    
    if not key:
        print("ERROR: No API Key found. Usage: python scripts/list_real_ids.py <YOUR_KEY>")
        return

    print(f"DEBUG: Using Key starting with {key[:8]}...")
    
    url = "https://openrouter.ai/api/v1/models"
    headers = {
        "Authorization": f"Bearer {key}",
        "HTTP-Referer": "https://localhost",
        "X-Title": "ifrontier-diag",
    }

    print("Fetching REAL model IDs from OpenRouter...")
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            models = data.get("data", [])
            print(f"Found {len(models)} models.")
            
            # 筛选 2026 年核心型号
            targets = ["gemini", "qwen", "deepseek", "gpt-5", "gpt-4o"]
            for m in sorted(models, key=lambda x: x['id']):
                mid = m['id']
                if any(t in mid.lower() for t in targets):
                    print(f"ID: {mid:50} | Name: {m.get('name')}")
    except Exception as e:
        print(f"Request failed: {e}")

if __name__ == "__main__":
    main()
