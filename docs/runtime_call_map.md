# 运行循环调用链地图（可核对版）

覆盖范围：**在线回合循环**——一次 `POST /sessions/{session_id}/generate` 请求从进入后端到返回的完整调用链。
不覆盖：campaign 生成/编辑流（`campaign_generator/`、`routers/campaigns.py`）、知识库重载（`/meta`）、
`scripts/` 下的跑测脚本、前端内部实现。

> **读法**：先看下面的"一图流"掌握形状；后文的 EDGE 清单是给
> `verify_callmap.py` 核对用的索引，**不需要通读**——迷路时按行号跳代码用。

## 怎么核对这份地图

```bash
# 1. 核对下文每条 EDGE 是否真实存在于代码（行号漂移会报 BROKEN）
python scripts/verify_callmap.py check docs/runtime_call_map.md

# 2. 完整性反查：打印"调用了关键协作对象但地图没收录"的调用点
python scripts/verify_callmap.py missing docs/runtime_call_map.md
```

- 所有 `EDGE:` 行由 `scripts/verify_callmap.py` 用 stdlib AST 从代码机械提取，非人工转写。
- `check` 的覆盖文件集 = 脚本顶部 `CHECK_SCOPE`；`missing` 只反查 `WATCH` 名单中的协作对象
  （`state_manager`、`retriever`、`prompt_builder`、`llm_client`、`campaign_manager`、`memory_ctrl`、
  `knowledge_service`、`evaluation_module`、`db`、`knowledge`、`scripted_story`、`_llm`）。
- 同文件内部的私有辅助调用（如 `self._evict`）不参与反查，地图只选择性收录；
  prose 中的行号引用（无 EDGE 前缀）需人工跳转核对。
- 目标串规范化：属性链按点号拼接；夹在链中的表达式记作 `(...).方法名`。

---

## 一图流：一个回合的形状

```
玩家输入
  │
  ▼
routers/generate.py:17 ──出错──▶ 503 无Key / 502 LLM失败 / 404 会话不存在
  │
  ▼
ScenarioGenerator.generate (generator.py:56)
  │
  ├─1▶ 取会话状态 + 取战役管理器(带TTL缓存)      manager.py:36  campaign_cache.py:105
  │
  ├─2▶ [Hook1] turn==0 且有开场白? ──是──▶ 返回剧本开场(source=scripted)，不调LLM
  │
  ├─3▶ [Hook2] 组装提示词                        prompting.py:7
  │        RAG检索(向量+关键词) + 战役上下文注入 + 按优先级截断
  │
  ├─4▶ [Hook3] 生成                              agent_pipeline.py:17
  │        有战役: ①Examiner 行动可行? ──blocked──▶ 叙事内拒绝，提前返回
  │                ②Director 锚点/偏差/重定向 → 注入导演指令
  │                ③Narrator 调LLM 产出剧情JSON
  │        无战役: 一次LLM调用(旧行为)
  │        JSON坏了: 本地修 → 模型temperature=0重修 → 才报错
  │
  ├─5▶ 状态推进(纯本地代码)                      manager.py:50
  │        SAN/体力/回合、物品NPC任务按名合并、事件追加、超限裁剪
  │
  ├─6▶ [Hook4] 每5回合LLM抽世界事实; NPC好感写库  post_generation.py:10
  │
  ├─7▶ 对话×2落库 + 状态存盘                     generator.py:91-93
  │
  ├─8▶ [Hook5] 唯一推进点: 提交锚点→turn+1→满则进下一session   generator.py:124
  │
  ▼
GenerateResponse（新状态 + 剧情 + 检索块 + source标记）──▶ 前端
```

---

## 0. 启动期（import 时，先于任何请求）

uvicorn 载入 `app.main`，import 链按顺序执行：

1. `backend/app/main.py:6-7` — import config 与 routers；
2. routers → `backend/app/dependencies/__init__.py:16-38` → `backend/app/dependencies/singletons.py:21-43`
   —— **第一次真正的 `get_settings()` 调用在这里**（config.py:22 定义，`@lru_cache` 单例），
   随后逐个创建 `Database`、`KnowledgeBase`（并 `load_chunks`）、`GameStateManager`、`LLMClient` 等单例；
3. `backend/app/dependencies/__init__.py:40-50` — 组装 `KnowledgeService`，
   其构造函数（`backend/app/dependencies/knowledge_service.py:44-46`）重建 chunks/retriever 并创建
   `ScenarioGenerator`（:49-58，注入 `campaign_manager_provider=get_campaign_manager_for_session`，:56）；
