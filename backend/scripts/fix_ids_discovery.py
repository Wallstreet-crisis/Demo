import json
import os
import sys
import urllib.request
from pathlib import Path

# 确保能导入项目 src
ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ifrontier.services.app_settings import get_runtime_llm_config

def main():
    # 复用 benchmark 的逻辑获取配置
    try:
        runtime = get_runtime_llm_config()
        api_key = str(runtime.get("api_key") or os.getenv("OPENROUTER_API_KEY") or "").strip()
        base_url = str(runtime.get("base_url") or os.getenv("OPENROUTER_BASE_URL") or "https://openrouter.ai/api/v1")
    except Exception as e:
        print(f"Error loading config: {e}")
        return

    if not api_key:
        print("Error: Missing OpenRouter API key.")
        return

    print(f"Fetching model list from OpenRouter (Key: {api_key[:6]}...)...")
    
    # 修正 URL
    if base_url.endswith("/"):
        models_url = f"{base_url}models"
    else:
        models_url = f"{base_url}/models"
        
    headers = {
        "Authorization": f"Bearer {api_key}",
        "HTTP-Referer": "https://localhost",
        "X-Title": "ifrontier-diag",
    }

    try:
        req = urllib.request.Request(models_url, headers=headers)
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            models = data.get("data", [])
            print(f"Found {len(models)} models.")
            
            # 过滤我们关心的品牌
            targets = ["gemini", "gpt-5", "qwen", "deepseek"]
            found = []
            for m in models:
                mid = m.get("id", "").lower()
                if any(t in mid for t in targets):
                    found.append(m)
            
            print("\n--- Correct Model IDs (Partial List) ---")
            for m in sorted(found, key=lambda x: x['id']):
                print(f"ID: {m['id']:50} | Name: {m.get('name')}")
                
    except Exception as e:
        print(f"Request failed: {e}")

if __name__ == "__main__":
    main()
