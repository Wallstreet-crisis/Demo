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
    conn = get_connection()
    securities = list_securities()
    symbols = [s.symbol for s in securities]

    with conn:
        # 确保做市商账号也存在（如果不在 profile 里）
        # 做市商 mm:1 的初始化在 market_maker 服务中，但这里我们也给它充值
        row = conn.execute("SELECT 1 FROM accounts WHERE account_id = ?", ("mm:1",)).fetchone()
        if not row:
            create_account("mm:1", owner_type="market_maker", initial_cash=500_000_000.0)
        else:
            conn.execute(
                "UPDATE accounts SET cash = ? WHERE account_id = ?",
                (500_000_000.0, "mm:1")
            )

        if symbols:
            for sym in symbols:
                conn.execute(
                    "INSERT INTO positions(account_id, symbol, quantity) VALUES (?, ?, ?) "
                    "ON CONFLICT(account_id, symbol) DO UPDATE SET quantity = CASE "
                    "WHEN quantity < excluded.quantity THEN excluded.quantity ELSE quantity END",
                    ("mm:1", sym, 1_000_000.0),
                )

        for p in default_bot_profiles():
            row = conn.execute("SELECT 1 FROM accounts WHERE account_id = ?", (p.account_id,)).fetchone()
            if not row:
                create_account(p.account_id, owner_type=p.owner_type, initial_cash=p.initial_cash)
            else:
                conn.execute(
                    "UPDATE accounts SET cash = ? WHERE account_id = ?",
                    (p.initial_cash, p.account_id)
                )
            
            # 默认开启机器人的 AI 托管
            upsert_hosting_state(user_id=p.account_id, enabled=True, status="ON_IDLE")

            # 强制重置持仓，确保机构有足够弹药，散户有足够筹码
            if p.owner_type == "bot_institution" and symbols:
                for sym in symbols:
                    # 使用 REPLACE 确保库存被重置为巨额初值
                    conn.execute(
                        "INSERT OR REPLACE INTO positions(account_id, symbol, quantity) VALUES (?, ?, ?)",
                        (p.account_id, sym, 1_000_000.0)
                    )
            
            elif p.owner_type == "bot_retail" and symbols:
                import random
                # 随机分配一些初始持仓
                for sym in random.sample(symbols, min(len(symbols), 3)):
                    conn.execute(
                        "INSERT OR REPLACE INTO positions(account_id, symbol, quantity) VALUES (?, ?, ?)",
                        (p.account_id, sym, 5000.0) # 提升散户持筹
                    )