4. `backend/app/main.py:11-26` — 创建 FastAPI app、挂 CORS（:12-18）、include_router
   （slots 必须在 campaigns 之前，见 :20-21 注释）。

EDGE（启动期调用，同样可核对）：

EDGE: backend/app/dependencies/singletons.py:24 -> knowledge.load_chunks
EDGE: backend/app/dependencies/knowledge_service.py:44 -> knowledge.load_chunks
EDGE: backend/app/dependencies/knowledge_service.py:63 -> self.knowledge.load_chunks
EDGE: backend/app/dependencies/knowledge_service.py:45 -> RAGRetriever
EDGE: backend/app/dependencies/knowledge_service.py:46 -> self._build_scenario_generator
EDGE: backend/app/dependencies/knowledge_service.py:49 -> ScenarioGenerator

---

## 1. 一次生成回合的完整序列

前端入口：`frontend/src/lib/api.ts:12` 定义 `API_BASE_URL`（默认 `http://localhost:8000`），
:148 拼接请求 URL；`POST {API_BASE_URL}/sessions/{session_id}/generate`。

### Step 0 — 路由进入

`backend/app/routers/generate.py:17` `generate()` 把请求整体交给 ScenarioGenerator。

EDGE: backend/app/routers/generate.py:19 -> knowledge_service.scenario_generator.generate

错误映射（generate.py:20-25）：`MissingAPIKeyError`→503、`ScenarioGenerationError`→502、
session 不存在→404。另一个在线端点 `POST /evaluate`（generate.py:29-31）：

EDGE: backend/app/routers/generate.py:31 -> evaluation_module.score

### Step 1 — 读会话与战役管理器

generate.py:56-64：读会话 payload；取 campaign_manager（provider 是注入的
`get_campaign_manager_for_session`，带 TTL 缓存，未命中则从 campaigns 目录重新 load）。

EDGE: backend/app/services/scenario_generator/generator.py:57 -> self.state_manager.get_session_payload
EDGE: backend/app/services/game_state/manager.py:37 -> self.db.get_session
EDGE: backend/app/services/scenario_generator/generator.py:63 -> self._campaign_manager_for
EDGE: backend/app/services/scenario_generator/generator.py:155 -> self.campaign_manager_provider
EDGE: backend/app/services/scenario_generator/generator.py:160 -> campaign_manager.is_loaded
EDGE: backend/app/dependencies/campaign_cache.py:109 -> db.get_session
EDGE: backend/app/dependencies/campaign_cache.py:113 -> campaign_manager_cache.get_or_load
EDGE: backend/app/dependencies/campaign_cache.py:77 -> build_campaign_manager
EDGE: backend/app/dependencies/campaign_cache.py:95 -> CampaignManager
EDGE: backend/app/dependencies/campaign_cache.py:78 -> manager.load

### Step 2 — Hook 1：开场早退（不走 LLM）

`opening_scene.py`：turn==0 且战役带开场白时，直接返回剧本输出（source="scripted"），
但落库与推进流程与普通回合一致。

EDGE: backend/app/services/scenario_generator/generator.py:67 -> self._handle_opening_scene
EDGE: backend/app/services/scenario_generator/opening_scene.py:11 -> campaign_manager.is_loaded
EDGE: backend/app/services/scenario_generator/opening_scene.py:14 -> campaign_manager.get_opening_scene
EDGE: backend/app/services/scenario_generator/opening_scene.py:19 -> StoryOutput
EDGE: backend/app/services/scenario_generator/opening_scene.py:28 -> self.db.add_message
EDGE: backend/app/services/scenario_generator/opening_scene.py:29 -> self.db.add_message
EDGE: backend/app/services/scenario_generator/opening_scene.py:30 -> self.state_manager.apply_output
EDGE: backend/app/services/scenario_generator/opening_scene.py:31 -> self.state_manager.save_state
EDGE: backend/app/services/scenario_generator/opening_scene.py:33 -> campaign_manager.record_turn
EDGE: backend/app/services/scenario_generator/opening_scene.py:34 -> self.db.add_model_output
EDGE: backend/app/services/scenario_generator/opening_scene.py:43 -> self._advance_campaign
EDGE: backend/app/services/scenario_generator/opening_scene.py:45 -> GenerateResponse

### Step 3 — Hook 2：组装提示（RAG + 战役上下文 + 截断）

