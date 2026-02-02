# 信息边境：AI / Agent 架构（部署级参考）

## 1. 总体定位
- AI 不是装饰 NPC，而是底层“流动性 / 契约生成 / 信息过滤 / 世界熵增调节”的模型库
- 后端落地原则：所有 AI 行为以 `EventEnvelope` 形式进入事件流，可审计、可回放、可推送

## 2. 四层 AI 分工
### 2.1 Common Bots（流动性源）
- **目标**：提供市场基础流动性，主观能动性低，响应“市场表象”
- **输入**：
  - 新闻卡 `visual_truth`（系统预置）与可选 `Truth_Tags`
  - 新闻变体的 `text_overlay`（FastText/关键词）
  - 价格动量 `W_trend`
- **输出**：
  - 交易意向/成交：`trade.intent_submitted` / `trade.executed`
  - 可观测解释：`ai.commonbot.decision`

### 2.2 Contract Agent（语义化逻辑翻译官）
- **目标**：把自然语言映射为受限 Python DSL（仅预置 Financial_Lib）
- **输出**：
  - `ai.contract.drafted`（含 python_preview + risk_rating）
  - 玩家确认后再进入 `contract.created/signed/activated`

### 2.3 Whisperer AI（信息过滤与虚假真相分析）
- **目标**：阶级特权 AI：溯源、冲突热力图、离线简报
- **输出**：
  - `ai.whisperer.assessment`（conflict_score + summary）
  - 简报可以后续扩展为 `ai.whisperer.briefing_generated`（暂不强制）

### 2.4 World Engine（熵增平衡器）
- **目标**：维护市场波动与暗示链（T-Minus 队列）
- **输出**：
  - `ai.world_event.omen_emitted`（暗示碎屑）
  - `ai.world_event.purchased`（富豪购买背景大卡）
  - `ai.world_event.resolved`（物理坍缩落地）

## 3. 玩家代理（Player Agent）
- **定位**：陪玩/托管，能力与玩家一致，但可调用后端接口进行自动化
- **事件链**：
  - `ai.player_agent.task_submitted` -> 过程触发 `trade.* / news.* / contract.*` -> `ai.player_agent.task_completed`

## 4. Neo4j 建议图模型（最小）
- `AiAgent {agent_id, kind}`
- `AiModel {model_id, name, provider}`
- `(AiAgent)-[:USES_MODEL]->(AiModel)`
- `(AiAgent)-[:EMITTED_EVENT]->(Any)`：用于审计投影（与现有 `EMITTED_EVENT` 兼容）

## 5. 与 WebSocket 的对接
- 建议按 Channel 分流：
  - `market.*`：行情与撮合
  - `news.*`：新闻变体与传播
  - `ai.*`：AI 决策解释/评估/暗示链
- 推送统一使用 `EventEnvelopeJson`
