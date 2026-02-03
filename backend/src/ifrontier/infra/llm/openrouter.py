from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Dict, Optional
from urllib import request


@dataclass(frozen=True)
class OpenRouterConfig:
    api_key: str
    model: str
    base_url: str = "https://openrouter.ai/api/v1"
    timeout_seconds: float = 20.0


class OpenRouterError(RuntimeError):
    pass


class OpenRouterClient:
    def __init__(self, cfg: OpenRouterConfig) -> None:
        self._cfg = cfg

    @staticmethod
    def from_env() -> Optional["OpenRouterClient"]:
        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            return None

        model = os.getenv("OPENROUTER_MODEL") or "google/gemini-flash-2.5"
        base_url = os.getenv("OPENROUTER_BASE_URL") or "https://openrouter.ai/api/v1"
        timeout = float(os.getenv("OPENROUTER_TIMEOUT_SECONDS") or "20")

        return OpenRouterClient(
            OpenRouterConfig(api_key=api_key, model=model, base_url=base_url, timeout_seconds=timeout)
        )

    def chat_completions(
        self,
        *,
        system: str,
        user: str,
        temperature: float = 0.2,
        max_tokens: int = 300,
        extra_headers: Dict[str, str] | None = None,
    ) -> Dict[str, Any]:
        print(f"[LLM] Calling OpenRouter with model: {self._cfg.model}")
        url = f"{self._cfg.base_url}/chat/completions"
        body = {
            "model": self._cfg.model,
            "temperature": float(temperature),
            "max_tokens": int(max_tokens),
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }

        headers = {
            "Authorization": f"Bearer {self._cfg.api_key}",
            "Content-Type": "application/json",
        }
        if extra_headers:
            headers.update(extra_headers)

        req = request.Request(
            url=url,
            method="POST",
            headers=headers,
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        )

        try:
            with request.urlopen(req, timeout=self._cfg.timeout_seconds) as resp:
                raw = resp.read().decode("utf-8")
        except Exception as exc:
            raise OpenRouterError(str(exc)) from exc

        try:
            return json.loads(raw)
        except Exception as exc:
            raise OpenRouterError(f"invalid json response: {raw[:2000]}") from exc


def extract_first_message_text(resp_json: Dict[str, Any]) -> str:
    choices = resp_json.get("choices") or []
    if not choices:
        return ""
    msg = (choices[0] or {}).get("message") or {}
    content = msg.get("content")
    return str(content or "")
