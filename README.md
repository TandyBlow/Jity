# Jity

Jity 是一个 AI 驱动的中文文字跑团项目。FastAPI 后端负责会话状态、知识库检索、提示词组装、LLM 调用和战役数据管理；Next.js 前端提供游戏控制台、战役编辑器和剧情时间线。

当前 `tian` 分支正在开发 Campaign Narrative Engine，用结构化的 Arc、Session 和 Anchor Event 约束长篇剧情走向。该部分仍处于集成阶段，不建议直接作为稳定版本发布。

## 主要功能

- 自由输入行动或点击选项，生成下一幕剧情、NPC 对话和可选行动。
- 使用 SQLite 保存游戏会话、消息、模型输出和结构化记忆。
- 从 `knowledge/` 加载 NPC、地点、任务、规则和世界观资料，进行轻量 RAG 检索。
- 使用 Campaign 描述叙事弧、章节开场和关键锚点事件。
- 提供战役策展编辑器、发现时间线和小说 TXT 转战役接口。
- 没有配置 API Key 时仍可运行固定开场；进入 LLM 生成阶段后必须配置 API Key。

## 项目结构

| 路径 | 职责 |
|---|---|
| `backend/app/main.py` | FastAPI 入口与 API 路由 |
| `backend/app/services/` | 剧情生成、状态管理、RAG、Campaign 和 LLM 服务 |
| `backend/app/schemas/` | 游戏与 Campaign 的 Pydantic 数据模型 |
| `backend/tests/` | 后端单元测试和集成测试 |
| `backend/data/` | 本地数据库、战役和小说运行数据 |
| `frontend/` | Next.js 游戏控制台 |
| `frontend/src/app/curator/` | 战役生成与编辑页面 |
| `frontend/src/app/timeline/` | 锚点和世界事实时间线 |
| `knowledge/` | RAG 知识库源文件 |
| `scripts/auto_play.py` | 自动长回合跑测与日志记录 |
| `index.html`、`api.js`、`game.js`、`ui.js` | 旧版 vanilla JS 原型，仅保留作参考 |

## 环境要求

- Python 3.11
- Node.js 20 或更高版本
- npm
- DeepSeek API Key（LLM 生成功能需要）

## 本地脚本

从仓库根目录执行：

```bash
scripts/setup_local.sh
```

该脚本会创建或更新 `jity-backend` Conda 环境、安装前端依赖、按需复制 `backend/.env.example` 到 `backend/.env`，并按需复制 `frontend/.env.example` 到 `frontend/.env.local`。

启动后端：

```bash
scripts/start_backend.sh
```

启动前端：

```bash
scripts/start_frontend.sh
```

同时启动前后端：

```bash
scripts/start_local.sh
```

默认地址：

- 后端：http://localhost:8000
- 前端：http://localhost:3000

可用环境变量覆盖端口：

```bash
JITY_BACKEND_PORT=8010 JITY_FRONTEND_PORT=3010 scripts/start_local.sh
```

清理本地缓存和构建产物：

```bash
scripts/clean_local.sh
```

清理依赖或运行时数据需要显式参数：

```bash
scripts/clean_local.sh --deps
scripts/clean_local.sh --runtime
```

`--runtime` 会删除本地数据库和跑测日志，执行前请确认不需要保留当前游戏状态。

## 启动后端

```bash
cd backend
conda env create -f environment.yml
conda activate jity-backend
cp .env.example .env
```

编辑 `backend/.env`：

```dotenv
DEEPSEEK_API_KEY=your_api_key
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-v4-flash
```

启动服务：

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

健康检查：

```bash
curl http://localhost:8000/health
```

## 启动前端

```bash
cd frontend
npm ci
cp .env.example .env.local
npm run dev
```

浏览器打开 [http://localhost:3000](http://localhost:3000)。

默认请求地址为 `http://localhost:8000`，可以在 `frontend/.env.local` 中修改：

```dotenv
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

## Campaign 系统

Campaign JSON 的主要层级为：

```text
Campaign
└── Arc
    └── Session
        ├── Opening Scene
        └── Anchor Events
```

相关页面：

- `/`：游戏控制台与战役选择。
- `/curator`：生成、上传、编辑和保存 Campaign。
- `/timeline`：查看叙事弧、锚点揭示状态和世界事实。
- `/dev-log`：开发记录，生产环境默认关闭。

相关 API：

- `GET /campaigns`：列出本地 Campaign。
- `GET /campaigns/{filename}`：读取 Campaign。
- `POST /campaigns/save`：保存编辑后的 Campaign。
- `POST /campaigns/generate`：根据提示词生成 Campaign。
- `POST /campaigns/generate-from-novel`：从 TXT 小说生成 Campaign。
- `POST /sessions`：创建自由模式或 Campaign 会话。
- `POST /sessions/{session_id}/generate`：生成下一幕。
- `GET /sessions/{session_id}/progress`：读取 Campaign 进度。

## 自动跑测

启动后端后，在仓库根目录执行：

```bash
python3 scripts/auto_play.py --runs 1 --turns 5
```

长回合测试：

```bash
python3 scripts/auto_play.py \
  --api-base-url http://localhost:8000 \
  --model deepseek-v4-flash \
  --runs 3 \
  --turns 300 \
  --retries 2
```

日志默认写入 `playtest_logs/`，该目录不会提交到 Git。

## 测试与构建

后端：

```bash
cd backend
python -m pytest -q
```

前端：

```bash
cd frontend
npm run build
```

## 本地文件约定

以下内容不得提交：

- `.env`、`.env.local` 和 API Key。
- SQLite 数据库与运行时数据。
- `node_modules/`、`.next/`、Python 虚拟环境和缓存。
- 自动跑测日志和原始小说 TXT。

需要提交的内容包括源码、依赖清单、`.env.example`、知识库源文件，以及经过审核的示例 Campaign。

## License

MIT
