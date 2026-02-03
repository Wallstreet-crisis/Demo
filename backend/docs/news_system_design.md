# 新闻（卡牌）系统：设计理念与后端规格（v0）

> 本文档是《信息边境》新闻/卡牌系统的后端实现依据，目标是把“物理真实（图像锚点）+ 语义篡改（文本覆层）+ 病毒传播（社交网络）+ 权力杠杆（影响力/阶级）”落为可审计、可回放、可测试的后端接口与事件。

## 1. 设计理念（Design Philosophy）

### 1.1 价格不被外力改写（No Exogenous Price Shock）
- 新闻系统不直接修改任何价格曲线、盘口、估值、撮合结果。
- 市场价格只能由玩家/Bots 的下单与撮合自然形成。
- 新闻的作用是制造“认知差异”，从而让玩家/Bots 产生不同交易行为。

### 1.2 图像锚点与文本覆层二元化（Image Anchor + Text Overlay）
- **图像锚点**：若存在，则视为“物理发生证明”，不可被玩家篡改。
- **文本覆层**：可被编辑、可被分叉传播，形成多个“病毒株”。
- **占位与无配图**：允许新闻先占位（未绑定插画），也允许“无配图小新闻”；这两类新闻仍允许被篡改，类似纯文本谣言。

### 1.3 病毒传播而非全服广播（Viral Delivery, not Global Spam）
- 大多数新闻不全服广播，而是通过“投递（Delivery）”进入玩家的收件箱。
- 传播依赖社交网络与传播者资源投入（影响力），并可被对手抑制。

### 1.4 审计与可回放（Auditability & Replayability）
- 新闻的生成、篡改、投递、广播、真相揭示，都必须落为事件流记录。
- 事件需幂等、可追溯，便于回放与调试。

### 1.5 阶级差异不是内容差异（Class-based Rendering, not Content Fork）
- 阶级/影响力会影响“看得清不清楚”（可见性等级、渲染质量、溯源能力），而不是改变同一条强制广播的内容。

---

## 2. 已确认的关键取舍（v0 决策）

- **无配图小新闻允许被篡改**：更像纯文本谣言，利于传播与信息战。
- **强制广播内容一致**：广播只保证“全员收到同一份内容”，阶级差异体现在可见性/渲染等级。
- **新闻资产化 MVP**：先只做 `Ownership` 转移（P2P），传播/编辑权跟随所有权。

补充（v0.1 决策）：
- **购买卡片以现金结算**：从系统购买 `NewsCard` 直接消耗现金（ledger）。
- **购买后两类发布路径**：
  - `MAJOR_EVENT`（系统级重大事件）：购买后进入孵化/前兆链，并在 T=0 延迟广播（Mandatory Broadcast）。
  - 其他普通卡：购买后等效“随机拾到的新闻”，走社交关系网链式病毒传播（Propagate）。
- **助推/压制都花现金**：传播助推（propagate boost）和抑制他人助推（suppress）均消耗现金，并落为事件流审计。

---

## 3. 核心概念与数据模型

### 3.1 NewsCard（新闻卡牌母体）
代表同一张“卡牌母体”，允许先占位、后绑定插画，也允许无配图。

建议字段：
- `card_id: str`（UUID）
- `kind: str`（如：`RUMOR`、`OMEN`、`MAJOR_EVENT`、`EARNINGS`、`DISCLOSURE`）
- `image_anchor_id: str | None`（可空/后绑定）
- `image_uri: str | None`（可选：前端取图）
- `truth_payload: dict | None`（系统真相载荷；可能仅在 T=0 揭示）
- `symbols: list[str]`（关联公司/资产/板块）
- `tags: list[str]`
- `created_at: datetime`
- `resolved_at: datetime | None`

### 3.2 NewsVariant（文本版本/病毒株）
所有篡改都产生新版本（分叉），不覆盖旧版本。

