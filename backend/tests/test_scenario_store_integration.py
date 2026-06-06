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
from ifrontier.app.room_meta import create_or_update_room_meta
from ifrontier.infra.sqlite.db import room_id_var
from ifrontier.infra.sqlite.ledger import create_account
from ifrontier.infra.sqlite.news import get_main_card
from ifrontier.infra.sqlite.schema import init_schema

client = TestClient(app)


def test_scenario_store_catalog_overrides_blueprint_defaults_and_purchase_uses_config() -> None:
    scenario_id = f"scenario:store:{uuid4()}"
    room_id = f"room_{uuid4().hex}"
    player_id = f"user:store:{uuid4()}"

    token = room_id_var.set(room_id)
    try:
        init_schema()
        create_account(player_id, owner_type="user", initial_cash=100000.0)
    finally:
        room_id_var.reset(token)

    meta_resp = client.patch(
        f"/global/studio/news/scenarios/{scenario_id}/meta",
        json={
            "actor_id": "author",
            "background_story": "场景商店背景剧情",
            "worldview": {
                "featured_symbols": ["BLUEGOLD"],
                "market_open_note": "开市",
                "market_close_note": "闭市",
                "holiday_note": "假日",
                "overview_note": "商店场景世界观",
            },
            "news_store_items": [
                {
                    "kind": "RUMOR",
                    "price_cash": 7777.0,
                    "description": "场景商店商品",
                    "requires_symbols": True,
                    "trigger_mode": "MANUAL",
                    "tags": ["scenario", "store"],
                    "rarity": "EPIC",
                    "chain_kind": None,
                    "chain_defaults": {"seed": 17, "grant_count": 2},
                    "enabled": True,
                }
            ],
        },
    )
    assert meta_resp.status_code == 200, meta_resp.text

    create_or_update_room_meta(room_id, "author", game_settings={"scenario_id": scenario_id})

    catalog_resp = client.get(
        "/news/store/catalog",
        params={"user_id": player_id, "force_refresh": True},
        headers={"X-Room-Id": room_id},
    )
    assert catalog_resp.status_code == 200, catalog_resp.text
    catalog = catalog_resp.json()
    assert len(catalog["items"]) == 1
    item = catalog["items"][0]
    assert item["kind"] == "RUMOR"
    assert item["price_cash"] == 7777.0
    assert item["requires_symbols"] is True
    assert item["trigger_mode"] == "MANUAL"
    assert item["tags"] == ["scenario", "store"]
    assert item["rarity"] == "EPIC"
    assert item["chain_kind"] == "RUMOR"
    assert item["preview_text"]

    purchase_resp = client.post(
        "/news/store/purchase",
        headers={"X-Room-Id": room_id},
        json={
            "buyer_user_id": player_id,
            "kind": "RUMOR",
            "price_cash": 1.0,
            "symbols": ["BLUEGOLD"],
            "initial_text": "购买时忽略请求价格，使用场景配置",
        },
    )
    assert purchase_resp.status_code == 200, purchase_resp.text
    purchase = purchase_resp.json()
    assert purchase["card_id"]
    assert purchase["variant_id"] is None
    assert purchase["chain_id"] is None

    token = room_id_var.set(room_id)
    try:
        card = get_main_card(purchase["card_id"])
        assert card is not None
        assert card.kind == "RUMOR"
        assert card.rarity == "EPIC"
        assert card.tags == ["scenario", "store"]
        assert card.symbols == ["BLUEGOLD"]
    finally:
        room_id_var.reset(token)

    bad_resp = client.post(
        "/news/store/purchase",
        headers={"X-Room-Id": room_id},
        json={
            "buyer_user_id": player_id,
            "kind": "LEAK",
            "price_cash": 1.0,
            "symbols": ["BLUEGOLD"],
            "initial_text": "should fail",
        },
    )
    assert bad_resp.status_code == 400, bad_resp.text
    assert "unknown kind" in bad_resp.json()["detail"]
