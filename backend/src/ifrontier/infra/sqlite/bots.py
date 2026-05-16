from __future__ import annotations

import os
from dataclasses import dataclass
from typing import List

from ifrontier.infra.sqlite.db import get_connection
from ifrontier.infra.sqlite.ledger import create_account
from ifrontier.infra.sqlite.securities import list_securities
from ifrontier.infra.sqlite.hosting import upsert_hosting_state


@dataclass(frozen=True)
class BotProfile:
    account_id: str
    owner_type: str
    initial_cash: float


def default_bot_profiles() -> List[BotProfile]:
    # 机构：巨头级别，掌控大量筹码和现金
    inst = [
        BotProfile(account_id="bot:inst:1", owner_type="bot_institution", initial_cash=100_000_000.0),
        BotProfile(account_id="bot:inst:2", owner_type="bot_institution", initial_cash=100_000_000.0),
        BotProfile(account_id="bot:inst:3", owner_type="bot_institution", initial_cash=50_000_000.0),
    ]

    # 散户大户/游资：极具攻击性，现金充足
    retail = [
        BotProfile(account_id=f"bot:ret:{i}", owner_type="bot_retail", initial_cash=2_000_000.0)
        for i in range(1, 11)
    ]
    return inst + retail


def init_bot_accounts() -> None:
    """幂等初始化 Bot 和做市商账户。

    确保账户存在，并为做市商补齐持仓。
    """
    conn = get_connection()
    securities = list_securities()
    symbols = [s.symbol for s in securities]

    # 做市商初始资本池配置（仅首次创建时使用）
    MM_INITIAL_CASH = 1_000_000_000.0
    MM_INITIAL_POSITION_PER_SYMBOL = 1_000_000.0

    with conn:
        # ── 做市商 mm:1 —— 仅首次创建时分配资金，不再每次启动补仓 ──
        row = conn.execute("SELECT 1 FROM accounts WHERE account_id = ?", ("mm:1",)).fetchone()
        if not row:
            create_account("mm:1", owner_type="market_maker", initial_cash=MM_INITIAL_CASH)
            if symbols:
                for sym in symbols:
                    conn.execute(
                        "INSERT OR IGNORE INTO positions(account_id, symbol, quantity) VALUES (?, ?, ?)",
                        ("mm:1", sym, MM_INITIAL_POSITION_PER_SYMBOL),
                    )
        else:
            # 已有做市商：仅确保新标的有初始持仓行（不补量）
            if symbols:
                for sym in symbols:
                    conn.execute(
                        "INSERT OR IGNORE INTO positions(account_id, symbol, quantity) VALUES (?, ?, ?)",
                        ("mm:1", sym, 0.0),
                    )

        # ── Bot 账户 ──
        for p in default_bot_profiles():
            row = conn.execute("SELECT 1 FROM accounts WHERE account_id = ?", (p.account_id,)).fetchone()
            is_new = row is None
            if is_new:
                create_account(p.account_id, owner_type=p.owner_type, initial_cash=p.initial_cash)

            # 默认开启机器人的 AI 托管
            upsert_hosting_state(user_id=p.account_id, enabled=True, status="ON_IDLE")

            # 仅首次创建时分配持仓
            if is_new and symbols:
                if p.owner_type == "bot_institution":
                    for sym in symbols:
                        conn.execute(
                            "INSERT OR IGNORE INTO positions(account_id, symbol, quantity) VALUES (?, ?, ?)",
                            (p.account_id, sym, 1_000_000.0),
                        )
                elif p.owner_type == "bot_retail":
                    import random
                    for sym in random.sample(symbols, min(len(symbols), 3)):
                        conn.execute(
                            "INSERT OR IGNORE INTO positions(account_id, symbol, quantity) VALUES (?, ?, ?)",
                            (p.account_id, sym, 5000.0),
                        )