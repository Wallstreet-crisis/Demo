from __future__ import annotations

import random
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
        self._driver = driver
        self._event_store = event_store
        self._news = news_service
        self._commonbot_emergency_runner = CommonBotEmergencyRunner(news=self._news, event_store=self._event_store)

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
        correlation_id: UUID | None = None,
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
            "phase": "INCUBATING",
            "t0_at": t0_at.isoformat(),
            "abort_probability": float(abort_probability),
        }
        major_card_id, card_event_json = self._news.create_card(
            kind=kind,
            image_anchor_id=None,
            image_uri=None,
            truth_payload=truth_payload,
            symbols=[],
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

    def tick(
        self,
        *,
        now: datetime | None = None,
        limit: int = 50,
    ) -> Dict[str, Any]:
        now = now or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)

        with self._driver.session() as session:
            chains = session.execute_read(
                self._list_due_chains_tx,
                {"now": now.isoformat(), "limit": int(limit)},
            )

        results: List[Dict[str, Any]] = []
        for c in chains:
            results.append(self._tick_one_chain(now=now, chain=dict(c)))

        return {"now": now.isoformat(), "chains": results}

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

        with self._driver.session() as session:
            ok = session.execute_write(
                self._add_suppression_tx,
                {
                    "chain_id": chain_id,
                    "spend": float(spend_influence),
                    "signal_class": signal_class,
                },
            )
        if not ok:
            raise ValueError("chain not found")

        payload = NewsPropagationSuppressedPayload(
            suppression_id=suppression_id,
            actor_id=actor_id,
            target_chain_id=chain_id,
            target_card_id=None,
            target_variant_id=None,
            spend_influence=float(spend_influence),
            scope=scope,
            suppressed_at=now,
        )
        env = EventEnvelope[NewsPropagationSuppressedPayload](
            event_type=EventType.NEWS_PROPAGATION_SUPPRESSED,
            correlation_id=correlation_id or uuid4(),
            actor=EventActor(user_id=actor_id),
            payload=payload,
        )
        event_json = EventEnvelopeJson.from_envelope(env)
        self._event_store.append(event_json)
        return event_json

    def _tick_one_chain(self, *, now: datetime, chain: Dict[str, Any]) -> Dict[str, Any]:
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

        rnd = random.Random(f"{chain_id}:{seed}")

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
            omen_card_id, omen_card_event = self._news.create_card(
                kind="OMEN",
                image_anchor_id=None,
                image_uri=None,
                truth_payload={
                    "chain_id": chain_id,
                    "signal_class": signal_class,
                    "signal_strength": int(rnd.randint(1, 3)),
                    "t_minus_seconds": int((t0_at - now).total_seconds()),
                },
                symbols=[],
                tags=["omen"],
                actor_id="system",
                correlation_id=None,
            )

            omen_text = rnd.choice(
                [
                    "外交关系降级。",
                    "预备役到位。",
                    "港口开始管制。",
                    "边境出现异常调动。",
                ]
            )
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
                    self._news.deliver_variant(
                        variant_id=omen_variant_id,
                        to_player_id=to_player_id,
                        from_actor_id="system",
                        visibility_level="NORMAL",
                        delivery_reason="SYSTEM_GRANT",
                        correlation_id=None,
                    )
                    delivered_to.append(to_player_id)

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

            final_text = "全面战争爆发。" if not aborted else "全面战争事件流产。"
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
            truth_payload = NewsTruthRevealedPayload(
                card_id=major_card_id,
                chain_id=chain_id,
                outcome=outcome,
                image_anchor_id=None,
                image_uri=None,
                truth_payload={"chain_id": chain_id, "outcome": outcome},
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
            if kind in {"MAJOR_EVENT", "EARNINGS", "DISCLOSURE"}:
                broadcasted, broadcast_event = self._news.broadcast_variant(
                    variant_id=final_variant_id,
                    channel="GLOBAL_MANDATORY",
                    visibility_level="NORMAL",
                    actor_id="system",
                    limit_users=5000,
                    correlation_id=None,
                )
                if broadcast_event is not None:
                    emergency_events = self._commonbot_emergency_runner.maybe_react(
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

    @staticmethod
    def _create_chain_tx(tx, params: Dict[str, Any]) -> None:
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
                ch.seed = $seed
            """,
            **params,
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
                   ch.seed AS seed
            ORDER BY ch.t0_at ASC
            LIMIT $limit
            """,
            **params,
        )
        return [dict(r) for r in result]

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
