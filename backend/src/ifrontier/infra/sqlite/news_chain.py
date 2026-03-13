from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from ifrontier.infra.sqlite.db import get_connection


@dataclass
class NewsChainRecord:
    chain_id: str
    root_card_id: str
    current_card_id: str
    kind: str
    omen_interval_seconds: int
    abort_probability: float
    phase: str
    next_publish_at: Optional[str]
    created_at: str
    seed: int
    t0_at: Optional[str] = None
    resolved_at: Optional[str] = None
    extra_truth_json: Optional[str] = None
    suppression_budget_grants: int = 0
    suppression_budget_total: float = 0.0

    @staticmethod
    def from_row(row: Any) -> NewsChainRecord:
        return NewsChainRecord(
            chain_id=row["chain_id"],
            root_card_id=row["root_card_id"],
            current_card_id=row["current_card_id"],
            kind=row["kind"],
            omen_interval_seconds=int(row["omen_interval_seconds"]),
            abort_probability=float(row["abort_probability"]),
            phase=row["phase"],
            next_publish_at=row["next_publish_at"],
            created_at=row["created_at"],
            seed=int(row["seed"]),
            t0_at=row["t0_at"],
            resolved_at=row["resolved_at"],
            extra_truth_json=row["extra_truth_json"],
            suppression_budget_grants=int(row["suppression_budget_grants"]) if row["suppression_budget_grants"] else 0,
            suppression_budget_total=float(row["suppression_budget_total"]) if row["suppression_budget_total"] else 0.0,
        )


def init_news_chain_schema() -> None:
    conn = get_connection()
    cur = conn.cursor()

    cur.executescript(
        """
        DROP TABLE IF EXISTS news_chains;

        CREATE TABLE IF NOT EXISTS news_chains (
            chain_id TEXT PRIMARY KEY,
            root_card_id TEXT NOT NULL,
            current_card_id TEXT NOT NULL,
            kind TEXT NOT NULL,
            omen_interval_seconds INTEGER NOT NULL DEFAULT 3600,
            abort_probability REAL NOT NULL DEFAULT 0.0,
            phase TEXT NOT NULL DEFAULT 'INCUBATING',
            next_publish_at TEXT,
            created_at TEXT NOT NULL,
            seed INTEGER NOT NULL,
            t0_at TEXT,
            resolved_at TEXT,
            extra_truth_json TEXT,
            suppression_budget_grants INTEGER DEFAULT 0,
            suppression_budget_total REAL DEFAULT 0.0
        );

        CREATE INDEX IF NOT EXISTS idx_chains_phase ON news_chains(phase);
        CREATE INDEX IF NOT EXISTS idx_chains_root ON news_chains(root_card_id);
        CREATE INDEX IF NOT EXISTS idx_chains_next_publish ON news_chains(next_publish_at);
        CREATE INDEX IF NOT EXISTS idx_chains_t0 ON news_chains(t0_at);
        """
    )
    conn.commit()


