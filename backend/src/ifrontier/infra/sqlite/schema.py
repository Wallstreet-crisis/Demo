from __future__ import annotations

from ifrontier.infra.sqlite.bots import init_bot_accounts
from ifrontier.infra.sqlite.chat import init_chat_schema
from ifrontier.infra.sqlite.contract_agent import init_contract_agent_schema
from ifrontier.infra.sqlite.db import get_connection
from ifrontier.infra.sqlite.hosting import init_hosting_schema
from ifrontier.infra.sqlite.market import init_market_schema
from ifrontier.infra.sqlite.orders import init_order_schema
from ifrontier.infra.sqlite.securities import init_securities_schema, load_securities_pool_from_env


def init_schema() -> None:
    conn = get_connection()
    cur = conn.cursor()

    cur.executescript(
        """
        CREATE TABLE IF NOT EXISTS accounts (
            account_id TEXT PRIMARY KEY,
            owner_type TEXT NOT NULL,
            cash REAL NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS positions (
            account_id TEXT NOT NULL,
            symbol TEXT NOT NULL,
            quantity REAL NOT NULL DEFAULT 0,
            PRIMARY KEY (account_id, symbol),
            FOREIGN KEY (account_id) REFERENCES accounts(account_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS ledger_entries (
            entry_id TEXT PRIMARY KEY,
            account_id TEXT NOT NULL,
            asset_type TEXT NOT NULL,
            symbol TEXT NOT NULL,
            delta REAL NOT NULL,
            event_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (account_id) REFERENCES accounts(account_id) ON DELETE CASCADE
        );
        """
    )

    conn.commit()

    # 订单簿（LIMIT 订单入簿，MARKET 订单由撮合引擎吃单实现）
    init_order_schema()

    init_securities_schema()
    load_securities_pool_from_env()

    # 市场成交记录/价格序列（用于 K 线等）
    init_market_schema()

    init_contract_agent_schema()

    init_chat_schema()

    init_hosting_schema()

    # Bot 入局资产（机构/散户代表群），只在创世阶段写入，之后交易严格走账本
    init_bot_accounts()
