from __future__ import annotations

from datetime import datetime, timezone
import sys
from pathlib import Path
from time import sleep
from uuid import uuid4

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ifrontier.app.main import app
from ifrontier.app.room_meta import create_or_update_room_meta, RoomGameSettings
from ifrontier.infra.sqlite.ledger import create_account, get_snapshot
from ifrontier.infra.sqlite.db import get_connection, room_id_var
from ifrontier.infra.sqlite.news import get_main_card
from ifrontier.infra.sqlite.schema import init_schema

client = TestClient(app)


def _set_room_id(room_id: str):
    token = room_id_var.set(room_id)
    return token


def _reset_room_id(token):
    room_id_var.reset(token)


def test_purchase_with_chain_tree_creates_root_and_scheduled_nodes() -> None:
    room_id = f"room_chain_tree_{uuid4()}"
    buyer = f"user:chain:buyer:{uuid4()}"

    scenario_id = f"scenario_chain_tree_demo_{uuid4()}"
    meta_resp = client.patch(
        f"/global/studio/news/scenarios/{scenario_id}/meta",
        json={
            "actor_id": "author",
            "background_story": "chain tree scenario",
            "worldview": {
                "featured_symbols": ["BLUEGOLD"],
                "market_open_note": "open",
                "market_close_note": "close",
                "holiday_note": "holiday",
                "overview_note": "overview",
            },
            "news_store_items": [
                {
                    "kind": "RUMOR",
                    "price_cash": 5000.0,
                    "description": "Chain root",
                    "requires_symbols": False,
                    "trigger_mode": "AUTO_CHAIN",
                    "tags": ["demo"],
                    "rarity": "RARE",
                    "chain_tree": [
                        {
                            "node_id": "node_1",
                            "kind": "RUMOR",
                            "text": "First leak",
                            "scheduled_delay_seconds": 10,
                            "activation_prob": 1.0,
                            "symbols": ["BLUEGOLD"],
                            "tags": ["leak"],
                            "truth_payload": {"impact": "up"},
                            "parent_node_id": None,
                        },
                        {
                            "node_id": "node_2",
                            "kind": "MAJOR_EVENT",
                            "text": "Follow-up report",
                            "scheduled_delay_seconds": 25,
                            "activation_prob": 0.75,
                            "symbols": ["BLUEGOLD"],
                            "tags": ["report"],
                            "truth_payload": {"impact": "stable"},
                            "parent_node_id": "node_1",
                        },
                    ],
                }
            ],
        },
    )
    assert meta_resp.status_code == 200, meta_resp.text

    create_or_update_room_meta(
        room_id=room_id,
        player_id="host",
        name="chain tree test",
        game_settings=RoomGameSettings(scenario_id=scenario_id),
    )

    # 避免房间激活全局冷却导致 429（全量测试时前面可能刚激活过房间）
    sleep(2.5)

    token = _set_room_id(room_id)
    try:
        init_schema()
        create_account(buyer, owner_type="user", initial_cash=100000.0)
        conn = get_connection()
        conn.execute("DELETE FROM news")
        conn.commit()

        resp = client.post(
            "/news/store/purchase",
            json={
                "buyer_user_id": buyer,
                "kind": "RUMOR",
                "price_cash": 5000.0,
                "symbols": ["BLUEGOLD"],
                "initial_text": "chain root text",
            },
            headers={"X-Room-Id": room_id},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["card_id"]
        assert body["variant_id"]
        root_id = body["card_id"]

        snap = get_snapshot(buyer)
        assert abs(float(snap.cash) - 95000.0) < 1e-6

        # 根卡 + 2 个链树节点 = 3 张主卡
        rows = conn.execute("SELECT * FROM news WHERE variant_id IS NULL").fetchall()
        assert len(rows) == 3, f"expected 3 main cards, got {len(rows)}"

        root = get_main_card(root_id)
        assert root is not None
        assert root.kind == "RUMOR"
        assert "store_chain_root" in root.tags

        # 找到子节点
        children = [dict(r) for r in rows if r["parent_card_id"] == root_id]
        assert len(children) == 1
        first_child = children[0]
        assert first_child["kind"] == "RUMOR"
        assert first_child["scheduled_at"] is not None

        # 第二个节点依赖第一个节点
        second_rows = [dict(r) for r in rows if r["parent_card_id"] == first_child["card_id"]]
        assert len(second_rows) == 1
        second = second_rows[0]
        assert second["kind"] == "MAJOR_EVENT"
        assert second["scheduled_at"] is not None

        # 第二个节点的 scheduled_at 应该晚于第一个节点
        t1 = datetime.fromisoformat(first_child["scheduled_at"])
        t2 = datetime.fromisoformat(second["scheduled_at"])
        assert (t2 - t1).total_seconds() >= 15
    finally:
        _reset_room_id(token)


def test_purchase_chain_tree_transaction_rolls_back_on_failure(monkeypatch) -> None:
    room_id = f"room_chain_tree_rollback_{uuid4()}"
    buyer = f"user:chain:rollback:{uuid4()}"

    scenario_id = f"scenario_chain_tree_rollback_{uuid4()}"
    meta_resp = client.patch(
        f"/global/studio/news/scenarios/{scenario_id}/meta",
        json={
            "actor_id": "author",
            "background_story": "chain tree rollback scenario",
            "worldview": {
                "featured_symbols": ["BLUEGOLD"],
                "market_open_note": "open",
                "market_close_note": "close",
                "holiday_note": "holiday",
                "overview_note": "overview",
            },
            "news_store_items": [
                {
                    "kind": "RUMOR",
                    "price_cash": 5000.0,
                    "description": "Chain root",
                    "requires_symbols": False,
                    "trigger_mode": "AUTO_CHAIN",
                    "chain_tree": [
                        {
                            "node_id": "node_1",
                            "kind": "RUMOR",
                            "text": "First leak",
                            "scheduled_delay_seconds": 10,
                            "activation_prob": 1.0,
                            "parent_node_id": None,
                        },
                    ],
                }
            ],
        },
    )
    assert meta_resp.status_code == 200, meta_resp.text

    create_or_update_room_meta(
        room_id=room_id,
        player_id="host",
        name="chain tree rollback test",
        game_settings=RoomGameSettings(scenario_id=scenario_id),
    )

    from ifrontier.app import api as api_module
    from ifrontier.services import news as news_service_module

    original_create_card = news_service_module.NewsService.create_card

    def _failing_create_card(self, *args, **kwargs):
        # 第一次成功（根卡），第二次失败（链树节点），模拟中间步骤失败
        calls = getattr(_failing_create_card, "_calls", 0)
        _failing_create_card._calls = calls + 1
        if calls >= 1:
            raise ValueError("simulated chain expansion failure")
        return original_create_card(self, *args, **kwargs)

    monkeypatch.setattr(news_service_module.NewsService, "create_card", _failing_create_card)

    # 避免房间激活全局冷却导致 429
    sleep(2.5)

    token = _set_room_id(room_id)
    try:
        init_schema()
        create_account(buyer, owner_type="user", initial_cash=100000.0)
        conn = get_connection()
        conn.execute("DELETE FROM news")
        conn.commit()

        resp = client.post(
            "/news/store/purchase",
            json={
                "buyer_user_id": buyer,
                "kind": "RUMOR",
                "price_cash": 5000.0,
                "symbols": ["BLUEGOLD"],
            },
            headers={"X-Room-Id": room_id},
        )
        assert resp.status_code == 400, resp.text

        # 资金必须回滚
        snap = get_snapshot(buyer)
        assert abs(float(snap.cash) - 100000.0) < 1e-6

        # 数据库中不应留下任何主卡
        rows = conn.execute("SELECT * FROM news WHERE variant_id IS NULL").fetchall()
        assert len(rows) == 0, f"expected 0 main cards after rollback, got {len(rows)}"
    finally:
        _reset_room_id(token)
        if hasattr(_failing_create_card, "_calls"):
            delattr(_failing_create_card, "_calls")
