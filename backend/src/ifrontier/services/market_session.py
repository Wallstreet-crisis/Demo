from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from ifrontier.services.game_time import GameTimeConfig, GameTimeSnapshot, game_time_now, is_holiday


class MarketPhase(str, Enum):
    TRADING = "TRADING"
    CLOSING_BUFFER = "CLOSING_BUFFER"
    HOLIDAY = "HOLIDAY"


@dataclass(frozen=True)
class MarketSessionSnapshot:
    enabled: bool
    phase: MarketPhase
    game_day_index: int
    seconds_into_day: int
    seconds_per_game_day: int
    trading_seconds: int
    closing_buffer_seconds: int


def get_market_session(*, cfg: GameTimeConfig, now: Optional[GameTimeSnapshot] = None) -> MarketSessionSnapshot:
    if not cfg.enabled:
        return MarketSessionSnapshot(
            enabled=False,
            phase=MarketPhase.TRADING,
            game_day_index=0,
            seconds_into_day=0,
            seconds_per_game_day=cfg.seconds_per_game_day,
            trading_seconds=int(cfg.seconds_per_game_day * cfg.trading_ratio),
            closing_buffer_seconds=int(cfg.seconds_per_game_day * cfg.closing_buffer_ratio),
        )

    gt = now or game_time_now(cfg=cfg)

    trading_seconds = int(cfg.seconds_per_game_day * cfg.trading_ratio)
    closing_seconds = int(cfg.seconds_per_game_day * cfg.closing_buffer_ratio)
    if trading_seconds <= 0:
        trading_seconds = int(cfg.seconds_per_game_day * 0.85)
    if closing_seconds <= 0:
        closing_seconds = cfg.seconds_per_game_day - trading_seconds

    if is_holiday(cfg=cfg, day_index=gt.game_day_index):
        phase = MarketPhase.HOLIDAY
    else:
        # 取消闭市时间限制：非假日全时段允许交易
        phase = MarketPhase.TRADING

    return MarketSessionSnapshot(
        enabled=True,
        phase=phase,
        game_day_index=gt.game_day_index,
        seconds_into_day=gt.seconds_into_day,
        seconds_per_game_day=cfg.seconds_per_game_day,
        trading_seconds=trading_seconds,
        closing_buffer_seconds=closing_seconds,
    )


def assert_market_accepts_orders(*, cfg: GameTimeConfig) -> None:
    snap = get_market_session(cfg=cfg)
    if not snap.enabled:
        return
    # 保留假日停市，其余时间均允许下单
    if snap.phase == MarketPhase.HOLIDAY:
        raise ValueError("market is closed")
