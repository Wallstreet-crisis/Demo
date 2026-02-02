from __future__ import annotations

import os
from pathlib import Path
import sys

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ifrontier.app.main import app
from ifrontier.infra.sqlite.db import get_connection
from ifrontier.infra.sqlite.ledger import create_account, get_snapshot


client = TestClient(app)


def _reset_db() -> None:
    # Danger: test-only helper, clears all ledger tables.
    conn = get_connection()
    with conn:
        conn.execute("DELETE FROM ledger_entries")
        conn.execute("DELETE FROM positions")
        conn.execute("DELETE FROM accounts")


def test_debug_earnings_news_basic() -> None:
    _reset_db()

    resp = client.post(
        "/debug/earnings_news",
        json={
            "symbol": "BLUEGOLD",
            "visual_truth": "PROFIT",
            "headline_text": "Q1 扭亏为盈",
            "price_series": [10.0, 10.5, 11.0],
        },
    )

    assert resp.status_code == 200
    data = resp.json()

    assert "news_event_id" in data
    assert "ai_decision_event_id" in data
    assert "correlation_id" in data


def test_execute_trade_success() -> None:
    _reset_db()

    # 准备账户：买家有足够现金，卖家有足够持仓
    create_account("buyer", owner_type="user", initial_cash=1000.0)
    create_account("seller", owner_type="user", initial_cash=0.0)

    conn = get_connection()
    with conn:
        conn.execute(
            "INSERT INTO positions(account_id, symbol, quantity) VALUES (?, ?, ?)",
            ("seller", "BLUEGOLD", 100.0),
        )

    resp = client.post(
        "/debug/execute_trade",
        json={
            "buy_account_id": "buyer",
            "sell_account_id": "seller",
            "symbol": "BLUEGOLD",
            "price": 10.0,
            "quantity": 50.0,
        },
    )

    assert resp.status_code == 200
    data = resp.json()
    assert "event_id" in data

    buyer = get_snapshot("buyer")
    seller = get_snapshot("seller")

    assert buyer.cash == 1000.0 - 500.0
    assert buyer.positions.get("BLUEGOLD", 0.0) == 50.0

    assert seller.cash == 500.0
    assert seller.positions.get("BLUEGOLD", 0.0) == 50.0


def test_execute_trade_insufficient_cash() -> None:
    _reset_db()

    create_account("poor_buyer", owner_type="user", initial_cash=100.0)
    create_account("seller", owner_type="user", initial_cash=0.0)

    conn = get_connection()
    with conn:
        conn.execute(
            "INSERT INTO positions(account_id, symbol, quantity) VALUES (?, ?, ?)",
            ("seller", "BLUEGOLD", 100.0),
        )

    resp = client.post(
        "/debug/execute_trade",
        json={
            "buy_account_id": "poor_buyer",
            "sell_account_id": "seller",
            "symbol": "BLUEGOLD",
            "price": 10.0,
            "quantity": 50.0,
        },
    )

    # 账本层的 ValueError 会被映射为 400，这里确保不会修改账本
    assert resp.status_code == 400

    buyer = get_snapshot("poor_buyer")
    seller = get_snapshot("seller")

    # 现金和持仓保持初始状态
    assert buyer.cash == 100.0
    assert buyer.positions.get("BLUEGOLD", 0.0) == 0.0

    assert seller.cash == 0.0
    assert seller.positions.get("BLUEGOLD", 0.0) == 100.0


def test_earnings_news_triggers_bot_limit_order_and_match() -> None:
    """财报触发 CommonBot 决策后，Bot 账户通过撮合真实成交。

    场景：
    - seller 预先持有 100 股 BLUEGOLD，并在 10.0 价位挂出 50 股卖单；
    - 发布盈利财报，CommonBot 对 BLUEGOLD 给出 BUY 决策；
    - Bot 账户 bot:inst:1 以略高价格挂限价买单，应与卖单撮合成交 50 股；
    - 验证 Bot 与 seller 的现金与持仓变化符合 50 股、价格 10.0 的成交结果。
    """

    _reset_db()

    # 准备 Bot 与卖家账户
    create_account("bot:inst:1", owner_type="bot_institution", initial_cash=1_000_000.0)
    create_account("bot:ret:1", owner_type="bot_retail", initial_cash=50_000.0)
    create_account("seller", owner_type="user", initial_cash=0.0)

    conn = get_connection()
    with conn:
        conn.execute(
            "INSERT INTO positions(account_id, symbol, quantity) VALUES (?, ?, ?)",
            ("seller", "BLUEGOLD", 100.0),
        )

    # 卖家在 10.0 价位挂出 50 股卖单
    resp = client.post(
        "/debug/submit_order",
        json={
            "account_id": "seller",
            "symbol": "BLUEGOLD",
            "side": "SELL",
            "price": 10.0,
            "quantity": 50.0,
        },
    )
    assert resp.status_code == 200

    # 触发盈利财报；对于 BLUEGOLD（军工股）+ PROFIT，CommonBot 应给出 BUY 决策
    resp = client.post(
        "/debug/earnings_news",
        json={
            "symbol": "BLUEGOLD",
            "visual_truth": "PROFIT",
            "headline_text": "Q1 扭亏为盈",
            "price_series": [10.0, 10.0, 10.0],
        },
    )
    assert resp.status_code == 200

    bot = get_snapshot("bot:inst:1")
    seller = get_snapshot("seller")

    # 预期成交 50 股，现金在 Bot 与 seller 之间守恒
    assert bot.positions.get("BLUEGOLD", 0.0) == 50.0
    assert seller.positions.get("BLUEGOLD", 0.0) == 50.0

    total_cash = bot.cash + seller.cash
    assert abs(total_cash - 1_000_000.0) < 1e-6
