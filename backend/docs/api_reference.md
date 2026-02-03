# Backend API Reference (for Frontend)

## Base
- Base URL: `http://<host>:<port>`
- Content-Type: `application/json`

## Error Format
- Most endpoints return `HTTP 400` with:
  - `{"detail": "<error message>"}`

## WebSocket
- Endpoint: `GET /ws/{channel}`
- The server broadcasts JSON messages to channels.

### Payload (Event Envelope)
Most broadcasts are `EventEnvelopeJson`-like objects:
```json
{
  "event_id": "4f5e3c1a-1111-2222-3333-1234567890ab",
  "event_type": "NEWS_CARD_CREATED",
  "occurred_at": "2026-01-01T00:00:00+00:00",
  "correlation_id": "2d2d2d2d-aaaa-bbbb-cccc-111111111111",
  "causation_id": null,
  "actor": {"user_id": "user:alice", "agent_id": null},
  "payload": {}
}
```

Notes:
- `actor` may contain `user_id` or `agent_id` (or both), depending on the producer.
- Some internal tick code may broadcast plain dicts (still JSON) for convenience.

### Common Channels
- `events`: all events
- `<EventType>`: event-specific stream (server will broadcast to `str(event_type)`)
- `chat.public.global`: public chat messages
- `chat.pm.<thread_id>`: PM thread messages

Client behavior:
- Connect to desired channels.
- Send any text periodically (server currently ignores payload but requires receive loop).

---

## Health
### GET `/health`
Response:
```json
{"status": "ok"}
```

---

## Securities Pool / Trading Halt / Market Maker (debug)
> Used for per-session securities pool, halts, and minimum market making.

### POST `/debug/securities/load_pool`
Loads securities pool from env var `IF_SECURITIES_POOL_JSON`.

Response:
```json
{"ok": true}
```

### POST `/debug/securities/set_status`
Request:
```json
{"symbol": "BLUEGOLD", "status": "HALTED"}
```
- `status`: `TRADABLE` | `HALTED`

Response:
```json
{"ok": true}
```

### POST `/debug/market_maker/tick_once`
Runs one market maker tick.

Env vars:
- `IF_MARKET_MAKER_ACCOUNT_ID` (default `mm:1`)
- `IF_MARKET_MAKER_SPREAD_PCT` (default `0.02`)
- `IF_MARKET_MAKER_MIN_QTY` (default `1.0`)

Response:
```json
{"placed": 12}
```

---

## Market Data
### GET `/market/quote/{symbol}`
Response:
```json
{
  "symbol": "BLUEGOLD",
  "last_price": 10.0,
  "prev_price": 9.5,
  "change_pct": 0.0526315,
  "ma_5": 9.9,
  "ma_20": 8.8,
  "vol_20": 0.12
}
```

### GET `/market/series/{symbol}?limit=200`
Response:
```json
{"symbol": "BLUEGOLD", "prices": [10.0, 9.8]}
```

### GET `/market/candles/{symbol}?interval_seconds=60&limit=200`
Response:
```json
{
  "symbol": "BLUEGOLD",
  "interval_seconds": 60,
  "candles": [
    {
      "bucket_start": "2026-01-01T00:00:00+00:00",
      "open": 10.0,
      "high": 10.0,
      "low": 10.0,
      "close": 10.0,
      "volume": 2.0,
      "vwap": 10.0,
      "trades": 1
    }
  ]
}
```

### GET `/market/session`
Response:
```json
{
  "enabled": true,
  "phase": "TRADING",
  "game_day_index": 0,
  "seconds_into_day": 12,
  "seconds_per_game_day": 10,
  "trading_seconds": 8,
  "closing_buffer_seconds": 2
}
```

---

## Orders
### POST `/orders/limit`
Request:
```json
{"player_id": "alice", "symbol": "BLUEGOLD", "side": "BUY", "price": 10.0, "quantity": 5.0}
```
Response:
```json
{"order_id": "..."}
```

### POST `/orders/market`
Request:
```json
{"player_id": "alice", "symbol": "BLUEGOLD", "side": "BUY", "quantity": 5.0}
```
Response: `200 OK` with empty body.

Notes:
- Orders are validated against market session (trading hours).
- Orders are validated against securities pool:
  - If securities pool is configured, `symbol` must exist and be `TRADABLE`.

---

## Accounts
### GET `/players/{player_id}/account`
Response:
```json
{"account_id": "user:alice", "cash": 100.0, "positions": {"BLUEGOLD": 3.0}}
```

