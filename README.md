# Jity

AI 驱动文字跑团游戏。FastAPI 后端负责会话状态、知识库检索、提示词组装和 LLM 调用，Next.js 前端提供 GM scenario console。

## 功能

- 自由输入玩家行动，生成下一幕剧情、NPC 对话和可选行动。
- SQLite 保存 session、消息、模型输出和知识库 chunk。
- `knowledge/` 中的 Markdown/JSON 会被后端加载为轻量 RAG 知识源。
- 没有配置 API key 时，后端会返回 fallback 输出，方便本地调试 UI 和 API 链路。

## 项目结构

| 路径 | 职责 |
|------|------|
| `backend/app/main.py` | FastAPI 入口，提供 health、session、generate、evaluate、knowledge reload 接口 |
| `backend/app/services/` | 状态管理、知识库加载、检索、prompt 构建、LLM 客户端和剧情生成 |
| `backend/data/` | 本地 SQLite 运行数据，默认不提交 |
| `frontend/` | Next.js 前端控制台 |
| `knowledge/` | JSON/Markdown 知识库源文件 |
| `index.html`、`api.js`、`game.js`、`ui.js` | 旧版 vanilla JS 前端，保留作参考 |

## 后端启动

```bash
cd backend
conda env create -f environment.yml
conda activate jity-backend
cp .env.example .env
```

如果环境已经创建过，只需要更新依赖：

```bash
cd backend
conda env update -f environment.yml --prune
conda activate jity-backend
```

可选：编辑 `backend/.env`，填入 DeepSeek 配置：

```bash
DEEPSEEK_API_KEY=your_api_key
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-chat
```

启动 API：

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

检查服务：

```bash
curl http://localhost:8000/health
```

## 前端启动

```bash
cd frontend
npm install
cp .env.example .env.local
npm run dev
```

浏览器打开：

```text
http://localhost:3000
```

默认前端会请求 `http://localhost:8000`。如需修改后端地址，编辑 `frontend/.env.local`：

```bash
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

## API 概览

- `GET /health`：检查数据库、知识库 chunk 数量和检索后端。
- `GET /models`：返回可选模型名。
- `POST /sessions`：创建新游戏会话。
- `GET /sessions/{session_id}`：读取会话状态。
- `POST /sessions/{session_id}/generate`：根据玩家行动生成下一幕。
- `POST /evaluate`：对结构化剧情输出做轻量启发式评分。
- `POST /knowledge/reload`：重新加载 `knowledge/` 和可选规则书。

## 知识库格式

`knowledge/` 支持两类文件：

- `.json`：数组或 `{ "entries": [...] }`，每条记录可包含 `title`、`source_type`、`keywords`、`content`。
- `.md`：按 Markdown 标题切分为 chunk。

当前检索是轻量词袋哈希向量加 FAISS/NumPy 相似度检索，不依赖外部 embedding 服务。

## 版本控制约定

这个项目拆成两套本地环境：

- Backend：Anaconda/Conda 管理 Python 与 FastAPI 依赖，配置在 `backend/environment.yml`。
- Frontend：Node/npm 单独管理 Next.js、React 依赖，配置在 `frontend/package.json`。
- `.env` 只保存在本地，提交示例文件 `.env.example`。
- 不要提交 Conda/venv 目录、SQLite 运行库、Next 构建产物或 `node_modules/`。

源码、示例 env、知识库源文件和依赖清单应提交。

## License

MIT
