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
    # 完全复用 benchmark 脚本中已被验证有效的 Key 读取逻辑
    runtime = get_runtime_llm_config()
    api_key = str(runtime.get("api_key") or os.getenv("OPENROUTER_API_KEY") or "").strip()
    
    if not api_key:
        print("Error: 仍然无法读取 API Key。请确保你在 backend 目录下运行。")
        return

    print(f"Using Key: {api_key[:8]}...{api_key[-4:]}")
    
    url = "https://openrouter.ai/api/v1/models"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "HTTP-Referer": "https://localhost",
        "X-Title": "ifrontier-diagnostic",
    }

    print("正在从 OpenRouter 实时抓取 2026.3 可用模型列表...")
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            models = data.get("data", [])
            print(f"成功找到 {len(models)} 个可用模型。")
            
            # 我们重点看 Gemini, Qwen, DeepSeek, Claude 的最新 ID
            targets = ["gemini", "qwen", "deepseek", "claude", "gpt-5"]
            
            print("\n--- 2026.3 真实可用 ID 列表 (部分筛选) ---")
            found = []
            for m in models:
                mid = m['id']
                if any(t in mid.lower() for t in targets):
                    found.append(m)
            
            # 按 ID 排序方便查看
            for m in sorted(found, key=lambda x: x['id']):
                # 打印 ID 和对应的定价/延迟参考（如果有）
                print(f"ID: {m['id']:50}")
                
    except Exception as e:
        print(f"API 请求失败: {e}")

if __name__ == "__main__":
    main()