`prompting.py:7-34`。各协作对象实现位置：`retriever.retrieve_async`→`services/retriever.py:55`
（向量检索 :62-64、关键词加成 :45/:67）、`prompt_builder.build_sections`→`prompt_builder/builder.py:15`。

EDGE: backend/app/services/scenario_generator/generator.py:74 -> self._build_prompt
EDGE: backend/app/services/scenario_generator/prompting.py:9 -> self._build_query
EDGE: backend/app/services/scenario_generator/prompting.py:10 -> self.retriever.retrieve_async
EDGE: backend/app/services/scenario_generator/prompting.py:11 -> self._serialize_retrieved_chunks
EDGE: backend/app/services/scenario_generator/prompting.py:14 -> campaign_manager.is_loaded
EDGE: backend/app/services/scenario_generator/prompting.py:16 -> campaign_manager.inject_context
EDGE: backend/app/services/scenario_generator/prompting.py:18 -> PromptInput
EDGE: backend/app/services/scenario_generator/prompting.py:25 -> self.db.get_recent_messages
EDGE: backend/app/services/scenario_generator/prompting.py:27 -> self.prompt_builder.build_sections
EDGE: backend/app/services/scenario_generator/prompting.py:31 -> campaign_manager.is_loaded
EDGE: backend/app/services/scenario_generator/prompting.py:32 -> campaign_manager.truncate_prompt_sections

### Step 4 — Hook 3：生成（三段 Agent 管线或单次调用）

`agent_pipeline.py:17`。**分支 A**：无战役 → 单次 LLM 调用（旧行为）。

EDGE: backend/app/services/scenario_generator/agent_pipeline.py:27 -> campaign_manager.is_loaded
EDGE: backend/app/services/scenario_generator/agent_pipeline.py:28 -> self._execute_single_llm
EDGE: backend/app/services/scenario_generator/agent_pipeline.py:135 -> self.llm_client.generate

**分支 B**：有战役 → 三段管线（每段各自调一次 LLM，失败都有兜底）。

Stage 1 Examiner（判定行动可行性；blocked 则叙事内拒绝、提前返回 source="examiner_blocked"，
agent_pipeline.py:50-62）：

EDGE: backend/app/services/scenario_generator/agent_pipeline.py:36 -> ExaminerAgent
EDGE: backend/app/services/scenario_generator/agent_pipeline.py:37 -> self._collect_relevant_rules
EDGE: backend/app/services/scenario_generator/agent_pipeline.py:39 -> examiner.examine
EDGE: backend/app/services/agents/examiner.py:100 -> self._llm.generate_json
EDGE: backend/app/services/agents/examiner.py:106 -> _parse_ruling

Stage 2 Director（锚点评估、偏差检测、重定向策略）：

EDGE: backend/app/services/scenario_generator/agent_pipeline.py:65 -> self._run_director_stage
EDGE: backend/app/services/scenario_generator/agent_pipeline.py:79 -> campaign_manager._load_recap_compressed
EDGE: backend/app/services/scenario_generator/agent_pipeline.py:81 -> self._describe_anchor_candidates
EDGE: backend/app/services/scenario_generator/director_support.py:48 -> campaign_manager.is_loaded
EDGE: backend/app/services/scenario_generator/director_support.py:52 -> campaign_manager.evaluate_anchors
EDGE: backend/app/services/scenario_generator/agent_pipeline.py:82 -> campaign_manager.detect_deviation
EDGE: backend/app/services/scenario_generator/agent_pipeline.py:83 -> self._format_score_item_states
EDGE: backend/app/services/scenario_generator/director_support.py:103 -> campaign_manager.is_loaded
EDGE: backend/app/services/scenario_generator/agent_pipeline.py:86 -> director.direct
EDGE: backend/app/services/agents/director.py:123 -> self._llm.generate_json
EDGE: backend/app/services/agents/director.py:129 -> _parse_instruction
EDGE: backend/app/services/scenario_generator/agent_pipeline.py:68 -> self._inject_direction

Stage 3 Narrator（真正的剧情生成；成功后 fire-and-forget 记忆维护）：

EDGE: backend/app/services/scenario_generator/agent_pipeline.py:71 -> self._run_narrator_stage
EDGE: backend/app/services/scenario_generator/agent_pipeline.py:105 -> self.llm_client.generate
EDGE: backend/app/services/scenario_generator/agent_pipeline.py:124 -> self._get_memory_controller
EDGE: backend/app/services/scenario_generator/agent_pipeline.py:125 -> memory_ctrl.on_turn_generated
EDGE: backend/app/services/scenario_generator/agent_pipeline.py:126 -> asyncio.create_task
EDGE: backend/app/services/scenario_generator/agent_pipeline.py:126 -> memory_ctrl.maintain

