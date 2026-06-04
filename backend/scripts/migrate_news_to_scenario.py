import sqlite3
import json
import os

def migrate():
    source_db = 'backend/data/ledger.db'
    target_db = 'global_studio.db'
    
    if not os.path.exists(source_db):
        print(f"Source DB {source_db} not found.")
        return

    s_conn = sqlite3.connect(source_db)
    s_conn.row_factory = sqlite3.Row
    
    t_conn = sqlite3.connect(target_db)
    t_conn.row_factory = sqlite3.Row
    
    # 初始化目标表结构
    t_conn.executescript("""
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
        faction TEXT,
        parent_card_id TEXT,
        activation_prob REAL DEFAULT 1.0,
        scheduled_at TEXT,
        success_criteria_json TEXT,
        failure_outcome_json TEXT,
        scenario_id TEXT
    );
    """)
    
    # 1. 获取源数据
    cards = s_conn.execute("SELECT * FROM news").fetchall()
    print(f"Found {len(cards)} records in source.")
    
    # 2. 插入或替换到目标数据库
    inserted = 0
    for card in cards:
        d = dict(card)
        if not d.get('scenario_id'):
            d['scenario_id'] = 'DEFAULT_SIMULATION'
            
        columns = ', '.join(d.keys())
        placeholders = ', '.join(['?'] * len(d))
        sql = f"INSERT OR REPLACE INTO news ({columns}) VALUES ({placeholders})"
        t_conn.execute(sql, tuple(d.values()))
        inserted += 1
    
    t_conn.commit()
    s_conn.close()
    t_conn.close()
    print(f"Migration finished: {inserted} records moved to {target_db}")

if __name__ == '__main__':
    migrate()
