# Jity

Jity 是一个 AI 驱动的中文文字跑团项目。FastAPI 后端负责会话状态、知识库检索、提示词组装、LLM 调用和战役数据管理；Next.js 前端提供游戏控制台、战役编辑器和剧情时间线。

Campaign Narrative Engine 使用结构化的 Arc、Session 和 Anchor Event 约束长篇剧情走向；剧情时间线会为每个回合保存不可变快照，允许恢复任意历史节点并从该节点建立新分支。

## 主要功能

- 自由输入行动或点击选项，生成下一幕剧情、NPC 对话和可选行动。
- 使用 SQLite 保存游戏会话、消息、模型输出和结构化记忆。
- 从 `knowledge/` 加载 NPC、地点、任务、规则和世界观资料，进行轻量 RAG 检索。
- 使用 Campaign 描述叙事弧、章节开场和关键锚点事件。
- 提供战役策展编辑器、可恢复的分支剧情时间线和小说 TXT 转战役接口。
- 新建战役会话时自动创建存档，加载时恢复对应时间线节点、角色状态和战役进度。
- 战役行动由本地 Python Examiner 检查，再由 LLM Director 和 Narrator 组织剧情。
- 支持浏览器自动跑团，以及可选的 AI 场景背景生成与缓存。
- 没有配置 API Key 时仍可运行固定开场；进入 LLM 生成阶段后必须配置 API Key。

## 技术栈与回合流程

前端使用 Next.js 15、React 19、TypeScript 和 Tailwind CSS；后端使用 FastAPI、Pydantic 和 SQLite。知识源采用 JSON / Markdown，当前 RAG 使用 NumPy 向量评分与关键词加权；虽然会构建 FAISS 索引，当前排序路径仍由 NumPy 完成。

战役中的普通生成回合按以下流程执行：

```text
玩家行动 → 读取当前分支状态与历史 → 知识检索与提示词组装
         → 本地 Examiner → LLM Director → LLM Narrator
         → 合并角色状态与记忆 → 推进战役 → 保存剧情节点与存档进度
```

自由模式使用单次叙事生成路径；战役有固定开场时直接读取开场文本。本地 Examiner 检查明确的物品、NPC、地点和资源前置条件，阻止不满足条件的行动，并标记需要处理的检定；目前不掷骰、不计算命中或伤害。详见 [本地 Examiner](docs/local_examiner.md)。

## 项目结构

| 路径 | 职责 |
|---|---|
| `backend/app/main.py` | FastAPI 入口、路由注册与静态资源挂载 |
| `backend/app/routers/` | 会话、生成、战役、存档与背景图 API |
| `backend/app/database/` | SQLite 表结构、会话、消息与时间线快照持久化 |
| `backend/app/services/` | 剧情生成、状态管理、RAG、Campaign 和 LLM 服务 |
| `backend/app/schemas/` | 游戏与 Campaign 的 Pydantic 数据模型 |
| `backend/tests/` | 后端单元测试和集成测试 |
| `backend/data/` | 本地数据库、战役和小说运行数据 |
| `frontend/` | Next.js 游戏控制台 |
| `frontend/src/app/curator/` | 战役生成与编辑页面 |
| `frontend/src/app/timeline/` | 剧情分支树、节点快照和恢复界面 |
| `docs/branching_timeline.md` | 分支时间线、跨幕上下文和回归测试维护说明 |
| `knowledge/` | RAG 知识库源文件 |
| `scripts/auto_play.py` | 自动长回合跑测与日志记录 |
| `index.html`、`api.js`、`game.js`、`ui.js` | 旧版 vanilla JS 原型，仅保留作参考 |

## 环境要求

- Python 3.11（Conda 环境配置；CI 使用 Python 3.12）
- Conda（使用一键安装脚本时需要）
- Node.js 20 或更高版本
- npm
- DeepSeek API Key（LLM 生成功能需要）

## 本地脚本

首次下载项目：

```bash
git clone https://github.com/TandyBlow/Jity.git
cd Jity
```

从仓库根目录执行：

```bash
scripts/setup_local.sh
```

该脚本会创建或更新 `jity-backend` Conda 环境、安装前端依赖、按需复制 `backend/.env.example` 到 `backend/.env`，并按需复制 `frontend/.env.example` 到 `frontend/.env.local`。

安装完成后，先在 `backend/.env` 中填写 `DEEPSEEK_API_KEY`，再启动服务。

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

