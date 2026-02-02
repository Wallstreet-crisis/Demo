from __future__ import annotations

from pathlib import Path
import sys

from ifrontier.infra.sqlite.db import get_connection
from ifrontier.infra.sqlite.ledger import create_account, get_snapshot
from ifrontier.services.matching import submit_limit_order, submit_market_order

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def _reset_db() -> None:
    conn = get_connection()
    with conn:
        conn.execute("DELETE FROM ledger_entries")
        conn.execute("DELETE FROM positions")
        conn.execute("DELETE FROM accounts")
        conn.execute("DELETE FROM orders")


def test_limit_order_simple_match() -> None:
    _reset_db()

    # seller: 100 shares, buyer: 1000 cash
    create_account("buyer", owner_type="user", initial_cash=1000.0)
    create_account("seller", owner_type="user", initial_cash=0.0)

    conn = get_connection()
    with conn:
        conn.execute(
            "INSERT INTO positions(account_id, symbol, quantity) VALUES (?, ?, ?)",
            ("seller", "BLUEGOLD", 100.0),
        )

    # seller posts ask @10
    submit_limit_order(
        account_id="seller",
        symbol="BLUEGOLD",
        side="SELL",
        price=10.0,
        quantity=50.0,
    )

    # buyer posts bid @10.5, should fully match 50@10
    submit_limit_order(
        account_id="buyer",
        symbol="BLUEGOLD",
        side="BUY",
        price=10.5,
        quantity=50.0,
    )

    buyer = get_snapshot("buyer")
    seller = get_snapshot("seller")

    assert buyer.cash == 1000.0 - 500.0
    assert buyer.positions.get("BLUEGOLD", 0.0) == 50.0

    assert seller.cash == 500.0
    assert seller.positions.get("BLUEGOLD", 0.0) == 50.0


def test_price_priority() -> None:
    _reset_db()

    create_account("buyer", owner_type="user", initial_cash=2000.0)
    create_account("s1", owner_type="user", initial_cash=0.0)
    create_account("s2", owner_type="user", initial_cash=0.0)

    conn = get_connection()
    with conn:
        conn.execute("INSERT INTO positions(account_id, symbol, quantity) VALUES ('s1', 'BLUEGOLD', 30.0)")
        conn.execute("INSERT INTO positions(account_id, symbol, quantity) VALUES ('s2', 'BLUEGOLD', 30.0)")

    # s1: SELL @10, s2: SELL @9.5
    submit_limit_order(account_id="s1", symbol="BLUEGOLD", side="SELL", price=10.0, quantity=30.0)
    submit_limit_order(account_id="s2", symbol="BLUEGOLD", side="SELL", price=9.5, quantity=30.0)

    # buyer: BUY @11, qty=50 -> 应优先吃 9.5 再吃 10
    submit_limit_order(account_id="buyer", symbol="BLUEGOLD", side="BUY", price=11.0, quantity=50.0)

    buyer = get_snapshot("buyer")
    s1 = get_snapshot("s1")
    s2 = get_snapshot("s2")

    # 成交金额: 30*9.5 + 20*10 = 285 + 200 = 485
    assert buyer.cash == 2000.0 - 485.0
    assert round(buyer.positions.get("BLUEGOLD", 0.0), 6) == 50.0

    assert round(s2.cash, 6) == 285.0
    assert s2.positions.get("BLUEGOLD", 0.0) == 0.0

    assert round(s1.cash, 6) == 200.0
    assert s1.positions.get("BLUEGOLD", 0.0) == 10.0


def test_time_priority_same_price() -> None:
    _reset_db()

    create_account("buyer", owner_type="user", initial_cash=2000.0)
    create_account("s1", owner_type="user", initial_cash=0.0)
    create_account("s2", owner_type="user", initial_cash=0.0)

    conn = get_connection()
    with conn:
        conn.execute("INSERT INTO positions(account_id, symbol, quantity) VALUES ('s1', 'BLUEGOLD', 30.0)")
        conn.execute("INSERT INTO positions(account_id, symbol, quantity) VALUES ('s2', 'BLUEGOLD', 30.0)")

    # 先挂 s1 再挂 s2，都是 SELL @10
    submit_limit_order(account_id="s1", symbol="BLUEGOLD", side="SELL", price=10.0, quantity=30.0)
    submit_limit_order(account_id="s2", symbol="BLUEGOLD", side="SELL", price=10.0, quantity=30.0)

    # 买家挂 BUY @10, qty=40，应先吃完 s1 的 30 再吃 s2 的 10
    submit_limit_order(account_id="buyer", symbol="BLUEGOLD", side="BUY", price=10.0, quantity=40.0)

    buyer = get_snapshot("buyer")
    s1 = get_snapshot("s1")
    s2 = get_snapshot("s2")

    assert buyer.cash == 2000.0 - 400.0
    assert buyer.positions.get("BLUEGOLD", 0.0) == 40.0

    assert s1.cash == 300.0
    assert s1.positions.get("BLUEGOLD", 0.0) == 0.0

    assert s2.cash == 100.0
    assert s2.positions.get("BLUEGOLD", 0.0) == 20.0


def test_market_order_eats_best_price_first() -> None:
    _reset_db()

    create_account("buyer", owner_type="user", initial_cash=2000.0)
    create_account("s1", owner_type="user", initial_cash=0.0)
    create_account("s2", owner_type="user", initial_cash=0.0)

    conn = get_connection()
    with conn:
        conn.execute("INSERT INTO positions(account_id, symbol, quantity) VALUES ('s1', 'BLUEGOLD', 30.0)")
        conn.execute("INSERT INTO positions(account_id, symbol, quantity) VALUES ('s2', 'BLUEGOLD', 30.0)")

    # 先挂两层卖单：9.5 更优
    submit_limit_order(account_id="s1", symbol="BLUEGOLD", side="SELL", price=10.0, quantity=30.0)
    submit_limit_order(account_id="s2", symbol="BLUEGOLD", side="SELL", price=9.5, quantity=30.0)

    # 市价买单吃 40 股：应先吃 30@9.5，再吃 10@10
    matches = submit_market_order(account_id="buyer", symbol="BLUEGOLD", side="BUY", quantity=40.0)
    assert len(matches) == 2

    buyer = get_snapshot("buyer")
    s1 = get_snapshot("s1")
    s2 = get_snapshot("s2")

    # 成交金额: 30*9.5 + 10*10 = 285 + 100 = 385
    assert buyer.cash == 2000.0 - 385.0
    assert buyer.positions.get("BLUEGOLD", 0.0) == 40.0

    assert s2.cash == 285.0
    assert s2.positions.get("BLUEGOLD", 0.0) == 0.0

    assert s1.cash == 100.0
    assert s1.positions.get("BLUEGOLD", 0.0) == 20.0
