from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator
import sys
import uuid
import shutil

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ifrontier.infra.sqlite.db import close_connection, get_connection, room_id_var
from ifrontier.infra.sqlite.ledger import create_account
from ifrontier.infra.sqlite.schema import init_schema
from ifrontier.app.room_meta import RoomGameSettings, create_or_update_room_meta, load_room_meta
from ifrontier.services.victory import (
    BANKRUPTCY_REVIVAL_THRESHOLD,
    PlayerStatus,
    VictoryConditionType,
    VictoryService,
)


@contextmanager
def _victory_room() -> Iterator[None]:
    room_id = f"victory_test_{uuid.uuid4().hex[:8]}"
    token = room_id_var.set(room_id)
    try:
        init_schema()
        conn = get_connection()
        with conn:
            conn.execute("DELETE FROM ledger_entries")
            conn.execute("DELETE FROM positions")
            conn.execute("DELETE FROM accounts")
            conn.execute("DELETE FROM market_trades")
        yield
    finally:
        room_id_var.reset(token)
        close_connection(room_id)


def test_victory_settlement_branches_cover_expected_statuses() -> None:
    with _victory_room():
        svc = VictoryService()
        conn = get_connection()

        create_account("working", "user", 1_100_000.0, "WORKING")
        create_account("middle", "user", 2_100_000.0, "MIDDLE")
        create_account("elite", "user", 4_000.0, "ELITE")
        create_account("revive", "user", 100.0, "WORKING")
        with conn:
            conn.execute("UPDATE accounts SET status='BANKRUPT' WHERE account_id='revive'")

        working = svc.update_player_settlement("working")
        middle = svc.update_player_settlement("middle")
        elite = svc.update_player_settlement("elite")

        with conn:
            conn.execute(
                "UPDATE accounts SET cash = ?, status = 'BANKRUPT' WHERE account_id = ?",
                (BANKRUPTCY_REVIVAL_THRESHOLD + 50.0, "revive"),
            )
        revive = svc.update_player_settlement("revive")

        assert working["status"] == PlayerStatus.WINNER.value
        assert working["achievement"] == VictoryConditionType.SELF_MADE

        assert middle["status"] == PlayerStatus.RETIRED.value
        assert middle["achievement"] == VictoryConditionType.FINANCIAL_FREEDOM

        assert elite["status"] == PlayerStatus.WINNER.value
        assert elite["achievement"] == VictoryConditionType.PHILOSOPHER

        assert revive["status"] == PlayerStatus.ACTIVE.value
        assert revive["achievement"] is None


def test_room_game_settings_round_trip_persists_time_limit() -> None:
    room_id = f"test-room-{uuid.uuid4().hex[:8]}"
    room_dir = Path(ROOT / "data" / "rooms" / room_id)
    with _victory_room():
        try:
            meta = create_or_update_room_meta(
                room_id=room_id,
                player_id="user:creator",
                name="Test Room",
                game_settings=RoomGameSettings(time_limit_seconds=1800, mass_bankruptcy_mode=False),
                ensure_game_started=True,
            )

            reloaded = load_room_meta(room_id)
            assert reloaded is not None
            assert reloaded.game_started_at is not None
            assert reloaded.game_settings.time_limit_seconds == 1800
            assert reloaded.game_settings.mass_bankruptcy_mode is False
            assert meta.game_settings.time_limit_seconds == 1800
        finally:
            if room_dir.exists():
                shutil.rmtree(room_dir, ignore_errors=True)


def test_global_victory_detects_ultimate_owner_after_settlement_refresh() -> None:
    with _victory_room():
        svc = VictoryService()
        create_account("rich", "user", 1_600_000_000.0, "WORKING")

        settle = svc.update_player_settlement("rich")
        assert settle["status"] == PlayerStatus.WINNER.value
        assert settle["achievement"] == VictoryConditionType.MM_DOMINATION

        result = svc.check_global_victory(
            {
                "ultimate_owner_threshold": 1_500_000_000.0,
                "mass_bankruptcy_mode": True,
                "min_active_players": 1,
            }
        )

        assert result is not None
        assert result["type"] == VictoryConditionType.ULTIMATE_OWNER
        assert result["winner"] == "rich"


def test_global_victory_detects_time_limit_settlement() -> None:
    with _victory_room():
        svc = VictoryService()
        create_account("alpha", "user", 10_000.0, "WORKING")
        create_account("beta", "user", 20_000.0, "WORKING")

        started_at = (datetime.now(timezone.utc) - timedelta(seconds=3600)).isoformat()
        result = svc.check_global_victory(
            {
                "time_limit_seconds": 1200,
                "game_started_at": started_at,
            }
        )

        assert result is not None
        assert result["type"] == VictoryConditionType.TIME_LIMIT
        assert result["winner"] == "beta"


def test_global_victory_detects_mass_bankruptcy_with_one_active_player() -> None:
    with _victory_room():
        svc = VictoryService()
        create_account("active", "user", 1_000.0, "WORKING")
        create_account("bankrupt", "user", 1_000.0, "WORKING")

        conn = get_connection()
        with conn:
            conn.execute("UPDATE accounts SET status='ACTIVE' WHERE account_id='active'")
            conn.execute("UPDATE accounts SET status='BANKRUPT' WHERE account_id='bankrupt'")

        result = svc.check_global_victory(
            {
                "ultimate_owner_threshold": 9_999_999_999.0,
                "mass_bankruptcy_mode": True,
                "min_active_players": 1,
            }
        )

        assert result is not None
        assert result["type"] == VictoryConditionType.MASS_BANKRUPTCY
        assert result["winner"] == "active"
