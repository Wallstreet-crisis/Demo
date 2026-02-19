# React + TypeScript + Vite

## 项目启动（前后端）

> 这份是当前仓库可直接用的本地开发启动流程（前端 + 后端）。

### 0) 前置准备

- Python 环境：请在你自己的 conda 环境里运行后端。
- Node.js：用于运行前端（建议 Node 20+）。
- Neo4j：后端依赖 Neo4j（默认 `bolt://127.0.0.1:7687`）。

---

### 1) 启动后端（端口 8010）

在 `backend/` 目录执行：

```bash
uvicorn ifrontier.app.main:app --reload --port 8010 --app-dir src
```
Powershell: `docker start neo4j`


可选环境变量（按需）：

- `IF_NEO4J_URI`（默认 `bolt://localhost:7687`）
- `IF_NEO4J_USER`（默认 `neo4j`）
- `IF_NEO4J_PASSWORD`（默认 `password`）
- `OPENROUTER_API_KEY`（启用 LLM 能力时需要）

健康检查：

- `http://127.0.0.1:8010/health`

---

### 2) 启动前端（Vite）

在 `frontend/` 目录执行：

```bash
npm install
npm run dev
```

默认前端地址通常是：

- `http://127.0.0.1:5173`

当前项目的 Vite 代理默认转发到后端：

- `http://127.0.0.1:8010`（见 `frontend/vite.config.ts`）

所以前端请求 `/api/*` 会自动代理到后端，无需额外 CORS 配置。

---

### 3) 最快自检

1. 打开前端 `http://127.0.0.1:5173`
2. 进入页面后检查是否能正常请求 `/api/health`
3. 如果页面报后端不可用，先确认后端 `8010` 端口是否已启动

---

### 4) 常见问题

- 前端能开但接口全失败：
  - 先看后端是否在 `8010` 启动。
- 后端启动报 Neo4j 连接错误：
  - 检查 Neo4j 是否运行，以及 `IF_NEO4J_*` 是否正确。
- 改了前端但线上没变化（Docker 部署）：
  - 需要重建 web 镜像（`docker compose up -d --build web`）。

This template provides a minimal setup to get React working in Vite with HMR and some ESLint rules.

Currently, two official plugins are available:

- [@vitejs/plugin-react](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react/README.md) uses [Babel](https://babeljs.io/) for Fast Refresh
- [@vitejs/plugin-react-swc](https://github.com/vitejs/vite-plugin-react-swc) uses [SWC](https://swc.rs/) for Fast Refresh

## Development with backend

### 1) Start backend
Start the FastAPI backend first (default `http://127.0.0.1:8000`).

### 2) Start frontend
```bash
npm run dev
```

### Proxy (recommended)
This project proxies `http://localhost:<vite-port>/api/*` to the backend.

- Default backend target: `http://127.0.0.1:8000`
- You can override proxy target:
  - `VITE_PROXY_TARGET=http://127.0.0.1:8000`

The frontend API client defaults to calling `/api` so you usually do not need to configure CORS.

### Optional env vars
Create `frontend/.env.local` if needed:

```ini
# Override API base URL (default: /api)
VITE_API_BASE_URL=/api

# Override WebSocket base URL (optional)
# VITE_WS_BASE_URL=ws://127.0.0.1:8000

# Vite dev proxy target (optional)
# VITE_PROXY_TARGET=http://127.0.0.1:8000
```

## React Compiler

The React Compiler is not enabled on this template because of its impact on dev & build performances. To add it, see [this documentation](https://react.dev/learn/react-compiler/installation).

## Expanding the ESLint configuration

If you are developing a production application, we recommend updating the configuration to enable type-aware lint rules:

```js
export default defineConfig([
  globalIgnores(['dist']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      // Other configs...

      // Remove tseslint.configs.recommended and replace with this
      tseslint.configs.recommendedTypeChecked,
      // Alternatively, use this for stricter rules
      tseslint.configs.strictTypeChecked,
      // Optionally, add this for stylistic rules
      tseslint.configs.stylisticTypeChecked,

      // Other configs...
    ],
    languageOptions: {
      parserOptions: {
        project: ['./tsconfig.node.json', './tsconfig.app.json'],
        tsconfigRootDir: import.meta.dirname,
      },
      // other options...
    },
  },
])
```

You can also install [eslint-plugin-react-x](https://github.com/Rel1cx/eslint-react/tree/main/packages/plugins/eslint-plugin-react-x) and [eslint-plugin-react-dom](https://github.com/Rel1cx/eslint-react/tree/main/packages/plugins/eslint-plugin-react-dom) for React-specific lint rules:

```js
// eslint.config.js
import reactX from 'eslint-plugin-react-x'
import reactDom from 'eslint-plugin-react-dom'

export default defineConfig([
  globalIgnores(['dist']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      // Other configs...
      // Enable lint rules for React
      reactX.configs['recommended-typescript'],
      // Enable lint rules for React DOM
      reactDom.configs.recommended,
    ],
    languageOptions: {
      parserOptions: {
        project: ['./tsconfig.node.json', './tsconfig.app.json'],
        tsconfigRootDir: import.meta.dirname,
      },
      // other options...
    },
  },
])
```
