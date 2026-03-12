from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from ifrontier.infra.sqlite.db import get_connection


@dataclass
class NewsRecord:
    card_id: str
    variant_id: Optional[str]
    kind: str
    text: Optional[str]
    symbols: List[str]
    tags: List[str]
    publisher_id: Optional[str]
    published_at: Optional[str]
    is_suppressed: bool
    suppression_reason: Optional[str]
    truth_payload: Dict[str, Any]
    image_uri: Optional[str]
    preset_id: Optional[str]

    @staticmethod
    def from_row(row: Any) -> NewsRecord:
        symbols = []
        tags = {}
        truth_payload = {}
        
        if row["symbols_json"]:
            try:
                symbols = json.loads(row["symbols_json"])
            except (json.JSONDecodeError, TypeError):
                pass

        if row["tags_json"]:
            try:
                tags = json.loads(row["tags_json"])
            except (json.JSONDecodeError, TypeError):
                pass
                
        if row["truth_payload_json"]:
            try:
                truth_payload = json.loads(row["truth_payload_json"])
            except (json.JSONDecodeError, TypeError):
                pass

        return NewsRecord(
            card_id=row["card_id"],
            variant_id=row["variant_id"],
            kind=row["kind"],
            text=row["text"],
            symbols=symbols,
            tags=tags,
            publisher_id=row["publisher_id"],
            published_at=row["published_at"],
            is_suppressed=bool(row["is_suppressed"]),
            suppression_reason=row["suppression_reason"],
            truth_payload=truth_payload,
            image_uri=row["image_uri"],
            preset_id=row["preset_id"],
        )


def init_news_schema() -> None:
    conn = get_connection()
    cur = conn.cursor()

    cur.executescript(
        """
        CREATE TABLE IF NOT EXISTS news (
            card_id TEXT NOT NULL,
            variant_id TEXT,
            kind TEXT NOT NULL,
            text TEXT,
            symbols_json TEXT,
            tags_json TEXT,
            publisher_id TEXT,
            published_at TEXT,
            is_suppressed INTEGER NOT NULL DEFAULT 0,
            suppression_reason TEXT,
            truth_payload_json TEXT,
            image_uri TEXT,
            image_anchor_id TEXT,
            preset_id TEXT,
            created_at TEXT NOT NULL,
            
            author_id TEXT,
            parent_variant_id TEXT,
            mutation_depth INTEGER DEFAULT 0,
            influence_cost REAL DEFAULT 0.0,
            risk_roll_json TEXT,
            
            PRIMARY KEY (card_id, variant_id)
        );

        CREATE INDEX IF NOT EXISTS idx_news_published_at ON news(published_at DESC);
        CREATE INDEX IF NOT EXISTS idx_news_symbols ON news(symbols_json);
        CREATE INDEX IF NOT EXISTS idx_news_tags ON news(tags_json);
        CREATE INDEX IF NOT EXISTS idx_news_kind ON news(kind);
        """
    )
    conn.commit()


def save_news(
    card_id: str,
    kind: str,
    publisher_id: Optional[str] = None,
    variant_id: Optional[str] = None,
    text: Optional[str] = None,
    symbols: Optional[List[str]] = None,
    tags: Optional[List[str]] = None,
    truth_payload: Optional[Dict[str, Any]] = None,
    image_uri: Optional[str] = None,
    image_anchor_id: Optional[str] = None,
    preset_id: Optional[str] = None,
    published_at: Optional[str] = None,
    author_id: Optional[str] = None,
    parent_variant_id: Optional[str] = None,
    mutation_depth: int = 0,
    influence_cost: float = 0.0,
    risk_roll: Optional[Dict[str, Any]] = None,
) -> None:
    conn = get_connection()
    now = datetime.now(timezone.utc).isoformat()
    
    # Determine published_at
    pub_at = published_at
    if pub_at is None and variant_id is not None:
        # If emitting a variant, usually it's "published" immediately or later
        # But if we are creating a card, it might not be published yet.
        # We can default to now if not provided, or let caller decide.
        # For safety, let's allow None (draft) but if we are calling "save_news" for a variant, we probably want to set it.
        # Let's check the signature of emit_variant: it has no published_at param in the neo4j version I saw.
        # However, the prompt asks for "published_at" field.
        # I will allow None for draft cards.
        pass

    with conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO news (
                card_id, variant_id, kind, text, symbols_json, tags_json, 
                publisher_id, published_at, is_suppressed, suppression_reason,
                truth_payload_json, image_uri, image_anchor_id, preset_id, created_at,
                author_id, parent_variant_id, mutation_depth, influence_cost, risk_roll_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                card_id,
                variant_id,
                kind,
                text,
                json.dumps(symbols or [], ensure_ascii=False),
                json.dumps(tags or [], ensure_ascii=False),
                publisher_id,
                pub_at,
                0,
                None,
                json.dumps(truth_payload or {}, ensure_ascii=False),
                image_uri,
                image_anchor_id,
                preset_id,
                now,
                author_id,
                parent_variant_id,
                mutation_depth,
                influence_cost,
                json.dumps(risk_roll or {}, ensure_ascii=False),
            ),
        )


