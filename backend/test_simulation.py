"""AI Simulation Test Script"""
import urllib.request, json, time

BASE = 'http://127.0.0.1:8010'

def api(method, path, body=None, room='ai-sim-1'):
    headers = {'X-Room-Id': room, 'Content-Type': 'application/json'}
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(f'{BASE}{path}', data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return {'error': e.code, 'detail': e.read().decode()[:300]}

# 1. Health
print('=== Health ===')
print(api('GET', '/health'))

# 2. Create room
print('\n=== Create Room ===')
r = api('POST', '/rooms', {
    'room_id': 'ai-sim-1',
    'player_id': 'HOST',
    'game_settings': {
        'ai_simulation_mode': True,
        'small_news_interval_seconds': 10,
        'chain_interval_seconds': 60,
    }
})
print(r)

# 3. Activate
print('\n=== Activate Room ===')
print(api('POST', '/rooms/ai-sim-1/activate'))
time.sleep(3)

# 4. Create 4 AI players
agents = ['ai:trader_1', 'ai:trader_2', 'ai:momenta_1', 'ai:arb_1']
castes = ['ELITE', 'MIDDLE', 'WORKING', 'ELITE']
for a, c in zip(agents, castes):
    print(f'\n=== Bootstrap {a} ({c}) ===')
    r = api('POST', '/players/bootstrap', {'player_id': a, 'caste_id': c}, room='ai-sim-1')
    print(f"  cash={r.get('cash','?')}  caste={r.get('caste_id','?')}")

# 5. Enable hosting
for a in agents:
    print(f'\n=== Enable Hosting {a} ===')
    print(api('POST', f'/hosting/{a}/enable', {}, room='ai-sim-1'))

print('\n=== Waiting 20 seconds for AI ticks ===')
for i in range(20):
    time.sleep(1)
    print(f'  {i+1}s...', end='\r')

# 6. Check status
print('\n=== Hosting Status ===')
for a in agents:
    s = api('GET', f'/hosting/{a}/status', room='ai-sim-1')
    if isinstance(s, dict):
        print(f'  {a}: enabled={s.get("enabled")}, status={s.get("status")}, ticks={s.get("total_ticks")}')

# 7. Check accounts
print('\n=== Accounts ===')
for a in agents:
    r = api('GET', f'/players/{a}/account', room='ai-sim-1')
    if isinstance(r, dict):
        pos = dict(r.get('positions') or {})
        pos_str = ', '.join(f'{k}={v}' for k, v in pos.items()) if pos else 'none'
        print(f'  {a}: cash={r.get("cash")}, status={r.get("status")}, positions=[{pos_str}]')

# 8. Check open orders
print('\n=== Open Orders ===')
for a in agents:
    orders = api('GET', f'/orders/open/{a}', room='ai-sim-1')
    if isinstance(orders, list):
        for o in orders:
            if isinstance(o, dict):
                print(f'  {a}: {o.get("side")} {o.get("symbol")} @ {o.get("price")} qty={o.get("quantity_remaining")}')

# 9. Check market quotes
print('\n=== Market Quotes ===')
import urllib.error
try:
    syms = api('GET', '/market/symbols', room='ai-sim-1')
    if isinstance(syms, list):
        for s in syms[:6]:
            q = api('GET', f'/market/quote/{s}', room='ai-sim-1')
            if isinstance(q, dict):
                print(f'  {s}: last={q.get("last_price")} prev={q.get("prev_price")} chg%={q.get("change_pct")}')
except Exception as e:
    print(f'  market error: {e}')

# 10. Check news
print('\n=== Inbox News ===')
for a in agents:
    news = api('GET', f'/news/inbox/{a}', room='ai-sim-1')
    if isinstance(news, list):
        print(f'  {a}: {len(news)} news items')

# 11. Check market session
print('\n=== Market Session ===')
s = api('GET', '/market/session', room='ai-sim-1')
if isinstance(s, dict):
    print(f'  phase={s.get("phase")}, day={s.get("game_day_index")}, elapsed={s.get("elapsed_seconds")}s')

print('\n=== Done ===')
