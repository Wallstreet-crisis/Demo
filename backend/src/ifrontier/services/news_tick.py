from __future__ import annotations

import json
import random as py_random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from neo4j import Driver

from ifrontier.domain.events.envelope import EventActor, EventEnvelope, EventEnvelopeJson
from ifrontier.domain.events.payloads import (
    NewsChainAbortedPayload,
    NewsChainStartedPayload,
    NewsPropagationSuppressedPayload,
    NewsTruthRevealedPayload,
    NewsVariantEmittedPayload,
)
from ifrontier.domain.events.types import EventType
from ifrontier.infra.neo4j.event_store import Neo4jEventStore
from ifrontier.services.commonbot_emergency import CommonBotEmergencyRunner
from ifrontier.services.news import NewsService
from ifrontier.services.game_time import game_time_now, load_game_time_config_from_env


@dataclass(frozen=True)
class ChainConfig:
    kind: str
    t0_seconds: int
    omen_interval_seconds: int
    abort_probability: float
    grant_count: int
    seed: int


class NewsTickEngine:
    def __init__(
        self,
        driver: Driver,
        event_store: Neo4jEventStore,
        news_service: NewsService,
    ) -> None:
        from ifrontier.services.market_analytics import get_market_trends
        self._driver = driver
        self._event_store = event_store
        self._news = news_service
        self._commonbot_emergency_runner = CommonBotEmergencyRunner(
            news=self._news, 
            event_store=self._event_store,
            market_data_provider=get_market_trends
        )
        # 初始化为过去的某个时间，确保启动后立即触发首轮投放
        past = datetime.now(timezone.utc) - timedelta(hours=1)
        self._last_small_news_at: datetime | None = past
        self._last_chain_at: datetime | None = past

        self._ensure_news_chain_extra_truth_schema()

    def _ensure_news_chain_extra_truth_schema(self) -> None:
        with self._driver.session() as session:
            session.execute_write(self._ensure_news_chain_extra_truth_schema_tx, {})

    @staticmethod
    def _ensure_news_chain_extra_truth_schema_tx(tx, params: Dict[str, Any]) -> None:
        tx.run(
            """
            CREATE (t:__SchemaWarmup {extra_truth_json: '{}'})
            WITH t
            DELETE t
            """
        )
        tx.run(
            """
            MATCH (ch:NewsChain)
            WHERE ch.extra_truth_json IS NULL
            SET ch.extra_truth_json = '{}'
            """
        )

    def suppress_propagation(
        self,
        *,
        actor_id: str,
        chain_id: str,
        spend_influence: float,
        signal_class: str | None = None,
        scope: str = "chain",
        correlation_id: UUID | None = None,
    ) -> EventEnvelopeJson:
        if spend_influence <= 0:
            raise ValueError("spend_influence must be > 0")

        now = datetime.now(timezone.utc)
        suppression_id = str(uuid4())
        sc = str(signal_class or "ANY")

        with self._driver.session() as session:
            ok = session.execute_write(
                self._add_suppression_tx,
                {
                    "chain_id": str(chain_id),
                    "spend": float(spend_influence),
                    "signal_class": sc,
                },
            )
        if not ok:
            raise ValueError("chain not found")

        payload = NewsPropagationSuppressedPayload(
            suppression_id=suppression_id,
            actor_id=str(actor_id),
            target_chain_id=str(chain_id),
            target_card_id=None,
            target_variant_id=None,
            spend_influence=float(spend_influence),
            scope=str(scope or "chain"),
            suppressed_at=now,
        )
        env = EventEnvelope[NewsPropagationSuppressedPayload](
            event_type=EventType.NEWS_PROPAGATION_SUPPRESSED,
            correlation_id=correlation_id or uuid4(),
            actor=EventActor(user_id=str(actor_id)),
            payload=payload,
        )
        event_json = EventEnvelopeJson.from_envelope(env)
        self._event_store.append(event_json)
        return event_json

    def start_chain(
        self,
        *,
        kind: str,
        actor_id: str,
        t0_seconds: int,
        t0_at: datetime | None = None,
        omen_interval_seconds: int,
        abort_probability: float,
        grant_count: int,
        seed: int,
        symbols: List[str] | None = None,
        correlation_id: UUID | None = None,
        extra_truth: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        if t0_seconds <= 0:
            raise ValueError("t0_seconds must be > 0")
        if omen_interval_seconds <= 0:
            raise ValueError("omen_interval_seconds must be > 0")
        if abort_probability < 0.0 or abort_probability > 1.0:
            raise ValueError("abort_probability must be in [0, 1]")
        if grant_count < 0:
            raise ValueError("grant_count must be >= 0")

        cfg = load_game_time_config_from_env()
        now = game_time_now(cfg=cfg, real_now_utc=None).real_now_utc
        chain_id = str(uuid4())
        min_t0_at = now + timedelta(seconds=int(t0_seconds))
        if t0_at is None:
            t0_at = min_t0_at
        else:
            if t0_at.tzinfo is None:
                t0_at = t0_at.replace(tzinfo=timezone.utc)
            t0_at = t0_at.astimezone(timezone.utc)
            if t0_at < min_t0_at:
                raise ValueError("t0_at must be >= now + t0_seconds")
        next_omen_at = now

        truth_payload = {
            "chain_id": chain_id,
            "kind": kind,
            "system_spawn": True, # 标识为系统生成的权威事件
            "phase": "INCUBATING",
            "t0_at": t0_at.isoformat(),
            "abort_probability": float(abort_probability),
            "symbols": symbols or [],
        }
        if extra_truth:
            truth_payload.update(extra_truth)

        major_card_id, card_event_json = self._news.create_card(
            kind=kind,
            image_anchor_id=None,
            image_uri=None,
            truth_payload=truth_payload,
            symbols=symbols or [],
            tags=["chain"],
            actor_id=actor_id,
            correlation_id=correlation_id,
        )

        with self._driver.session() as session:
            session.execute_write(
                self._create_chain_tx,
                {
                    "chain_id": chain_id,
                    "major_card_id": major_card_id,
                    "kind": kind,
                    "phase": "INCUBATING",
                    "created_at": now.isoformat(),
                    "t0_at": t0_at.isoformat(),
                    "next_omen_at": next_omen_at.isoformat(),
                    "omen_interval_seconds": int(omen_interval_seconds),
                    "abort_probability": float(abort_probability),
                    "grant_count": int(grant_count),
                    "seed": int(seed),
                    "symbols": symbols or [],
                },
            )

        corr = correlation_id or uuid4()
        chain_payload = NewsChainStartedPayload(
            chain_id=chain_id,
            major_card_id=major_card_id,
            kind=kind,
            t0_at=t0_at,
            started_at=now,
        )
        chain_envelope = EventEnvelope[NewsChainStartedPayload](
            event_type=EventType.NEWS_CHAIN_STARTED,
            correlation_id=corr,
            actor=EventActor(user_id=actor_id),
            payload=chain_payload,
        )
        chain_event_json = EventEnvelopeJson.from_envelope(chain_envelope)
        self._event_store.append(chain_event_json)

        return {
            "chain_id": chain_id,
            "major_card_id": major_card_id,
            "card_created_event": card_event_json,
            "chain_started_event": chain_event_json,
            "t0_at": t0_at,
        }

    async def tick(
        self,
        *,
        now: datetime | None = None,
        limit: int = 50,
    ) -> Dict[str, Any]:
        if now is None:
            now = datetime.now(timezone.utc)

        # 0) 定期生成新的系统新闻
        spawn_events = await self._periodic_spawn(now=now)

        chains = self._list_active_chains(now=now, limit=limit)

        results: List[Dict[str, Any]] = []
        for c in chains:
            results.append(await self._tick_one_chain(now=now, chain=dict(c)))

        return {
            "now": now.isoformat(), 
            "chains": results,
            "spawned_events": spawn_events
        }

    async def _periodic_spawn(self, *, now: datetime) -> List[Dict[str, Any]]:
        """系统自动投放逻辑：每隔一段时间尝试生成一条新闻"""
        spawned_events: List[Dict[str, Any]] = []
        
        # 1) 小新闻投放 (每 60s 触发)
        if self._last_small_news_at is None or (now - self._last_small_news_at).total_seconds() >= 60:
            self._last_small_news_at = now
            kind = py_random.choice(["RUMOR", "LEAK", "ANALYST_REPORT"])
            from ifrontier.infra.sqlite.securities import list_securities
            secs = [s.symbol for s in list_securities(status="TRADABLE")]
            if secs:
                target_symbol = py_random.choice(secs)
                text = self._news.get_preset_template(kind=kind, symbols=[target_symbol])
                
                # 随机生成一个利好或利空倾向
                impact_direction = py_random.choice(["UP", "DOWN", "STABLE"])
                
                # 增加 kind 信息，方便机器人识别新闻类型
                truth_payload = {
                    "system_spawn": True, 
                    "direction": impact_direction,
                    "kind": kind
                }
                
                card_id, card_ev = self._news.create_card(
                    kind=kind,
                    image_anchor_id=None,
                    image_uri=None,
                    truth_payload=truth_payload,
                    symbols=[target_symbol],
                    tags=["system_spawn"],
                    actor_id="system"
                )
                variant_id, var_ev = self._news.emit_variant(
                    card_id=card_id,
                    author_id="system",
                    text=text
                )
                spawned_events.append(card_ev.model_dump(mode="json"))
                spawned_events.append(var_ev.model_dump(mode="json"))
                
                users = self._news.list_users(limit=5000)
                if users:
                    # 随机挑选 1-5 个幸运玩家投递
                    lucky_ones = py_random.sample(users, min(len(users), py_random.randint(1, 5)))
                    for uid in lucky_ones:
                        _deliv_id, deliv_ev = self._news.deliver_variant(
                            variant_id=variant_id,
                            to_player_id=str(uid),
                            from_actor_id="system",
                            visibility_level="NORMAL",
                            delivery_reason="SYSTEM_SPAWN"
                        )
                        spawned_events.append(deliv_ev.model_dump(mode="json"))
                        
                        # 立即触发机器人对该投递的反应
                        emergency_events = await self._commonbot_emergency_runner.react_to_delivery(delivery_event=deliv_ev)
                        for eev in emergency_events:
                            spawned_events.append(eev.model_dump(mode="json"))
                            
                    print(f"[NewsTick:Spawn] Spawned {kind} for {target_symbol} to {len(lucky_ones)} users. Bias: {impact_direction}")

        # 2) 重大事件链投放 (每 600s 触发)
        if self._last_chain_at is None or (now - self._last_chain_at).total_seconds() >= 600:
            self._last_chain_at = now
            kind = py_random.choice(["MAJOR_EVENT", "WORLD_EVENT"])
            from ifrontier.infra.sqlite.securities import list_securities
            from ifrontier.domain.assets.profile import get_profile
            
            all_secs = list_securities(status="TRADABLE")
            if all_secs:
                # 核心联动逻辑：
                # 1. WAR (战争) -> MILITARY/ENERGY (UP), FINANCE/CONSUMER/LOGISTICS (DOWN)
                # 2. TECH_BREAKTHROUGH (技术突破) -> TECH/HEALTHCARE (UP), ENERGY (UP)
                # 3. FINANCIAL_CRISIS (金融危机) -> FINANCE (DOWN), CONSUMER/TECH (DOWN), MILITARY (STABLE)
                # 4. ENERGY_SHORTAGE (能源荒) -> ENERGY (UP), LOGISTICS/TECH (DOWN), CONSUMER (DOWN)
                # 5. BIO_HAZARD (生化危机) -> HEALTHCARE (UP), CONSUMER/LOGISTICS (DOWN), TECH (STABLE)
                
                theme = py_random.choice(["WAR", "TECH_BREAKTHROUGH", "FINANCIAL_CRISIS", "ENERGY_SHORTAGE", "BIO_HAZARD"])
                target_symbols = []
                impact_map = {} # symbol -> direction
                
                if theme == "WAR":
                    for s in all_secs:
                        prof = get_profile(s.symbol)
                        if prof:
                            if prof.sector in ["MILITARY", "ENERGY"]:
                                impact_map[s.symbol] = "UP"
                                target_symbols.append(s.symbol)
                            elif prof.sector in ["FINANCE", "CONSUMER", "LOGISTICS"]:
                                impact_map[s.symbol] = "DOWN"
                                target_symbols.append(s.symbol)
                elif theme == "TECH_BREAKTHROUGH":
                    for s in all_secs:
                        prof = get_profile(s.symbol)
                        if prof:
                            if prof.sector in ["TECH", "HEALTHCARE", "ENERGY"]:
                                impact_map[s.symbol] = "UP"
                                target_symbols.append(s.symbol)
                elif theme == "FINANCIAL_CRISIS":
                    for s in all_secs:
                        prof = get_profile(s.symbol)
                        if prof:
                            if prof.sector == "FINANCE":
                                impact_map[s.symbol] = "DOWN"
                                target_symbols.append(s.symbol)
                            elif prof.sector in ["CONSUMER", "TECH"]:
                                impact_map[s.symbol] = "DOWN"
                                target_symbols.append(s.symbol)
                elif theme == "ENERGY_SHORTAGE":
                    for s in all_secs:
                        prof = get_profile(s.symbol)
                        if prof:
                            if prof.sector == "ENERGY":
                                impact_map[s.symbol] = "UP"
                                target_symbols.append(s.symbol)
                            elif prof.sector in ["LOGISTICS", "TECH", "CONSUMER"]:
                                impact_map[s.symbol] = "DOWN"
                                target_symbols.append(s.symbol)
                elif theme == "BIO_HAZARD":
                    for s in all_secs:
                        prof = get_profile(s.symbol)
                        if prof:
                            if prof.sector == "HEALTHCARE":
                                impact_map[s.symbol] = "UP"
                                target_symbols.append(s.symbol)
                            elif prof.sector in ["CONSUMER", "LOGISTICS"]:
                                impact_map[s.symbol] = "DOWN"
                                target_symbols.append(s.symbol)
                
                if not target_symbols:
                    target_symbols = [py_random.choice(all_secs).symbol]
                    impact_map[target_symbols[0]] = py_random.choice(["UP", "DOWN"])

                # 限制参与标的数量，避免刷屏，但增加到 6 个以体现连锁反应
                target_symbols = py_random.sample(target_symbols, min(len(target_symbols), 6))
                final_impact_map = {s: impact_map[s] for s in target_symbols}

                print(f"[NewsTick:Spawn] Starting system chain: {kind} ({theme}) for {target_symbols}")
                res = self.start_chain(
                    kind=kind,
                    actor_id="system",
                    t0_seconds=py_random.randint(60, 300), # 1-5 分钟后爆发
                    omen_interval_seconds=py_random.randint(20, 45),
                    abort_probability=0.15,
                    grant_count=py_random.randint(3, 8),
                    seed=py_random.randint(1, 1000000),
                    symbols=target_symbols,
                    extra_truth={"theme": theme, "impact_map": final_impact_map}
                )
                spawned_events.append(res["card_created_event"].model_dump(mode="json"))
                spawned_events.append(res["chain_started_event"].model_dump(mode="json"))

        return spawned_events

    async def _tick_one_chain(self, *, now: datetime, chain: Dict[str, Any]) -> Dict[str, Any]:
        chain_id = str(chain["chain_id"])
        major_card_id = str(chain["major_card_id"])
        kind = str(chain["kind"])
        phase = str(chain["phase"])
        t0_at = datetime.fromisoformat(str(chain["t0_at"]))
        next_omen_at = datetime.fromisoformat(str(chain["next_omen_at"]))
        omen_interval_seconds = int(chain["omen_interval_seconds"])
        abort_probability = float(chain["abort_probability"])
        grant_count = int(chain["grant_count"])
        seed = int(chain["seed"])
        symbols = chain.get("symbols") or []

        rnd = py_random.Random(f"{chain_id}:{seed}")

        out: Dict[str, Any] = {"chain_id": chain_id, "actions": []}

        if phase != "INCUBATING":
            return out

        # 1) Emit omen(s) up to now, but do not advance beyond T0
        if now >= next_omen_at and now < t0_at:
            signal_class = rnd.choice(["DIPLOMACY", "MOBILIZATION", "LOGISTICS"])
            suppressed, suppression_left = self._consume_suppression_budget(
                chain_id=chain_id,
                signal_class=signal_class,
                requested=int(grant_count),
            )
            effective_grant_count = max(0, int(grant_count) - int(suppressed))
            
            # 从链的真相中提取针对各标的的冲击方向，传递给预兆
            # 这允许内幕机器人通过预兆提前布局
            chain_impact_map = chain.get("impact_map") or {}
            
            # 增强 OMEN 真真负载，标识为系统生成的预兆
            omen_truth = {
                "chain_id": chain_id,
                "kind": "OMEN",
                "system_spawn": True,
                "signal_class": signal_class,
                "signal_strength": int(rnd.randint(1, 3)),
                "t_minus_seconds": int((t0_at - now).total_seconds()), # 后台可见，文本不可见
            }
            if chain_impact_map:
                omen_truth["impact_map"] = chain_impact_map

            omen_card_id, omen_card_event = self._news.create_card(
                kind="OMEN",
                image_anchor_id=None,
                image_uri=None,
                truth_payload=omen_truth,
                symbols=symbols,
                tags=["omen"],
                actor_id="system",
                correlation_id=None,
            )

            omen_text = self._news.get_preset_template(kind="OMEN", symbols=symbols)
            omen_variant_id, omen_variant_event = self._news.emit_variant(
                card_id=omen_card_id,
                author_id="system",
                text=omen_text,
                parent_variant_id=None,
                influence_cost=0.0,
                risk_roll=None,
                correlation_id=None,
            )

            delivered_to: List[str] = []
            if effective_grant_count > 0:
                users = self._news.list_users(limit=5000)
                rnd.shuffle(users)
                for u in users[: min(effective_grant_count, len(users))]:
                    to_player_id = str(u)
                    _deliv_id, deliv_ev = self._news.deliver_variant(
                        variant_id=omen_variant_id,
                        to_player_id=to_player_id,
                        from_actor_id="system",
                        visibility_level="NORMAL",
                        delivery_reason="SYSTEM_GRANT",
                        correlation_id=None,
                    )
                    delivered_to.append(to_player_id)
                    
                    # 立即触发机器人对该投递的反应（如果是机器人）
                    await self._commonbot_emergency_runner.react_to_delivery(delivery_event=deliv_ev)

            next_omen_at2 = now + timedelta(seconds=omen_interval_seconds)
            with self._driver.session() as session:
                session.execute_write(
                    self._update_next_omen_tx,
                    {"chain_id": chain_id, "next_omen_at": next_omen_at2.isoformat()},
                )

            out["actions"].append(
                {
                    "type": "omen_emitted",
                    "omen_card_id": omen_card_id,
                    "omen_variant_id": omen_variant_id,
                    "delivered_to": delivered_to,
                    "suppressed": int(suppressed),
                    "suppression_left": float(suppression_left),
                    "events": [
                        omen_card_event.model_dump(mode="json"),
                        omen_variant_event.model_dump(mode="json"),
                    ],
                }
            )

        # 2) Resolve at T0
        if now >= t0_at:
            aborted = rnd.random() < abort_probability
            outcome = "ABORTED" if aborted else "RESOLVED"

            if not aborted:
                final_text = self._news.get_preset_template(kind=kind, symbols=symbols)
            else:
                final_text = f"计划中的 {kind} 事件由于未知干扰已流产。"

            final_variant_id, final_variant_event = self._news.emit_variant(
                card_id=major_card_id,
                author_id="system",
                text=final_text,
                parent_variant_id=None,
                influence_cost=0.0,
                risk_roll={"abort_probability": abort_probability, "aborted": aborted},
                correlation_id=None,
            )

            # 更新链状态
            with self._driver.session() as session:
                session.execute_write(
                    self._resolve_chain_tx,
                    {
                        "chain_id": chain_id,
                        "phase": outcome,
                        "resolved_at": now.isoformat(),
                    },
                )

            # 记录 truth_revealed 与 chain_aborted 事件
            final_truth = {
                "chain_id": chain_id, 
                "kind": kind,
                "system_spawn": True,
                "outcome": outcome
            }
            if chain.get("theme"):
                final_truth["theme"] = chain["theme"]
            if chain.get("impact_map"):
                final_truth["impact_map"] = chain["impact_map"]

            truth_payload = NewsTruthRevealedPayload(
                card_id=major_card_id,
                chain_id=chain_id,
                outcome=outcome,
                image_anchor_id=None,
                image_uri=None,
                truth_payload=final_truth,
                revealed_at=now,
            )
            truth_env = EventEnvelope[NewsTruthRevealedPayload](
                event_type=EventType.NEWS_TRUTH_REVEALED,
                correlation_id=uuid4(),
                actor=EventActor(user_id="system"),
                payload=truth_payload,
            )
            truth_event_json = EventEnvelopeJson.from_envelope(truth_env)
            self._event_store.append(truth_event_json)

            aborted_event_json: EventEnvelopeJson | None = None
            if aborted:
                aborted_payload = NewsChainAbortedPayload(
                    chain_id=chain_id,
                    major_card_id=major_card_id,
                    abort_reason="probabilistic_abort",
                    aborted_at=now,
                )
                aborted_env = EventEnvelope[NewsChainAbortedPayload](
                    event_type=EventType.NEWS_CHAIN_ABORTED,
                    correlation_id=uuid4(),
                    actor=EventActor(user_id="system"),
                    payload=aborted_payload,
                )
                aborted_event_json = EventEnvelopeJson.from_envelope(aborted_env)
                self._event_store.append(aborted_event_json)

            broadcasted = 0
            broadcast_event: EventEnvelopeJson | None = None
            emergency_events: List[EventEnvelopeJson] = []
            # v0：重大事件在 T0 强制全局广播（内容一致）
            if kind in {"MAJOR_EVENT", "EARNINGS", "DISCLOSURE", "WORLD_EVENT"}:
                broadcasted, broadcast_event = self._news.broadcast_variant(
                    variant_id=final_variant_id,
                    channel="GLOBAL_MANDATORY",
                    visibility_level="NORMAL",
                    actor_id="system",
                    limit_users=5000,
                    correlation_id=None,
                )
                if broadcast_event is not None:
                    emergency_events = await self._commonbot_emergency_runner.maybe_react(
                        broadcast_event=broadcast_event,
                        force=True,
                    )

            out["actions"].append(
                {
                    "type": "resolved",
                    "outcome": outcome,
                    "final_variant_id": final_variant_id,
                    "broadcasted": broadcasted,
                    "events": [
                        final_variant_event.model_dump(mode="json"),
                        truth_event_json.model_dump(mode="json"),
                        aborted_event_json.model_dump(mode="json") if aborted_event_json else None,
                        broadcast_event.model_dump(mode="json") if broadcast_event else None,
                    ],
                    "emergency_events": [e.model_dump(mode="json") for e in emergency_events],
                }
            )

        return out

    def _list_active_chains(self, *, now: datetime, limit: int = 50) -> List[Dict[str, Any]]:
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        now = now.astimezone(timezone.utc)

        with self._driver.session() as session:
            return session.execute_read(
                self._list_due_chains_tx,
                {
                    "now": now.isoformat(),
                    "limit": int(limit),
                },
            )

    @staticmethod
    def _create_chain_tx(tx, params: Dict[str, Any]) -> None:
        # 允许存储额外的真相数据（如 impact_map）
        import json
        extra_json = json.dumps(params.get("extra_truth") or {}, ensure_ascii=False)
        tx.run(
            """
            MERGE (ch:NewsChain {chain_id: $chain_id})
            SET ch.major_card_id = $major_card_id,
                ch.kind = $kind,
                ch.phase = $phase,
                ch.created_at = $created_at,
                ch.t0_at = $t0_at,
                ch.next_omen_at = $next_omen_at,
                ch.omen_interval_seconds = $omen_interval_seconds,
                ch.abort_probability = $abort_probability,
                ch.grant_count = $grant_count,
                ch.seed = $seed,
                ch.symbols = $symbols,
                ch.extra_truth_json = $extra_json
            """,
            **{**params, "extra_json": extra_json},
        )

    def _consume_suppression_budget(self, *, chain_id: str, signal_class: str, requested: int) -> tuple[int, float]:
        if requested <= 0:
            return 0, 0.0

        with self._driver.session() as session:
            rec = session.execute_write(
                self._consume_suppression_tx,
                {
                    "chain_id": chain_id,
                    "signal_class": signal_class,
                    "requested": int(requested),
                },
            )

        if rec is None:
            return 0, 0.0
        return int(rec.get("suppressed") or 0), float(rec.get("suppression_left") or 0.0)

    @staticmethod
    def _add_suppression_tx(tx, params: Dict[str, Any]) -> bool:
        rec = tx.run(
            """
            MATCH (ch:NewsChain {chain_id: $chain_id})
            WITH ch,
                 CASE WHEN ch.suppression_budget_grants IS NULL THEN 0 ELSE toInteger(ch.suppression_budget_grants) END AS grants,
                 CASE WHEN ch.suppression_budget_total IS NULL THEN 0.0 ELSE toFloat(ch.suppression_budget_total) END AS total,
                 toInteger(toFloat($spend)) AS spend_grants
            SET ch.suppression_budget_grants = grants + spend_grants,
                ch.suppression_budget_total = total + toFloat($spend)
            RETURN true AS ok
            """,
            **params,
        ).single()
        return bool(rec and rec.get("ok"))

    @staticmethod
    def _consume_suppression_tx(tx, params: Dict[str, Any]) -> Dict[str, Any] | None:
        # v0：只消费 suppression_budget_grants（不区分 signal_class），避免引入 APOC 依赖。
        rec = tx.run(
            """
            MATCH (ch:NewsChain {chain_id: $chain_id})
            WITH ch,
                 CASE WHEN ch.suppression_budget_grants IS NULL THEN 0 ELSE toInteger(ch.suppression_budget_grants) END AS grants,
                 toInteger($requested) AS requested
            WITH ch, grants,
                 CASE WHEN grants <= 0 THEN 0 ELSE
                   CASE WHEN grants >= requested THEN requested ELSE grants END
                 END AS suppressed
            SET ch.suppression_budget_grants = grants - suppressed
            RETURN suppressed AS suppressed, toFloat(ch.suppression_budget_grants) AS suppression_left
            """,
            **params,
        ).single()
        return dict(rec) if rec is not None else None

    @staticmethod
    def _list_due_chains_tx(tx, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        result = tx.run(
            """
            MATCH (ch:NewsChain {phase: 'INCUBATING'})
            WHERE ch.next_omen_at <= $now OR ch.t0_at <= $now
            RETURN ch.chain_id AS chain_id,
                   ch.major_card_id AS major_card_id,
                   ch.kind AS kind,
                   ch.phase AS phase,
                   ch.t0_at AS t0_at,
                   ch.next_omen_at AS next_omen_at,
                   ch.omen_interval_seconds AS omen_interval_seconds,
                   ch.abort_probability AS abort_probability,
                   ch.grant_count AS grant_count,
                   ch.seed AS seed,
                   ch.symbols AS symbols,
                   coalesce(ch.extra_truth_json, '{}') AS extra_truth_json
            ORDER BY ch.t0_at ASC
            LIMIT $limit
            """,
            **params,
        )
        out = []
        for r in result:
            d = dict(r)
            if d.get("extra_truth_json") and d["extra_truth_json"] != '{}':
                try:
                    extra = json.loads(d["extra_truth_json"])
                    d.update(extra)
                except Exception:
                    pass
            out.append(d)
        return out

    @staticmethod
    def _update_next_omen_tx(tx, params: Dict[str, Any]) -> None:
        tx.run(
            """
            MATCH (ch:NewsChain {chain_id: $chain_id})
            SET ch.next_omen_at = $next_omen_at
            """,
            **params,
        )

    @staticmethod
    def _resolve_chain_tx(tx, params: Dict[str, Any]) -> None:
        tx.run(
            """
            MATCH (ch:NewsChain {chain_id: $chain_id})
            SET ch.phase = $phase,
                ch.resolved_at = $resolved_at
            """,
            **params,
        )