def suppress_news(card_id: str, reason: str) -> None:
    conn = get_connection()
    with conn:
        conn.execute(
            "UPDATE news SET is_suppressed = 1, suppression_reason = ? WHERE card_id = ?",
            (reason, card_id),
        )


def get_news(card_id: str, variant_id: Optional[str] = None) -> Optional[NewsRecord]:
    conn = get_connection()
    if variant_id:
        row = conn.execute(
            "SELECT * FROM news WHERE card_id = ? AND variant_id = ?", (card_id, variant_id)
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT * FROM news WHERE card_id = ?", (card_id,)
        ).fetchone()

    if row is None:
        return None
    return NewsRecord.from_row(row)


def get_variant(variant_id: str) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM news WHERE variant_id = ?", (variant_id,)
    ).fetchone()
    if row is None:
        return None
    return dict(row)


def list_news(limit: int = 50, offset: int = 0) -> List[NewsRecord]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM news ORDER BY published_at DESC LIMIT ? OFFSET ?",
        (limit, offset),
    ).fetchall()
    return [NewsRecord.from_row(r) for r in rows]


def list_news_by_symbol(symbol: str, limit: int = 50) -> List[NewsRecord]:
    # Simple JSON search: contains the symbol
    conn = get_connection()
    pattern = f'%"{symbol}"%'
    rows = conn.execute(
        "SELECT * FROM news WHERE symbols_json LIKE ? ORDER BY published_at DESC LIMIT ?",
        (pattern, limit),
    ).fetchall()
    return [NewsRecord.from_row(r) for r in rows]


def list_news_by_tag(tag: str, limit: int = 50) -> List[NewsRecord]:
    conn = get_connection()
    pattern = f'%"{tag}"%'
    rows = conn.execute(
        "SELECT * FROM news WHERE tags_json LIKE ? ORDER BY published_at DESC LIMIT ?",
        (pattern, limit),
    ).fetchall()
    return [NewsRecord.from_row(r) for r in rows]


def list_user_inbox(user_id: str, limit: int = 50) -> List[NewsRecord]:
    # This is different from "list_news". 
    # In the Neo4j version, "inbox" is a relationship `(:User)-[:INBOX_ITEM]->(:Delivery)`.
    # We don't have a delivery table here yet. 
    # The prompt didn't explicitly ask for "inbox" implementation in the new file, but "list_news" etc.
    # However, `NewsService.list_inbox` exists.
    # Let's assume for now we just implement the "news" storage.
    # If I need to implement inbox, I'd need a "deliveries" table.
    # The user asked for "functions like ... list_news, list_news_by_symbol, ...".
    # I will skip inbox for now unless I see it's strictly required.
    return []


def get_card_owner(card_id: str) -> Optional[str]:
    # In Neo4j: MATCH (u:User)-[:OWNS_NEWS]->(c:NewsCard {card_id: ...}) RETURN u.user_id
    conn = get_connection()
    row = conn.execute(
        "SELECT user_id FROM news_ownership WHERE card_id = ?", (card_id,)
    ).fetchone()
    return row["user_id"] if row else None


