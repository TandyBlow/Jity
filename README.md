# Jity

Jity 是一个 AI 驱动的中文文字跑团项目。FastAPI 后端负责会话状态、知识库检索、提示词组装、LLM 调用和战役数据管理；Next.js 前端提供游戏控制台、战役编辑器和剧情时间线。

Campaign Narrative Engine 使用结构化的 Arc、Session 和 Anchor Event 约束长篇剧情走向；剧情时间线为每个回合保存分支快照，允许恢复历史节点并建立新分支。后台摘要只在活动节点和版本仍匹配时补齐该快照的记忆字段，不改写剧情正文。

## 主要功能

- 自由输入行动或点击选项，生成下一幕剧情、NPC 对话和可选行动。
- 使用 SQLite 保存游戏会话、消息、模型输出和结构化记忆。
- 从 `knowledge/` 加载 NPC、地点、任务、规则和世界观资料，进行轻量 RAG 检索。
- 使用 Campaign 描述叙事弧、章节开场和关键锚点事件。
- 提供战役策展编辑器、可恢复的分支剧情时间线和小说 TXT 转战役接口。
- 新建战役会话时自动创建存档，加载时恢复对应时间线节点、角色状态和战役进度。
- 战役行动由本地 Python Examiner 检查，再由 LLM Director 和 Narrator 组织剧情。
- 支持浏览器自动跑团，以及可选的 AI 场景背景生成与缓存。
- 固定开场正文来自战役，但选项仍由模型生成，因此开始游玩也需要 API Key。
- 加载存档和设置菜单支持按槽 ID 确认删除，包括活动存档；不删除会话或共享剧情节点，继续游戏时会重新自动存档。
- 整局与最后章节预算负责及时收束；物品账本、长期摘要及待摘要输入跟随分支快照保存，背包无固定条数上限。

## 技术栈与回合流程

前端使用 Next.js 15、React 19、TypeScript 和 Tailwind CSS；后端使用 FastAPI、Pydantic 和 SQLite。知识源采用 JSON / Markdown，当前 RAG 使用 NumPy 向量评分与关键词加权。知识库只在启动时加载一次；重载时替换检索器，保留会话锁、记忆缓存和后台任务。

战役中的普通生成回合按以下流程执行：

```text
玩家行动 → 读取当前分支状态与历史 → 知识检索与提示词组装
         → 本地 Examiner → LLM Director → LLM Narrator
         → 校验物品与最终结局 → 采集最终记忆 → 原子提交状态、节点和战役进度
         → 独立副本后台摘要 → 按节点与版本比较写回
```

生成入口统一为战役；旧自由会话仅可读取。战役有固定开场时读取正文并调用模型生成选项。本地 Examiner 检查明确的物品、NPC、地点和资源前置条件，阻止不满足条件的行动，并标记需要处理的检定；目前不掷骰、不计算命中或伤害。详见 [本地 Examiner](docs/local_examiner.md) 和 [记忆与一致性](docs/campaign_memory.md)。

生成失败或取消会恢复运行时进度。后台摘要失败保留输入、重启后重试，切档或恢复节点后迟到摘要不得覆盖新分支。预算结局仍需事实条件；普通结局拒绝否定、假设与多路线歧义选择。界面保留设置、记忆抽屉、节点对比、提示词追踪及回合进度；HTTP 409 会重新读取当前节点，刷新失败会明确报错。

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
| `eval/` | 长期一致性评测工具、冻结题库和独立回归测试 |

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

### 存档归属与用途

存档列表按会话的 `account_id` 和 `save_purpose` 查询；命名存档、自动保存和时间线分支继承原会话的归属与用途。当前尚未实现账号登录，`account_id` 为 `NULL`，表示本地未绑定账号，不能将其视为已完成多用户身份认证。之后接入登录时，应由 `get_save_scope` 从已认证身份取得账号 ID，并为全部会话接口启用授权检查；禁止信任客户端提交的账号 ID。

浏览器新游戏标记为 `user`，列表默认显示“游玩存档”，可分别查看“开发存档”“测试存档”和“历史未分类”。API 通过 `X-Jity-Save-Purpose: user | development | test | legacy` 选择列表用途；未传时默认为 `development`，跑测脚本明确传 `test`。用途只用于分类，不是权限凭据，`legacy` 仅用于旧存档查询，不能用于新建游戏。

