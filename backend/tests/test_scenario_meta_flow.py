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
from ifrontier.app.room_engine import RoomEngine
from ifrontier.app.room_meta import create_or_update_room_meta
from ifrontier.infra.sqlite.db import get_connection, room_id_var
from ifrontier.infra.sqlite.event_store import SqliteEventStore
from ifrontier.services.news import NewsService

client = TestClient(app)


def test_global_scenario_meta_roundtrip_and_editing() -> None:
    scenario_id = f"scenario:meta:{uuid4()}"

    first_payload = {
        "actor_id": "author",
        "background_story": "第一版背景剧情",
        "worldview": {
            "featured_symbols": ["AAA", "BBB"],
            "market_open_note": "开市说明",
            "market_close_note": "闭市说明",
            "holiday_note": "假日说明",
            "overview_note": "世界观概览",
        },
        "news_store_items": [
            {
                "kind": "RUMOR",
                "price_cash": 1234.0,
                "description": "自定义商店条目",
                "requires_symbols": False,
                "trigger_mode": "IMMEDIATE",
                "tags": ["scenario", "custom"],
                "rarity": "COMMON",
                "chain_kind": None,
                "chain_defaults": {"seed": 7, "grant_count": 1},
                "enabled": True,
            }
        ],
    }

    resp = client.patch(f"/global/studio/news/scenarios/{scenario_id}/meta", json=first_payload)
    assert resp.status_code == 200, resp.text

    body = resp.json()
    assert body["scenario_id"] == scenario_id
    assert body["background_story"] == "第一版背景剧情"
    assert body["worldview"]["featured_symbols"] == ["AAA", "BBB"]
    assert body["worldview"]["market_open_note"] == "开市说明"
    assert body["news_store_items"][0]["kind"] == "RUMOR"
    assert body["news_store_items"][0]["price_cash"] == 1234.0
    assert body["news_store_items"][0]["chain_defaults"]["seed"] == 7

    updated_payload = {
        **first_payload,
        "background_story": "第二版背景剧情",
        "worldview": {
            "featured_symbols": ["CCC"],
            "market_open_note": "新的开市说明",
            "market_close_note": "新的闭市说明",
            "holiday_note": "新的假日说明",
            "overview_note": "新的世界观概览",
        },
        "news_store_items": [
            {
                "kind": "LEAK",
                "price_cash": 8888.0,
                "description": "已编辑的自定义商店条目",
                "requires_symbols": True,
                "trigger_mode": "AUTO_CHAIN",
                "tags": ["scenario", "updated"],
                "rarity": "RARE",
                "chain_kind": "WORLD_EVENT",
                "chain_defaults": {"seed": 99, "grant_count": 3},
                "enabled": False,
            }
        ],
    }

    resp = client.patch(f"/global/studio/news/scenarios/{scenario_id}/meta", json=updated_payload)
    assert resp.status_code == 200, resp.text

    body = resp.json()
    assert body["scenario_id"] == scenario_id
    assert body["background_story"] == "第二版背景剧情"
    assert body["worldview"]["featured_symbols"] == ["CCC"]
    assert body["worldview"]["overview_note"] == "新的世界观概览"
    assert len(body["news_store_items"]) == 1
    assert body["news_store_items"][0]["kind"] == "LEAK"
    assert body["news_store_items"][0]["chain_kind"] == "WORLD_EVENT"
    assert body["news_store_items"][0]["enabled"] is False

    list_resp = client.get("/global/studio/news/scenarios")
    assert list_resp.status_code == 200, list_resp.text
    scenario_ids = {item["id"] for item in list_resp.json()}
    assert scenario_id in scenario_ids


def test_room_initialize_db_imports_scenario_cards_for_bound_scenario() -> None:
    scenario_id = f"scenario:room:{uuid4()}"
    room_id = f"room_{uuid4().hex}"

    meta_resp = client.patch(
        f"/global/studio/news/scenarios/{scenario_id}/meta",
        json={
            "actor_id": "author",
            "background_story": "房间导入前的背景剧情",
            "worldview": {
                "featured_symbols": ["ROOM1"],
                "market_open_note": "房间开市",
                "market_close_note": "房间闭市",
                "holiday_note": "房间假日",
                "overview_note": "房间世界观",
            },
            "news_store_items": [
                {
                    "kind": "RUMOR",
                    "price_cash": 1000.0,
                    "description": "房间自定义商店",
                    "requires_symbols": False,
                    "trigger_mode": "IMMEDIATE",
                    "tags": ["room"],
                    "rarity": "COMMON",
                    "chain_kind": None,
                    "chain_defaults": {},
                    "enabled": True,
                }
            ],
        },
    )
    assert meta_resp.status_code == 200, meta_resp.text

    card_resp = client.post(
        "/global/studio/news/cards",
        json={
            "actor_id": "author",
            "kind": "RUMOR",
            "text": "场景正文卡片",
            "symbols": ["ROOM1"],
            "tags": ["scenario", "tree"],
            "scenario_id": scenario_id,
        },
    )
    assert card_resp.status_code == 200, card_resp.text
    card_id = card_resp.json()["card_id"]

    create_or_update_room_meta(room_id, "author", game_settings={"scenario_id": scenario_id})

    engine = RoomEngine(room_id)
    engine.initialize_db()

    token = room_id_var.set(room_id)
    try:
        conn = get_connection()
        row = conn.execute(
            "SELECT COUNT(*) AS count FROM news WHERE scenario_id = ? AND variant_id IS NULL",
            (scenario_id,),
        ).fetchone()
        assert row is not None
        assert row["count"] == 1

        imported = conn.execute(
            "SELECT card_id, kind, text, scenario_id FROM news WHERE card_id = ? LIMIT 1",
            (card_id,),
        ).fetchone()
        assert imported is not None
        assert imported["kind"] == "RUMOR"
        assert imported["text"] == "场景正文卡片"
        assert imported["scenario_id"] == scenario_id
    finally:
        room_id_var.reset(token)


def test_scenario_story_card_can_be_delivered_to_inbox_after_room_import() -> None:
    scenario_id = f"scenario:story:{uuid4()}"
    room_id = f"room_{uuid4().hex}"
    recipient = f"user:story:{uuid4()}"

    create_or_update_room_meta(room_id, "author", game_settings={"scenario_id": scenario_id})

    card_resp = client.post(
        "/global/studio/news/cards",
        json={
            "actor_id": "author",
            "kind": "RUMOR",
            "text": "背景剧情新闻：公司传出重大内部变动",
            "symbols": ["STORY"],
            "tags": ["scenario", "background"],
            "scenario_id": scenario_id,
        },
    )
    assert card_resp.status_code == 200, card_resp.text
    card_id = card_resp.json()["card_id"]

    engine = RoomEngine(room_id)
    engine.initialize_db()

    token = room_id_var.set(room_id)
    try:
        service = NewsService(SqliteEventStore())
        variant_id, _variant_event = service.emit_variant(
            card_id=card_id,
            author_id="author",
            text="背景剧情正式投递",
        )
        delivery_id, delivered_event = service.deliver_variant(
            variant_id=variant_id,
            to_player_id=recipient,
            from_actor_id="system",
            visibility_level="NORMAL",
            delivery_reason="BROADCAST",
        )

        assert delivery_id is not None
        assert delivered_event is not None

        inbox = service.list_inbox(player_id=recipient, limit=20)
        assert inbox
        assert any(item["variant_id"] == variant_id for item in inbox)
        assert any(item["delivery_reason"] == "BROADCAST" for item in inbox)
    finally:
        room_id_var.reset(token)
