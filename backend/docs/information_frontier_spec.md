# Information Frontier Backend Spec

## 1. 核心原则

- 所有影响市场预期的变化统一抽象为事件。
- 事件必须可追溯、可审计、可回放。
- 当前后端以 SQLite 为权威存储。
- 社交关系、新闻投递、所有权等原图关系已改为 SQLite 关系表建模。

## 2. 统一事件 Envelope

- `event_id`
- `event_type`
- `occurred_at`
- `correlation_id`
- `causation_id`
- `actor`
- `payload`

事件统一通过 `EventEnvelope` / `EventEnvelopeJson` 表达，并写入 SQLite `events` 表。

## 3. 当前核心领域事件

- `news.card_created`
- `news.variant_emitted`
- `news.variant_mutated`
- `news.delivered`
- `news.broadcasted`
- `news.ownership_granted`
- `news.ownership_transferred`
- `trade.intent_submitted`
- `trade.executed`
- `contract.*`
- `ai.*`

## 4. SQLite 权威模型

### 4.1 账户与市场

- `accounts`
- `positions`
- `ledger_entries`
- `orders`
- 市场成交与价格相关表
- `securities`

### 4.2 新闻与关系

- `news`
- `news_users`
- `news_follows`
- `news_ownership`
- `news_deliveries`
- `news_chain_*` 相关表

### 4.3 事件与合约

- `events`
- `contracts`
- `contract_terms`
- `contract_proposals`

## 5. 新闻系统当前建模

### 5.1 News Card

卡牌母体保存在 `news` 表中，满足：

- `variant_id IS NULL`
- 包含 `kind`
- 包含 `truth_payload_json`
- 可选 `image_uri` / `image_anchor_id`

### 5.2 News Variant

文本变体同样保存在 `news` 表中，满足：

- `variant_id IS NOT NULL`
- 通过 `card_id` 关联母体
- 支持 `parent_variant_id`
- 支持 `mutation_depth`

### 5.3 Social Graph / Delivery / Ownership

原图关系已改为关系表：

- follow 关系：`news_follows`
- 用户池：`news_users`
- 所有权：`news_ownership`
- 收件箱投递：`news_deliveries`

## 6. AI / Agent 系统

AI 层不拥有独立数据库模型，统一写入同一套事件系统，并调用同一套 SQLite 读写模型。

当前主要 AI / Agent 角色：

- `CommonBot`
- `ContractAgent`
- `HostingAgent`
- `NewsTickEngine`
- `CommonBotEmergencyRunner`

## 7. 时间与调度

系统存在显式调度器：

- `ContractRuleScheduler`
- `NewsTickScheduler`
- `MarketSessionScheduler`
- `MarketMakerScheduler`
- `HostingScheduler`

游戏内时间通过 `game_time` 相关服务统一映射。

## 8. 当前迁移结论

- Neo4j 已不再作为后端运行依赖。
- 主运行链路已迁移到 SQLite。
- 仓库中的设计与实现应以 SQLite 结构为准。
