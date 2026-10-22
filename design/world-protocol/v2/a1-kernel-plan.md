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

## 二、固定预期资产（现有、未接线）

| 资产 | 现状 | A1a 用法 |
|---|---|---|
| `fixtures/projections/normal`、`segmented`、`time.expected.json` | 全量 world 文档，仅 manifest 记哈希、无测试消费；B 测得摘要分别等于 T01/T02/T03 终态（`4f5a33e7…`、`85848d51…`、`61569325…`） | 等值断言落成 Python 测试；该测试即对 B 测量值的独立复核 |
| `fixtures/projections/description-collapse`、`task-normalization.expected.json` | 同上未消费 | 塌缩与任务归一化行为断言 |
| traces T01、T03、T03-collapse | 11 个 commit 中仅此 3 个改状态：位置；时间＋任务达成＋个性＋理智；同点新增又达成塌缩＋外貌替换 | Python 侧回放与投影/摘要断言 |
| 其余 8 份轨迹 | 纯时间/结构点 | 回放覆盖，不新增状态预期 |
| 合并不变量 | B 已对全部 11 个 commit 验证 `point.entityDeltas == collapse(merge(groups ∪ timeScan))` | 落为内核不变量断言（无新增夹具） |

注：评审提到的 `pureRemoval`/`expectedCollapsed`/`expectedStandaloneState`/`chainExpectedTime`/`finalDelta` 位于 v1 `fixtures/`，v2 对应物即上表投影夹具。

## 三、A1a 任务分解（apply/merge/collapse/time/replay/preview）

| # | 任务 | 验收 |
|---|---|---|
| 1 | 通读 `WorldState`、v2 `requests`/`work`/`projections` 与 §二夹具，定函数面与模块划分（`backend/app/services/world/` 新建） | 函数面清单记入 server.md |
| 2 | 投影夹具绑定测试 | §二前两行等值/行为断言全部通过 |
| 3 | apply 正路径三条合并路：action 组；time-scan 候选（纯时间点 `settlementGroups` 为空、Δ 取 `stage_time_scan` 已存候选）；塌缩（`subtasksAdded` 带 `status:"achieved"`，不得进 `tasksAchieved`；T03-collapse 是唯一塌缩夹具） | 三路正例＋11-commit 不变量断言通过 |
| 4 | 时间推进与点时间锁判定谓词（出口映射留给 A2） | 时间先行轨迹（T03 等）回放通过 |
| 5 | preview 与 merge | 覆盖清单与 preview 字节预算判定谓词（`preview_budget_exceeded` 判定侧） |
| 6 | replay 与回放摘要一致（工作投影、最终提交、回放摘要三者一致） | 11 份轨迹 ×2 样本回放全绿 |

## 四、A1b 任务分解（六阶段校验与负例）

六阶段指状态阶段 positions→appearances→tasks→subtasks→personalities→sanities，与控制阶梯无关。

| # | 任务 | 验收 |
|---|---|---|
| 1 | 单元级候选校验、单元外层顺序、覆盖清单 | 正反例全绿；给 A2 的纯谓词签名冻结 |
| 2 | 自建负例夹具（`backend/tests/fixtures/world/`，约 15 条，现有夹具零覆盖）：固定实体违规、同点 supersedes、跨房间 relative、任务环、个性无达成、理智/个性配对、slot 归属等 | 每条挂映射表出口并断言违规分类 |
| 3 | 违规分类法与 A2 映射表成文（server.md，作为 A2 验收输入） | 见下表初稿 |

映射表初稿（A2 交付时复核；已按决策「不新增码」锁定方向）：

| 违规类 | A2 出口码 | 依据 |
|---|---|---|
| ID 引用不可解析 | `version_mismatch` | errors.py 该码注释含 "unknown identities" |
| 内容语义非法（任务环、跨房间 relative、个性无达成等） | `request_malformed` | 400 `fix_request`；H1 用真实负分支复核是否误导客户端 |
| 位置/阶梯非法 | `phase_invalid` | 注释 "current phase or work position"（A2 判定） |
| 点时间已锁仍改 | `point_time_locked` | 既有码 |
| 其余 | 按 `ERROR_CODES` 注释逐一对号 | 不新增码 |

## 五、验收与收尾

- 门：全量 backend pytest（`-X utf8`）889＋新增全过（HEAD 实测 889 collected；CLAUDE.md 与 v2 README 的 923 已旧，随本线更正）；统一验收入口显式注册内核测试（backend/scripts 归 A，脚本不在 manifest 哈希清单内，改动无漂移）。
- CI 三作业绿；每 commit 同轮 push；提交信息与内容不含环境信息。
- 不碰清单：`frontend/` 全部、`design/world-protocol/v2/` 既有文件、契约四文件、manifest、traces。
- 后续：A2 消费 §四纯谓词与映射表；H1（T01）需 A2＋B1 另行预约；A3 真实事务（FC01–FC32）不在本计划。
