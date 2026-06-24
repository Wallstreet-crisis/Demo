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


def test_export_and_import_world_package() -> None:
    scenario_id = f"scenario_world_package_{uuid4().hex}"

    # 1. 创建场景 meta
    meta_resp = client.patch(
        f"/global/studio/news/scenarios/{scenario_id}/meta",
        json={
            "actor_id": "author",
            "background_story": "package test bg",
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
                    "price_cash": 1234.0,
                    "description": "pkg item",
                    "requires_symbols": False,
                    "trigger_mode": "IMMEDIATE",
                    "tags": ["pkg"],
                    "rarity": "COMMON",
                    "chain_kind": None,
                    "chain_defaults": {},
                    "chain_tree": [],
                    "enabled": True,
                }
            ],
        },
    )
    assert meta_resp.status_code == 200, meta_resp.text

    # 2. 创建场景卡
    card_resp = client.post(
        "/global/studio/news/cards",
        json={
            "actor_id": "author",
            "kind": "RUMOR",
            "text": "pkg card",
            "symbols": ["BLUEGOLD"],
            "tags": ["pkg"],
            "scenario_id": scenario_id,
        },
    )
    assert card_resp.status_code == 200, card_resp.text

    # 3. 导出世界包
    export_resp = client.get(f"/global/studio/news/scenarios/{scenario_id}/package")
    assert export_resp.status_code == 200, export_resp.text
    pkg = export_resp.json()
    assert pkg["scenario_id"] == scenario_id
    assert pkg["background_story"] == "package test bg"
    assert len(pkg["news_store_items"]) == 1
    assert len(pkg["cards"]) == 1
    assert pkg["cards"][0]["text"] == "pkg card"

    # 4. 创建新场景并导入
    new_scenario_id = f"scenario_world_package_target_{uuid4().hex}"
    import_resp = client.post(
        f"/global/studio/news/scenarios/{new_scenario_id}/package",
        json={
            "actor_id": "author",
            "package": pkg,
        },
    )
    assert import_resp.status_code == 200, import_resp.text

    # 5. 验证新场景 meta 和卡片
    new_meta = client.get(f"/global/studio/news/scenarios/{new_scenario_id}/meta")
    assert new_meta.status_code == 200, new_meta.text
    new_meta_body = new_meta.json()
    assert new_meta_body["background_story"] == "package test bg"
    assert len(new_meta_body["news_store_items"]) == 1

    new_cards = client.get(f"/global/studio/news/scenarios/{new_scenario_id}/cards")
    assert new_cards.status_code == 200, new_cards.text
    new_cards_body = new_cards.json()
    assert len(new_cards_body) == 1
    assert new_cards_body[0]["text"] == "pkg card"


def test_default_template_renders_in_frontend_shape() -> None:
    # 1. 拉取默认模板
    template_resp = client.get("/global/studio/news/templates/default")
    assert template_resp.status_code == 200, template_resp.text
    template = template_resp.json()

    # 2. 验证模板结构完整
    assert template["scenario_id"] == "DEFAULT_TEMPLATE"
    assert template["background_story"]
    assert template["worldview"]["featured_symbols"]
    assert len(template["news_store_items"]) >= 5
    assert len(template["cards"]) >= 5

    # 3. 验证剧情树存在父子关系
    cards = template["cards"]
    root = next((c for c in cards if c.get("parent_card_id") is None), None)
    assert root is not None
    children = [c for c in cards if c.get("parent_card_id") == root["card_id"]]
    assert len(children) >= 3

    # 4. 验证商店链树存在
    auto_chain_items = [i for i in template["news_store_items"] if i.get("trigger_mode") == "AUTO_CHAIN"]
    assert len(auto_chain_items) >= 1
    for item in auto_chain_items:
        assert len(item.get("chain_tree") or []) >= 1

    # 5. 导入到一个新 scenario，确保前端能真正加载渲染
    target_id = f"scenario_default_template_{uuid4().hex}"
    import_resp = client.post(
        f"/global/studio/news/scenarios/{target_id}/package",
        json={
            "actor_id": "author",
            "package": {**template, "scenario_id": target_id},
        },
    )
    assert import_resp.status_code == 200, import_resp.text

    cards_resp = client.get(f"/global/studio/news/scenarios/{target_id}/cards")
    assert cards_resp.status_code == 200, cards_resp.text
    assert len(cards_resp.json()) == len(template["cards"])

    meta_resp = client.get(f"/global/studio/news/scenarios/{target_id}/meta")
    assert meta_resp.status_code == 200, meta_resp.text
    meta = meta_resp.json()
    assert len(meta["news_store_items"]) == len(template["news_store_items"])
    assert meta["background_story"] == template["background_story"]
