from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


_DEFAULT_EPOCH_UTC = datetime.now(timezone.utc)


@dataclass(frozen=True)
class GameTimeConfig:
    enabled: bool
    epoch_utc: datetime
    seconds_per_game_day: int

    trading_ratio: float
    closing_buffer_ratio: float

    holiday_every_days: int
    holiday_length_days: int


def _parse_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    v = value.strip().lower()
    if v in {"1", "true", "yes", "y", "on"}:
        return True
    if v in {"0", "false", "no", "n", "off"}:
        return False
    return default


def load_game_time_config_from_env() -> GameTimeConfig:
    enabled = _parse_bool(os.getenv("IF_GAME_TIME_ENABLED"), default=True)

    epoch = None
    if enabled:
        from ifrontier.infra.sqlite.db import get_connection
        conn = get_connection()
        row = conn.execute("SELECT value FROM game_meta WHERE key = 'epoch_utc'").fetchone()
        if row:
            try:
                epoch = datetime.fromisoformat(row[0])
                if epoch.tzinfo is None:
                    epoch = epoch.replace(tzinfo=timezone.utc)
            except Exception:
                epoch = None

    if epoch is None:
        epoch_raw = os.getenv("IF_GAME_EPOCH_UTC")
        if epoch_raw:
            try:
                epoch = datetime.fromisoformat(epoch_raw)
                if epoch.tzinfo is None:
                    epoch = epoch.replace(tzinfo=timezone.utc)
                epoch = epoch.astimezone(timezone.utc)
            except Exception:
                epoch = _DEFAULT_EPOCH_UTC
        else:
            epoch = _DEFAULT_EPOCH_UTC
        
        # Persist if enabled
        if enabled:
            from ifrontier.infra.sqlite.db import get_connection
            conn = get_connection()
            with conn:
                conn.execute("INSERT OR REPLACE INTO game_meta(key, value) VALUES ('epoch_utc', ?)", (epoch.isoformat(),))

    seconds_per_game_day = int(os.getenv("IF_SECONDS_PER_GAME_DAY") or "1200")
    if seconds_per_game_day <= 0:
        seconds_per_game_day = 1200

    trading_ratio = float(os.getenv("IF_TRADING_RATIO") or "0.85")
    closing_ratio = float(os.getenv("IF_CLOSING_BUFFER_RATIO") or "0.15")
    if trading_ratio <= 0 or closing_ratio <= 0 or abs((trading_ratio + closing_ratio) - 1.0) > 1e-6:
        trading_ratio, closing_ratio = 0.85, 0.15

    holiday_every_days = int(os.getenv("IF_HOLIDAY_EVERY_DAYS") or "5")
    holiday_length_days = int(os.getenv("IF_HOLIDAY_LENGTH_DAYS") or "2")
    if holiday_every_days < 0:
        holiday_every_days = 0
    if holiday_length_days < 0:
        holiday_length_days = 0

    return GameTimeConfig(
        enabled=enabled,
        epoch_utc=epoch,
        seconds_per_game_day=seconds_per_game_day,
        trading_ratio=trading_ratio,
        closing_buffer_ratio=closing_ratio,
        holiday_every_days=holiday_every_days,
        holiday_length_days=holiday_length_days,
    )


@dataclass(frozen=True)
class GameTimeSnapshot:
    real_now_utc: datetime
    game_day_index: int
    seconds_into_day: int


def game_time_now(*, cfg: GameTimeConfig, real_now_utc: datetime | None = None) -> GameTimeSnapshot:
    now = real_now_utc
    if now is None:
        override = os.getenv("IF_GAME_NOW_UTC")
        if override:
            try:
                dt = datetime.fromisoformat(override)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                now = dt.astimezone(timezone.utc)
            except Exception:
                now = None

    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    now = now.astimezone(timezone.utc)

    delta = now - cfg.epoch_utc
    total_seconds = int(delta.total_seconds())
    if total_seconds < 0:
        total_seconds = 0

    day = total_seconds // cfg.seconds_per_game_day
    sec = total_seconds % cfg.seconds_per_game_day
    return GameTimeSnapshot(real_now_utc=now, game_day_index=int(day), seconds_into_day=int(sec))


def is_holiday(*, cfg: GameTimeConfig, day_index: int) -> bool:
    if cfg.holiday_every_days <= 0 or cfg.holiday_length_days <= 0:
        return False

    cycle = cfg.holiday_every_days + cfg.holiday_length_days
    pos = int(day_index) % int(cycle)
    return pos >= cfg.holiday_every_days