LLM 调用与三级修复（`llm_client/client.py:41-121`）：直接解析 → 本地 json_repair →
temperature=0 让模型自我修复。`_parse_story_output` 实现在 `output_normalizer.py:11`
（:13 `StoryOutput.model_validate`）。

EDGE: backend/app/services/llm_client/client.py:57 -> self._request_completion
EDGE: backend/app/services/llm_client/client.py:139 -> self.client.chat.completions.create
EDGE: backend/app/services/llm_client/client.py:75 -> self._parse_story_output
EDGE: backend/app/services/llm_client/client.py:77 -> self._regenerate_or_raise
EDGE: backend/app/services/llm_client/client.py:91 -> self._repair_json_local
EDGE: backend/app/services/llm_client/client.py:93 -> self._parse_story_output
EDGE: backend/app/services/llm_client/client.py:102 -> self._request_completion
EDGE: backend/app/services/llm_client/client.py:112 -> self._parse_story_output

`generate_json`（Examiner/Director/事实抽取用）走同一 `_request_completion`，
见 `llm_client/structured.py:42-96`。

### Step 5 — 状态推进（纯本地，无 LLM）

`generator.py:84` → `game_state/manager.py:50-94`：sanity/health/turn 更新，物品/NPC/任务/
世界事实按名字合并（`normalization.py:7` `merge_by_name`），关键事件追加，超限裁剪
（`enforce_state_caps`，20/15/10/15 上限，`defaults.py` 定义）。

EDGE: backend/app/services/scenario_generator/generator.py:84 -> self.state_manager.apply_output
EDGE: backend/app/services/game_state/manager.py:48 -> self.db.write_session
EDGE: backend/app/services/game_state/manager.py:51 -> self._ensure_state_shape
EDGE: backend/app/services/game_state/manager.py:65 -> self._infer_world_facts
EDGE: backend/app/services/game_state/manager.py:67 -> self._remove_by_name
EDGE: backend/app/services/game_state/manager.py:68 -> self.merge_by_name
EDGE: backend/app/services/game_state/manager.py:71 -> self.merge_by_name
EDGE: backend/app/services/game_state/manager.py:77 -> self.merge_by_name
EDGE: backend/app/services/game_state/manager.py:78 -> self.merge_by_name
EDGE: backend/app/services/game_state/manager.py:83 -> self._merge_player_status
EDGE: backend/app/services/game_state/manager.py:89 -> self._append_recent
EDGE: backend/app/services/game_state/manager.py:91 -> self._build_key_event
EDGE: backend/app/services/game_state/manager.py:93 -> self.enforce_state_caps

### Step 6 — Hook 4：事后处理（每 5 回合抽事实 + NPC 好感）

`post_generation.py:10-70`。

EDGE: backend/app/services/scenario_generator/generator.py:87 -> self._apply_post_generation
EDGE: backend/app/services/scenario_generator/post_generation.py:14 -> campaign_manager.is_loaded
EDGE: backend/app/services/scenario_generator/post_generation.py:18 -> campaign_manager.extract_facts
EDGE: backend/app/services/scenario_generator/post_generation.py:23 -> self.state_manager.merge_by_name
EDGE: backend/app/services/scenario_generator/post_generation.py:28 -> self.state_manager.enforce_state_caps
EDGE: backend/app/services/scenario_generator/post_generation.py:32 -> self._process_npc_relations_delta
EDGE: backend/app/services/scenario_generator/post_generation.py:40 -> self.db.read_campaign_progress
EDGE: backend/app/services/scenario_generator/post_generation.py:61 -> self.db.update_npc_relations

### Step 7 — 对话落库

EDGE: backend/app/services/scenario_generator/generator.py:91 -> self.db.add_message
EDGE: backend/app/services/scenario_generator/generator.py:92 -> self.db.add_message
EDGE: backend/app/services/scenario_generator/generator.py:93 -> self.state_manager.save_state

### Step 8 — Hook 5：记录与战役推进（唯一的推进点）

`post_generation.py:72-93` → `_advance_campaign`（generator.py:124-132）：提交待定锚点 →
turn+1 → 达到 session 最大回合则进入下一 session。

