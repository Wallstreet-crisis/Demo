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
    created_at: str = ""
    author_id: Optional[str] = None
    parent_variant_id: Optional[str] = None
    rarity: str = "COMMON"
    faction: Optional[str] = None

    @staticmethod
    def from_row(row: Any) -> NewsRecord:
        symbols = []
        tags = []
        truth_payload = {}
        
        is_dict = isinstance(row, dict)
        def get_v(key: str, default: Any = None):
            if is_dict: return row.get(key, default)
            try: return row[key]
            except: return default

        symbols_json = get_v("symbols_json")
        if symbols_json:
            try: symbols = json.loads(symbols_json)
            except: pass

        tags_json = get_v("tags_json")
        if tags_json:
            try: tags = json.loads(tags_json)
            except: pass
                
        truth_payload_json = get_v("truth_payload_json")
        if truth_payload_json:
            try: truth_payload = json.loads(truth_payload_json)
            except: pass

        return NewsRecord(
            card_id=get_v("card_id"),
            variant_id=get_v("variant_id"),
            kind=get_v("kind"),
            text=get_v("text"),
            symbols=symbols,
            tags=tags,
            publisher_id=get_v("publisher_id"),
            published_at=get_v("published_at"),
            is_suppressed=bool(get_v("is_suppressed", 0)),
            suppression_reason=get_v("suppression_reason"),
            truth_payload=truth_payload,
            image_uri=get_v("image_uri"),
            preset_id=get_v("preset_id"),
            created_at=get_v("created_at", ""),
            author_id=get_v("author_id"),
            parent_variant_id=get_v("parent_variant_id"),
            rarity=get_v("rarity") or "COMMON",
            faction=get_v("faction"),
        )


def _add_column_if_not_exists(cur, table: str, column: str, type_def: str):
    try:
        cur.execute(f"ALTER TABLE {table} ADD COLUMN {column} {type_def}")
    except:
        pass


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
            created_at TEXT,
            author_id TEXT,
            parent_variant_id TEXT,
            rarity TEXT DEFAULT 'COMMON',
            faction TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_news_card_id ON news(card_id);
        CREATE INDEX IF NOT EXISTS idx_news_variant_id ON news(variant_id);

        CREATE TABLE IF NOT EXISTS news_market_shelves (
            player_id TEXT PRIMARY KEY,
            items_json TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        """
    )

    # 动态迁移补充缺失列
    _add_column_if_not_exists(cur, "news", "created_at", "TEXT")
    _add_column_if_not_exists(cur, "news", "author_id", "TEXT")
    _add_column_if_not_exists(cur, "news", "parent_variant_id", "TEXT")
    _add_column_if_not_exists(cur, "news", "rarity", "TEXT DEFAULT 'COMMON'")
    _add_column_if_not_exists(cur, "news", "faction", "TEXT")

    conn.commit()

    # 动态迁移缺失列
    info = cur.execute("PRAGMA table_info(news)").fetchall()
    columns = {str(row[1]) for row in info}
    
    migrations = [
        ("rarity", "TEXT DEFAULT 'COMMON'"),
        ("author_id", "TEXT"),
        ("parent_variant_id", "TEXT"),
        ("mutation_depth", "INTEGER DEFAULT 0"),
        ("influence_cost", "REAL DEFAULT 0.0"),
        ("risk_roll_json", "TEXT"),
    ]
    
    for col_name, col_def in migrations:
        if col_name not in columns:
            cur.execute(f"ALTER TABLE news ADD COLUMN {col_name} {col_def}")

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
    rarity: str = "COMMON",
    published_at: Optional[str] = None,
    author_id: Optional[str] = None,
    parent_variant_id: Optional[str] = None,
    mutation_depth: int = 0,
    influence_cost: float = 0.0,
    risk_roll: Optional[Dict[str, Any]] = None,
    faction: Optional[str] = None,
) -> None:
    conn = get_connection()
    now = datetime.now(timezone.utc).isoformat()
    
    pub_at = published_at
    if pub_at is None and variant_id is not None:
        pass

    with conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO news (
                card_id, variant_id, kind, text, symbols_json, tags_json, 
                publisher_id, published_at, is_suppressed, suppression_reason,
                truth_payload_json, image_uri, image_anchor_id, preset_id, rarity, faction, created_at,
                author_id, parent_variant_id, mutation_depth, influence_cost, risk_roll_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                rarity,
                faction,
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
    rows = list_inbox(user_id=user_id, limit=limit)
    return [NewsRecord.from_row(r) for r in rows]


def get_card_owner(card_id: str) -> Optional[str]:
    # 通过 news_ownership 表查找卡牌当前所有者
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

        CREATE TABLE IF NOT EXISTS news_market_shelves (
            user_id TEXT PRIMARY KEY,
            items_json TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS news_deliveries (
            delivery_id TEXT PRIMARY KEY,
            card_id TEXT NOT NULL,
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
    # SQLite 版本通过更新 news_ownership 记录完成转移。
    conn = get_connection()
    now = datetime.now(timezone.utc).isoformat()
    with conn:
        cursor = conn.execute(
            "UPDATE news_ownership SET user_id = ?, granted_at = ?, granter_id = ? WHERE card_id = ? AND user_id = ?",
            (to_user_id, now, transferred_by, card_id, from_user_id),
        )
    if int(getattr(cursor, "rowcount", 0) or 0) <= 0:
        raise ValueError("current owner not found")


def list_owned_cards(user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
    conn = get_connection()
    # Join with news table to get card details
    rows = conn.execute(
        """
        SELECT n.*, no.granted_at, no.granter_id FROM news_ownership no
        JOIN news n ON n.card_id = no.card_id AND n.variant_id IS NULL
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
    card_id: str,
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
                delivery_id, card_id, variant_id, to_player_id, from_actor_id, 
                visibility_level, delivery_reason, delivered_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                delivery_id,
                card_id,
                variant_id,
                to_player_id,
                from_actor_id,
                visibility_level,
                delivery_reason,
                now,
            ),
        )


