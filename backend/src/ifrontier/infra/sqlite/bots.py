from __future__ import annotations

from dataclasses import dataclass
from typing import List

from ifrontier.infra.sqlite.db import get_connection
from ifrontier.infra.sqlite.ledger import create_account
from ifrontier.infra.sqlite.securities import list_securities


@dataclass(frozen=True)
class BotProfile:
    account_id: str
    owner_type: str
    initial_cash: float


def default_bot_profiles() -> List[BotProfile]:
    # 机构：少量几个，每个 100w
    inst = [
        BotProfile(account_id="bot:inst:1", owner_type="bot_institution", initial_cash=1_000_000.0),
        BotProfile(account_id="bot:inst:2", owner_type="bot_institution", initial_cash=1_000_000.0),
    ]

    # 散户代表群：数量控制在 10（可调），每个 5w
    retail = [
        BotProfile(account_id=f"bot:ret:{i}", owner_type="bot_retail", initial_cash=50_000.0)
        for i in range(1, 11)
    ]
    return inst + retail


def init_bot_accounts() -> None:
    conn = get_connection()
    securities = list_securities()
    symbols = [s.symbol for s in securities]

    with conn:
        for p in default_bot_profiles():
            # 确保账户存在
            row = conn.execute("SELECT 1 FROM accounts WHERE account_id = ?", (p.account_id,)).fetchone()
            if not row:
                create_account(p.account_id, owner_type=p.owner_type, initial_cash=p.initial_cash)
            
            # 即使账户已存在，也确保机构（做市商）持有足够的初始证券以供卖出
            if p.owner_type == "bot_institution" and symbols:
                for sym in symbols:
                    # 使用 INSERT OR IGNORE 确保每个 symbol 至少有初始库存，不覆盖已有库存
                    conn.execute(
                        "INSERT OR IGNORE INTO positions(account_id, symbol, quantity) VALUES (?, ?, ?)",
                        (p.account_id, sym, 100000.0)
                    )


        # 简化说明：
        # 初版 Bot 初始持仓为 0（不凭空造股）。因此 SELL 下单可能失败，直到你显式分配持仓。
        # 你后续可以在这里插入 positions 作为“创世分配”的一部分。