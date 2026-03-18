from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from ifrontier.infra.sqlite.db import get_connection


def init_settings_schema() -> None:
    conn = get_connection()
    cur = conn.cursor()
    cur.executescript(
        """
        CREATE TABLE IF NOT EXISTS user_preferences (
            actor_id TEXT PRIMARY KEY,
            language TEXT NOT NULL DEFAULT 'zh-CN',
            rise_color TEXT NOT NULL DEFAULT 'red_up',
            display_json TEXT NOT NULL DEFAULT '{}',
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS secure_app_configs (
            config_key TEXT PRIMARY KEY,
            encrypted_payload TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """
    )
    conn.commit()


@dataclass(frozen=True)
class UserPreferencesRecord:
    actor_id: str
    language: str
    rise_color: str
    display: Dict[str, Any]
    updated_at: str


@dataclass(frozen=True)
class SecureConfigRecord:
    config_key: str
    encrypted_payload: str
    updated_at: str


def get_user_preferences(actor_id: str) -> Optional[UserPreferencesRecord]:
    conn = get_connection()
    row = conn.execute(
        "SELECT actor_id, language, rise_color, display_json, updated_at FROM user_preferences WHERE actor_id = ?",
        (str(actor_id),),
    ).fetchone()
    if row is None:
        return None

    try:
        display = json.loads(str(row["display_json"] or "{}"))
    except json.JSONDecodeError:
        display = {}
    if not isinstance(display, dict):
        display = {}

    return UserPreferencesRecord(
        actor_id=str(row["actor_id"]),
        language=str(row["language"] or "zh-CN"),
        rise_color=str(row["rise_color"] or "red_up"),
        display=display,
        updated_at=str(row["updated_at"]),
    )


def save_user_preferences(*, actor_id: str, language: str, rise_color: str, display: Dict[str, Any]) -> UserPreferencesRecord:
    conn = get_connection()
    now = datetime.now(timezone.utc).isoformat()
    payload = json.dumps(display or {}, ensure_ascii=False)
    with conn:
        conn.execute(
            "INSERT INTO user_preferences(actor_id, language, rise_color, display_json, updated_at) VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(actor_id) DO UPDATE SET language=excluded.language, rise_color=excluded.rise_color, display_json=excluded.display_json, updated_at=excluded.updated_at",
            (str(actor_id), str(language), str(rise_color), payload, now),
        )
    return UserPreferencesRecord(
        actor_id=str(actor_id),
        language=str(language),
        rise_color=str(rise_color),
        display=dict(display or {}),
        updated_at=now,
    )


def get_secure_config(config_key: str) -> Optional[SecureConfigRecord]:
    conn = get_connection()
    row = conn.execute(
        "SELECT config_key, encrypted_payload, updated_at FROM secure_app_configs WHERE config_key = ?",
        (str(config_key),),
    ).fetchone()
    if row is None:
        return None
    return SecureConfigRecord(
        config_key=str(row["config_key"]),
        encrypted_payload=str(row["encrypted_payload"]),
        updated_at=str(row["updated_at"]),
    )


def save_secure_config(*, config_key: str, encrypted_payload: str) -> SecureConfigRecord:
    conn = get_connection()
    now = datetime.now(timezone.utc).isoformat()
    with conn:
        conn.execute(
            "INSERT INTO secure_app_configs(config_key, encrypted_payload, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT(config_key) DO UPDATE SET encrypted_payload=excluded.encrypted_payload, updated_at=excluded.updated_at",
            (str(config_key), str(encrypted_payload), now),
        )
    return SecureConfigRecord(config_key=str(config_key), encrypted_payload=str(encrypted_payload), updated_at=now)