### GET `/accounts/{account_id}/valuation?discount_factor=1.0`
Response:
```json
{
  "account_id": "user:alice",
  "cash": 100.0,
  "positions": {"BLUEGOLD": 3.0},
  "equity_value": 60.0,
  "total_value": 160.0,
  "discount_factor": 1.0,
  "prices": {"BLUEGOLD": 20.0}
}
```

---

## Contracts
### POST `/contracts/create`
Request:
```json
{
  "actor_id": "user:alice",
  "kind": "MASTER",
  "title": "...",
  "terms": {},
  "parties": ["user:alice", "user:bob"],
  "required_signers": ["user:alice", "user:bob"],
  "participation_mode": null,
  "invited_parties": null
}
```
Response:
```json
{"contract_id": "..."}
```

### POST `/contracts/batch_create`
Request:
```json
{"actor_id": "user:alice", "contracts": [{"kind": "...", "title": "...", "terms": {}, "parties": ["..."], "required_signers": ["..."]}]}
```
Response:
```json
{"contracts": [{"index": 0, "contract_id": "..."}]}
```

### POST `/contracts/{contract_id}/join`
Request:
```json
{"joiner": "user:charlie"}
```

### POST `/contracts/{contract_id}/sign`
Request:
```json
{"signer": "user:alice"}
```
Response:
```json
{"status": "SIGNED"}
```

### POST `/contracts/{contract_id}/activate`
Request:
```json
{"actor_id": "user:alice"}
```

### POST `/contracts/{contract_id}/settle`
Request:
```json
{"actor_id": "user:alice"}
```

### POST `/contracts/{contract_id}/run_rules`
Request:
```json
{"actor_id": "user:alice"}
```

### Proposals
- POST `/contracts/{contract_id}/proposals/create`
- POST `/contracts/{contract_id}/proposals/{proposal_id}/approve`

#### POST `/contracts/{contract_id}/proposals/create`
Request:
```json
{
  "proposer": "user:alice",
  "proposal_type": "AMEND_TERMS",
  "details": {
    "patch": {"terms": {"rules": []}}
  }
}
```
Response:
```json
{"proposal_id": "..."}
```

#### POST `/contracts/{contract_id}/proposals/{proposal_id}/approve`
Request:
```json
{"approver": "user:bob"}
```
Response:
```json
{
  "applied": true,
  "contract_status": "ACTIVE",
  "proposal_type": "AMEND_TERMS"
}
```

---

## Contract Agent (LLM)
### POST `/contract-agent/draft`
Request:
```json
{"actor_id": "user:alice", "natural_language": "..."}
```
Response:
```json
{
  "draft_id": "...",
  "template_id": "...",
  "contract_create": {},
  "explanation": "...",
  "questions": ["..."],
  "risk_rating": "LOW"
}
```

### GET `/contract-agent/context/{actor_id}`
Response:
```json
{"actor_id": "user:alice", "context": {}}
```

### POST `/contract-agent/context/{actor_id}/clear`
Response: `200 OK`.

---

## Chat

### POST `/chat/intro-fee/quote`
Set or update a rich user's intro fee quote.

Request:
```json
{"rich_user_id": "user:rich", "fee_cash": 1000.0, "actor_id": "user:rich"}
```

Response:
```json
{"event_id": "...", "correlation_id": "..."}
```

### POST `/chat/pm/open`
Open (or reuse) a PM thread. Might charge intro fee depending on policy.

Request:
```json
{"requester_id": "user:alice", "target_id": "user:rich"}
```

Response:
```json
{"thread_id": "pm:...", "paid_intro_fee": true, "intro_fee_cash": 1000.0}
```

### POST `/chat/public/send`
Request:
```json
{
  "sender_id": "user:alice",
  "message_type": "TEXT",
  "content": "hello world",
  "payload": {},
  "anonymous": false,
  "alias": null
}
```

Response:
```json
{"event_id": "...", "correlation_id": "..."}
```

### POST `/chat/pm/send`
Request:
```json
{
  "thread_id": "pm:...",
  "sender_id": "user:alice",
  "message_type": "TEXT",
  "content": "hi",
  "payload": {},
  "anonymous": false,
  "alias": null
}
```

Response:
```json
{"event_id": "...", "correlation_id": "..."}
```

### GET `/chat/public/messages?limit=50&before=<message_id>`
Response:
```json
{
  "items": [
    {
      "message_id": "msg:...",
      "thread_id": "public:global",
      "sender_id": "user:alice",
      "sender_display": "user:alice",
      "message_type": "TEXT",
      "content": "hello world",
      "payload": {},
      "created_at": "2026-01-01T00:00:00+00:00"
    }
  ]
}
```

