# AI Architecture

## 1. 目标

AI 系统负责：

- 让 CommonBot 根据新闻与市场数据产生交易行为
- 让 ContractAgent 参与合约生成与解析
- 让 HostingAgent 代替离线玩家执行有限动作
- 让世界事件与新闻系统形成联动

## 2. 总体原则

- AI 不是独立持久化系统。
- AI 的结果统一写回现有事件系统。
- AI 读取的数据来自 SQLite 权威存储。
- AI 只能通过服务层或 facade 访问能力，不能绕开权限边界。

## 3. 关键组件

### 3.1 `CommonBotEmergencyRunner`

负责让 Bot 在新闻广播、市场开盘等场景下快速反应。

输入：

- 新闻上下文
- 市场数据
- Bot 账户状态

输出：

- `ai.commonbot.decision`
- 可能触发 `trade.*`

### 3.2 `HostingAgent`

面向托管用户：

- 通过 `UserCapabilityFacade` 获取受限观测
- 使用 LLM 或降级策略生成动作
- 将行为落到已有交易 / 合约 / 新闻接口

### 3.3 `ContractAgent`

负责：

- 合约草拟
- 合约上下文理解
- 规则辅助生成

### 3.4 `NewsTickEngine`

负责：

- 前兆生成
- 事件链推进
- 广播时机控制

## 4. 当前数据来源

AI 读取的数据主要来自：

- `events`
- `news`
- `news_deliveries`
- `accounts`
- `positions`
- `orders`
- 市场相关表
- 合约相关表

## 5. 审计

AI 相关动作应当可追踪：

- 输入上下文来自哪里
- 输出做了什么
- 是否触发下游交易 / 新闻 / 合约行为

最终仍统一落到事件与业务存储，而不是独立图模型。

## 6. 当前迁移结论

- 旧 Neo4j 图模型已不再作为 AI 的运行基础
- AI 层当前依赖 SQLite 读模型与服务层
- 后续新增 AI 能力应继续沿用 SQLite + Event Store 的架构