建议字段：
- `variant_id: str`（UUID）
- `card_id: str`
- `parent_variant_id: str | None`（分叉链）
- `author_id: str`（`system` / `gm:*` / `user:*` / `bot:*`）
- `text: str`
- `influence_cost: float`（用于篡改/传播消耗的记账入口）
- `risk_roll: dict | None`（预留：运气检定/暴露）
- `created_at: datetime`

### 3.3 NewsDelivery（投递/感染记录）
大多数新闻进入玩家视野依赖投递。

建议字段：
- `delivery_id: str`（UUID）
- `variant_id: str`
- `to_player_id: str`
- `from_actor_id: str`（`system`/传播者）
- `delivered_at: datetime`
- `visibility_level: str`（阶级相关渲染等级）
- `delivery_reason: str`（`SYSTEM_GRANT`/`SOCIAL_PROPAGATION`/`PURCHASED`/`BROADCAST`/`DISCLOSURE`）
- `read_at: datetime | None`

### 3.4 Ownership（新闻资产所有权）
MVP：只做所有权转移，传播/编辑权跟随所有权。

建议关系：
- `(u:User)-[:OWNS_NEWS {acquired_at, quality}]->(c:NewsCard)`

---

## 4. 传播模型（社交网络 + 影响力）

### 4.1 社交网络（Neo4j 权威关系）
- `(u1:User)-[:FOLLOWS {strength?}]->(u2:User)`

### 4.2 传播动作（Propagate）
传播不是自动扩散，而是传播者投入资源推动投递。

- 输入：`variant_id`、`from_actor_id`、传播半径/目标集合、`spend_influence`
- 输出：一组 `NewsDelivery`（投递记录）

影响力的作用（v0 推荐先做确定性策略）：
- 决定可覆盖人数/跳数上限
- 决定 `visibility_level`（高阶级/高影响力 -> 更清晰）

### 4.3 抑制传播（Suppress）
预留：玩家/机构可以花影响力对特定 `card_id` 或 `variant_id` 做“压制”，降低其投递成功率或降低可见性等级。

---

## 5. 系统生成（Tick 驱动）与前兆链

新闻产生方式包含：
- **GM/脚本手动发**：适合作为卡牌发行与剧情干预
- **系统 tick 生成**：产生碎屑、前兆、孵化与落地

### 5.1 前兆（Omen）与孵化（Incubation）
- 系统在事件落地（T=0）前，分批生成相关 `NewsCard/NewsVariant`（可无配图/可占位）。

### 5.1.1 事件链（Event Chain）与“流产”机制（Abortable Resolution）

新闻不仅是单点事件，而是一条“事件链”：
- **主事件（Major Event）**：例如“全面战争”。它通常带倒计时（T-Δ），在 T=0 才真正落地。
- **前兆/碎屑小事件（Omens / Minor Incidents）**：例如“外交关系降级”“预备役到位”“局部征兵”“港口管制”等。

核心目标：
- 玩家/Bots 可以通过前兆小事件做“提前反应”，从而在市场上制造真实的价格行为（但价格仍由撮合产生）。
- **前兆小事件不应泄露主事件必然发生**：即使主事件最终流产，前兆小事件也可能发生，以避免形成“看到征兵就必然全面战争”的确定性信号。

行为规则（v0 建议）：
- **前兆独立成立**：前兆小事件的发生与投递，可以独立于主事件是否最终落地。
- **主事件可流产**：主事件在 T=0 时允许以一定概率“流产”（或被机制/玩家干预阻止）。
- **前兆可被压制传播**：富豪/机构可以消耗影响力，压制某条前兆（或某类前兆）的传播覆盖与可见性，从而降低其他玩家/Bots 的提前反应能力。
- **系统发布的重大新闻同样遵循该机制**：系统级重大事件同样可以拥有孵化期与前兆链；区别仅在于某些事件在 T=0 可能触发“强制全局广播”。

