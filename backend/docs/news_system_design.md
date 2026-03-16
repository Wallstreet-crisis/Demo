# 新闻系统设计（SQLite 版）

## 1. 目标

新闻系统负责表达：

- 新闻卡牌母体
- 文本变体分叉
- 用户传播关系
- 收件箱投递
- 所有权转移
- 广播与事件链

系统当前不再依赖图数据库，统一用 SQLite 建模。

## 2. 设计原则

- 新闻不直接修改价格。
- 市场价格由订单与撮合形成。
- 新闻通过改变玩家和 Bot 的认知来间接影响市场。
- 每次创建、篡改、投递、广播都要留下事件记录。

## 3. 数据模型

### 3.1 `news`

同一张表同时存：

- 卡牌母体
- 文本变体

约定：

- `variant_id IS NULL` 表示卡牌母体
- `variant_id IS NOT NULL` 表示某个文本变体

关键字段：

- `card_id`
- `variant_id`
- `kind`
- `text`
- `symbols_json`
- `tags_json`
- `truth_payload_json`
- `author_id`
- `parent_variant_id`
- `mutation_depth`
- `published_at`

### 3.2 `news_users`

表示参与新闻传播系统的用户集合。

### 3.3 `news_follows`

表示传播关系：

- `follower_id`
- `followee_id`

### 3.4 `news_ownership`

表示卡牌所有权：

- `card_id`
- `user_id`
- `granted_at`
- `granter_id`

### 3.5 `news_deliveries`

表示投递记录：

- `delivery_id`
- `variant_id`
- `to_player_id`
- `from_actor_id`
- `visibility_level`
- `delivery_reason`
- `delivered_at`

## 4. 服务职责

### 4.1 `NewsService`

负责：

- `create_card`
- `emit_variant`
- `mutate_variant`
- `deliver_variant`
- `broadcast_variant`
- `list_inbox`
- `grant_ownership`
- `transfer_ownership`

### 4.2 `infra.sqlite.news`

负责：

- schema 初始化
- 关系表读写
- inbox 查询
- ownership 查询
- 调试查询

## 5. 传播模型

### 5.1 Follow 传播

传播从某个 actor 出发，查询其 followers，再对 followers 写入 `news_deliveries`。

### 5.2 广播

广播先列出 `news_users`，再批量写入 `news_deliveries`，并额外写入 `news.broadcasted` 事件。

### 5.3 所有权

卡牌编辑权和传播权的上层策略由服务层决定，底层所有权记录落在 `news_ownership`。

## 6. 事件链

事件链由 `news_chain` 相关 SQLite 表承载，用于支持：

- omen
- incubating
- resolved
- aborted

## 7. 当前实现状态

- 新闻主链路已迁移到 SQLite
- Follow / ownership / delivery 已迁移到关系表
- inbox / debug 查询已可直接从 SQLite 读取
- Neo4j 旧实现已不再参与运行