def init_news_relationships_schema() -> None:
    conn = get_connection()
    cur = conn.cursor()

    cur.executescript(
        """
        CREATE TABLE IF NOT EXISTS news_users (
            user_id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS news_follows (
            follower_id TEXT NOT NULL,
            followee_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (follower_id, followee_id)
        );

        CREATE TABLE IF NOT EXISTS news_ownership (
            card_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            granted_at TEXT NOT NULL,
            granter_id TEXT NOT NULL,
            PRIMARY KEY (card_id, user_id)
        );

        CREATE TABLE IF NOT EXISTS news_deliveries (
            delivery_id TEXT PRIMARY KEY,
            variant_id TEXT NOT NULL,
            to_player_id TEXT NOT NULL,
            from_actor_id TEXT NOT NULL,
            visibility_level TEXT NOT NULL,
            delivery_reason TEXT NOT NULL,
            delivered_at TEXT NOT NULL,
            is_read INTEGER NOT NULL DEFAULT 0
        );

        CREATE INDEX IF NOT EXISTS idx_follows_follower ON news_follows(follower_id);
        CREATE INDEX IF NOT EXISTS idx_follows_followee ON news_follows(followee_id);
        CREATE INDEX IF NOT EXISTS idx_deliveries_recipient ON news_deliveries(to_player_id);
        CREATE INDEX IF NOT EXISTS idx_deliveries_variant ON news_deliveries(variant_id);
        """
    )
    conn.commit()


def create_user(user_id: str) -> None:
    conn = get_connection()
    now = datetime.now(timezone.utc).isoformat()
    with conn:
        conn.execute(
            "INSERT OR IGNORE INTO news_users (user_id, created_at) VALUES (?, ?)",
            (user_id, now),
        )


def follow(follower_id: str, followee_id: str) -> None:
    # Ensure users exist
    create_user(follower_id)
    create_user(followee_id)

    conn = get_connection()
    now = datetime.now(timezone.utc).isoformat()
    with conn:
        conn.execute(
            "INSERT OR REPLACE INTO news_follows (follower_id, followee_id, created_at) VALUES (?, ?, ?)",
            (follower_id, followee_id, now),
        )


def list_followers(followee_id: str, limit: int = 100) -> List[str]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT follower_id FROM news_follows WHERE followee_id = ? LIMIT ?",
        (followee_id, limit),
    ).fetchall()
    return [r["follower_id"] for r in rows]


def list_following(follower_id: str, limit: int = 100) -> List[str]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT followee_id FROM news_follows WHERE follower_id = ? LIMIT ?",
        (follower_id, limit),
    ).fetchall()
    return [r["followee_id"] for r in rows]


def grant_ownership(card_id: str, user_id: str, granter_id: str) -> None:
    conn = get_connection()
    now = datetime.now(timezone.utc).isoformat()
    with conn:
        conn.execute(
            "INSERT OR REPLACE INTO news_ownership (card_id, user_id, granted_at, granter_id) VALUES (?, ?, ?, ?)",
            (card_id, user_id, now, granter_id),
        )


def transfer_ownership(card_id: str, from_user_id: str, to_user_id: str, transferred_by: str) -> None:
    # In Neo4j: MATCH (u:User {user_id: from})-[:OWNS_NEWS]->(c:NewsCard {card_id: card_id}) DETACH DELETE r ...
    # But here we just update.
    conn = get_connection()
    now = datetime.now(timezone.utc).isoformat()
    with conn:
        conn.execute(
            "UPDATE news_ownership SET user_id = ?, granted_at = ?, granter_id = ? WHERE card_id = ? AND user_id = ?",
            (to_user_id, now, transferred_by, card_id, from_user_id),
        )


