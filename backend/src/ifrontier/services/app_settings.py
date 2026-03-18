from __future__ import annotations

import base64
import hashlib
import json
import os
from typing import Any, Dict

from ifrontier.infra.sqlite import settings as settings_db

DEFAULT_LANGUAGE = "zh-CN"
DEFAULT_RISE_COLOR = "red_up"
DEFAULT_DISPLAY: Dict[str, Any] = {
    "price_color_scheme": "cn_red_up",
    "compact_quotes": False,
    "show_market_phase_badge": True,
}
DEFAULT_LLM_PROVIDER = "openrouter"
DEFAULT_LLM_MODEL = "google/gemini-2.5-flash"
DEFAULT_LLM_BASE_URL = "https://openrouter.ai/api/v1"
SUPPORTED_LLM_PROVIDERS = [
    "openrouter",
    "deepseek",
    "minimax",
    "kimi",
    "openai",
    "anthropic",
    "google",
    "xai",
]
DEFAULT_PROVIDER_BASE_URLS: Dict[str, str] = {
    "openrouter": "https://openrouter.ai/api/v1",
    "deepseek": "https://api.deepseek.com/v1",
    "minimax": "https://api.minimax.chat/v1",
    "kimi": "https://api.moonshot.cn/v1",
    "openai": "https://api.openai.com/v1",
    "anthropic": "https://api.anthropic.com/v1",
    "google": "https://generativelanguage.googleapis.com/v1beta/openai",
    "xai": "https://api.x.ai/v1",
}
SECURE_LLM_CONFIG_KEY = "llm_provider_config"
DEFAULT_LLM_PROFILES: Dict[str, Dict[str, Any]] = {
    "light": {
        "provider": "openrouter",
        "model": "google/gemini-2.0-flash-001",
        "base_url": DEFAULT_LLM_BASE_URL,
        "timeout_seconds": 12.0,
    },
    "standard": {
        "provider": "openrouter",
        "model": "google/gemini-2.0-flash-001",
        "base_url": DEFAULT_LLM_BASE_URL,
        "timeout_seconds": 20.0,
    },
    "heavy": {
        "provider": "openrouter",
        "model": "deepseek/deepseek-chat-v3-0324",
        "base_url": DEFAULT_LLM_BASE_URL,
        "timeout_seconds": 35.0,
    },
}
DEFAULT_LLM_ROUTING: Dict[str, str] = {
    "commonbot_news": "light",
    "hosting_agent": "standard",
    "contract_audit": "standard",
    "contract_draft": "heavy",
    "default": "standard",
}


def _master_key() -> bytes:
    raw = str(os.getenv("IF_SETTINGS_MASTER_KEY") or "information-frontier-dev-only-key")
    return hashlib.sha256(raw.encode("utf-8")).digest()


def _xor_stream(data: bytes, key: bytes) -> bytes:
    out = bytearray()
    counter = 0
    cursor = 0
    while cursor < len(data):
        block = hashlib.sha256(key + counter.to_bytes(8, "big")).digest()
        for b in block:
            if cursor >= len(data):
                break
            out.append(data[cursor] ^ b)
            cursor += 1
        counter += 1
    return bytes(out)


def encrypt_json(payload: Dict[str, Any]) -> str:
    raw = json.dumps(payload or {}, ensure_ascii=False).encode("utf-8")
    enc = _xor_stream(raw, _master_key())
    return base64.urlsafe_b64encode(enc).decode("ascii")


def decrypt_json(token: str) -> Dict[str, Any]:
    if not token:
        return {}
    raw = base64.urlsafe_b64decode(token.encode("ascii"))
    dec = _xor_stream(raw, _master_key())
    obj = json.loads(dec.decode("utf-8"))
    return obj if isinstance(obj, dict) else {}


def can_manage_llm(actor_id: str | None) -> bool:
    aid = str(actor_id or "").strip().lower()
    if not aid:
        return False

    configured_hosts = [
        str(x).strip().lower()
        for x in str(os.getenv("IF_SETTINGS_HOST_IDS") or os.getenv("IF_ROOM_HOST_ID") or "").split(",")
        if str(x).strip()
    ]
    if configured_hosts:
        return aid in set(configured_hosts)

    multiplayer_enabled = str(os.getenv("IF_MULTIPLAYER_ENABLED") or "0").strip().lower() in {"1", "true", "yes", "on"}
    if multiplayer_enabled:
        return False

    return True


