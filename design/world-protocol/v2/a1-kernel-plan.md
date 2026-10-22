# A1 内核实现计划

日期：2026-10-22。分支 `world-server`，基线 `79f8120`。按[分工](../../browser-world-state-work-split.md)§三 A1 制定，已并入 B 方评审（2026-10-22）的全部修正与两项会话决策；评审中两处表述按核实结果精化（错误码清单实为 11 码共享清单、v1/v2 夹具归属）。A1a 先行，是 A1b、A2 与 H1 的共同前置。

## 一、锁定决策

| 决策 | 内容与依据 |
|---|---|
| 硬标准 | 21 条规范向量是编码/投影排除向量而非 apply 答案（`test_world_protocol_v2_canonical.py` 首行 "not apply answers"，已 30 passed）；A1 硬标准 = §二投影夹具绑定 + 轨迹回放 + §四自建负例 |
| 状态结构 | 不建平行结构：内核是对既有 `WorldState` 与 `canonical_digest`/`prefix_projection` 的纯函数；v2 `__init__` 声明 `app.schemas.world` 对 WorldState 权威不变（T01 prefixDigest 逐字节等值已由 B 验证） |
| 拒绝出口 | 不新增错误码：内核纯谓词返回结构化违规（内部类型，不进契约）；A2 按映射表映射既有码并成文（§四）；H1 后按联调反馈再评估增码。已核实 `commit_point`/`checkpoint_stage_unit`/`checkpoint_stage_time_scan`/`checkpoint_seal_point`/`checkpoint_begin_point`/`preview_point` 的 errorCodes：前五个各挂同一份 11 码清单（`phase_invalid`、`version_mismatch` 均在），preview 另含 `preview_budget_exceeded` |
| 控制阶梯 | begin/discover/extend/close/stage/seal 属 A2「合法 phase 边」；A1 只做单元级候选校验、单元外层顺序与覆盖清单，给 A2 留纯谓词 |
| 共享资产只读 | 不改 traces（`acceptanceLayer: Literal['contract']`）、不改契约四文件与 manifest；回放用新增测试模块；A1 负例夹具放 `backend/tests/fixtures/world/`（不入 `design/`） |
| v1 隔离 | 内核只消费 v2（`v2.work.SettlementGroup`、`v2.requests.CommitPointRequest` 等）；`contracts.py` 的 `PointCommitRequest`/`RoundCheckpoint`/`SettlementCandidates` 是 v1 遗留，以架构断言防误 import |
| 文档漂移 | 往 `design/world-protocol/v2/` 新增 `*.md` 不触任何漂移：contractDigest 只覆盖四个接口生成文件，manifest 147 项不含 `*.md`（`export_world_protocol.py --version v2 --check` 已验证通过） |

## 二、固定预期资产（现有、未接线）

| 资产 | 现状 | A1a 用法 |
|---|---|---|
| `fixtures/projections/normal`、`segmented`、`time.expected.json` | 全量 world 文档，仅 manifest 记哈希、无测试消费；B 测得摘要分别等于 T01/T02/T03 终态（`4f5a33e7…`、`85848d51…`、`61569325…`） | 等值断言落成 Python 测试；该测试即对 B 测量值的独立复核 |
| `fixtures/projections/description-collapse`、`task-normalization.expected.json` | 同上未消费 | 塌缩与任务归一化行为断言 |
| traces T01、T03、T03-collapse | 11 个 commit 中仅此 3 个改状态：位置；时间＋任务达成＋个性＋理智；同点新增又达成塌缩＋外貌替换 | Python 侧回放与投影/摘要断言 |
| 其余 8 份轨迹 | 纯时间/结构点 | 回放覆盖，不新增状态预期 |
| 合并不变量 | B 已对全部 11 个 commit ×2 样本验证 `point.entityDeltas == collapse(merge(groups ∪ timeScan))`，0 mismatch；两个实跑前提：①必须把该点已存 `stage_time_scan` 候选并入（只拿 `settlementGroups` 跑，T03 假失败——groups 为空、Δ 来自 time-scan）；②collapse 必须同时把「本点新增且已达成」的 ID 从 `tasksAchieved` 摘掉并只改新增记录 `status:"achieved"`（只做一半，T03-collapse 假失败） | 落为内核不变量断言（无新增夹具）；`merge` 入参即含 `timeScanCandidates | None`（函数面见 server.md） |

摘要配方（B 以 raw / 校验后模型 / 轨迹实例化三条独立路径复现，三者一致；`4f5a33e7…`/`85848d51…`/`61569325…`）：`canonical_digest(WorldState.model_validate(doc).model_dump(mode='json'))`。规范化对 v2 全量文档是恒等变换，A1a-2 直接对 `model_dump(mode='json')` 断言，勿用 `json.dumps(sort_keys=True)` 的字节（`canonical_bytes` 无空格、不转义、数组不排序）。