旧存档没有可靠来源记录，迁移时统一保留为 `legacy`，不会按名称猜测归属、删除数据或自动认领到某个账号。可在“历史未分类”中继续加载和管理。后端 pytest 在应用导入前强制切换到独立临时数据库，不再向 `backend/data/jity.sqlite3` 写入测试会话。

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
归档失败只会记录 warning，不会中断游戏。Embedding 输入、固定开场正文和图片缓存命中不会生成记录；固定开场选项的模型调用仍会记录。

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
- `/dev-log`：开发记录，开始页右上角可进入；设置 `ENABLE_DEV_LOG=false` 可关闭。

新建战役后可直接开始游戏，自动存档名称采用 `auto_日期_时间` 格式。时间线保留「剧情分支、战役锚点、世界线索」三个页签；先预览历史节点，再恢复并返回游戏继续，原来的后续节点仍然保留。继续生成时只读取当前分支的祖先消息，避免混入其他分支的剧情。

相关 API：

- `GET /campaigns`：列出本地 Campaign。
- `GET /campaigns/{filename}`：读取 Campaign。
- `POST /campaigns/save`：保存编辑后的 Campaign。
- `POST /campaigns/generate`：根据提示词生成 Campaign。
- `POST /campaigns/generate-from-novel`：从 TXT 小说生成 Campaign。
- `POST /sessions`：创建 Campaign 会话，省略文件名时使用默认战役；旧自由会话仍可读取但不能生成。
- `POST /sessions/{session_id}/generate`：生成下一幕。
- `GET /campaigns/slots`：列出存档，可通过 `session_id` 筛选。
- `POST /campaigns/slots/{slot_id}/load`：加载存档及其时间线节点。
- `DELETE /campaigns/slots/{slot_id}`：仅删除指定存档槽；不存在返回 404，活动槽返回 409，不删除会话或共享节点。
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

自动选择选项的关键词权重位于 `scripts/auto_play_config.json`，仅供跑测脚本使用，不影响后端运行规则。脚本不再读取 `backend/scripts/option_config.json`。

四战役跨幕真实 LLM 冒烟测试：

```bash
python scripts/campaign_transition_smoke.py
```

脚本通过临时的两回合 Campaign 副本依次执行“开场 → 继续 → 下一幕开场 → 继续”，记录提示词、地点、人物、剧情、模型来源与连续性检查，并在结束后删除临时 Campaign。新报告写入本地 `artifacts/smoke/`，已保留的历史报告见 `docs/research/reports/smoke/`；维护细节见 [分支剧情时间线开发文档](docs/branching_timeline.md)。

### 回合预算配置

- 每幕预算：战役中当前幕的 `max_turns_per_session` → 战役级同名字段 → 后端 `MAX_TURNS_PER_SESSION`（默认 30）。现有整局预算分配规则仍会给后续章节预留回合。
- 整局预算：建档时选择并持久化的 `max_turns_per_campaign` → 战役级同名字段 → 后端 `MAX_TURNS_PER_CAMPAIGN`（默认 50）。保留 1–50 回合的产品边界及存档恢复行为。
- 后端默认值通过 `backend/.env` 配置，示例见 `backend/.env.example`。战役已有显式配置时优先使用战役配置；自动跑测的选择策略不能覆盖这些规则。

### 开发文档与研究材料

- 开发日志原始内容位于 [`docs/dev-log/`](docs/dev-log/README.md)，`/dev-log` 网页继续提供展示、搜索和筛选。
- 论文生成脚本、章节、配图和专用依赖位于 [`tools/research/`](tools/research/README.md)，不参与游戏运行。
- 已归档的 Examiner 与幕间转换历史报告位于 [`docs/research/reports/`](docs/research/README.md)。运行日志与新跑测输出保持独立，历史实验结论不代表当前版本的效果。

## 测试与构建

长期一致性评测已整合到 [`eval/`](eval/README.md)。从仓库根目录执行 `cd eval` 后可使用 `python -m jity_eval`；完整用法见 [评测集成说明](eval/docs/repository-integration.md)。评测的真实组件回放和录制数据必须保存在仓库外，不写入游戏存档。历史运行数据库继续留在原本地目录，不随源码上传。

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

浏览器测试（在 `frontend/` 中运行）：

```bash
npx playwright test
```

Playwright 会自动使用独立的 `.next-playwright/` 目录构建并在 3100 端口启动测试服务；
构建和启动共用 `JITY_PLAYWRIGHT=1`，类型检查使用 `tsconfig.playwright.json`。
开发服务继续使用 `.next/`，可与浏览器测试同时运行。测试构建产物已加入 Git 忽略规则。

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
