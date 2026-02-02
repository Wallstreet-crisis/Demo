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
