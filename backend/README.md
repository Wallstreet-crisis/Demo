# Information Frontier Backend

## 运行
- 安装依赖（任选一种）：
  - `pip install -r requirements.txt`

- 启动：
  - `uvicorn ifrontier.app.main:app --reload --port 8000`

## WebSocket
- `ws://localhost:8000/ws/{channel}`

## Neo4j
- 初始化 Cypher：`backend/scripts/neo4j/init.cypher`