### GET `/chat/pm/{thread_id}/messages?limit=50&before=<message_id>`
Response:
```json
{
  "items": [
    {
      "message_id": "msg:...",
      "thread_id": "pm:...",
      "sender_id": "user:alice",
      "sender_display": "user:alice",
      "message_type": "TEXT",
      "content": "hi",
      "payload": {},
      "created_at": "2026-01-01T00:00:00+00:00"
    }
  ]
}
```

### GET `/chat/threads/{user_id}?limit=200`
Response:
```json
{
  "items": [
    {
      "thread_id": "pm:...",
      "kind": "PM",
      "participant_a": "user:alice",
      "participant_b": "user:rich",
      "status": "OPEN",
      "created_at": "2026-01-01T00:00:00+00:00"
    }
  ]
}
```

---

## Wealth (Public)

### POST `/wealth/public/refresh`
Recomputes public wealth top10 and broadcasts events.

Response:
```json
{"public_count": 10, "event_id": "...", "correlation_id": "..."}
```

### GET `/wealth/public/{user_id}`
Response:
```json
{"user_id": "user:alice", "public_total_value": 12345.67}
```

---

## Social
### POST `/social/follow`
Request:
```json
{"follower_id": "user:alice", "followee_id": "user:bob"}
```

Response: `200 OK` with empty body.

---

## News

### POST `/news/cards`
Create a news card.

Request:
```json
{
  "actor_id": "user:alice",
  "kind": "RUMOR",
  "image_anchor_id": null,
  "image_uri": null,
  "truth_payload": {"truth": "..."},
  "symbols": ["BLUEGOLD"],
  "tags": ["market"],
  "correlation_id": null
}
```

Response:
```json
{"card_id": "card:...", "event_id": "...", "correlation_id": "..."}
```

### POST `/news/variants/emit`
Emit a variant (text) for a card.

Request:
```json
{
  "card_id": "card:...",
  "author_id": "user:alice",
  "text": "headline...",
  "parent_variant_id": null,
  "influence_cost": 0.0,
  "risk_roll": null,
  "correlation_id": null
}
```

Response:
```json
{"variant_id": "var:...", "event_id": "...", "correlation_id": "..."}
```

### POST `/news/variants/mutate`
Create a mutated variant from a parent variant. May charge cash depending on length.

Request:
```json
{
  "parent_variant_id": "var:...",
  "editor_id": "user:alice",
  "new_text": "edited text...",
  "influence_cost": 0.0,
  "spend_cash": null,
  "risk_roll": null,
  "correlation_id": null
}
```

Response:
```json
{"new_variant_id": "var:...", "event_id": "...", "correlation_id": "..."}
```

### POST `/news/propagate`
Propagate a variant to followers.

Request:
```json
{
  "variant_id": "var:...",
  "from_actor_id": "user:alice",
  "visibility_level": "NORMAL",
  "spend_influence": 0.0,
  "spend_cash": null,
  "limit": 50,
  "correlation_id": null
}
```

Response:
```json
{"delivered": 12, "correlation_id": "..."}
```

### GET `/news/inbox/{player_id}?limit=50`
Response:
```json
{
  "items": [
    {
      "delivery_id": "del:...",
      "card_id": "card:...",
      "variant_id": "var:...",
      "from_actor_id": "user:alice",
      "visibility_level": "NORMAL",
      "delivery_reason": "FOLLOWED",
      "delivered_at": "2026-01-01T00:00:00+00:00",
      "text": "headline..."
    }
  ]
}
```

### POST `/news/broadcast`
Broadcast a variant to a global channel.

Request:
```json
{
  "variant_id": "var:...",
  "actor_id": "user:alice",
  "channel": "GLOBAL_MANDATORY",
  "visibility_level": "NORMAL",
  "limit_users": 5000,
  "correlation_id": null
}
```

Response:
```json
{"delivered": 123, "event_id": "...", "correlation_id": "..."}
```

### POST `/news/chains/start`
Start a major event chain. Usually creates a major card and schedules T0 broadcast.

Request:
```json
{
  "kind": "WAR",
  "actor_id": "user:alice",
  "t0_seconds": 60,
  "t0_at": null,
  "omen_interval_seconds": 10,
  "abort_probability": 0.3,
  "grant_count": 2,
  "seed": 1,
  "correlation_id": null
}
```

Response:
```json
{"chain_id": "chain:...", "major_card_id": "card:...", "t0_at": "2026-01-01T00:01:00+00:00"}
```

### POST `/news/tick`
Tick the event chain engine once.

