from __future__ import annotations

from pathlib import Path
import sys

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ifrontier.app.main import app
from ifrontier.infra.sqlite.db import get_connection
from ifrontier.infra.sqlite.ledger import get_snapshot


client = TestClient(app)


def _reset_db() -> None:
    conn = get_connection()
    with conn:
        conn.execute("DELETE FROM ledger_entries")
        conn.execute("DELETE FROM positions")
        conn.execute("DELETE FROM accounts")
        conn.execute("DELETE FROM orders")


def test_player_limit_order_against_existing_sell() -> None:
    _reset_db()

    # 创建玩家 alice，初始现金 1000
    resp = client.post(
        "/debug/create_player",
        json={"player_id": "alice", "initial_cash": 1000.0},
    )
    assert resp.status_code == 200

    # 准备对手盘：market_maker 持有 100 股 BLUEGOLD，并挂出 50 股卖单 @10
    conn = get_connection()
    with conn:
        conn.execute(
            "INSERT INTO accounts(account_id, owner_type, cash) VALUES (?, ?, ?)",
            ("market_maker", "user", 0.0),
        )
        conn.execute(
            "INSERT INTO positions(account_id, symbol, quantity) VALUES (?, ?, ?)",
            ("market_maker", "BLUEGOLD", 100.0),
        )

    resp = client.post(
        "/debug/submit_order",
        json={
            "account_id": "market_maker",
            "symbol": "BLUEGOLD",
            "side": "SELL",
            "price": 10.0,
            "quantity": 50.0,
        },
    )
    assert resp.status_code == 200

    # 玩家 alice 以 10.5 的限价买入 50 股，应与卖单撮合
    resp = client.post(
        "/orders/limit",
        json={
            "player_id": "alice",
            "symbol": "BLUEGOLD",
            "side": "BUY",
            "price": 10.5,
            "quantity": 50.0,
        },
    )
    assert resp.status_code == 200

    alice = get_snapshot("user:alice")
    mm = get_snapshot("market_maker")

    assert alice.cash == 1000.0 - 500.0
    assert alice.positions.get("BLUEGOLD", 0.0) == 50.0

    assert mm.cash == 500.0
    assert mm.positions.get("BLUEGOLD", 0.0) == 50.0


def test_get_player_account_view() -> None:
    _reset_db()

    # 直接用调试接口创建玩家
    resp = client.post(
        "/debug/create_player",
        json={"player_id": "bob", "initial_cash": 2000.0},
    )
    assert resp.status_code == 200

    # 查询账户视图
    resp = client.get("/players/bob/account")
    assert resp.status_code == 200
    data = resp.json()

    assert data["account_id"] == "user:bob"
    assert data["cash"] == 2000.0
    assert data["positions"] == {}


def test_create_player_with_caste_assigns_initial_cash() -> None:
    _reset_db()

    # 使用阶级配置创建玩家, 不显式给 initial_cash
    resp = client.post(
        "/debug/create_player",
        json={"player_id": "c1", "caste_id": "MIDDLE"},
    )
    assert resp.status_code == 200
    data = resp.json()

    assert data["account_id"] == "user:c1"
    # 来自 CasteConfig.MIDDLE.initial_cash = 200_000.0
    assert data["cash"] == 200_000.0


def test_create_player_caste_overridden_by_initial_cash() -> None:
    _reset_db()

    # 同时提供 caste_id 和 initial_cash 时, 以 explicit initial_cash 为准
    resp = client.post(
        "/debug/create_player",
        json={"player_id": "c2", "caste_id": "WORKING", "initial_cash": 12345.0},
    )
    assert resp.status_code == 200
    data = resp.json()

    assert data["account_id"] == "user:c2"
    assert data["cash"] == 12345.0
