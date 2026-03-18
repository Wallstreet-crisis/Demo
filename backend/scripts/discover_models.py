import json
import os
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ifrontier.services.app_settings import get_runtime_llm_config

def main():
    # 1. 尝试通过官方 service 获取配置（最稳，因为 benchmark 就是这么跑通的）
    try:
        from ifrontier.services.app_settings import get_runtime_llm_config
        runtime = get_runtime_llm_config()
        api_key = str(runtime.get("api_key") or os.getenv("OPENROUTER_API_KEY") or "").strip()
        print(f"DEBUG: Successfully loaded API Key from runtime config.")
    except Exception as e:
        print(f"DEBUG: Official service load failed: {e}")
        api_key = os.getenv("OPENROUTER_API_KEY") or os.getenv("IF_OPENROUTER_API_KEY")

    if not api_key:
        print("Error: Missing OpenRouter API key. Please set OPENROUTER_API_KEY env var or save it in App UI.")
        return

    print(f"Using API Key: {api_key[:8]}...{api_key[-4:]}")

    url = "https://openrouter.ai/api/v1/models"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "HTTP-Referer": "https://localhost",
        "X-Title": "ifrontier-model-discovery",
    }

    print("Fetching available models from OpenRouter...")
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            models = data.get("data", [])
            print(f"Found {len(models)} models.")
            
            # Filter for some common ones to see their exact IDs
            targets = ["deepseek", "qwen", "gemini", "gpt-4", "gpt-5", "claude"]
            found_targets = []
            for m in models:
                m_id = m.get("id", "").lower()
                if any(t in m_id for t in targets):
                    found_targets.append(m)
            
            print("\n--- Relevant Model IDs for 2026.3 ---")
            for m in sorted(found_targets, key=lambda x: x['id']):
                # Some models might have pricing/context info
                print(f"ID: {m['id']:50} | Name: {m.get('name', 'N/A')}")

    except Exception as e:
        print(f"Error fetching models: {e}")

if __name__ == "__main__":
    main()
