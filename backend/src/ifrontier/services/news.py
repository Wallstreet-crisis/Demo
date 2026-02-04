from __future__ import annotations

import json
import random
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from neo4j import Driver

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
from ifrontier.infra.neo4j.event_store import Neo4jEventStore
from ifrontier.services.game_time import game_time_now, load_game_time_config_from_env


class NewsService:
    def __init__(self, driver: Driver, event_store: Neo4jEventStore) -> None:
        self._driver = driver
        self._event_store = event_store

    def _preset_templates(self) -> Dict[str, List[str]]:
        return {
            "RUMOR": [
                "听说 {symbol} 内部正在秘密洽谈一项巨额收购案。",
                "有人在夜店看到 {symbol} 的 CEO 与竞争对手共进晚餐。",
                "传闻 {symbol} 的下一代产品由于供应链问题将延期发布。",
                "市场都在议论 {symbol} 可能会在近期宣布派息计划。",
                "路边社消息：{symbol} 的核心专利可能面临侵权诉讼。",
                "匿名论坛传出 {symbol} 正在考虑整体私有化退市。",
            ],
            "LEAK": [
                "【绝密泄露】{symbol} 上季度的实际营收增长率可能远超财报预期。",
                "内部邮件显示，{symbol} 的核心技术团队已有超过 30% 的人员离职。",
                "一份未公开的文件指出，监管机构正在调查 {symbol} 的财务合规性。",
                "{symbol} 内部实验室的初步测试数据显示，新工艺成本降低了 40%。",
                "【深度爆料】{symbol} 的最大股东正在秘密质押全部股权。",
                "泄露的内部评估报告认为 {symbol} 进军新市场的计划已陷入停滞。",
            ],
            "ANALYST_REPORT": [
                "【机构内参】维持 {symbol} ‘买入’评级，目标价上调 15%。",
                "深研报告：{symbol} 在当前宏观环境下具有极强的防御属性。",
                "风险警示：{symbol} 的资产负债率已接近行业预警线。",
                "行业透视：{symbol} 正在通过 AI 转型重塑其核心竞争力。",
                "摩根大通分析：{symbol} 的现金流状况足以支持其三年的研发投入。",
                "行业蓝皮书：{symbol} 在细分市场的占有率已达到 45% 的统治地位。",
            ],
            "OMEN": [
                "外交部发言人对 {symbol} 所在地区的局势表示深切关注。",
                "监测到 {symbol} 总部大楼连续三晚彻夜通明。",
                "大宗交易系统出现针对 {symbol} 的异常看跌期权成交。",
                "卫星图像显示 {symbol} 的主要工厂外围有大量军方车辆出入。",
            ],
            "MAJOR_EVENT": [
                "【紧急公告】{symbol} 宣布由于不可抗力暂停所有生产活动。",
                "突发新闻：针对 {symbol} 的反垄断法案在议会高票通过。",
                "重大突破：{symbol} 宣布其划时代的‘量子能源’已实现商业化落地。",
                "地缘政经：跨国禁令正式生效，{symbol} 失去其主要海外市场渠道。",
            ],
        }

    def _now_game_utc(self) -> datetime:
        cfg = load_game_time_config_from_env()
        return game_time_now(cfg=cfg, real_now_utc=None).real_now_utc

    def follow(self, *, follower_id: str, followee_id: str) -> None:
        with self._driver.session() as session:
            session.execute_write(
                self._follow_tx,
                {"follower_id": follower_id, "followee_id": followee_id},
            )

    def list_users(self, *, limit: int = 5000) -> List[str]:
        with self._driver.session() as session:
            users = session.execute_read(self._list_users_tx, {"limit": int(limit)})
        return [str(r["user_id"]) for r in users]

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
        correlation_id: UUID | None = None,
    ) -> tuple[str, EventEnvelopeJson]:
        now = self._now_game_utc()
        card_id = str(uuid4())

        with self._driver.session() as session:
            session.execute_write(
                self._create_card_tx,
                {
                    "card_id": card_id,
                    "kind": kind,
                    "image_anchor_id": image_anchor_id,
                    "image_uri": image_uri,
                    "truth_payload_json": json.dumps(truth_payload or {}, ensure_ascii=False),
                    "symbols": symbols or [],
                    "tags": tags or [],
                    "created_at": now.isoformat(),
                },
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
        envelope = EventEnvelope[
            NewsCardCreatedPayload
        ](
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

        with self._driver.session() as session:
            session.execute_write(
                self._emit_variant_tx,
                {
                    "card_id": card_id,
                    "variant_id": variant_id,
                    "parent_variant_id": parent_variant_id,
                    "author_id": author_id,
                    "text": text,
                    "mutation_depth": 0,
                    "influence_cost": float(influence_cost),
                    "risk_roll_json": json.dumps(risk_roll or {}, ensure_ascii=False),
                    "created_at": now.isoformat(),
                },
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
        envelope = EventEnvelope[
            NewsVariantEmittedPayload
        ](
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

        with self._driver.session() as session:
            record = session.execute_write(
                self._mutate_variant_tx,
                {
                    "parent_variant_id": parent_variant_id,
                    "new_variant_id": new_variant_id,
                    "editor_id": editor_id,
                    "new_text": new_text,
                    "influence_cost": float(influence_cost),
                    "risk_roll_json": json.dumps(risk_roll or {}, ensure_ascii=False),
                    "mutated_at": now.isoformat(),
                },
            )

        if record is None or record.get("card_id") is None:
            raise ValueError("parent variant not found")

        card_id = str(record["card_id"])
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
        envelope = EventEnvelope[
            NewsVariantMutatedPayload
        ](
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
    ) -> tuple[str, EventEnvelopeJson]:
        now = self._now_game_utc()
        delivery_id = str(uuid4())

        with self._driver.session() as session:
            record = session.execute_write(
                self._deliver_variant_tx,
                {
                    "delivery_id": delivery_id,
                    "variant_id": variant_id,
                    "to_player_id": to_player_id,
                    "from_actor_id": from_actor_id,
                    "visibility_level": visibility_level,
                    "delivery_reason": delivery_reason,
                    "delivered_at": now.isoformat(),
                },
            )

        if record is None or record.get("card_id") is None:
            raise ValueError("variant not found")

        card_id = str(record["card_id"])
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
        envelope = EventEnvelope[
            NewsDeliveredPayload
        ](
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
        with self._driver.session() as session:
            followers = session.execute_read(
                self._list_followers_tx,
                {"followee_id": from_actor_id, "limit": int(limit)},
            )

        delivered_events: List[EventEnvelopeJson] = []
        for f in followers:
            to_player_id = str(f["user_id"])
            _delivery_id, event_json = self.deliver_variant(
                variant_id=variant_id,
                to_player_id=to_player_id,
                from_actor_id=from_actor_id,
                visibility_level=visibility_level,
                delivery_reason="SOCIAL_PROPAGATION",
                correlation_id=correlation_id,
            )
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

        with self._driver.session() as session:
            users = session.execute_read(self._list_users_tx, {"limit": int(limit_users)})

        count = 0
        for u in users:
            to_player_id = str(u["user_id"])
            _delivery_id, _delivery_event = self.deliver_variant(
                variant_id=variant_id,
                to_player_id=to_player_id,
                from_actor_id=actor_id,
                visibility_level=visibility_level,
                delivery_reason="BROADCAST",
                correlation_id=corr,
            )
            count += 1

        # 记录 broadcast 事件（并不需要与每个 delivery 事务一致）
        with self._driver.session() as session:
            rec = session.execute_read(self._get_card_id_by_variant_tx, {"variant_id": variant_id})
        card_id = str((rec or {}).get("card_id") or "")

        payload = NewsBroadcastedPayload(
            broadcast_id=broadcast_id,
            card_id=card_id,
            variant_id=variant_id,
            channel=channel,
            delivered_count=count,
            broadcasted_at=self._now_game_utc(),
        )
        envelope = EventEnvelope[
            NewsBroadcastedPayload
        ](
            event_type=EventType.NEWS_BROADCASTED,
            correlation_id=corr,
            actor=EventActor(user_id=actor_id),
            payload=payload,
        )
        event_json = EventEnvelopeJson.from_envelope(envelope)
        self._event_store.append(event_json)
        return count, event_json

    def list_inbox(self, *, player_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        with self._driver.session() as session:
            records = session.execute_read(
                self._list_inbox_tx,
                {"player_id": player_id, "limit": int(limit)},
            )

        return [dict(r) for r in records]

    def get_variant_context(self, *, variant_id: str) -> Dict[str, Any] | None:
        with self._driver.session() as session:
            rec = session.execute_read(
                self._get_variant_context_tx,
                {"variant_id": variant_id},
            )
        return dict(rec) if rec is not None else None

    def grant_ownership(
        self,
        *,
        card_id: str,
        to_user_id: str,
        granter_id: str,
        correlation_id: UUID | None = None,
    ) -> EventEnvelopeJson:
        now = self._now_game_utc()
        with self._driver.session() as session:
            ok = session.execute_write(
                self._grant_ownership_tx,
                {"card_id": card_id, "to_user_id": to_user_id},
            )
        if not ok:
            raise ValueError("card not found")

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
        with self._driver.session() as session:
            ok = session.execute_write(
                self._transfer_ownership_tx,
                {
                    "card_id": card_id,
                    "from_user_id": from_user_id,
                    "to_user_id": to_user_id,
                },
            )
        if not ok:
            raise ValueError("ownership not found")

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
        with self._driver.session() as session:
            rows = session.execute_read(
                self._list_owned_cards_tx,
                {"user_id": user_id, "limit": int(limit)},
            )
        return [str(r["card_id"]) for r in rows]

    def init_news_seed_data(self) -> None:
        """初始化预设的新闻卡牌组"""
        with self._driver.session() as session:
            # 检查是否已有卡牌，避免重复创建
            count = session.execute_read(lambda tx: tx.run("MATCH (c:NewsCard) RETURN count(c) as c").single()["c"])
            if count > 0:
                return

        seeds = [
            {
                "kind": "EARNINGS",
                "symbols": ["NEURALINK"],
                "text": "Neuralink 脑机接口三期临床实验数据远超预期。",
                "truth_payload": {"impact": 0.15, "direction": "UP"}
            },
            {
                "kind": "MILITARY",
                "symbols": ["BLUEGOLD"],
                "text": "BlueGold 获得北方联盟 500 亿信用点防御订单。",
                "truth_payload": {"impact": 0.2, "direction": "UP"}
            },
            {
                "kind": "ENERGY",
                "symbols": ["MARS_GEN"],
                "text": "火星二号核聚变电站发生容器泄漏事故。",
                "truth_payload": {"impact": -0.25, "direction": "DOWN"}
            },
            {
                "kind": "FINANCE",
                "symbols": ["CIVILBANK"],
                "text": "联邦储备局宣布将维持当前基准利率不变。",
                "truth_payload": {"impact": 0.02, "direction": "STABLE"}
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

    @staticmethod
    def _follow_tx(tx, params: Dict[str, Any]) -> None:
        tx.run(
            """
            MERGE (a:User {user_id: $follower_id})
            MERGE (b:User {user_id: $followee_id})
            MERGE (a)-[:FOLLOWS]->(b)
            """,
            **params,
        )

    @staticmethod
    def _create_card_tx(tx, params: Dict[str, Any]) -> None:
        tx.run(
            """
            MERGE (c:NewsCard {card_id: $card_id})
            SET c.kind = $kind,
                c.image_anchor_id = $image_anchor_id,
                c.image_uri = $image_uri,
                c.truth_payload_json = $truth_payload_json,
                c.symbols = $symbols,
                c.tags = $tags,
                c.created_at = $created_at
            """,
            **params,
        )

    @staticmethod
    def _emit_variant_tx(tx, params: Dict[str, Any]) -> None:
        tx.run(
            """
            MATCH (c:NewsCard {card_id: $card_id})
            MERGE (v:NewsVariant {variant_id: $variant_id})
            SET v.text = $text,
                v.author_id = $author_id,
                v.mutation_depth = $mutation_depth,
                v.influence_cost = $influence_cost,
                v.risk_roll_json = $risk_roll_json,
                v.created_at = $created_at
            MERGE (c)-[:HAS_VARIANT]->(v)

            WITH c, v
            FOREACH (_ IN CASE WHEN $parent_variant_id IS NULL THEN [] ELSE [1] END |
              MERGE (p:NewsVariant {variant_id: $parent_variant_id})
              MERGE (p)-[:PARENT_OF]->(v)
            )
            """,
            **params,
        )

    @staticmethod
    def _mutate_variant_tx(tx, params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        rec = tx.run(
            """
            MATCH (p:NewsVariant {variant_id: $parent_variant_id})
            MATCH (c:NewsCard)-[:HAS_VARIANT]->(p)
            MERGE (v:NewsVariant {variant_id: $new_variant_id})
            SET v.text = $new_text,
                v.author_id = $editor_id,
                v.mutation_depth = CASE WHEN p.mutation_depth IS NULL THEN 1 ELSE toInteger(p.mutation_depth) + 1 END,
                v.influence_cost = $influence_cost,
                v.risk_roll_json = $risk_roll_json,
                v.created_at = $mutated_at
            MERGE (c)-[:HAS_VARIANT]->(v)
            MERGE (p)-[:PARENT_OF]->(v)
            RETURN c.card_id AS card_id
            """,
            **params,
        ).single()
        return dict(rec) if rec is not None else None

    @staticmethod
    def _deliver_variant_tx(tx, params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        rec = tx.run(
            """
            MATCH (v:NewsVariant {variant_id: $variant_id})
            MATCH (c:NewsCard)-[:HAS_VARIANT]->(v)
            MERGE (u:User {user_id: $to_player_id})
            MERGE (d:NewsDelivery {delivery_id: $delivery_id})
            SET d.variant_id = $variant_id,
                d.card_id = c.card_id,
                d.to_player_id = $to_player_id,
                d.from_actor_id = $from_actor_id,
                d.visibility_level = $visibility_level,
                d.delivery_reason = $delivery_reason,
                d.delivered_at = $delivered_at
            MERGE (u)-[:INBOX_ITEM]->(d)
            MERGE (d)-[:DELIVERS_VARIANT]->(v)
            RETURN c.card_id AS card_id
            """,
            **params,
        ).single()
        return dict(rec) if rec is not None else None

    @staticmethod
    def _list_followers_tx(tx, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        result = tx.run(
            """
            MATCH (f:User)-[:FOLLOWS]->(x:User {user_id: $followee_id})
            RETURN f.user_id AS user_id
            LIMIT $limit
            """,
            **params,
        )
        return [dict(r) for r in result]

    @staticmethod
    def _grant_ownership_tx(tx, params: Dict[str, Any]) -> bool:
        rec = tx.run(
            """
            MATCH (c:NewsCard {card_id: $card_id})
            MERGE (u:User {user_id: $to_user_id})
            MERGE (u)-[:OWNS_NEWS]->(c)
            RETURN true AS ok
            """,
            **params,
        ).single()
        return bool(rec and rec.get("ok"))

    @staticmethod
    def _transfer_ownership_tx(tx, params: Dict[str, Any]) -> bool:
        rec = tx.run(
            """
            MATCH (from:User {user_id: $from_user_id})-[r:OWNS_NEWS]->(c:NewsCard {card_id: $card_id})
            MERGE (to:User {user_id: $to_user_id})
            DELETE r
            MERGE (to)-[:OWNS_NEWS]->(c)
            RETURN true AS ok
            """,
            **params,
        ).single()
        return bool(rec and rec.get("ok"))

    @staticmethod
    def _list_owned_cards_tx(tx, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        result = tx.run(
            """
            MATCH (u:User {user_id: $user_id})-[:OWNS_NEWS]->(c:NewsCard)
            RETURN c.card_id AS card_id
            ORDER BY c.created_at DESC
            LIMIT $limit
            """,
            **params,
        )
        return [dict(r) for r in result]

    @staticmethod
    def _list_users_tx(tx, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        result = tx.run(
            """
            MATCH (u:User)
            RETURN u.user_id AS user_id
            LIMIT $limit
            """,
            **params,
        )
        return [dict(r) for r in result]

    @staticmethod
    def _get_card_id_by_variant_tx(tx, params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        rec = tx.run(
            """
            MATCH (c:NewsCard)-[:HAS_VARIANT]->(v:NewsVariant {variant_id: $variant_id})
            RETURN c.card_id AS card_id
            """,
            **params,
        ).single()
        return dict(rec) if rec is not None else None

    @staticmethod
    def _get_variant_context_tx(tx, params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        rec = tx.run(
            """
            MATCH (c:NewsCard)-[:HAS_VARIANT]->(v:NewsVariant {variant_id: $variant_id})
            RETURN v.text AS text,
                   CASE WHEN v.mutation_depth IS NULL THEN 0 ELSE toInteger(v.mutation_depth) END AS mutation_depth,
                   c.symbols AS symbols
            """,
            **params,
        ).single()
        return dict(rec) if rec is not None else None

    @staticmethod
    def _list_inbox_tx(tx, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        result = tx.run(
            """
            MATCH (u:User {user_id: $player_id})-[:INBOX_ITEM]->(d:NewsDelivery)-[:DELIVERS_VARIANT]->(v:NewsVariant)
            RETURN d.delivery_id AS delivery_id,
                   d.card_id AS card_id,
                   d.variant_id AS variant_id,
                   d.from_actor_id AS from_actor_id,
                   d.visibility_level AS visibility_level,
                   d.delivery_reason AS delivery_reason,
                   d.delivered_at AS delivered_at,
                   v.text AS text
            ORDER BY d.delivered_at DESC
            LIMIT $limit
            """,
            **params,
        )
        return [dict(r) for r in result]