设计建议：
- 把“主事件是否落地”的信息仅存于 `truth_payload` 或独立的 `EventChainState`，不要让前兆事件文本直接泄露该 bit。
- 即使主事件流产，也可在后续产生“解释性前兆”（例如“外交误会已澄清”），但这也是新闻的一种，不是直接改写历史。

### 5.2 流产（Abort）
- 事件链允许流产：T=0 到来前被标记为 aborted，作为“虚晃一枪”。

### 5.3 真相揭示（Truth Revealed, T=0）
- 触发 `news.truth_revealed`：
  - 若是占位卡，此时绑定 `image_anchor_id/image_uri`
  - 写入 `resolved_at`
- 前端表现：全屏插画；此前的文本覆层可以视觉上“撕裂/作废”，但后端不删除历史版本（便于审计）。

### 5.4 事件链状态字段建议（用于 Tick 生成器）

为支持倒计时、孵化、流产与落地，建议在 `truth_payload` 或专门状态对象中包含：
- `chain_id: str`（事件链 ID，关联主事件与其前兆）
- `phase: str`（`INCUBATING`/`RESOLVED`/`ABORTED`）
- `t0_at: datetime | None`（计划落地时间）
- `aborted_at: datetime | None`
- `abort_reason: str | None`（可选）

并允许前兆小事件携带：
- `chain_id`（同链 ID）
- `signal_class: str`（例如 `DIPLOMACY`/`MOBILIZATION`/`LOGISTICS`），用于 Bots 过滤与推理
- `signal_strength: int|float`（预留：强度；不等价为“主事件概率”）

---

## 6. 强制全局广播（Mandatory Global Broadcast）

### 6.1 哪些属于强制广播
- **重大事件（MAJOR_EVENT）**：系统触发，强制全局广播
- **企业财报（EARNINGS）**：强制全局广播
- **披露法案（DISCLOSURE）**触发的披露：强制全局广播

### 6.2 广播内容一致
- 强制广播对所有玩家投递同一份内容（同一 `variant_id`）。
- 阶级差异仅影响 `visibility_level`（看得清楚程度），不产生“内容分叉”。

实现建议：广播也落为对全体用户生成 `NewsDelivery(reason=BROADCAST)`，以统一 inbox 与审计模型。

---

## 7. 披露法案（Disclosure Act）

披露法案要求某些重大交易/契约行为必须公开广播。

建议触发源：
- `trade.executed`（成交事件）
- `contract.*`（签署/结算/激活等）

触发后的动作：
- 生成 `NewsCard(kind=DISCLOSURE, truth_payload=...)`
- 生成不可删除的 `NewsVariant(author=system, text=披露文本)`
- 强制全局广播（全员 Delivery）

---

## 8. 事件类型（建议与 information_frontier_spec.md 对齐）

建议事件类型（EventType）：
- `news.card_created`
- `news.variant_emitted`
- `news.variant_mutated`
- `news.delivered`
- `news.truth_revealed`
- `news.broadcasted`（可选；若广播完全等价为全员 delivered，也可不单独要）
- `disclosure.emitted`

事件链相关（建议补充）：
- `news.chain_started`（可选：事件链启动，创建主事件占位卡）
- `news.omen_emitted`（可选：语义上标识“前兆”；也可复用 `news.variant_emitted` + payload.kind）
- `news.chain_aborted`（可选：主事件流产；也可复用 `news.truth_revealed` 并在 payload 标识 aborted）
- `news.propagation_suppressed`（预留：某 actor 消耗影响力压制传播，影响投递覆盖/可见性）

---

## 9. API 规划（实现顺序建议）

### 9.1 MVP（第一阶段）
- `POST /news/cards`：创建占位/无配图卡牌
- `POST /news/variants/emit`：发布初始文本版本
- `POST /news/variants/{variant_id}/mutate`：篡改生成新版本（需 ownership 或付费策略）
- `POST /news/variants/{variant_id}/propagate`：按社交图传播（消耗影响力）
- `GET /news/inbox/{player_id}`：收件箱
- `POST /news/broadcast`：强制广播（系统/GM）