- 后端：[http://localhost:8000](http://localhost:8000)
- 前端：[http://localhost:3000](http://localhost:3000)
- API 文档：[http://localhost:8000/docs](http://localhost:8000/docs)

联合启动的日志位于 `.local/logs/backend.log` 和 `.local/logs/frontend.log`，按 `Ctrl+C` 停止服务。

可用环境变量覆盖端口：

```bash
JITY_BACKEND_PORT=8010 JITY_FRONTEND_PORT=3010 scripts/start_local.sh
```

修改端口后，还需同步设置 `frontend/.env.local` 中的 `NEXT_PUBLIC_API_BASE_URL=http://localhost:8010`，以及 `backend/.env` 中的 `FRONTEND_ORIGIN=http://localhost:3010`，然后重启服务。启动脚本不会自动修改这两项配置。

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
PROMPT_LOGGING_ENABLED=false
PROMPT_LOG_DIR=data/prompt_logs
```

如需为论文分析归档所有生成式 API 的完整 Prompt，将
`PROMPT_LOGGING_ENABLED` 改为 `true` 并重启后端。每次文本或图片生成请求会在
`PROMPT_LOG_DIR/YYYY-MM-DD/` 下保存一个 JSON 文件；终端只显示文件路径。
归档失败只会记录 warning，不会中断游戏。Embedding 输入、固定开场和图片缓存命中不会生成记录。

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

如果前端使用 `npm run dev -- -p 3100` 启动，后端也已允许 `http://localhost:3100` 和 `http://127.0.0.1:3100` 的跨域请求。

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
- `/timeline`：查看剧情分支树、节点剧情与状态，并从历史节点继续。
- `/dev-log`：开发记录，生产环境默认关闭。

新建战役后可直接开始游戏，自动存档名称采用 `auto_日期_时间` 格式。时间线保留「剧情分支、战役锚点、世界线索」三个页签；先预览历史节点，再恢复并返回游戏继续，原来的后续节点仍然保留。继续生成时只读取当前分支的祖先消息，避免混入其他分支的剧情。

相关 API：

- `GET /campaigns`：列出本地 Campaign。
- `GET /campaigns/{filename}`：读取 Campaign。
- `POST /campaigns/save`：保存编辑后的 Campaign。
- `POST /campaigns/generate`：根据提示词生成 Campaign。
- `POST /campaigns/generate-from-novel`：从 TXT 小说生成 Campaign。
- `POST /sessions`：创建自由模式或 Campaign 会话。
- `POST /sessions/{session_id}/generate`：生成下一幕。
- `GET /campaigns/slots`：列出存档，可通过 `session_id` 筛选。
- `POST /campaigns/slots/{slot_id}/load`：加载存档及其时间线节点。
- `GET /sessions/{session_id}/progress`：读取 Campaign 进度。
- `GET /sessions/{session_id}/timeline`：读取完整剧情分支树和当前路径。
- `GET /sessions/{session_id}/timeline/{node_id}`：读取节点的剧情、状态和 Campaign 快照。
- `POST /sessions/{session_id}/timeline/{node_id}/activate`：恢复指定节点；下一次生成会从这里建立新分支。

## 自动跑测

### 浏览器自动跑团

打开 [自动跑团入口](http://localhost:3000/?autoplay=1&turns=20&delay=1000&seed=42)，选择战役并开始游戏。也可添加 `session=会话ID` 恢复指定会话。

- `turns`：目标总回合数，达到该值或游戏结束时停止，并非额外执行的回合数。
- `delay`：自动选择行动后的等待时间，单位为毫秒。
- `seed`：选项评分中随机扰动的种子，不保证 LLM 输出可复现。

浏览器按当前目标、任务、推进关键词和近期重复情况选择选项，可在页面暂停与继续。自动跑团需要保持游戏页面打开，并会实际调用配置的 LLM API。

### 命令行跑测

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

四战役跨幕真实 LLM 冒烟测试：

```bash
python scripts/campaign_transition_smoke.py
```

脚本通过临时的两回合 Campaign 副本依次执行“开场 → 继续 → 下一幕开场 → 继续”，记录提示词、地点、人物、剧情、模型来源与连续性检查，并在结束后删除临时 Campaign。报告写入 `artifacts/smoke/`；维护细节见 [分支剧情时间线开发文档](docs/branching_timeline.md)。

## 测试与构建

后端：

```bash
cd backend
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

前端：

```bash
cd frontend
npm run build
```

## 可选背景图配置

在 `backend/.env` 中配置 `IMAGE_API_KEY`、`IMAGE_BASE_URL`、`IMAGE_API_PROVIDER` 和 `IMAGE_MODEL` 可启用场景背景生成，完整默认值见 [后端配置模板](backend/.env.example)。生成图片缓存在 `backend/data/backgrounds/`，未配置图片服务时仍可进行文字游戏。

## 开发文档

- [本地 Examiner 规则与边界](docs/local_examiner.md)
- [分支时间线与跨幕上下文](docs/branching_timeline.md)
- [运行循环调用链地图](docs/runtime_call_map.md)
- [知识库组织说明](knowledge/README.md)

## 本地文件约定

以下内容不得提交：

- `.env`、`.env.local` 和 API Key。
- SQLite 数据库与运行时数据。
- `node_modules/`、`.next/`、Python 虚拟环境和缓存。
- 自动跑测日志和原始小说 TXT。

需要提交的内容包括源码、依赖清单、`.env.example`、知识库源文件，以及经过审核的示例 Campaign。

## Dice checks and third-party attribution

Options that require a check open a dice overlay in the console, which rolls a physics d20 before the outcome is applied.

That overlay uses `open-dice-dnd@1.3.1`, from [richardhealy/open-dice](https://github.com/richardhealy/open-dice), for the Three.js + Cannon-es 3D physics d20, face textures, authoritative `rolled` values, shadows, and settled effects. The integration locks the result before the animation and passes the same value to the renderer so the final number is shown on the landed die face.

`open-dice-dnd` is MIT-licensed. Its license text is distributed in `frontend/node_modules/open-dice-dnd/LICENSE` during development and must be included in the release third-party notices.

## License

MIT
