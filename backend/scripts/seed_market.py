import random
import uuid
from datetime import datetime, timedelta, timezone
from ifrontier.infra.sqlite.db import get_connection
from ifrontier.infra.sqlite.market import record_trade, init_market_schema
from ifrontier.infra.sqlite.securities import list_securities, init_securities_schema

def seed_market_history():
    """为市场中的所有股票生成模拟的历史交易数据，使 K 线图看起来是满的"""
    print("Initializing schemas...")
    init_securities_schema()
    init_market_schema()
    
    securities = list_securities()
    if not securities:
        print("No securities found. Please ensure seed symbols are inserted.")
        return

    print(f"Seeding history for {len(securities)} symbols...")
    
    # 模拟过去 24 小时，每 5 分钟一笔交易
    now = datetime.now(timezone.utc)
    start_time = now - timedelta(hours=24)
    
    conn = get_connection()
    
    for sec in securities:
        symbol = sec.symbol
        base_price = sec.seed_price
        current_price = base_price
        
        print(f"  -> Seeding {symbol} (Base: {base_price})")
        
        # 批量插入以提高效率
        trades_to_insert = []
        
        temp_time = start_time
        while temp_time < now:
            # 随机波动 0.5% - 2%
            volatility = random.uniform(-0.015, 0.015)
            current_price *= (1 + volatility)
            
            # 随机成交量
            qty = random.uniform(10, 1000)
            
            trades_to_insert.append((
                symbol,
                current_price,
                qty,
                temp_time.isoformat(),
                str(uuid.uuid4())
            ))
            
            temp_time += timedelta(minutes=5)
            
        with conn:
            conn.executemany(
                "INSERT INTO market_trades(symbol, price, quantity, occurred_at, event_id) VALUES (?, ?, ?, ?, ?)",
                trades_to_insert
            )

    print("Seeding complete. Market terminal is now active with historical data.")

if __name__ == "__main__":
    seed_market_history()
