# 信息边境（Information Frontier）后端参考规格（策划案对齐）

## 1. 核心原则
- 所有改变市场预期的变量统一抽象为“事件（Event）”，并可投影成“卡牌（Card/News）”
- 事件必须可追溯、可审计、可去重（幂等）
- Neo4j 作为权威感染图与关系图存储

## 2. 统一事件 Envelope
- `event_id`：UUID，全局唯一
- `event_type`：字符串枚举，例如 `news.created`
- `occurred_at`：UTC 时间
- `correlation_id`：一次链式行为的同一根 ID（例如一次多方协作的操作链）
- `causation_id`：上游触发事件 ID
- `actor`：用户/代理/阶级信息
- `payload`：强类型载荷（Pydantic）

## 3. 领域事件（最小集合）
- `news.created`：生成新闻根卡与初始变体
- `news.text_mutated`：产生新变体（分叉），记录影响力成本
- `news.propagated`：传播边，记录权重与成本
- `trade.intent_submitted`：意向单提交
- `trade.executed`：成交落地
- `disclosure.emitted`：触发不可销毁公示
- `settlement.tick_opened / tick_closed`：定时结算窗口

## 4. Neo4j 图模型（权威关系）
### 4.1 节点
- `User {user_id}`
- `News {news_id, kind, visual_truth, original_image_uri, created_at}`
- `NewsVariant {variant_id, text_overlay, created_at, influence_cost}`
- `Asset {symbol}`
- `Contract {contract_id}`
- `Disclosure {disclosure_id, trigger}`

### 4.2 关系
- `(n:News)-[:HAS_VARIANT]->(v:NewsVariant)`
- `(v:NewsVariant)-[:PARENT_OF]->(v2:NewsVariant)`（可选，表示分叉链）
- `(u:User)-[:AUTHORED]->(v:NewsVariant)`
- `(u1:User)-[:PROPAGATED {variant_id, weight, influence_cost, propagated_at}]->(u2:User)`
- `(x)-[:EMITTED_EVENT {event_id, event_type, occurred_at}]->(y)`（审计投影，可选）

## 5. 初始化脚本
见 `backend/scripts/neo4j/init.cypher`

## 6. AI/Agent 系统（最小落地对接点）
- AI 层本身不是“另一个系统”，而是以事件流方式写入同一套 Envelope，统一被审计、被回放、被推送。
- Common Bots / Player Agent 的交易行为，最终仍落为 `trade.*`、`news.*`、`contract.*` 事件；AI 事件主要用于解释与可观测性（why/how）。

### 6.1 AI 领域事件（最小集合）
- `ai.commonbot.decision`：流动性 Bot 的一次决策（权重与置信度）
- `ai.contract.drafted`：契约秘书生成代码预览与风险评级
- `ai.whisperer.assessment`：高阶特权 AI 的“图文冲突”评估结果
- `ai.world_event.omen_emitted / purchased / resolved`：世界引擎的暗示链与落地
- `ai.player_agent.task_submitted / task_completed`：玩家托管代理的任务链路

### 6.2 Neo4j 图模型扩展（建议）
- `AiModel {model_id, name, provider}`（可选：记录 Gemini/Llama 等来源）
- `AiAgent {agent_id, kind}`（CommonBot / ContractAgent / Whisperer / WorldEngine / PlayerAgent）
- `(a:AiAgent)-[:USES_MODEL]->(m:AiModel)`
- `(a:AiAgent)-[:EMITTED_EVENT {event_id, event_type, occurred_at}]->(x)`（与审计投影复用）

## 7. 市场时段与结算规则（时间映射 / 一天一个回合）

### 7.1 游戏时间映射（Real-time -> Game-time）
- 游戏整体以实时推进为主，但引入“游戏日历”用于节奏控制。
- 约定一个游戏起点时间 `GAME_EPOCH_UTC`，并通过配置 `SECONDS_PER_GAME_DAY` 定义“现实秒 -> 游戏日”的映射。
- 游戏日历的主要用途：
  - 市场时段切换（盘中/收盘缓冲/休市）
  - 周末/假期规则（休市但事件不停）
  - 日终统计（收盘价、账户估值快照、合约规则触发等）

### 7.2 一个游戏日（回合）的结构
一个游戏日被视为一个“回合”，但回合内部仍然是实时推进。

#### 7.2.1 TRADING（盘中连续竞价）
- 允许：
  - 挂单/撤单/撮合成交（撮合引擎持续运行）
  - 新闻、事件链、AI 行为照常运行
- 价格形成：连续竞价（continuous auction），成交写入市场成交记录，形成盘中价格序列。

#### 7.2.2 CLOSING_BUFFER（日终缓冲 + 收盘集合）
- 允许：
  - P2P 行为不受影响（聊天、合约、信息传播、谈判等）
  - 新闻与事件仍可发生（用于制造“收盘后消息”）
- 限制：
  - 市场挂单/撮合暂停（新订单可拒绝或排队到下个 TRADING）
- 数据动作：
  - 执行收盘集合统计（closing call / close price）
  - 产出“收盘价锚点”，用于日终估值/合约结算/AI 策略基准

### 7.3 HOLIDAY（放假/休市期）
- 触发：每隔若干回合出现一段放假期（可配置或由剧情事件触发）。
- 允许：
  - 新闻、事件链、AI、合约、P2P 行为持续运行
- 限制：
  - 市场不开市（不进入 TRADING；订单/撮合禁用）
- 设计目标：为“周末紧急应对/假期黑天鹅”等玩法提供空间。