def get_user_preferences(actor_id: str) -> Dict[str, Any]:
    rec = settings_db.get_user_preferences(actor_id)
    if rec is None:
        return {
            "language": DEFAULT_LANGUAGE,
            "rise_color": DEFAULT_RISE_COLOR,
            "display": dict(DEFAULT_DISPLAY),
            "updated_at": None,
        }
    merged_display = dict(DEFAULT_DISPLAY)
    merged_display.update(rec.display or {})
    return {
        "language": rec.language or DEFAULT_LANGUAGE,
        "rise_color": rec.rise_color or DEFAULT_RISE_COLOR,
        "display": merged_display,
        "updated_at": rec.updated_at,
    }


def save_user_preferences(*, actor_id: str, language: str | None, rise_color: str | None, display: Dict[str, Any] | None) -> Dict[str, Any]:
    merged = dict(DEFAULT_DISPLAY)
    if isinstance(display, dict):
        merged.update(display)
    rec = settings_db.save_user_preferences(
        actor_id=actor_id,
        language=str(language or DEFAULT_LANGUAGE),
        rise_color=str(rise_color or DEFAULT_RISE_COLOR),
        display=merged,
    )
    return {
        "language": rec.language,
        "rise_color": rec.rise_color,
        "display": rec.display,
        "updated_at": rec.updated_at,
    }


def load_secure_llm_config() -> Dict[str, Any]:
    rec = settings_db.get_secure_config(SECURE_LLM_CONFIG_KEY)
    if rec is None:
        return {}
    try:
        obj = decrypt_json(rec.encrypted_payload)
    except Exception:
        return {}
    return obj if isinstance(obj, dict) else {}


def get_llm_settings_view(*, actor_id: str | None) -> Dict[str, Any]:
    can_manage = can_manage_llm(actor_id)
    cfg = load_secure_llm_config() if can_manage else {}
    provider = _normalize_provider(cfg.get("provider") or os.getenv("OPENROUTER_PROVIDER") or DEFAULT_LLM_PROVIDER)
    profiles = _normalize_profiles(cfg.get("profiles"))
    routing = _normalize_routing(cfg.get("routing"))
    standard = profiles.get("standard") or dict(DEFAULT_LLM_PROFILES["standard"])
    model = str(cfg.get("model") or standard.get("model") or os.getenv("OPENROUTER_MODEL") or DEFAULT_LLM_MODEL)
    base_url = str(cfg.get("base_url") or standard.get("base_url") or _default_base_url_for_provider(provider))
    timeout_seconds = float(cfg.get("timeout_seconds") or standard.get("timeout_seconds") or os.getenv("OPENROUTER_TIMEOUT_SECONDS") or "20")
    api_keys = _normalize_api_keys(cfg.get("api_keys"), cfg.get("provider"), cfg.get("api_key"))
    api_key = str(api_keys.get(provider) or "")
    return {
        "can_manage": can_manage,
        "provider": provider,
        "model": model,
        "base_url": base_url,
        "timeout_seconds": timeout_seconds,
        "profiles": profiles,
        "routing": routing,
        "providers_supported": list(SUPPORTED_LLM_PROVIDERS),
        "provider_api_key_masks": {key: _mask_secret(value) for key, value in api_keys.items()},
        "has_api_key": bool(api_key),
        "api_key_masked": _mask_secret(api_key),
    }


def save_llm_settings(*, actor_id: str, provider: str, model: str, base_url: str, timeout_seconds: float, api_key: str | None) -> Dict[str, Any]:
    if not can_manage_llm(actor_id):
        raise PermissionError("actor is not allowed to manage llm settings")

    current = load_secure_llm_config()
    normalized_provider = _normalize_provider(provider or current.get("provider"))
    next_api_keys = _normalize_api_keys(current.get("api_keys"), current.get("provider"), current.get("api_key"))
    if api_key is not None and str(api_key).strip():
        next_api_keys[normalized_provider] = str(api_key).strip()
    next_profiles = _normalize_profiles(current.get("profiles"))
    payload = {
        "provider": normalized_provider,
        "model": str(model or current.get("model") or DEFAULT_LLM_MODEL),
        "base_url": str(base_url or current.get("base_url") or _default_base_url_for_provider(normalized_provider)),
        "timeout_seconds": float(timeout_seconds or current.get("timeout_seconds") or 20.0),
        "profiles": next_profiles,
        "routing": _normalize_routing(current.get("routing")),
        "api_keys": next_api_keys,
        "api_key": str(next_api_keys.get(normalized_provider) or ""),
        "updated_by": str(actor_id),
    }
    settings_db.save_secure_config(config_key=SECURE_LLM_CONFIG_KEY, encrypted_payload=encrypt_json(payload))
    return get_llm_settings_view(actor_id=actor_id)


