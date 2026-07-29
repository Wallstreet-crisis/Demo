"""Check AI sim room state"""
import sqlite3, os

db_path = r'D:\project\Demo\backend\data\rooms\ai-sim-1\ledger.db'
if not os.path.exists(db_path):
    print(f"DB not found at {db_path}")
    # List available rooms
    rooms_dir = r'D:\project\Demo\backend\data\rooms'
    if os.path.exists(rooms_dir):
        print("Available rooms:", os.listdir(rooms_dir))
    exit()

conn = sqlite3.connect(db_path)
cur = conn.cursor()

tables = [t[0] for t in cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
print('Tables:', tables)

# hosting state
try:
    rows = cur.execute('SELECT * FROM user_hosting_state').fetchall()
    cols = [d[0] for d in cur.description]
    print('\nhosting_state:')
    for r in rows:
        d = dict(zip(cols, r))
        print(f"  {d['user_id']}: enabled={d['enabled']} status={d['status']} updated={d['updated_at']}")
except Exception as e:
    print(f'hosting_state error: {e}')

# hosting context
try:
    rows = cur.execute('SELECT * FROM user_hosting_context').fetchall()
    cols = [d[0] for d in cur.description]
    print('\nhosting_context:')
    for r in rows:
        d = dict(zip(cols, r))
        ctx = str(d.get('context') or '')[:200]
        print(f"  {d['user_id']}: ctx={ctx}")
except Exception as e:
    print(f'hosting_context error: {e}')

# accounts
rows = cur.execute('SELECT account_id, cash, status, caste_id FROM accounts').fetchall()
print('\naccounts:')
for r in rows:
    print(f"  {r[0]}: cash={r[1]} status={r[2]} caste={r[3]}")

# orders
rows = cur.execute('SELECT count(*) FROM orders').fetchall()
print(f'\norders: {rows[0][0]} total')

# trades
try:
    rows = cur.execute('SELECT count(*) FROM market_trades').fetchall()
    print(f'trades: {rows[0][0]} total')
except Exception as e:
    print(f'trades error: {e}')

# events
try:
    rows = cur.execute('SELECT count(*) FROM events').fetchall()
    print(f'events: {rows[0][0]} total')
except Exception as e:
    print(f'events error: {e}')

# market session
try:
    rows = cur.execute('SELECT * FROM game_meta').fetchall()
    cols = [d[0] for d in cur.description]
    print('\ngame_meta:')
    for r in rows:
        for k, v in zip(cols, r):
            print(f"  {k}={v}")
except Exception as e:
    print(f'game_meta error: {e}')

conn.close()