### 9.2 现金购买与投递策略（v0.1）

#### 9.2.1 购买（Purchase）

目标：后端策划/系统用一条 API 完成“扣现金 + 铸造卡牌 + 绑定发布策略”。

- `POST /news/store/purchase`

请求建议：
```json
{
  "buyer_user_id": "user:rich:xxx",
  "kind": "RUMOR",
  "price_cash": 100.0,
  "image_anchor_id": null,
  "image_uri": null,
  "truth_payload": {"topic": "..."},
  "symbols": ["ABC"],
  "tags": ["purchased"],
  "initial_text": "...",
  "policy": {
    "type": "PURCHASED_RANDOM_PICKUP",
    "seed_deliveries": 1,
    "delivery_reason": "PURCHASED"
  }
}
```

语义：
- 现金扣款：从 `buyer_user_id` 的账户扣减 `price_cash`
- 创建卡牌与初始版本：`create_card` + `emit_variant(author=buyer_user_id)`
- 授予所有权：`ownership.grant` 给 `buyer_user_id`
- 执行发布策略：
  - 普通卡（非 `MAJOR_EVENT`）：等效随机拾到（至少给购买者自己投递 1 次），之后进入社交链传播。
  - `MAJOR_EVENT`：创建/绑定事件链状态（`truth_payload` 含 `t0_at/chain_id/phase`），并由 tick 在孵化期生成 omen，在 T0 广播。

#### 9.2.2 普通卡：随机拾到 + 社交链式传播

推荐策略：
- 购买瞬间至少投递给购买者（让其“拿到卡”）
- 后续传播通过关系图传播（followers / 朋友链），传播由“助推现金”驱动

- `POST /news/variants/{variant_id}/propagate`

请求建议（现金助推）：
```json
{
  "from_actor_id": "user:rich:xxx",
  "spend_cash": 50.0,
  "scope": "followers",
  "limit": 30,
  "visibility_level": "NORMAL"
}
```

语义：
- 从传播者扣现金（ledger）
- 将现金映射为可覆盖人数/跳数（v0 先做确定性：例如 `limit = floor(spend_cash / unit_cost)`）
- 对目标集合投递 `deliver_variant(reason=SOCIAL_PROPAGATION)`

#### 9.2.3 系统级重大事件：延迟广播（孵化/前兆链）

购买 `kind=MAJOR_EVENT` 后：
- 创建主事件占位卡（或购买即是主事件卡）
- `truth_payload` 内包含 `chain_id/phase/t0_at/abort_probability` 等
- 由 `/news/tick` 驱动：
  - 孵化期按 `omen_interval_seconds` 生成前兆 omen，并随机播撒（可被压制）
  - 到达 `t0_at` 后触发强制全局广播（同一份内容）

#### 9.2.4 压制（Suppress）与反制（仍以现金计费）

- `POST /news/suppress`

请求建议：
```json
{
  "actor_id": "user:rich:yyy",
  "chain_id": "...",
  "spend_cash": 100.0,
  "scope": "chain"
}
```

语义：
- 从 `actor_id` 扣现金（ledger）
- 将现金转为 suppression budget（以“可抑制的投递次数”计）
- 影响 `/news/tick` 的 omen 投递覆盖，使 `delivered_to` 下降甚至归零

备注：当前实现中 suppression 是针对 chain omen 的投递预算；后续可扩展到 variant 级别。

### 9.2 第二阶段
- tick 生成器：前兆/孵化/流产/T=0
- 抑制传播
- 新闻资产交易接口（P2P ownership 转移），可接入契约系统

---

## 10. Bots 对接点

Bots 必须响应新闻以制造流动性，但价格仍由交易撮合形成。

建议 Bots 输入：
- `GET /news/inbox/{bot_id}` 或 `GET /news/recent?symbols=...`
- Bots 基于：关键词、符号、传播范围、版本冲突、溯源能力（后续）决定下单策略。