def save_llm_settings_layered(
    *,
    actor_id: str,
    provider: str,
    api_key: str | None,
    api_keys: Dict[str, Any] | None,
    profiles: Dict[str, Any] | None,
    routing: Dict[str, Any] | None,
) -> Dict[str, Any]:
    if not can_manage_llm(actor_id):
        raise PermissionError("actor is not allowed to manage llm settings")

    current = load_secure_llm_config()
    normalized_provider = _normalize_provider(provider or current.get("provider"))
    next_api_keys = _normalize_api_keys(current.get("api_keys"), current.get("provider"), current.get("api_key"))
    for raw_provider, raw_key in dict(api_keys or {}).items():
        normalized_key_provider = _normalize_provider(raw_provider)
        normalized_key_value = str(raw_key or "").strip()
        if normalized_key_value:
            next_api_keys[normalized_key_provider] = normalized_key_value
    if api_key is not None and str(api_key).strip():
        next_api_keys[normalized_provider] = str(api_key).strip()
    next_profiles = _normalize_profiles(profiles if profiles is not None else current.get("profiles"))
    next_routing = _normalize_routing(routing if routing is not None else current.get("routing"))
    standard = next_profiles.get("standard") or dict(DEFAULT_LLM_PROFILES["standard"])
    payload = {
        "provider": normalized_provider,
        "model": str(standard.get("model") or DEFAULT_LLM_MODEL),
        "base_url": str(standard.get("base_url") or _default_base_url_for_provider(normalized_provider)),
        "timeout_seconds": float(standard.get("timeout_seconds") or 20.0),
        "profiles": next_profiles,
        "routing": next_routing,
        "api_keys": next_api_keys,
        "api_key": str(next_api_keys.get(normalized_provider) or ""),
        "updated_by": str(actor_id),
    }
    settings_db.save_secure_config(config_key=SECURE_LLM_CONFIG_KEY, encrypted_payload=encrypt_json(payload))
    return get_llm_settings_view(actor_id=actor_id)


def get_runtime_llm_config() -> Dict[str, Any]:
    cfg = load_secure_llm_config()
    provider = _normalize_provider(cfg.get("provider") or DEFAULT_LLM_PROVIDER)
    api_key = _resolve_api_key(cfg, provider)
    if not api_key:
        return {}
    return {
        "provider": provider,
        "api_key": api_key,
        "model": str(cfg.get("model") or os.getenv("OPENROUTER_MODEL") or DEFAULT_LLM_MODEL),
        "base_url": str(cfg.get("base_url") or os.getenv("OPENROUTER_BASE_URL") or _default_base_url_for_provider(provider)),
        "timeout_seconds": float(cfg.get("timeout_seconds") or os.getenv("OPENROUTER_TIMEOUT_SECONDS") or "20"),
        "profiles": _normalize_profiles(cfg.get("profiles")),
        "routing": _normalize_routing(cfg.get("routing")),
        "api_keys": _normalize_api_keys(cfg.get("api_keys"), cfg.get("provider"), cfg.get("api_key")),
    }


def get_runtime_llm_profile(*, profile: str | None = None, task: str | None = None) -> Dict[str, Any]:
    runtime = get_runtime_llm_config()
    if not runtime:
        return {}
    profiles = _normalize_profiles(runtime.get("profiles"))
    routing = _normalize_routing(runtime.get("routing"))
    selected = str(profile or routing.get(str(task or "")) or routing.get("default") or "standard")
    prof = dict(profiles.get(selected) or profiles.get("standard") or DEFAULT_LLM_PROFILES["standard"])
    provider = _normalize_provider(prof.get("provider") or runtime.get("provider") or DEFAULT_LLM_PROVIDER)
    api_key = str((runtime.get("api_keys") or {}).get(provider) or runtime.get("api_key") or _provider_env_api_key(provider) or "")
    if not api_key:
        return {}
    return {
        "provider": provider,
        "api_key": api_key,
        "profile": selected,
        "task": str(task or "default"),
        "model": str(prof.get("model") or DEFAULT_LLM_MODEL),
        "base_url": str(prof.get("base_url") or _default_base_url_for_provider(provider)),
        "timeout_seconds": float(prof.get("timeout_seconds") or 20.0),
    }


