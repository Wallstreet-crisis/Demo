# Information Frontier Backend

## 运行
- 安装依赖（任选一种）：
  - `pip install -r requirements.txt`

- 启动：
  - `uvicorn ifrontier.app.main:app --reload --port 8010 --app-dir src`  

## 数据与依赖

### SQLite
- 本项目使用 SQLite 落盘到 `backend/data/ledger.db`（首次启动会自动创建表）。
- 当前后端主运行链路（账户、账本、订单、事件、新闻、社交关系、托管等）均以 SQLite 为权威存储。

### 前端
- frontend\vite.config.ts   去看这个配置

### Neo4j
- 项目正在从 Neo4j 完全迁移到 SQLite。
- 当前后端主流程已不再依赖 Neo4j 才能启动或运行。
- 仓库中仍可能保留少量历史文档表述，需按 SQLite 现状理解。

### 大模型（可选，但托管AI/ContractAgent会用到）
- 通过 OpenRouter 调用（代码在 `src/ifrontier/infra/llm/openrouter.py`）。
- 环境变量：
  - `OPENROUTER_API_KEY`：必填（启用 LLM 能力）
  - `OPENROUTER_MODEL`：可选，默认 `google/gemini-2.5-flash`
  - `OPENROUTER_BASE_URL`：可选，默认 `https://openrouter.ai/api/v1`
  - `OPENROUTER_TIMEOUT_SECONDS`：可选，默认 `20`
- 未配置 `OPENROUTER_API_KEY` 时：
  - Contract Agent 会回退到模板/正则解析
  - 托管用户 HostingAgent 会保持 IDLE（仍会写审计事件，但不会调用 LLM）

## WebSocket
- `ws://localhost:8000/ws/{channel}`

常用 channel：
- `events`：全局事件流
- `chat.public.global`：公屏聊天
- `chat.pm.{thread_id}`：私聊频道

## HTTP
- `GET /health`
- `POST /debug/emit_event`

### Contract Agent
- `POST /contract-agent/draft`
- `GET /contract-agent/context/{actor_id}`
- `POST /contract-agent/context/{actor_id}/clear`

### Chat（支持匿名/实名）
- `POST /chat/public/send`
- `GET /chat/public/messages`
- `POST /chat/pm/open`
- `POST /chat/pm/send`
- `GET /chat/pm/{thread_id}/messages`
- `GET /chat/threads/{user_id}`

### Hosting（托管用户AI）
- `POST /hosting/{user_id}/enable`
- `POST /hosting/{user_id}/disable`
- `GET /hosting/{user_id}/status`
- `POST /hosting/debug/tick_once`

## 测试
- `pytest -q`
