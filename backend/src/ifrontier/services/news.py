from __future__ import annotations

import json
import random
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from ifrontier.domain.events.envelope import EventActor, EventEnvelope, EventEnvelopeJson
from ifrontier.domain.events.payloads import (
    NewsBroadcastedPayload,
    NewsCardCreatedPayload,
    NewsDeliveredPayload,
    NewsOwnershipGrantedPayload,
    NewsOwnershipTransferredPayload,
    NewsVariantEmittedPayload,
    NewsVariantMutatedPayload,
)
from ifrontier.domain.events.types import EventType
from ifrontier.infra.sqlite.event_store import SqliteEventStore
from ifrontier.infra.sqlite import news as news_db
from ifrontier.services.game_time import game_time_now, load_game_time_config_from_env

from ifrontier.domain.news.blueprints import IntelligenceBlueprint, registry as blueprint_registry

class NewsService:
    _REPEATABLE_DELIVERY_REASONS = {
        "PURCHASED",
        "PAID_PROMOTION",
    }

    def __init__(self, event_store: SqliteEventStore) -> None:
        self._event_store = event_store

    def _get_primary_blueprint(self, kind: str) -> IntelligenceBlueprint | None:
        pool = blueprint_registry.find_by_kind(str(kind or "").upper())
        return pool[0] if pool else None

    def _preset_templates(self) -> Dict[str, List[str]]:
        """Deprecated: use blueprint_registry instead."""
        out = {}
        for bp in blueprint_registry.list_blueprints():
            out[bp.kind] = bp.templates
        return out

    def get_preset_news_params(self, *, kind: str, theme: str | None = None) -> Dict[str, Any]:
        kind_key = str(kind or "UNKNOWN").upper()
        
        bp = self._get_primary_blueprint(kind_key)
        ttl_seconds = (bp.default_ttl_hours * 3600) if bp else (6 * 3600)

        kind_defaults: Dict[str, Dict[str, Any]] = {
            "RUMOR": {
                "direction_weights": {"UP": 0.34, "DOWN": 0.34, "STABLE": 0.32},
                "intensity": 0.45,
                "reliability_prior": 0.42,
                "deception_risk": 0.52,
                "worldview": "cyberpunk_rumor_network",
            },
            "LEAK": {
                "direction_weights": {"UP": 0.36, "DOWN": 0.34, "STABLE": 0.30},
                "intensity": 0.52,
                "reliability_prior": 0.58,
                "deception_risk": 0.38,
                "worldview": "cyberpunk_corporate_whistle",
            },
            "ANALYST_REPORT": {
                "direction_weights": {"UP": 0.40, "DOWN": 0.30, "STABLE": 0.30},
                "intensity": 0.48,
                "reliability_prior": 0.66,
                "deception_risk": 0.22,
                "worldview": "cyberpunk_sellside_desk",
            },
            "OMEN": {
                "direction_weights": {"UP": 0.34, "DOWN": 0.34, "STABLE": 0.32},
                "intensity": 0.35,
                "reliability_prior": 0.45,
                "deception_risk": 0.45,
                "worldview": "cyberpunk_signals",
            },
            "MAJOR_EVENT": {
                "direction_weights": {"UP": 0.45, "DOWN": 0.45, "STABLE": 0.10},
                "intensity": 0.85,
                "reliability_prior": 0.95,
                "deception_risk": 0.05,
                "worldview": "cyberpunk_breaking_news",
            },
            "WORLD_EVENT": {
                "direction_weights": {"UP": 0.48, "DOWN": 0.48, "STABLE": 0.04},
                "intensity": 0.95,
                "reliability_prior": 1.0,
                "deception_risk": 0.0,
                "worldview": "cyberpunk_global_macro",
            },
        }

        res = kind_defaults.get(kind_key, kind_defaults["RUMOR"]).copy()
        res["ttl_seconds"] = ttl_seconds
        
        if bp and bp.image_pool:
            res["image_uri"] = random.choice(bp.image_pool)
            
        return res

    def get_preset_template(self, kind: str, symbols: List[str]) -> str:
        """获取预设的情报模板并填充符号"""
        bp = self._get_primary_blueprint(kind)
        if not bp:
            return f"[{kind}] 发生未知异动。"
            
        text = random.choice(bp.templates)
        symbol_str = ", ".join(symbols) if symbols else "某知名企业"
        return text.format(symbol=symbol_str)

    def get_preset_templates(self, kind: str, symbols: List[str]) -> List[str]:
        bp = self._get_primary_blueprint(kind)
        if not bp:
            return []

        symbol_str = ", ".join(symbols) if symbols else "某知名企业"
        return [str(t).format(symbol=symbol_str) for t in bp.templates]

    def generate_market_shelf(
        self, 
        *, 
        player_id: str, 
        player_net_worth: float, 
        shelf_size: int = 6
    ) -> List[tuple[IntelligenceBlueprint, float]]:
        """
        为特定玩家生成黑市货架商品。
        返回 [(蓝图, 计算后的价格), ...]
        """
        all_bps = blueprint_registry.list_blueprints()
        if not all_bps:
            return []

        # 1. 基础权重计算
        # 财富越高，稀有卡牌权重略微提升（增加“高端货”出现率）
        wealth_factor = max(1.0, player_net_worth / 1000000.0) # 每百万资产提升系数
        
        weighted_pool = []
        for bp in all_bps:
            w = bp.weight
            if str(getattr(bp.rarity, "value", bp.rarity)) in {"EPIC", "LEGENDARY"}:
                w *= (1.0 + 0.1 * wealth_factor) # 高资产玩家更容易刷出高级货
            weighted_pool.append((bp, w))

        # 2. 采样
        selected_bps: List[IntelligenceBlueprint] = []
        # 使用 random.choices 进行加权采样
        if weighted_pool:
            bps, weights = zip(*weighted_pool)
            # 允许重复采样（代表不同模板），或者去重
            chosen = random.choices(bps, weights=weights, k=shelf_size)
            selected_bps = list(chosen)

        # 3. 价格计算
        # 基础价格 * 稀有度倍率 * 蓝图修正 * 随机波动
        rarity_multipliers = {
            "COMMON": 1.0,
            "UNCOMMON": 2.5,
            "RARE": 6.0,
            "EPIC": 15.0,
            "LEGENDARY": 50.0
        }
        
        shelf = []
        for bp in selected_bps:
            base_price = 2000.0 # 基础起步价
            rarity_key = str(getattr(bp.rarity, "value", bp.rarity))
            rarity_mult = rarity_multipliers.get(rarity_key, 1.0)
            
            # 财富调节：资产极高的玩家，黑市商人会坐地起价
            wealth_premium = 1.0
            if player_net_worth > 5000000:
                wealth_premium = 1.0 + (player_net_worth - 5000000) / 20000000.0
                wealth_premium = min(wealth_premium, 3.0) # 最高3倍溢价

            random_fluctuation = random.uniform(0.85, 1.25) # 15% 价格波动
            
            final_price = base_price * rarity_mult * bp.price_modifier * wealth_premium * random_fluctuation
            # 对齐到整百
            final_price = round(final_price / 100.0) * 100.0
            
            shelf.append((bp, final_price))
            
        return shelf

    def create_card(
        self,
        *,
        kind: str,
        image_anchor_id: str | None,
        image_uri: str | None,
        truth_payload: Dict[str, Any] | None,
        symbols: List[str] | None,
        tags: List[str] | None,
        actor_id: str,
        rarity: str | None = None,
        correlation_id: UUID | None = None,
    ) -> tuple[str, EventEnvelopeJson]:
        now = self._now_game_utc()
        card_id = str(uuid4())

        # 如果没有传 rarity，尝试从 kind 的默认蓝图中获取
        if not rarity:
            bp = self._get_primary_blueprint(kind)
            if bp:
                rarity = str(getattr(bp.rarity, "value", bp.rarity))
            else:
                rarity = "COMMON"

        news_db.save_news(
            card_id=card_id,
            kind=kind,
            publisher_id=actor_id,
            image_anchor_id=image_anchor_id,
            image_uri=image_uri,
            truth_payload=truth_payload,
            symbols=symbols or [],
            tags=tags or [],
            rarity=rarity,
        )

        payload = NewsCardCreatedPayload(
            card_id=card_id,
            kind=kind,
            image_anchor_id=image_anchor_id,
            image_uri=image_uri,
            truth_payload=truth_payload,
            symbols=symbols or [],
            tags=tags or [],
            created_at=now,
        )
        # Note: NewsCardCreatedPayload may need rarity if events need it, 
        # but db persistence is the priority for now.
        envelope = EventEnvelope[NewsCardCreatedPayload](
            event_type=EventType.NEWS_CARD_CREATED,
            correlation_id=correlation_id or uuid4(),
            actor=EventActor(user_id=actor_id),
            payload=payload,
        )
        event_json = EventEnvelopeJson.from_envelope(envelope)
        self._event_store.append(event_json)
        return card_id, event_json

    def emit_variant(
        self,
        *,
        card_id: str,
        author_id: str,
        text: str,
        parent_variant_id: str | None = None,
        influence_cost: float = 0.0,
        risk_roll: Dict[str, Any] | None = None,
        correlation_id: UUID | None = None,
    ) -> tuple[str, EventEnvelopeJson]:
        now = self._now_game_utc()
        variant_id = str(uuid4())

        card = news_db.get_news(card_id=card_id, variant_id=None)
        if card is None:
            raise ValueError("card not found")

        news_db.save_news(
            card_id=card_id,
            variant_id=variant_id,
            kind=card.kind,
            text=text,
            author_id=author_id,
            parent_variant_id=parent_variant_id,
            mutation_depth=0,
            influence_cost=float(influence_cost),
            risk_roll=risk_roll,
            published_at=now.isoformat(),
        )

        payload = NewsVariantEmittedPayload(
            card_id=card_id,
            variant_id=variant_id,
            parent_variant_id=parent_variant_id,
            author_id=author_id,
            text=text,
            influence_cost=float(influence_cost),
            risk_roll=risk_roll,
            created_at=now,
        )
        envelope = EventEnvelope[NewsVariantEmittedPayload](
            event_type=EventType.NEWS_VARIANT_EMITTED,
            correlation_id=correlation_id or uuid4(),
            actor=EventActor(user_id=author_id),
            payload=payload,
        )
        event_json = EventEnvelopeJson.from_envelope(envelope)
        self._event_store.append(event_json)
        return variant_id, event_json

    def mutate_variant(
        self,
        *,
        parent_variant_id: str,
        editor_id: str,
        new_text: str,
        influence_cost: float = 0.0,
        risk_roll: Dict[str, Any] | None = None,
        correlation_id: UUID | None = None,
    ) -> tuple[str, EventEnvelopeJson]:
        now = self._now_game_utc()
        new_variant_id = str(uuid4())

        parent = news_db.get_variant(parent_variant_id)
        if parent is None or not parent.get("card_id"):
            raise ValueError("parent variant not found")

        card_id = str(parent["card_id"])
        card = news_db.get_news(card_id=card_id, variant_id=None)
        if card is None:
            raise ValueError("card not found")
        # Depth increases by 1
        new_depth = int(parent.get("mutation_depth", 0)) + 1

        news_db.save_news(
            card_id=card_id,
            variant_id=new_variant_id,
            kind=card.kind,
            text=new_text,
            author_id=editor_id,
            parent_variant_id=parent_variant_id,
            mutation_depth=new_depth,
            influence_cost=float(influence_cost),
            risk_roll=risk_roll,
            published_at=now.isoformat(),
        )
        payload = NewsVariantMutatedPayload(
            card_id=card_id,
            new_variant_id=new_variant_id,
            parent_variant_id=parent_variant_id,
            editor_id=editor_id,
            new_text=new_text,
            influence_cost=float(influence_cost),
            risk_roll=risk_roll,
            mutated_at=now,
        )
        envelope = EventEnvelope[NewsVariantMutatedPayload](
            event_type=EventType.NEWS_VARIANT_MUTATED,
            correlation_id=correlation_id or uuid4(),
            actor=EventActor(user_id=editor_id),
            payload=payload,
        )
        event_json = EventEnvelopeJson.from_envelope(envelope)
        self._event_store.append(event_json)
        return new_variant_id, event_json

    def deliver_variant(
        self,
        *,
        variant_id: str,
        to_player_id: str,
        from_actor_id: str,
        visibility_level: str,
        delivery_reason: str,
        correlation_id: UUID | None = None,
    ) -> tuple[str | None, EventEnvelopeJson | None]:
        now = self._now_game_utc()

        variant = news_db.get_variant(variant_id)
        if variant is None or not variant.get("card_id"):
            raise ValueError("variant not found")

        card_id = str(variant["card_id"])

        reason_key = str(delivery_reason or "").upper()
        if reason_key not in self._REPEATABLE_DELIVERY_REASONS:
            existing = news_db.find_delivery(
                variant_id=variant_id,
                to_player_id=to_player_id,
                from_actor_id=from_actor_id,
                delivery_reason=delivery_reason,
            )
            if existing is not None:
                return str(existing.get("delivery_id") or ""), None

        delivery_id = str(uuid4())

        news_db.deliver_variant(
            delivery_id=delivery_id,
            variant_id=variant_id,
            to_player_id=to_player_id,
            from_actor_id=from_actor_id,
            visibility_level=visibility_level,
            delivery_reason=delivery_reason,
        )
        payload = NewsDeliveredPayload(
            delivery_id=delivery_id,
            card_id=card_id,
            variant_id=variant_id,
            to_player_id=to_player_id,
            from_actor_id=from_actor_id,
            visibility_level=visibility_level,
            delivery_reason=delivery_reason,
            delivered_at=now,
        )
        envelope = EventEnvelope[NewsDeliveredPayload](
            event_type=EventType.NEWS_DELIVERED,
            correlation_id=correlation_id or uuid4(),
            actor=EventActor(user_id=from_actor_id),
            payload=payload,
        )
        event_json = EventEnvelopeJson.from_envelope(envelope)
        self._event_store.append(event_json)
        return delivery_id, event_json

    def propagate_to_followers(
        self,
        *,
        variant_id: str,
        from_actor_id: str,
        visibility_level: str,
        spend_influence: float = 0.0,
        limit: int = 50,
        correlation_id: UUID | None = None,
    ) -> List[EventEnvelopeJson]:
        # v0：只做一跳传播，从 from_actor_id 投递给其 followers
        followers = news_db.list_followers(followee_id=from_actor_id, limit=int(limit))

        delivered_events: List[EventEnvelopeJson] = []
        for to_player_id in followers:
            _delivery_id, event_json = self.deliver_variant(
                variant_id=variant_id,
                to_player_id=to_player_id,
                from_actor_id=from_actor_id,
                visibility_level=visibility_level,
                delivery_reason="SOCIAL_PROPAGATION",
                correlation_id=correlation_id,
            )
            if event_json is not None:
                delivered_events.append(event_json)

        return delivered_events

    def broadcast_variant(
        self,
        *,
        variant_id: str,
        channel: str,
        visibility_level: str,
        actor_id: str,
        limit_users: int = 5000,
        correlation_id: UUID | None = None,
    ) -> tuple[int, EventEnvelopeJson]:
        broadcast_id = str(uuid4())
        corr = correlation_id or uuid4()
        users = news_db.list_all_users(limit=int(limit_users))

        count = 0
        for to_player_id in users:
            _delivery_id, delivery_event = self.deliver_variant(
                variant_id=variant_id,
                to_player_id=to_player_id,
                from_actor_id=actor_id,
                visibility_level=visibility_level,
                delivery_reason="BROADCAST",
                correlation_id=corr,
            )
            if delivery_event is not None:
                count += 1

        variant = news_db.get_variant(variant_id)
        card_id = str((variant or {}).get("card_id") or "")

        payload = NewsBroadcastedPayload(
            broadcast_id=broadcast_id,
            card_id=card_id,
            variant_id=variant_id,
            channel=channel,
            delivered_count=count,
            broadcasted_at=self._now_game_utc(),
        )
        envelope = EventEnvelope[NewsBroadcastedPayload](
            event_type=EventType.NEWS_BROADCASTED,
            correlation_id=corr,
            actor=EventActor(user_id=actor_id),
            payload=payload,
        )
        event_json = EventEnvelopeJson.from_envelope(envelope)
        self._event_store.append(event_json)
        return count, event_json

    def list_inbox(self, *, player_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        return news_db.list_inbox(user_id=player_id, limit=int(limit))

    def get_variant_context(self, *, variant_id: str) -> Dict[str, Any] | None:
        v = news_db.get_variant(variant_id)
        if v is None:
            return None
        card_id = str(v.get("card_id") or "")
        if not card_id:
            return None

        card = news_db.get_news(card_id=card_id, variant_id=None)
        if card is None:
            return None

        truth_payload_json = json.dumps(card.truth_payload or {}, ensure_ascii=False)
        return {
            "text": v.get("text") or "",
            "author_id": v.get("author_id") or "",
            "mutation_depth": int(v.get("mutation_depth") or 0),
            "symbols": card.symbols or [],
            "truth_payload_json": truth_payload_json,
            "kind": card.kind,
        }

    def grant_ownership(
        self,
        *,
        card_id: str,
        to_user_id: str,
        granter_id: str,
        correlation_id: UUID | None = None,
    ) -> EventEnvelopeJson:
        now = self._now_game_utc()
        news_db.grant_ownership(card_id=card_id, user_id=to_user_id, granter_id=granter_id)

        payload = NewsOwnershipGrantedPayload(
            card_id=card_id,
            to_user_id=to_user_id,
            granter_id=granter_id,
            granted_at=now,
        )
        envelope = EventEnvelope[NewsOwnershipGrantedPayload](
            event_type=EventType.NEWS_OWNERSHIP_GRANTED,
            correlation_id=correlation_id or uuid4(),
            actor=EventActor(user_id=granter_id),
            payload=payload,
        )
        event_json = EventEnvelopeJson.from_envelope(envelope)
        self._event_store.append(event_json)
        return event_json

    def transfer_ownership(
        self,
        *,
        card_id: str,
        from_user_id: str,
        to_user_id: str,
        transferred_by: str,
        correlation_id: UUID | None = None,
    ) -> EventEnvelopeJson:
        if from_user_id == to_user_id:
            raise ValueError("from_user_id and to_user_id must be different")

        now = self._now_game_utc()
        news_db.transfer_ownership(
            card_id=card_id, from_user_id=from_user_id, to_user_id=to_user_id, transferred_by=transferred_by
        )

        payload = NewsOwnershipTransferredPayload(
            card_id=card_id,
            from_user_id=from_user_id,
            to_user_id=to_user_id,
            transferred_by=transferred_by,
            transferred_at=now,
        )
        envelope = EventEnvelope[NewsOwnershipTransferredPayload](
            event_type=EventType.NEWS_OWNERSHIP_TRANSFERRED,
            correlation_id=correlation_id or uuid4(),
            actor=EventActor(user_id=transferred_by),
            payload=payload,
        )
        event_json = EventEnvelopeJson.from_envelope(envelope)
        self._event_store.append(event_json)
        return event_json

    def list_owned_cards(self, *, user_id: str, limit: int = 200) -> List[str]:
        rows = news_db.list_owned_cards(user_id=user_id, limit=int(limit))
        return [str(r.get("card_id")) for r in rows if r.get("card_id")]

    def ensure_bot_users(self, bot_ids: List[str]) -> None:
        """确保内置机器人在新闻用户表中存在"""
        for bot_id in bot_ids:
            news_db.create_user(bot_id)

    def init_news_seed_data(self) -> None:
        """初始化预设的新闻卡牌组"""
        if news_db.count_cards() > 0:
            return

        seeds = [
            {
                "kind": "EARNINGS",
                "symbols": ["NEURALINK"],
                "text": "Neuralink 脑机接口三期临床实验数据远超预期。",
                "truth_payload": {
                    "impact": 0.15,
                    "direction": "UP",
                    "intensity": 0.62,
                    "ttl_seconds": 5400,
                    "reliability_prior": 0.85,
                    "deception_risk": 0.12,
                    "worldview": "cyberpunk_clinical_breakthrough",
                },
            },
            {
                "kind": "MILITARY",
                "symbols": ["BLUEGOLD"],
                "text": "BlueGold 获得北方联盟 500 亿信用点防御订单。",
                "truth_payload": {
                    "impact": 0.2,
                    "direction": "UP",
                    "intensity": 0.58,
                    "ttl_seconds": 4200,
                    "reliability_prior": 0.74,
                    "deception_risk": 0.2,
                    "worldview": "cyberpunk_defense_contract",
                },
            },
            {
                "kind": "ENERGY",
                "symbols": ["MARS_GEN"],
                "text": "火星二号核聚变电站发生容器泄漏事故。",
                "truth_payload": {
                    "impact": -0.25,
                    "direction": "DOWN",
                    "intensity": 0.64,
                    "ttl_seconds": 3600,
                    "reliability_prior": 0.77,
                    "deception_risk": 0.18,
                    "worldview": "cyberpunk_infrastructure_risk",
                },
            },
            {
                "kind": "FINANCE",
                "symbols": ["CIVILBANK"],
                "text": "联邦储备局宣布将维持当前基准利率不变。",
                "truth_payload": {
                    "impact": 0.02,
                    "direction": "STABLE",
                    "intensity": 0.35,
                    "ttl_seconds": 4800,
                    "reliability_prior": 0.82,
                    "deception_risk": 0.08,
                    "worldview": "cyberpunk_policy_signal",
                },
            }
        ]

        for s in seeds:
            card_id, _ = self.create_card(
                kind=s["kind"],
                image_anchor_id=None,
                image_uri=None,
                truth_payload=s["truth_payload"],
                symbols=s["symbols"],
                tags=["seed"],
                actor_id="system"
            )
            # 默认给系统生成一个变体
            self.emit_variant(
                card_id=card_id,
                author_id="system",
                text=s["text"]
            )

    def get_preset_template(self, kind: str, symbols: List[str]) -> str:
        """获取预设的情报模板并填充符号"""
        templates = self._preset_templates()
        kind_key = kind.upper()
        pool = templates.get(kind_key, templates["RUMOR"])
        text = random.choice(pool)
        
        symbol_str = ", ".join(symbols) if symbols else "某知名企业"
        return text.format(symbol=symbol_str)

    def get_preset_templates(self, kind: str, symbols: List[str]) -> List[str]:
        templates = self._preset_templates()
        kind_key = kind.upper()
        pool = templates.get(kind_key, templates["RUMOR"])
        symbol_str = ", ".join(symbols) if symbols else "某知名企业"
        return [str(t).format(symbol=symbol_str) for t in pool]