def list_owned_cards(user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
    conn = get_connection()
    # Join with news table to get card details
    rows = conn.execute(
        """
        SELECT n.*, no.granted_at, no.granter_id FROM news_ownership no
        JOIN news n ON n.card_id = no.card_id
        WHERE no.user_id = ?
        ORDER BY no.granted_at DESC
        LIMIT ?
        """,
        (user_id, limit),
    ).fetchall()
    # Convert rows to dicts
    return [dict(r) for r in rows]


def deliver_variant(
    delivery_id: str,
    variant_id: str,
    to_player_id: str,
    from_actor_id: str,
    visibility_level: str,
    delivery_reason: str,
) -> None:
    conn = get_connection()
    now = datetime.now(timezone.utc).isoformat()
    with conn:
        conn.execute(
            """
            INSERT INTO news_deliveries (
                delivery_id, variant_id, to_player_id, from_actor_id, 
                visibility_level, delivery_reason, delivered_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                delivery_id,
                variant_id,
                to_player_id,
                from_actor_id,
                visibility_level,
                delivery_reason,
                now,
            ),
        )


def list_inbox(user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT
            d.delivery_id,
            d.variant_id,
            d.to_player_id,
            d.from_actor_id,
            d.visibility_level,
            d.delivery_reason,
            d.delivered_at AS created_at,
            n.card_id,
            n.kind,
            n.text,
            n.symbols_json,
            n.tags_json,
            n.truth_payload_json
        FROM news_deliveries d
        JOIN news n ON n.variant_id = d.variant_id
        WHERE d.to_player_id = ?
        ORDER BY d.delivered_at DESC
        LIMIT ?
        """,
        (user_id, limit),
    ).fetchall()

    items: List[Dict[str, Any]] = []
    for r in rows:
        symbols: List[str] = []
        tags: List[str] = []
        truth_payload: Optional[Dict[str, Any]] = None
        if r["symbols_json"]:
            try:
                symbols = json.loads(r["symbols_json"])
            except Exception:
                symbols = []
        if r["tags_json"]:
            try:
                tags = json.loads(r["tags_json"])
            except Exception:
                tags = []
        if r["truth_payload_json"]:
            try:
                truth_payload = json.loads(r["truth_payload_json"])
            except Exception:
                truth_payload = {}

        items.append(
            {
                "delivery_id": str(r["delivery_id"]),
                "card_id": str(r["card_id"]),
                "variant_id": str(r["variant_id"]),
                "kind": str(r["kind"]),
                "from_actor_id": str(r["from_actor_id"]),
                "visibility_level": str(r["visibility_level"]),
                "delivery_reason": str(r["delivery_reason"]),
                "created_at": str(r["created_at"]),
                "text": str(r["text"]),
                "symbols": symbols,
                "tags": tags,
                "truth_payload": truth_payload,
                "owns_card": False,
            }
        )
    return items


def list_all_users(limit: int = 5000) -> List[str]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT user_id FROM news_users LIMIT ?", (limit,)
    ).fetchall()
    return [r["user_id"] for r in rows]


def count_cards() -> int:
    conn = get_connection()
    row = conn.execute("SELECT count(*) as c FROM news WHERE variant_id IS NULL").fetchone()
    return row["c"] if row else 0


def list_user_inbox_news(user_id: str, limit: int = 5) -> List[Dict[str, Any]]:
    """获取用户的 inbox 新闻，用于 AI 代理的市场情报"""
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT v.text as text, d.delivered_at as delivered_at
        FROM news_deliveries d
        JOIN news v ON d.variant_id = v.variant_id
        WHERE d.to_player_id = ?
        ORDER BY d.delivered_at DESC
        LIMIT ?
        """,
        (user_id, limit)
    ).fetchall()
    return [{"text": r["text"], "delivered_at": r["delivered_at"]} for r in rows]


def list_all_cards(limit: int = 50) -> List[Dict[str, Any]]:
    """获取所有新闻卡片，用于调试端点"""
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT card_id, kind, from_actor_id, visibility_level,
               delivery_reason, created_at, published_at, text,
               symbols_json, tags_json, truth_payload_json
        FROM news
        WHERE variant_id IS NULL
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        d["symbols"] = json.loads(d.get("symbols_json") or "[]")
        d["tags"] = json.loads(d.get("tags_json") or "[]")
        d["truth_payload"] = json.loads(d.get("truth_payload_json") or "{}")
        del d["symbols_json"], d["tags_json"], d["truth_payload_json"]
        result.append(d)
    return result


def list_variants_by_card(card_id: str, limit: int = 50) -> List[Dict[str, Any]]:
    """获取指定卡片的所有变体，用于调试端点"""
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT variant_id, text, author_id, mutation_depth,
               influence_cost, created_at
        FROM news
        WHERE card_id = ? AND variant_id IS NOT NULL
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (card_id, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def list_deliveries_by_variant(variant_id: str, limit: int = 200) -> List[Dict[str, Any]]:
    """获取指定变体的所有投递记录，用于调试端点"""
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT delivery_id, card_id, variant_id, to_player_id,
               from_actor_id, visibility_level, delivery_reason, delivered_at
        FROM news_deliveries
        WHERE variant_id = ?
        ORDER BY delivered_at DESC
        LIMIT ?
        """,
        (variant_id, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def list_deliveries_by_user(user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
    """获取指定用户的所有投递记录，用于调试端点"""
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT d.delivery_id, d.card_id, d.variant_id, d.to_player_id,
               d.from_actor_id, d.visibility_level, d.delivery_reason,
               d.delivered_at, d.is_read, v.text
        FROM news_deliveries d
        LEFT JOIN news v ON d.variant_id = v.variant_id
        WHERE d.to_player_id = ?
        ORDER BY d.delivered_at DESC
        LIMIT ?
        """,
        (user_id, limit),
    ).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        d["text"] = r["text"] if r["text"] else ""
        result.append(d)
    return result