def find_delivery(
    *,
    variant_id: str,
    to_player_id: str,
    from_actor_id: str,
    delivery_reason: str,
) -> Dict[str, Any] | None:
    conn = get_connection()
    row = conn.execute(
        """
        SELECT delivery_id, variant_id, to_player_id, from_actor_id, visibility_level, delivery_reason, delivered_at
        FROM news_deliveries
        WHERE variant_id = ? AND to_player_id = ? AND from_actor_id = ? AND delivery_reason = ?
        ORDER BY delivered_at DESC
        LIMIT 1
        """,
        (variant_id, to_player_id, from_actor_id, delivery_reason),
    ).fetchone()
    return dict(row) if row is not None else None


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
            d.delivered_at AS delivered_at,
            d.delivered_at AS published_at,
            n.*,
            CASE WHEN no.card_id IS NOT NULL THEN 1 ELSE 0 END AS owns_card
        FROM news_deliveries d
        JOIN news n ON n.variant_id = d.variant_id
        LEFT JOIN news_ownership no ON no.card_id = n.card_id AND no.user_id = d.to_player_id
        WHERE d.to_player_id = ?
        ORDER BY d.delivered_at DESC
        LIMIT ?
        """,
        (user_id, limit),
    ).fetchall()

    items: List[Dict[str, Any]] = []
    for r in rows:
        d_row = dict(r)
        
        # 转换 JSON 字段
        for field in ["symbols_json", "tags_json", "truth_payload_json", "risk_roll_json"]:
            if field in d_row and d_row[field]:
                try:
                    d_row[field.replace("_json", "")] = json.loads(d_row[field])
                except:
                    d_row[field.replace("_json", "")] = [] if "json" in field else {}
        
        # 兼容 NewsRecord.from_row 的字段名
        d_row["created_at"] = r["delivered_at"]
        d_row["owns_card"] = bool(r["owns_card"])
        
        items.append(d_row)
    return items


def list_all_users(limit: int = 5000) -> List[str]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT user_id FROM news_users LIMIT ?", (limit,)
    ).fetchall()
    return [r["user_id"] for r in rows]


def get_market_shelf(user_id: str) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    row = conn.execute(
        "SELECT items_json, expires_at, created_at FROM news_market_shelves WHERE user_id = ?",
        (user_id,),
    ).fetchone()
    if row is None:
        return None
    
    return {
        "user_id": user_id,
        "items": json.loads(row["items_json"]),
        "expires_at": row["expires_at"],
        "created_at": row["created_at"],
    }


def save_market_shelf(user_id: str, items: List[Dict[str, Any]], expires_at: str) -> None:
    conn = get_connection()
    now = datetime.now(timezone.utc).isoformat()
    with conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO news_market_shelves (user_id, items_json, expires_at, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (user_id, json.dumps(items, ensure_ascii=False), expires_at, now),
        )


def clear_market_shelf(user_id: str) -> None:
    conn = get_connection()
    with conn:
        conn.execute("DELETE FROM news_market_shelves WHERE user_id = ?", (user_id,))


def list_user_inbox_news(user_id: str, limit: int = 5) -> List[Dict[str, Any]]:
    """获取用户收件箱中的最近新闻，用于 AI 代理的市场情报。"""
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


def count_cards() -> int:
    """获取新闻卡片总数。"""
    conn = get_connection()
    row = conn.execute(
        "SELECT COUNT(*) as cnt FROM news WHERE variant_id IS NULL"
    ).fetchone()
    return row["cnt"] if row else 0


def list_all_cards(limit: int = 50) -> List[Dict[str, Any]]:
    """获取所有新闻卡片，用于调试端点。"""
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT card_id, kind, publisher_id, created_at, published_at, text,
               image_uri, image_anchor_id, preset_id,
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
    """获取指定卡片的所有变体，用于调试端点。"""
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
    """获取指定变体的所有投递记录，用于调试端点。"""
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
    """获取指定用户的所有投递记录，用于调试端点。"""
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