def create_news_chain(
    chain_id: str,
    root_card_id: str,
    kind: str,
    seed: int,
    t0_at: str,
    omen_interval_seconds: int = 3600,
    abort_probability: float = 0.0,
    grant_count: int = 0,
    symbols: Optional[List[str]] = None,
    extra_truth: Optional[Dict[str, Any]] = None,
) -> NewsChainRecord:
    conn = get_connection()
    now = datetime.now(timezone.utc).isoformat()

    next_publish_at = now  # For ticking, start immediately

    extra_truth_json = json.dumps(extra_truth or {}, ensure_ascii=False)
    symbols_json = json.dumps(symbols or [], ensure_ascii=False)

    with conn:
        conn.execute(
            """
            INSERT INTO news_chains (
                chain_id, root_card_id, current_card_id, kind,
                omen_interval_seconds, abort_probability, phase,
                next_publish_at, created_at, seed, t0_at,
                extra_truth_json, suppression_budget_grants, suppression_budget_total
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                chain_id,
                root_card_id,
                root_card_id,  # Initial current_card_id is root
                kind,
                omen_interval_seconds,
                abort_probability,
                "INCUBATING",
                next_publish_at,
                now,
                seed,
                t0_at,
                extra_truth_json,
                grant_count,  # Initialize suppression budget with grant_count
                0.0,
            ),
        )

    return NewsChainRecord(
        chain_id=chain_id,
        root_card_id=root_card_id,
        current_card_id=root_card_id,
        kind=kind,
        omen_interval_seconds=omen_interval_seconds,
        abort_probability=abort_probability,
        phase="INCUBATING",
        next_publish_at=next_publish_at,
        created_at=now,
        seed=seed,
        t0_at=t0_at,
    )


def get_news_chain(chain_id: str) -> Optional[NewsChainRecord]:
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM news_chains WHERE chain_id = ?", (chain_id,)
    ).fetchone()

    if row is None:
        return None
    return NewsChainRecord.from_row(row)


def update_news_chain(chain_id: str, **kwargs: Any) -> None:
    # Updates simple fields. For complex updates like advancing, use specific functions.
    conn = get_connection()
    set_clauses = []
    values = []

    valid_fields = [
        "phase", "next_publish_at", "current_card_id", "omen_interval_seconds",
        "abort_probability", "t0_at", "resolved_at", "extra_truth_json",
        "suppression_budget_grants", "suppression_budget_total"
    ]

    for key, value in kwargs.items():
        if key in valid_fields:
            set_clauses.append(f"{key} = ?")
            values.append(value)

    if not set_clauses:
        return

    values.append(chain_id)
    with conn:
        conn.execute(
            f"UPDATE news_chains SET {', '.join(set_clauses)} WHERE chain_id = ?",
            values,
        )


def advance_chain(chain_id: str, new_card_id: str) -> NewsChainRecord:
    conn = get_connection()
    chain = get_news_chain(chain_id)
    if not chain:
        raise ValueError("Chain not found")

    now = datetime.now(timezone.utc).isoformat()
    next_publish_dt = datetime.fromisoformat(now) + datetime.timedelta(seconds=chain.omen_interval_seconds)
    next_publish_at = next_publish_dt.isoformat()

    with conn:
        conn.execute(
            """
            UPDATE news_chains 
            SET current_card_id = ?, next_publish_at = ? 
            WHERE chain_id = ?
            """,
            (new_card_id, next_publish_at, chain_id),
        )

    # Return updated record
    return get_news_chain(chain_id)


def abort_chain(chain_id: str, reason: str = "MANUAL_ABORT") -> None:
    conn = get_connection()
    with conn:
        conn.execute(
            "UPDATE news_chains SET phase = ?, next_publish_at = NULL WHERE chain_id = ?",
            (reason, chain_id),
        )


def list_active_chains(limit: int = 50) -> List[NewsChainRecord]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM news_chains WHERE phase = 'ACTIVE' ORDER BY next_publish_at ASC LIMIT ?",
        (limit,),
    ).fetchall()
    return [NewsChainRecord.from_row(r) for r in rows]


def list_due_chains(now: str, limit: int = 50) -> List[Dict[str, Any]]:
    """获取需要处理的链（INCUBATING 阶段且到达下一次预兆时间或 T0 时间）"""
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT * FROM news_chains
        WHERE phase = 'INCUBATING'
          AND (next_publish_at <= ? OR t0_at <= ?)
        ORDER BY t0_at ASC
        LIMIT ?
        """,
        (now, now, limit),
    ).fetchall()

    results = []
    for r in rows:
        chain = dict(r)
        # Parse extra_truth_json
        extra_truth = {}
        if r["extra_truth_json"]:
            try:
                extra_truth = json.loads(r["extra_truth_json"])
            except json.JSONDecodeError:
                pass
        chain["extra_truth_json"] = json.dumps(extra_truth)
        chain.update(extra_truth)
        results.append(chain)
    return results


def update_next_omen(chain_id: str, next_omen_at: str) -> None:
    """更新链的下一次预兆时间"""
    conn = get_connection()
    with conn:
        conn.execute(
            "UPDATE news_chains SET next_omen_at = ? WHERE chain_id = ?",
            (next_omen_at, chain_id),
        )


def resolve_chain(chain_id: str, phase: str) -> None:
    """解决链（RESOLVED 或 ABORTED）"""
    conn = get_connection()
    now = datetime.now(timezone.utc).isoformat()
    with conn:
        conn.execute(
            "UPDATE news_chains SET phase = ?, resolved_at = ? WHERE chain_id = ?",
            (phase, now, chain_id),
        )


def add_suppression_budget(chain_id: str, spend: float) -> bool:
    """为链添加压制预算"""
    conn = get_connection()
    chain = get_news_chain(chain_id)
    if chain is None:
        return False

    new_grants = chain.suppression_budget_grants + int(spend)
    new_total = chain.suppression_budget_total + spend

    with conn:
        conn.execute(
            """
            UPDATE news_chains
            SET suppression_budget_grants = ?, suppression_budget_total = ?
            WHERE chain_id = ?
            """,
            (new_grants, new_total, chain_id),
        )
    return True


def consume_suppression_budget(chain_id: str, requested: int) -> tuple[int, float]:
    """消费压制预算，返回实际压制的数量和剩余预算"""
    chain = get_news_chain(chain_id)
    if chain is None:
        return 0, 0.0

    grants = chain.suppression_budget_grants
    if grants <= 0:
        return 0, 0.0

    suppressed = min(grants, requested)
    remaining = grants - suppressed

    conn = get_connection()
    with conn:
        conn.execute(
            "UPDATE news_chains SET suppression_budget_grants = ? WHERE chain_id = ?",
            (remaining, chain_id),
        )

    return suppressed, float(remaining)


def count_chains_by_status(status: str) -> int:
    """统计指定状态的新闻链数量"""
    conn = get_connection()
    row = conn.execute(
        "SELECT count(*) as c FROM news_chains WHERE phase = ?",
        (status,),
    ).fetchone()
    return int(row["c"]) if row else 0


def list_all_chains(limit: int = 50) -> List[Dict[str, Any]]:
    """获取所有新闻链，用于调试端点"""
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT
            chain_id, major_card_id, kind, phase, created_at, t0_at,
            next_omen_at, omen_interval_seconds, abort_probability,
            grant_count, seed, symbols
        FROM news_chains
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_chain_by_id(chain_id: str) -> Optional[Dict[str, Any]]:
    """根据 chain_id 获取新闻链详情"""
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM news_chains WHERE chain_id = ?",
        (chain_id,),
    ).fetchone()
    return dict(row) if row else None
