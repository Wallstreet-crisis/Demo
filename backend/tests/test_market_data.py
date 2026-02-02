from __future__ import annotations

import sys
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ifrontier.app.main import app

client = TestClient(app)


def test_market_records_trade_and_exposes_series_quote_and_candles() -> None:
    buy = f"user:mk:buy:{uuid4()}"
    sell = f"user:mk:sell:{uuid4()}"

    # create accounts with cash/positions via debug create_player and direct sqlite positions insert
    resp = client.post(
        "/debug/create_player",
        json={"player_id": buy.replace("user:", ""), "initial_cash": 100000},
    )
    assert resp.status_code == 200

    resp = client.post(
        "/debug/create_player",
        json={"player_id": sell.replace("user:", ""), "initial_cash": 0},
    )
    assert resp.status_code == 200

    # give seller some holdings
    from ifrontier.infra.sqlite.db import get_connection

    conn = get_connection()
    with conn:
        conn.execute(
            "INSERT INTO positions(account_id, symbol, quantity) VALUES (?, ?, ?) ON CONFLICT(account_id, symbol) DO UPDATE SET quantity = quantity + excluded.quantity",
            (sell, "BLUEGOLD", 10.0),
        )

    resp = client.post(
        "/debug/execute_trade",
        json={
            "buy_account_id": buy,
            "sell_account_id": sell,
            "symbol": "BLUEGOLD",
            "price": 10.0,
            "quantity": 2.0,
        },
    )
    assert resp.status_code == 200

    resp = client.get("/market/series/BLUEGOLD?limit=50")
    assert resp.status_code == 200
    data = resp.json()
    assert data["symbol"] == "BLUEGOLD"
    assert len(data["prices"]) >= 1

    resp = client.get("/market/quote/BLUEGOLD")
    assert resp.status_code == 200
    q = resp.json()
    assert q["symbol"] == "BLUEGOLD"
    assert q["last_price"] == 10.0

    resp = client.get("/market/candles/BLUEGOLD?interval_seconds=60&limit=50")
    assert resp.status_code == 200
    c = resp.json()
    assert c["symbol"] == "BLUEGOLD"
    assert len(c["candles"]) >= 1
    assert c["candles"][-1]["close"] == 10.0


def test_account_valuation_uses_last_price_and_discount() -> None:
    account_id = f"user:val:{uuid4()}"

    resp = client.post(
        "/debug/create_player",
        json={"player_id": account_id.replace("user:", ""), "initial_cash": 100.0},
    )
    assert resp.status_code == 200

    from ifrontier.infra.sqlite.db import get_connection

    conn = get_connection()
    with conn:
        conn.execute(
            "INSERT INTO positions(account_id, symbol, quantity) VALUES (?, ?, ?) ON CONFLICT(account_id, symbol) DO UPDATE SET quantity = quantity + excluded.quantity",
            (account_id, "BLUEGOLD", 3.0),
        )

    # record a market trade so last_price exists (need valid cash/positions)
    buy2 = f"user:val:other:{uuid4()}"
    sell2 = f"user:val:other2:{uuid4()}"

    resp = client.post(
        "/debug/create_player",
        json={"player_id": buy2.replace("user:", ""), "initial_cash": 100000.0},
    )
    assert resp.status_code == 200
    resp = client.post(
        "/debug/create_player",
        json={"player_id": sell2.replace("user:", ""), "initial_cash": 0.0},
    )
    assert resp.status_code == 200

    from ifrontier.infra.sqlite.db import get_connection

    conn = get_connection()
    with conn:
        conn.execute(
            "INSERT INTO positions(account_id, symbol, quantity) VALUES (?, ?, ?) ON CONFLICT(account_id, symbol) DO UPDATE SET quantity = quantity + excluded.quantity",
            (sell2, "BLUEGOLD", 10.0),
        )

    resp = client.post(
        "/debug/execute_trade",
        json={
            "buy_account_id": buy2,
            "sell_account_id": sell2,
            "symbol": "BLUEGOLD",
            "price": 20.0,
            "quantity": 1.0,
        },
    )
    assert resp.status_code == 200

    resp = client.get(f"/accounts/{account_id}/valuation?discount_factor=0.5")
    assert resp.status_code == 200
    v = resp.json()
    assert v["account_id"] == account_id
    assert v["cash"] == 100.0
    assert abs(v["equity_value"] - 3.0 * 20.0 * 0.5) < 1e-6
    assert abs(v["total_value"] - (100.0 + 3.0 * 20.0 * 0.5)) < 1e-6