注：`pureRemoval`/`expectedCollapsed`/`expectedStandaloneState`/`chainExpectedTime`/`finalDelta` 位于 v1 `fixtures/`。v2 **没有 pure-removal 行为夹具**——`description-collapse.expected.json` 只覆盖「替换后塌缩成单条」，`text: null + supersedes` 纯删除在 v2 零覆盖，归 A1b 自建负例。

## 三、A1a 任务分解（apply/merge/collapse/time/replay/preview）

| # | 任务 | 验收 |
|---|---|---|
| 1 | 通读 `WorldState`、v2 `requests`/`work`/`projections` 与 §二夹具，定函数面与模块划分（`backend/app/services/world/` 新建） | 函数面清单记入 server.md |
| 2 | 投影夹具绑定测试 | §二前两行等值/行为断言全部通过 |
| 3 | apply/merge 正路径三条合并路：action 组；time-scan 候选（纯时间点 `settlementGroups` 为空、Δ 取 `stage_time_scan` 已存候选）；塌缩（两步：摘 `tasksAchieved`＋新增记录置 `status:"achieved"`；T03-collapse 是唯一塌缩夹具） | 三路正例＋11-commit 不变量断言通过（timeScan 必须并入） |
| 4 | 时间推进与点时间锁判定谓词（出口映射留给 A2） | 时间先行轨迹（T03 等）回放通过 |
| 5 | preview：覆盖清单投影与字节预算判定谓词（merge 并入 §三#3） | preview 输出断言＋`preview_budget_exceeded` 判定侧 |
| 6 | replay 与回放摘要一致（工作投影、最终提交、回放摘要三者一致） | 11 份轨迹 ×2 样本回放全绿 |

## 四、A1b 任务分解（六阶段校验与负例）

六阶段指状态阶段 positions→appearances→tasks→subtasks→personalities→sanities，与控制阶梯无关。

| # | 任务 | 验收 |
|---|---|---|
| 1 | 单元级候选校验、单元外层顺序、覆盖清单 | 正反例全绿；给 A2 的纯谓词签名冻结 |
| 2 | 自建负例夹具（`backend/tests/fixtures/world/`，约 15 条，现有夹具零覆盖）：固定实体违规、同点 supersedes、跨房间 relative、任务环、个性无达成、理智/个性配对、slot 归属、pure-removal（`text: null + supersedes`）等 | 每条挂映射表出口并断言违规分类；违规分类法与 A2 映射表随本项成文进 server.md，作为 A2 验收输入（初稿见下表） |

映射表初稿（A2 交付时复核；已按决策「不新增码」锁定方向）：

| 违规类 | A2 出口码 | 依据 |
|---|---|---|
| ID 引用不可解析 | `version_mismatch` | 注释含 "unknown identities"；该码 409＋`refresh_context`，ID 不可解析时可能刷新后重试到同一错误，H1 真实负分支复核是否误导（与下行一并） |
| 提交点与封存前缀不符（kind/时长/绑定） | `version_mismatch`（`details.reason=prefix_binding_mismatch`） | T08 s9 实测 409；`point_time_locked` 只属 `set_point_time` |
| 内容语义非法（任务环、跨房间 relative、个性无达成、跨单元同 actor、同点跨组 supersedes 等） | `request_malformed` | 400 `fix_request`；跨单元同 actor 沿用 v1 唯一性意图（2026-10-22 拍板）；H1 用真实负分支复核是否误导客户端 |
| 位置/阶梯非法 | `phase_invalid` | 注释 "current phase or work position"（A2 判定） |
| 点时间已锁仍改 | `point_time_locked` | 既有码 |
| 其余 | 按 `ERROR_CODES` 注释逐一对号 | 不新增码 |

## 五、验收与收尾

- 门：全量 backend pytest（`-X utf8`）889＋新增全过（HEAD 实测 889 collected；CLAUDE.md 与 v2 README 的 923 已旧，随本线更正）；内核测试闸门在 CI backend 作业（全量跑 `backend/tests`）。
- 共同脚本 `check_world_interface_baseline.py` **不动**：它在两条开发分支逐字节相同（对 `origin/world-browser` diff 为空），按 required 名单强校验（缺模块直接 `SystemExit`）并按 `test_world_protocol_*` glob 全量执行——B 分支没有内核实现，任何注册或名单扩展都会打断 B 的共同检查与 CI world-interface 作业。内核测试命名避开该 glob 即天然隔离；本地一键门用新增的 `backend/scripts/check_world_kernel.py`（A 自有，不入 manifest，不进共同入口）。
- CI 三作业绿；每 commit 同轮 push；提交信息与内容不含环境信息。
- 不碰清单：`frontend/` 全部、`design/world-protocol/v2/` 既有文件、契约四文件、manifest、traces。
- 后续：A2 消费 §四纯谓词与映射表；H1（T01）需 A2＋B1 另行预约；A3 真实事务（FC01–FC32）不在本计划。