Request:
```json
{"now_iso": null, "limit": 50}
```

Response:
```json
{"now": "2026-01-01T00:00:12+00:00", "chains": []}
```

### POST `/news/suppress`
Attempt to suppress a chain propagation.

Request:
```json
{
  "actor_id": "user:alice",
  "chain_id": "chain:...",
  "spend_influence": 1.0,
  "signal_class": null,
  "scope": "chain",
  "correlation_id": null
}
```

Response:
```json
{"event_id": "...", "correlation_id": "..."}
```

### POST `/news/ownership/grant`
Request:
```json
{"card_id": "card:...", "to_user_id": "user:alice", "granter_id": "system", "correlation_id": null}
```
Response:
```json
{"event_id": "...", "correlation_id": "..."}
```

### POST `/news/ownership/transfer`
Request:
```json
{
  "card_id": "card:...",
  "from_user_id": "user:alice",
  "to_user_id": "user:bob",
  "transferred_by": "user:alice",
  "correlation_id": null
}
```
Response:
```json
{"event_id": "...", "correlation_id": "..."}
```

### GET `/news/ownership/{user_id}?limit=200`
Response:
```json
{"cards": ["card:...", "card:..."]}
```

### POST `/news/store/purchase`
Purchase a news item from store. For `MAJOR_EVENT`, returns chain_id; otherwise returns card_id + variant_id.

Request:
```json
{
  "buyer_user_id": "user:alice",
  "kind": "RUMOR",
  "price_cash": 100.0,
  "image_anchor_id": null,
  "image_uri": null,
  "truth_payload": null,
  "symbols": ["BLUEGOLD"],
  "tags": ["market"],
  "initial_text": "my initial text",
  "t0_seconds": 60,
  "t0_at": null,
  "omen_interval_seconds": 10,
  "abort_probability": 0.3,
  "grant_count": 2,
  "seed": 1,
  "correlation_id": null
}
```

Response (normal):
```json
{"kind": "RUMOR", "buyer_user_id": "user:alice", "card_id": "card:...", "variant_id": "var:...", "chain_id": null}
```

Response (MAJOR_EVENT):
```json
{"kind": "MAJOR_EVENT", "buyer_user_id": "user:alice", "card_id": "card:...", "variant_id": null, "chain_id": "chain:..."}
```

---

## Hosting

### POST `/hosting/{user_id}/enable`
Response:
```json
{
  "state": {"user_id": "alice", "enabled": true, "status": "ON_IDLE", "updated_at": "..."},
  "event_id": "...",
  "correlation_id": "..."
}
```

### POST `/hosting/{user_id}/disable`
Response:
```json
{
  "state": {"user_id": "alice", "enabled": false, "status": "OFF", "updated_at": "..."},
  "event_id": "...",
  "correlation_id": "..."
}
```

### GET `/hosting/{user_id}/status`
Response:
```json
{"user_id": "alice", "enabled": false, "status": "OFF", "updated_at": "..."}
```

### POST `/hosting/debug/tick_once`
Response:
```json
{"ok": true}
```

---

## Debug (misc)

### POST `/debug/emit_event`
Request:
```json
{
  "event_type": "NEWS_CREATED",
  "payload": {"any": "json"},
  "actor_user_id": "user:alice",
  "actor_agent_id": null,
  "correlation_id": null,
  "causation_id": null
}
```

Response:
```json
{"event_id": "...", "correlation_id": "..."}
```

### POST `/debug/earnings_news`
Request:
```json
{"symbol": "BLUEGOLD", "visual_truth": "BULL", "headline_text": "...", "price_series": [10.0, 10.2]}
```

Response:
```json
{
  "news_event_id": "...",
  "ai_decision_event_id": "...",
  "trade_intent_event_id": "...",
  "correlation_id": "..."
}
```

### POST `/debug/execute_trade`
Request:
```json
{"buy_account_id": "user:mk:buy:...", "sell_account_id": "user:mk:sell:...", "symbol": "BLUEGOLD", "price": 10.0, "quantity": 2.0}
```

Response:
```json
{"event_id": "...", "correlation_id": "..."}
```

### POST `/debug/submit_order`
Request:
```json
{"account_id": "user:alice", "symbol": "BLUEGOLD", "side": "BUY", "price": 10.0, "quantity": 5.0}
```

Response:
```json
{"order_id": "..."}
```

### POST `/debug/create_player`
Request:
```json
{"player_id": "alice", "initial_cash": 100000, "caste_id": null}
```

Response:
```json
{"account_id": "user:alice", "cash": 100000.0}
```
