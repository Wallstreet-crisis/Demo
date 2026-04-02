from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional
from urllib import request

from ifrontier.core.ai_logger import log_llm_metric
from ifrontier.core.logger import get_logger
from ifrontier.services.app_settings import get_runtime_llm_config, get_runtime_llm_profile

_log = get_logger(__name__)


@dataclass(frozen=True)
class LlmConfig:
    provider: str
    api_key: str
    model: str
    base_url: str
    timeout_seconds: float = 20.0


class LlmError(RuntimeError):
    pass


class LlmClient:
    def __init__(self, cfg: LlmConfig) -> None:
        self._cfg = cfg
        self._task = "default"
        self._profile = "standard"

    @staticmethod
    def from_env() -> Optional["LlmClient"]:
        runtime_cfg = get_runtime_llm_config()
        api_key = str(runtime_cfg.get("api_key") or "").strip()
        if not api_key:
            return None
        return LlmClient(
            LlmConfig(
                provider=str(runtime_cfg.get("provider") or "openrouter"),
                api_key=api_key,
                model=str(runtime_cfg.get("model") or ""),
                base_url=str(runtime_cfg.get("base_url") or ""),
                timeout_seconds=float(runtime_cfg.get("timeout_seconds") or 20.0),
            )
        )

    @staticmethod
    def for_task(*, task: str, profile: str | None = None) -> Optional["LlmClient"]:
        runtime_cfg = get_runtime_llm_profile(task=task, profile=profile)
        api_key = str(runtime_cfg.get("api_key") or "").strip()
        if not api_key:
            return None
        client = LlmClient(
            LlmConfig(
                provider=str(runtime_cfg.get("provider") or "openrouter"),
                api_key=api_key,
                model=str(runtime_cfg.get("model") or ""),
                base_url=str(runtime_cfg.get("base_url") or ""),
                timeout_seconds=float(runtime_cfg.get("timeout_seconds") or 20.0),
            )
        )
        client._task = str(task or "default")
        client._profile = str(runtime_cfg.get("profile") or profile or "standard")
        return client

    def ping(self) -> Dict[str, Any]:
        verbose = str(os.getenv("IF_LLM_VERBOSE") or "").strip().lower() in {"1", "true", "yes", "on"}
        url = f"{self._cfg.base_url.rstrip('/')}/models"
        req = request.Request(url=url, method="GET", headers=self._headers())
        try:
            with request.urlopen(req, timeout=self._cfg.timeout_seconds) as resp:
                raw = resp.read().decode("utf-8")
                if verbose:
                    _log.debug("ping %s status: %s", self._cfg.provider, resp.status)
        except Exception as exc:
            if hasattr(exc, "read"):
                try:
                    err_body = exc.read().decode("utf-8")
                except Exception:
                    err_body = ""
                raise LlmError(err_body or str(exc)) from exc
            raise LlmError(str(exc)) from exc
        try:
            payload = json.loads(raw)
        except Exception as exc:
            raise LlmError(f"invalid json response: {raw[:2000]}") from exc
        data = payload.get("data") or []
        first_model = None
        if isinstance(data, list) and data:
            first = data[0] or {}
            if isinstance(first, dict):
                first_model = first.get("id")
        return {
            "ok": True,
            "model_count": int(len(data)) if isinstance(data, list) else 0,
            "first_model": str(first_model) if first_model else None,
        }

    def chat_completions(
        self,
        *,
        system: str,
        user: str,
        temperature: float = 0.2,
        max_tokens: int = 300,
        extra_headers: Dict[str, str] | None = None,
    ) -> Dict[str, Any]:
        verbose = str(os.getenv("IF_LLM_VERBOSE") or "").strip().lower() in {"1", "true", "yes", "on"}
        started_at = time.perf_counter()
        prompt_chars = len(str(system or "")) + len(str(user or ""))
        if verbose:
            _log.debug("Calling provider=%s model=%s", self._cfg.provider, self._cfg.model)
        body = {
            "model": self._cfg.model,
            "temperature": float(temperature),
            "max_tokens": int(max_tokens),
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        headers = self._headers()
        if extra_headers:
            headers.update(extra_headers)
        req = request.Request(
            url=f"{self._cfg.base_url.rstrip('/')}/chat/completions",
            method="POST",
            headers=headers,
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        )
        try:
            with request.urlopen(req, timeout=self._cfg.timeout_seconds) as resp:
                raw = resp.read().decode("utf-8")
                if verbose:
                    _log.debug("response status: %s", resp.status)
        except Exception as exc:
            log_llm_metric(
                task=self._task,
                profile=self._profile,
                model=self._cfg.model,
                duration_ms=(time.perf_counter() - started_at) * 1000.0,
                success=False,
                prompt_chars=prompt_chars,
                max_tokens=max_tokens,
                extra={"provider": self._cfg.provider, "error": str(exc)[:240]},
            )
            if hasattr(exc, "read"):
                try:
                    err_body = exc.read().decode("utf-8")
                except Exception:
                    err_body = ""
                raise LlmError(err_body or str(exc)) from exc
            raise LlmError(str(exc)) from exc
        try:
            res = json.loads(raw)
        except Exception as exc:
            log_llm_metric(
                task=self._task,
                profile=self._profile,
                model=self._cfg.model,
                duration_ms=(time.perf_counter() - started_at) * 1000.0,
                success=False,
                prompt_chars=prompt_chars,
                max_tokens=max_tokens,
                extra={"provider": self._cfg.provider, "error": "invalid_json", "response_chars": len(raw)},
            )
            raise LlmError(f"invalid json response: {raw[:2000]}") from exc
        log_llm_metric(
            task=self._task,
            profile=self._profile,
            model=self._cfg.model,
            duration_ms=(time.perf_counter() - started_at) * 1000.0,
            success=True,
            prompt_chars=prompt_chars,
            max_tokens=max_tokens,
            extra={"provider": self._cfg.provider, "response_chars": len(raw)},
        )
        return res

    def _headers(self) -> Dict[str, str]:
        headers: Dict[str, str] = {
            "Authorization": f"Bearer {self._cfg.api_key}",
            "Content-Type": "application/json",
        }
        if self._cfg.provider == "openrouter":
            headers["HTTP-Referer"] = str(os.getenv("OPENROUTER_HTTP_REFERER") or "https://localhost")
            headers["X-Title"] = str(os.getenv("OPENROUTER_APP_TITLE") or "ifrontier")
        return headers


class OpenRouterConfig(LlmConfig):
    pass


class OpenRouterError(LlmError):
    pass


class OpenRouterClient(LlmClient):
    @staticmethod
    def from_env() -> Optional["OpenRouterClient"]:
        client = LlmClient.from_env()
        if client is None:
            return None
        if client._cfg.provider != "openrouter":
            return None
        wrapped = OpenRouterClient(OpenRouterConfig(**client._cfg.__dict__))
        wrapped._task = client._task
        wrapped._profile = client._profile
        return wrapped

    @staticmethod
    def for_task(*, task: str, profile: str | None = None) -> Optional["OpenRouterClient"]:
        client = LlmClient.for_task(task=task, profile=profile)
        if client is None:
            return None
        if client._cfg.provider != "openrouter":
            return None
        wrapped = OpenRouterClient(OpenRouterConfig(**client._cfg.__dict__))
        wrapped._task = client._task
        wrapped._profile = client._profile
        return wrapped


def extract_first_message_text(resp_json: Dict[str, Any]) -> str:
    choices = resp_json.get("choices") or []
    if not choices:
        return ""
    msg = (choices[0] or {}).get("message") or {}
    content = msg.get("content")
    if isinstance(content, list):
        return "".join(str(x.get("text") or "") for x in content if isinstance(x, dict))
    return str(content or "")