def _normalize_provider(provider: Any) -> str:
    value = str(provider or DEFAULT_LLM_PROVIDER).strip().lower()
    return value if value in set(SUPPORTED_LLM_PROVIDERS) else DEFAULT_LLM_PROVIDER


def _default_base_url_for_provider(provider: Any) -> str:
    pp = _normalize_provider(provider)
    return str(DEFAULT_PROVIDER_BASE_URLS.get(pp) or DEFAULT_LLM_BASE_URL)


def _provider_env_api_key(provider: str) -> str:
    pp = _normalize_provider(provider)
    names = {
        "openrouter": ["OPENROUTER_API_KEY", "IF_OPENROUTER_API_KEY"],
        "deepseek": ["DEEPSEEK_API_KEY", "IF_DEEPSEEK_API_KEY"],
        "minimax": ["MINIMAX_API_KEY", "IF_MINIMAX_API_KEY"],
        "kimi": ["KIMI_API_KEY", "MOONSHOT_API_KEY", "IF_KIMI_API_KEY"],
        "openai": ["OPENAI_API_KEY", "IF_OPENAI_API_KEY"],
        "anthropic": ["ANTHROPIC_API_KEY", "IF_ANTHROPIC_API_KEY"],
        "google": ["GOOGLE_API_KEY", "GEMINI_API_KEY", "IF_GOOGLE_API_KEY"],
        "xai": ["XAI_API_KEY", "IF_XAI_API_KEY"],
    }
    for name in names.get(pp, []):
        value = str(os.getenv(name) or "").strip()
        if value:
            return value
    return ""


def _normalize_api_keys(raw: Any, legacy_provider: Any = None, legacy_api_key: Any = None) -> Dict[str, str]:
    out: Dict[str, str] = {}
    if isinstance(raw, dict):
        for key, value in raw.items():
            pp = _normalize_provider(key)
            vv = str(value or "").strip()
            if vv:
                out[pp] = vv
    legacy_key = str(legacy_api_key or "").strip()
    if legacy_key:
        out[_normalize_provider(legacy_provider)] = legacy_key
    return out


def _resolve_api_key(cfg: Dict[str, Any], provider: str) -> str:
    api_keys = _normalize_api_keys(cfg.get("api_keys"), cfg.get("provider"), cfg.get("api_key"))
    stored = str(api_keys.get(_normalize_provider(provider)) or "").strip()
    if stored:
        return stored
    return _provider_env_api_key(provider)


def _normalize_profiles(raw: Any) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {k: dict(v) for k, v in DEFAULT_LLM_PROFILES.items()}
    if isinstance(raw, dict):
        for key in ["light", "standard", "heavy"]:
            value = raw.get(key)
            if not isinstance(value, dict):
                continue
            merged = dict(out[key])
            if value.get("provider"):
                merged["provider"] = _normalize_provider(value.get("provider"))
            if value.get("model"):
                merged["model"] = str(value.get("model"))
            if value.get("base_url"):
                merged["base_url"] = str(value.get("base_url"))
            elif value.get("provider"):
                merged["base_url"] = _default_base_url_for_provider(value.get("provider"))
            if value.get("timeout_seconds") is not None:
                merged["timeout_seconds"] = float(value.get("timeout_seconds") or out[key]["timeout_seconds"])
            out[key] = merged
    return out


def _normalize_routing(raw: Any) -> Dict[str, str]:
    out = dict(DEFAULT_LLM_ROUTING)
    if isinstance(raw, dict):
        for key, value in raw.items():
            if not value:
                continue
            vv = str(value)
            if vv not in {"light", "standard", "heavy"}:
                continue
            out[str(key)] = vv
    return out


def _mask_secret(secret: str) -> str | None:
    raw = str(secret or "")
    if not raw:
        return None
    if len(raw) <= 8:
        return "*" * len(raw)
    return f"{raw[:4]}***{raw[-4:]}"