EDGE: backend/app/services/scenario_generator/generator.py:96 -> self._record_and_finalize
EDGE: backend/app/services/scenario_generator/post_generation.py:78 -> campaign_manager.is_loaded
EDGE: backend/app/services/scenario_generator/post_generation.py:79 -> campaign_manager.record_turn
EDGE: backend/app/services/scenario_generator/post_generation.py:82 -> self.db.add_model_output
EDGE: backend/app/services/scenario_generator/post_generation.py:91 -> self._advance_campaign
EDGE: backend/app/services/scenario_generator/generator.py:126 -> campaign_manager.is_loaded
EDGE: backend/app/services/scenario_generator/generator.py:128 -> campaign_manager.commit_pending_anchors
EDGE: backend/app/services/scenario_generator/generator.py:129 -> campaign_manager.advance_turn
EDGE: backend/app/services/scenario_generator/generator.py:130 -> campaign_manager.resolve_max_turns
EDGE: backend/app/services/scenario_generator/generator.py:132 -> campaign_manager.advance_session

### Step 9 — 响应

`generator.py:101-120` 返回 `GenerateResponse`（新状态 + 剧情输出 + 检索块截断至 700 字 +
source 标记：`llm` / `scripted` / `examiner_blocked`）。

EDGE: backend/app/services/scenario_generator/generator.py:101 -> GenerateResponse

（`create_session` 内部落库走 `manager.py:33 -> self.db.write_session`，不在本回合循环内：）

EDGE: backend/app/services/game_state/manager.py:33 -> self.db.write_session

### 错误路径

LLM 请求/解析失败 → `_store_error`（generator.py:136-149，双消息 + model_outputs 错误行）
→ `ScenarioGenerationError` → 路由层转 502。

EDGE: backend/app/services/scenario_generator/agent_pipeline.py:111 -> self._store_error
EDGE: backend/app/services/scenario_generator/agent_pipeline.py:117 -> self._store_error
EDGE: backend/app/services/scenario_generator/generator.py:141 -> self.db.add_message
EDGE: backend/app/services/scenario_generator/generator.py:142 -> self.db.add_message
EDGE: backend/app/services/scenario_generator/generator.py:143 -> self.db.add_model_output

### 其他在线会话端点（routers/sessions.py）

create :27-72（含战役装载 :40-68）、get :75-80、history :83-88、progress :91-122。

EDGE: backend/app/routers/sessions.py:29 -> state_manager.create_session
EDGE: backend/app/routers/sessions.py:42 -> build_campaign_manager
EDGE: backend/app/routers/sessions.py:50 -> campaign_manager_cache.put
EDGE: backend/app/routers/sessions.py:51 -> db.set_session_campaign_id
EDGE: backend/app/routers/sessions.py:58 -> state_manager.merge_entry_state
EDGE: backend/app/routers/sessions.py:65 -> state_manager.save_state
EDGE: backend/app/routers/sessions.py:77 -> state_manager.get_session_payload
EDGE: backend/app/routers/sessions.py:85 -> state_manager.get_session_payload
EDGE: backend/app/routers/sessions.py:88 -> db.get_messages
EDGE: backend/app/routers/sessions.py:98 -> state_manager.get_session_payload
EDGE: backend/app/routers/sessions.py:111 -> db.get_session
EDGE: backend/app/routers/sessions.py:114 -> db.read_campaign_progress

---

## 2. 协作对象实现位置速查（prose 引用，需人工核对）

| 调用 | 实现位置 |
|---|---|
| `campaign_manager.inject_context` | `services/campaign_manager/facades.py:52` |
| `campaign_manager.evaluate_anchors` | `services/campaign_manager/facades.py:14` |
| `campaign_manager.commit_pending_anchors` | `services/campaign_manager/facades.py:22` |
| `campaign_manager.detect_deviation` | `services/campaign_manager/facades.py:35` |
| `campaign_manager.load` / `is_loaded` / `get_opening_scene` | `services/campaign_manager/facade.py:109/121/124` |
| `campaign_manager.record_turn` / `resolve_max_turns` / `truncate_prompt_sections` / `extract_facts` | `services/campaign_manager/metrics.py:62/32/35/45` |
| `campaign_manager.advance_turn` / `advance_session` / `_load_recap_compressed` | `services/campaign_manager/recap_advancer.py:39/42/25` |
| `memory_ctrl.on_turn_generated` / `maintain` | `services/memory/memory_controller/controller.py:105` / `maintenance.py:15` |
| `retriever.retrieve_async` | `services/retriever.py:55` |
| `evaluation_module.score` | `services/evaluation.py`（`EvaluationModule`） |
| `db.*` | `services/database/` 各模块（Database 门面） |
