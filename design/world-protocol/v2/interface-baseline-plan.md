# v2 共同接口基线实施计划（A0＋B0）

日期：2026-10-22。状态：**IF-01～IF-08 已完成，S1/S2 及 A0/B0 共同前置验收通过**。v1 `26011c8`、S1 `cabb04c`、共同接口实现 `e3b197a79f95adfbe215dddf5dfd3f9ed5b12823`；冻结依据见 [最终验收](change-list.md#共同前置最终验收2026-10-22if-03if-08-通过)。Python 426 项、TS 契约 38、轨迹 65、前端全套 165 及类型/lint/build 通过，干净检出重跑通过。CI 接线完成；frontend 在 `07924f3` 的远端运行中失败于 npm ci，`05c213e` 是首次带 world-interface 作业的运行、三个作业全部 success；全量 backend 923 passed、0 failed，此前单列的两个 campaign_wiring 失败已不存在。按用户安排共同收尾后再拆 A1/A2 与 B1，实际服务及事务保留 A2/A3、H1/H2。

## 一、本批目标与完成边界

交付一份双方可直接用于后续开发的接口基线：Python 定义、JSON Schema、完整 API 目录、SQL 约束规格、公共夹具与动态轨迹、TS 消费层，以及共同自动检查。A 维护契约和 CI，B 维护浏览器消费与检查命令，文件归属沿用分工文档。

本批完成时，两人可以分别开始 A1/A2 与 B1：A 从固定候选实现状态及服务，B 从固定响应实现浏览器调度。运行中的 apply、完整控制状态机、生产路由、SQLite 提交事务、真实模型和页面属于后续交付。SQL 本批交付可执行 DDL 及约束测试；事务故障本批交付输入、预期和后续验收位置，实际事务中断验证在 A3 实现。

基线覆盖正文已决定的全部接口形状，包含高级组工作、预约后继及接管。各接口的运行实现可以分批进行；必需字段、操作权限、错误语义和恢复动作在本批明确，不能留给双方各自推测。

本批按三个闸门验收：IF-01 关闭**决策级**未决，S1 关闭**字段级**未决，IF-08 关闭**行为级**未决。S1 必须同时交付 operation registry、每个操作的 request/success/error 夹具和机器可读权限矩阵；IF-04a 只交付轨迹格式与契约级轨迹，不承担 all-ops 覆盖。因此 IF-05 在 S1 后即可开始，不必等待 S2。

## 二、输入与实现约定（表内保留实施前盘点）

| 当前输入 | 本批处理 |
|---|---|
| `backend/app/schemas/world/contracts.py`、包级导出及现有两份协议测试 | 当前为 v1；保留原导入和验收入口，v2 源定义新增至 `backend/app/schemas/world/v2/` |
| `backend/app/schemas/world/canonical.py` | 沿用已冻结的 `world-canonical-v1` 编码规则；v2 新增自己的投影和向量，不擅自改编码版本 |
| `backend/scripts/export_world_protocol.py` | 已支持显式 v1/v2 选择，默认仍为 v1；检查模式和临时输出目录仍待 IF-07 交付 |
| `design/world-protocol/v1/` | 保留评审基线；v2 的导出与测试显式指向 v2，不能借用 v1 通过记录 |
| `frontend/package.json`、`frontend/vitest.config.mts` | 已有 Vitest 和 `npm test`；B 新增聚焦本批的脚本及类型检查配置 |
| `.github/workflows/ci.yml` | 后端运行 pytest；前端当前只有 lint/build；A 补入前端测试和本批共同检查 |
| `.gitattributes`、根目录 `nul`、`.zcodeignore`、`backend/requirements-dev.txt` | 首次卫生工作已随 26011c8 完成；保留 LF 规则、本地工具忽略和 jsonschema 测试依赖 |
| v1 已导出产物 | LF 基线已随 26011c8 提交；IF-07 仍须交付 `--version v1 --check` 字节检查入口 |
| 已提交输入 | v1 基线与 S1 已分别提交 26011c8 / 07924f3；IF-01 差异表记录现有产物及待交付文件，最终基线必须能从 Git 提交独立检出 |

本批采用手写 `types.ts` 配合导出的 v2 schema 做运行时校验及消费测试。B 负责 TS 文件，Python/schema 为契约权威；本批不引入第二份生成 TS 类型产物。B 固定支持 Draft 2020-12 的校验依赖及锁文件，验证其能够处理本项目导出的引用和组合约束。

### 2.1 版本口径与摘要

v2 目录名只是源码组织，不是数据版本；版本以字段和 `$id` 为准。下表由 IF-01 冻结表头，IF-02 填写 v2 取值并随导出产物发布：

| 名称 | 载体 | v1 | v2 | 变更含义 |
|---|---|---|---|---|
| `protocolVersion` | 请求/响应包络、错误码、HTTP 头 | 未定义 | `2` | wire 形状或错误码语义 |
| `$id` | `world-protocol.schema.json` | `urn:jity:world-protocol:v1` | `urn:jity:world-protocol:v2` | schema 文档身份，新增 v2 请求/响应定义 |
| `schemaVersion` | 世界状态、初始世界 | `1` | `1` | S1 不改 WorldState 形状 |
| `engineVersion` | 世界数据 | `world-engine-v1` | `world-engine-v1` | S1 不改 apply 语义 |
| `canonicalVersion` | 摘要 | `world-canonical-v1` | `world-canonical-v1` | 规范字节规则 |
| `traceFormatVersion` | `trace.schema.json` | 无 | `1` | 轨迹格式 |
| `contractDigest` | `manifest.json`、B 的 pin 文件 | 无 | 计算值 | 契约集合 |

递增规则：`protocolVersion` 管 wire、HTTP 状态、错误码与请求头，只新增错误码可单独递增；`schemaVersion` 管 WorldState/初始世界形状，递增时必须同时递增 `protocolVersion`；`engineVersion` 管 apply、资格、时间与合并语义，JSON 形状不变也可能递增；`canonicalVersion` 只在规范字节规则变化时递增，v2 沿用 `world-canonical-v1`，若改摘要定义必须整版迁移；`traceFormatVersion` 只随 trace schema 变化，不影响协议。

S1 新增的 `PointWork`、`ControlState`、`WorldContext` 等是 v2 schema 中的新 `$defs`，不改变 `WorldState`，因此 S1 不需要 v2 初始世界夹具，`schemaVersion` 与 `engineVersion` 保持 v1。若 A1 改变 apply 语义或 `WorldState` 形状，再 bump `engineVersion`/`schemaVersion` 并补 v2 世界夹具；不能只改版本字段而不改夹具。

每个响应包络携带 `protocolVersion`、`engineVersion`、`schemaVersion`、`canonicalVersion`。客户端以 `protocolVersion` 判断能否解码，以 `engineVersion` 判断世界规则是否可应用，不得用目录名推断。绝对时间统一为 `serverTimeEpochMilli` / `expiresAtEpochMilli` / `issuedAtEpochMilli`，全链路毫秒；测试 TTL 不小于 5 秒，测试时钟只注入服务端。`fenceEpoch` 为统一字段名：head claim 恒为正整数，history claim 恒为 `null`，不得用 0 表示缺失。

摘要不做域分隔：state/request/prefix/content/contract 五类使用不同投影 schema，摘要只在 `(projectionKind, canonicalVersion)` 组合下解释；同一投影形状复用同一算法。若未来需要跨投影混用摘要，再递增 `canonicalVersion` 并整版迁移，不能静默重新解释旧摘要。

四类哈希不要混用：

- `stateDigest`/`commitDigest`/`prefixDigest`：`world-canonical-v1` 规范 JSON 投影的 SHA-256。
- `contentHash`：冻结行动/目标原文的 UTF-8 字节 SHA-256，不做规范化、trim 或换行替换。
- `contractDigest`：固定接口生成物文件集合的 SHA-256（schema、api-contract、trace schema、版本声明），不是 JSON 投影。
- manifest artifact hash：夹具/向量/SQL 的单文件 SHA-256，只用于完整性校验，不进 `contractDigest`，B 的 pin 也不跟它们走。

## 三、执行顺序与依赖

任务编号代表交付顺序及依赖，不代表天数。两人各自完成所属任务，候选快照和交付物按最小提交同步。

| 任务 | 主负责人 | 前置 | 交付后可开始 |
|---|---|---|---|
| IF-01：差异及接口清单 | A，B 核对 | 现有 v1 与 v2 文档 | IF-02；B 可准备 transport/测试骨架 |
| IF-02：Python v2、API 契约与夹具，候选快照 S1 | A，B 核对 | IF-01 | IF-03、IF-04a、IF-05 |
| IF-03：SQL 约束及规范向量 | A | S1 | IF-07 |
| IF-04a：轨迹 schema、预期工具与契约级轨迹 | A，B 核对格式 | S1 | IF-04b、IF-06 骨架 |
| IF-04b：运行时级轨迹与动态样本，候选快照 S2 | A，B 核对格式 | IF-04a | IF-06、IF-07 |
| IF-05：TS 消费及 transport | B | S1 | IF-07；IF-06 可并行复用 |
| IF-06：TS 轨迹读取与请求核对 | B | S2、IF-05 的基础消费层 | IF-07 |
| IF-07：共同检查与 CI | A，B 提供命令 | IF-02～IF-06 | IF-08 |
| IF-08：冻结共同基线 | A 汇总，B 核对 | 全部检查通过 | A1/A2、B1 依共同基线开发 |

S1/S2 是明确标记“未验收”的候选提交：B 可以基于它们编写消费和测试，A 可以同步 B 的最小测试提交。S1 必须自带 all-ops 夹具与权限矩阵，否则 IF-05 的覆盖条件无法关闭；S2 只增加轨迹级内容。正式基线须等 IF-07 通过后冻结。双方不必等待完整 A0/B0 验收后才动手编写本批互相依赖的检查。

## 四、逐项任务与验收

### IF-01：形成可追溯差异表

A 新增 `change-list.md`，逐条对应 v2 README 的冻结决定和正文规则，列出旧类型/字段、v2 变化、请求/响应落点、校验层及对应夹具。B 核对调用信息是否足够，补出需要返回的工作进度、错误与恢复动作。

当前 A 侧登记与 B 消费核对已完成，11 项决定均有字段/夹具/服务验收落点；B01 修订经再次消费检查通过，S1 字段闸门已正式关闭。历史问题与最终结论见 [change-list.md](change-list.md)。放行依据包含独立 JS 消费，不仅是 registry 自覆盖或 Python 测试。

必须逐条登记 README 的 11 项决定，不能只覆盖正文摘要：

| 决定 | 本批落点 |
|---|---|
| 1b pendingGroup 只存模型目标，admission 从 roll 与资格基线重算 | pendingGroup schema、失败用例、A3 |
| 2b revision 只随控制器位置/游标/工作态/暂停变化 | ControlState、四个 resolve_gate 入口、A2 |
| 1c POST /worlds 同事务创建租约与根点 claim/gate | 创建请求/响应、SQL 事务、A2 |
| 5 settlementGroups 外层有序、memberIds 集合 | schema 校验、规范向量、A1 |
| 4a 工作表按本点消费组清理 | SQL 约束、failure-cases、A3 |
| 4b 所有工作表写入核对 leaseToken/fenceEpoch/revision | api-contract 前置条件、A2/A3 |
| 6 合并臂为条件默认，外貌受影响必须拆分 | 阶段 4 数据集，不进本批契约 |
| 5b PointWork/settledUnits/working 游标 | 数据 schema、字段夹具、A2 |
| 4c restore_group_work 原文复制 | 请求/响应、失败用例、A3 |
| 7b 时间锁与 prepare_successor | 窄操作 schema、失败用例、A3 |
| 2c pause 与 gate 分离 | ControlState、权限矩阵、A2 |

通过标准（决策闸门）：每条决定都有具体落点，或明确标注“阶段 4，不进本批契约”；schema 无法表达的条件登记为服务校验项并分配 A2/A3 验收；`change-list.md` 的未决列只允许出现字段级条目，并在 IF-02 回填。

另需登记 wire 命名重命名：`narrationBlock` 拆为 `gate`（结构化状态）与 `blockedReasons`（枚举数组），所有消费点同步。

首次提交条件（与 IF-01 同批）：

1. 删除根目录 `nul`；`.zcodeignore` 加入 `.gitignore` 并保持本地。
2. 新增 `.gitattributes`：`design/world-protocol/** text eol=lf`。
3. 导出脚本按 LF 写 bytes 并重新导出 v1；`world-protocol.schema.json` 与 `canonical-vectors.json` 不再含 CRLF。
4. 提交 `backend/app/schemas/world/` 源码、v1 导出产物、导出脚本、两份 v1 测试、`design/world-protocol/`、本计划与两份设计文档、`requirements-dev.txt`、`.gitattributes`、`.gitignore`。
5. 记录提交哈希；此后 v1 回归和 v2 导出检查都从该提交检出运行。

`CLAUDE.md` 与 `.planning/STATE.md` 保持本地：全局 pre-commit 规则禁止提交 `CLAUDE.md`，两者只同步内容，不入库。

### IF-02：交付 Python v2 与 API 快照 S1

A 在 `backend/app/schemas/world/v2/` 新增数据、请求/响应及轨迹需要的公共定义；旧 v1 包级导入保持可用。API 操作登记由 Python 维护，导出 `world-protocol.schema.json` 和 `api-contract.json`，避免分别手写两个端点清单。

先定义三个公共类型，所有操作复用，不再逐组设计不同响应形状：

- `WorldContext`：worldId、head（pointId、version、stateDigest、narrationStatus）、advance（advanceId、inputId、intentStatus、inputAvailable）、round（roundId、trigger、order、cursor、actedIds、visitedIds、conclusion）、time、lease（expiresAtEpochMilli、fenceEpoch）、successor 预约摘要、activePointId/activeRoundId。不返回租约令牌；context 读取不要求 requestId。
- `PointWorkView`：pointId、kind、timeAdvance、timeLocked、sealed、prefixDigest、predecessorWorkDigest、timeScanComplete、baseline（headPointId、version、stateDigest）、phase、working（cursor、actedIds、visitedIds、settledUnitIds、intentStatus）、settledUnits（unitId、groupId、memberIds、contentHash）、pendingGroup（groupId、sourceId、memberIds、targetIds、frontierIds、closed）、successor。只读投影，浏览器不能回传为权威状态。
- `ControlState`：`phase`、`paused`、`revision`、`gate`（status、generation、issuedAtEpochMilli、expiresAtEpochMilli；不含 claimToken）、`blockedReasons`（`narration_pending`、`narration_failed`、`cache_missing`、`claim_expired`、`claim_fenced`、`paused`、`phase_not_computable`、`lease_invalid`）、`canCompute`。`canCompute` 由服务端在事务内计算，客户端不得自行推导，也不得缓存为不变量；它只是响应时刻的快照，下一次写入仍须处理租约失效。
- `OperationResult<T>`：版本字段、`serverTimeEpochMilli`、`replayed`、operation/requestId/requestHash、`world: WorldContext`、`control: ControlState`、`work: PointWorkView | null`、`data`。`data` 只含结果身份、状态和绑定摘要，不得含 inputText。
- `ContextResponse`：版本字段、`serverTimeEpochMilli`、`world`、`control`、`work`、`activeInput`（仅 GET 返回；链未结束且未清理时为 `{advanceId, inputId, text}`，否则为 `null`）；GET 读取无 requestId。新增 recovery，默认 null；includeRecovery=true 的查询必须带有效 leaseToken/fenceEpoch，才读取当前与预约后继工作。restoreSources 独立返回仍活动引用的来源 epoch/attempt/manifest；复制前 payloadStatus=restore_required 且载荷隐藏，复制后 available 才返回当前 epoch 原文/完整目标/结果/候选。受控复制允许活动 open/sealed 工作，排除 consumed/abandoned；不进入写响应或幂等 data。
- `ErrorResponse`：版本字段、`serverTimeEpochMilli`、`replayed`、operation/requestId/worldId（已知时）、`error`（错误码枚举、HTTP 状态、`retryable`、`clientAction`、`details`）、可选 `world`/`control`/`work`。`controlRequiredOnError` 按操作与错误码登记；`clientAction` 枚举为 `retry_same_request|reacquire_lease|refresh_context|wait_narration|regenerate_narration|resolve_gate|pause|fix_request|none`。

`claimToken` 只在 narration-jobs/claim 的响应 `data` 中返回给有效租约持有者；只读 context、错误响应和成功重放都不带令牌。输入正文只经 GET context 的 `activeInput` 返回；所有写操作的响应与幂等记录都不带正文，清理后重放不能复活它。

错误码必须是枚举，至少覆盖：`narration_blocked`、`cache_missing`、`claim_expired`、`claim_fenced`、`paused`、`stale_epoch`、`lease_invalid`、`revision_mismatch`、`phase_invalid`、`version_mismatch`、`protocol_version_unsupported`、`request_id_reused`、`request_in_progress`、`point_time_locked`、`frozen_work_missing`、`frozen_work_corrupt`、`preview_budget_exceeded`。每个码固定 HTTP 状态、是否可重试和客户端动作；`narration_blocked`、`paused`、`stale_epoch`、`revision_mismatch`、`phase_invalid` 必须携带 `control`，400 malformed 可省略。`contract_mismatch` 只属于 CI/pin 检查，不进入运行时 `ErrorResponse`；运行时协议头不匹配用 `protocol_version_unsupported`，payload/引擎不匹配用 `version_mismatch`。

| 接口组 | 本批必须固定 |
|---|---|
| 世界创建、context、历史点/状态读取 | 根点与推进点形状、初始租约/claim/gate、无 round 状态、状态及工作进度返回 |
| lease 获取/续约/释放、ids、rolls | 作用域、预分配身份、幂等键、固定判定键、最终资格结果、所有权失效响应 |
| checkpoint | 启动玩家链、pause/resume、begin_point/set_point_time、discover/extend/close、stage_unit/record_skip/stage_time_scan、seal_point/prepare_successor、restore_group_work 的独立请求联合类型 |
| preview 与 points | 权威基线、阶段覆盖、摘要、时间绑定、settledUnits/settlementGroups 对应及提交返回 |
| round-conclusion | continue/handback/cancel、输入消费继承、后继 round、活动指针及取消后的终止身份 |
| narration-jobs/claim/确认/读取/删除 | head/history、generation、claimToken、签发 epoch、缓存缺失及重生成规则 |

每个操作登记 method/path、操作名、请求/响应 schema 引用、成功 HTTP 状态、错误码、适用绑定、前置条件、成功副作用、幂等行为及错误后的客户端动作。权限矩阵不写在散文里：`api-contract.json` 的每个操作至少包含 `preconditions`（机器可读枚举及参数，如 `phase=select_actor`、`timeLocked=false`、`head.narration=ready`、`noActivePendingGroup`、`leaseValid`）、`errorCodes`（含 `controlRequired`）、`bindings`、`mutatesRevision`、`sideEffects`、`idempotency`。散文只做解释，契约摘要只覆盖机器可读部分。所有引用必须可解析。模型原始输出、控制器填入的预分配 ID 与最终可提交候选之间的边界单独列出。

restore 请求只携带可读取的来源清单与当前绑定，不含目标 attempt。服务事务单调分配目标 attempt，并在成功 data 返回 pointId/groupId/fenceEpoch/attempt；请求幂等仍为 worldId/requestId，业务去重绑定 pointId/groupId/目标 epoch/sourceEpoch/sourceAttempt/manifest。同来源与目标 epoch 换 requestId 复用原副本，不分配第二个 attempt。分配原子性与并发去重留在 A3。

权限矩阵必须区分：resume 成功且 `canCompute=false`；计算请求被门槛拒绝；可以提交失效 gate 清理但不能推进；成功幂等重放读取原结果；普通状态写入与原文复制对 revision 的不同影响。JSON Schema 无法表达的历史/租约条件登记为服务校验项，不能在 schema 测试中声称已验证。

幂等键固定为：世界内操作 `(worldId, requestId)`，创建世界 `(requestId)`。每行保存 operation、规范化请求哈希、首次结果引用与提交事务；同键不同操作或不同哈希返回 `request_id_reused`（终态，不可重试）；首事务未提交时返回 `request_in_progress`（可重试，沿用同一 requestId）。成功记录与业务写入同事务提交，不能先写结果后补。除 claim 仅返回去 token 摘要外，重放返回首次 `data` 原值、重新计算的 `control` 和 `serverTimeEpochMilli`，`replayed=true`；不承诺响应字节相同，测试断言 `data` 相等、`control` 重新推导、`replayed=true`。`data` 不得包含 inputText，幂等表也不缓存正文；清理链输入后，旧响应不能把正文复活，需要上下文时重新 GET context。T04/T06 必须断言这一点。`POST /worlds` 的 `requestId` 由客户端生成、`worldId` 由服务端分配，同一 requestId 重发取回同一世界，不能再走 `/ids`。preview 不进入幂等表：可重算、不改变世界、`requestId` 不参与；请求体上限 512 KiB、响应体上限 2 MiB，超限返回 `preview_budget_exceeded` 并在 `details.limit` 标明是 `request` 还是 `response`，不存全文。

A 交付 `fixtures/api/<operation>/{request,success,error}.json`：每个操作交 request、success 与至少一个代表性 error，操作级 error 按 `clientAction` 去重；每个错误码另交 `fixtures/errors/<code>.json`，逐码覆盖。`fixtures/api/operations.json` 枚举 registry 中的全部操作。契约测试遍历 registry，缺夹具即失败；B 的 TS 侧用 `Record<WorldOperation, ...>` 做类型穷尽。all-ops 覆盖属于 S1，不推迟到 IF-04。

通过标准（字段闸门）：`WorldContext`/`PointWorkView`/`ControlState` 字段无 TBD；包络与错误码、`clientAction` 枚举闭合；`gate` 不泄露 claimToken；GET 使用无 requestId 的 `ContextResponse`；幂等 `data` 不含 inputText；preview 请求/响应上限明确；S1 只 bump `protocolVersion`，不伪造 v2 世界夹具。

A 新增 `test_world_protocol_v2_contract.py`。至少覆盖合法联合类型、非法 phase/字段组合、未知字段/版本处理、根点 claim、重复成员、集合排序与外层顺序、请求自身绑定、每个操作均有 request/success/error 夹具及完整覆盖清单。B 核对 S1 后开始 IF-05；S1 的导出产物及示例可使用，运行服务尚未提供。

### IF-03：交付存储约束和规范向量

A 新增 v2 `storage-contract.sql` 和 `test_world_protocol_v2_storage_contract.py`，使用独立内存 SQLite 装载 DDL，记录 Python/SQLite 版本，避免 CI 与 Windows 自带版本的 DDL 特性差异；验证根点空值/唯一约束、同世界引用、claim 模式、版本/epoch 类型、结论来源、组/工作来源引用、roll 唯一身份和最终非空结果等可由 SQL 表达的约束。

对 root-ready、当前有效租约、gate 解析、工作可见性、原文复制及跨表提交顺序，逐项决定由约束、视图或服务事务负责，并用 `failure-cases.json` 写出前置状态、操作、故障位置、预期结果和 A3 测试落点。重新处理 v1 的 round-ready 触发器，保留根点门槛的明确验收路径。DDL 能执行不等于这些事务行为已经通过。

A 新增 v2 `canonical-vectors.json`：保留编码边界的独立预期字节/哈希，增加 memberIds 排列等价、settlementGroups 换序不等价、时间/工作绑定、手写状态投影及封存前缀摘要向量，每类投影各自锁定摘要。预期内容独立手写，不调用未来 apply 生成答案。DDL 与向量均按 LF 提交；v1 向量不得改写。

通过标准：合法/非法 SQL 输入各有明确结果；向量锁定字节和哈希；每个服务层条件都有后续测试落点；v1 原产物与验收入口保持可追溯。

### IF-04a：轨迹 schema、预期工具与契约级轨迹

A 定义并导出 `trace.schema.json`，携带 `traceFormatVersion`、适用契约摘要和场景身份。每步固定：操作、URL/请求模板、预设响应、捕获路径、语义断言、预期投影和下一动作。引用使用结构化节点和有类型的变量，不使用任意字符串替换或可执行脚本表达式。

变量声明必须带 `kind: identity | clock | ownership | business`，单次赋值并记录捕获时机；`expectedProjection` 只允许引用前三类，业务预期必须由作者给出。工具和契约测试对 `business` 引用直接拒绝，防止从 actual response 捕获 sanity/location 再写进 expected。失败响应不提供的值不得被后续步骤引用。

断言操作首批限定为相等/不等、类型/范围、集合或有序数组比较、精确数值变化、时间界限和 `absent`（路径必须不存在）。每个响应先按对应 operation schema 校验，再执行断言；未知字段、缺失必需字段或 schema 失败不能被断言掩盖。

A 提供测试侧 `backend/scripts/world_trace_expected.py`，接收轨迹及捕获绑定，将手写 expectedProjection 实例化后，用 Python 规范编码计算 expectedDigests。验证所有 ID 引用同步替换，禁止沿用换 ID 前的哈希，禁止以 actualState/actualDigest 生成预期。该工具与生产 API 隔离。

A 新增 `test_world_protocol_v2_trace_schema.py`，覆盖：变量 kind 越权、未捕获引用、重复赋值、`absent` 断言、响应 schema 先行校验，以及 operation 覆盖率——遍历 registry，每个操作至少出现在一条轨迹步骤中，或在 `change-list.md` 标注 `fixture-only` 及理由。覆盖率由测试枚举，不靠人工检查。反例必须包括缺少字段/必要断言、epoch 未递增、换 ID 后旧哈希、错误数组次序。

| 轨迹 | 必须给出的规格 |
|---|---|
| T01：一个普通点 | 创建根点、固定叙事 ready、启动 round、单人行动完整阶段候选、暂存/封存/提交与该点叙事 |
| T02：A/B→C/D→E/F | A/B 同点暂存及工作进度，反应连锁、已行动目标、失败反应、后续威胁不改冻结文本、分段/空 linked 门槛 |
| T03：纯时间点 | 无行动的时间扫描、任务/个性/理智联动和叙事；同点新增又达成任务及临时描述折叠另有期望投影夹具 |
| T04：输入链 | continue/automatic/handback/cancel、跨 round 输入消费及正文保留/清理；重放/重读不复活已清理正文，幂等 data 不含 inputText |
| T05：gate 与暂停 | pending 时暂停、过期后恢复成功但禁止计算、ready 不自动清暂停、resolve_gate 不改 revision |
| T06：重试与冲突 | 响应丢失、同请求重发、同 ID 改内容、旧 head/version/revision 及未知身份拒绝；重放不回传 inputText、不重复消费 |
| T07：刷新与接管 | 当前 epoch 可见工作、原文/候选副本接续、claim 重领、旧持有者迟到写入/清理拒绝 |
| T08：时间锁与预约 | 锁定后改时长拒绝、P1 封存前缀及 successorWork 提升、不匹配拒绝、显式取消后不复活 |
| T09：损坏与缺失 | 未确认/跨作用域/已消费来源、缺失或损坏原文阻断、叙事 cache_missing 与旧代次迟到 |

04a 交付 T01/T04/T05/T06 的完整 expectedProjection；T02/T03/T07/T08/T09 在本任务只交请求模板与分支断言，完整投影和摘要由 04b 交付。每条轨迹标明 `contract`、`runtime-A2` 或 `runtime-A3` 验收层；本批验证语法、引用、手写期望和消费行为，A2/A3 再用同一轨迹调用真实服务。H1 只需要 T01，H2 需要 04b 的 T07；完整运行验收仍在后续阶段。

### IF-04b：运行时级轨迹与动态样本，候选快照 S2

在 04a 的 schema 和工具上补齐 T02/T03/T07/T08/T09 的完整 expectedProjection 与 expectedDigests，并提供两组动态身份/令牌/时钟样本。S2 只增加轨迹级内容，不改 S1 的字段与操作。

A 新增 `test_world_protocol_v2_traces.py`，验证 04b 两组动态样本的独立预期与 Python、TS 对照，并拒绝未捕获变量、覆盖旧变量、篡改业务预期和不匹配摘要。B 核对 S2 后开始 IF-06。

### IF-05：交付 TS 消费和 transport

B 在 `frontend/src/lib/world-engine/` 新增 `types.ts`、`protocol.ts`、`transport.ts`、`http-transport.ts` 及 `contract.test.ts`。读取共享 v2 schema，不复制维护另一份 schema；类型检查与运行时校验分别执行。S1 已交付 `fixtures/api/` 与 `api-contract.json`；B 从 registry 生成 `Record<WorldOperation, ...>` 穷尽检查，并用 S1 夹具覆盖每个操作的 request/success 与至少一个代表性 error 分支。

WorldTransport 暴露操作请求/响应，HTTP 实现处理序列化、HTTP/业务错误、契约版本和响应校验，API 地址由配置传入。使用受控 fetch 测试成功响应、错误响应、超时及非法 JSON；实际浏览器连接配置在 H1 验证。对所有 API 操作至少有请求/响应消费用例，对门槛、重试及恢复动作有具体分支断言。

通过标准：合法 fixture 完整读取及往返；每操作的请求/响应/错误用例直接来自 `fixtures/api/<operation>/`；缺失必需字段、非法联合类型和不兼容版本明确失败；resume 成功但不可计算不被当成可推进；重放响应按 `replayed=true`、`data` 原值、`control` 重算断言；TS 不计算 apply/admission/规范摘要。新增依赖及锁文件归 B 维护。

### IF-06：交付 TS 轨迹消费和固定响应

B 新增 `trace-runner.ts`、`fixture-transport.ts` 及 `traces.test.ts`。按共享 trace schema 执行模板实例化、捕获、请求核对和语义断言；同一轨迹可注入固定响应 transport 或 HTTP transport。本批测试使用固定响应和受控 fetch，不实现浏览器完整调度状态机。T07–T09 的完整投影在 S2 到达后接入；此前只跑请求模板与分支断言。

两组动态绑定样本均须通过：同一请求流程允许不同 ID/token/时钟，但身份继承、epoch/generation/revision 变化必须正确。读取 A 提供的 expectedDigests；HTTP 动态验收所需摘要由测试编排调用 Python 工具生成，浏览器不运行 Python。前端独立消费测试使用已交付的实例化样本及其固定预期。

必须拒绝未预设操作、错绑旧令牌、错误数组顺序、漏捕获、篡改业务预期和不匹配摘要。固定响应不能自己推进世界状态或生成缺失响应，遇到轨迹外请求直接失败。

### IF-07：接入本地检查与共同 CI

B 在 `frontend/package.json` 交付 `typecheck:world`、`test:world-contract`、`test:world-traces`；类型检查配置覆盖本批模块及测试引用，不要求加载模型。Vitest 匹配现有 `src/` 范围，不放入 Playwright 的 e2e 收集范围；空测试集必须失败。

A 扩展导出脚本支持 `--version v1|v2 --check`、`--output-dir`，检查模式不改工作树；默认 v1 导出保持兼容。所有生成物按 bytes 写 LF、无 BOM；`--check` 在临时目录重新生成后按 bytes 比较，只重生成 `generated: true` 的条目，手写物只校验哈希、不重写。`manifest.json` 每项含 `path`、`sha256`、`generated`。缺文件、内容不同、出现 CRLF、引用不闭合或清单不一致均失败。v1 也必须能 `--check`，证明首次提交后未被改动。新增 `backend/scripts/check_world_interface_baseline.py` 汇总导出检查、v1 回归、v2 Python 检查及 B 的三条命令，任一子检查失败即非零退出，兼容本地 Windows 和 CI Linux。

A 维护共同 CI：保留既有后端 pytest 与前端 lint/build，加入已有 `npm test`，并建立具备 Python/Node 环境的接口基线检查任务，执行上述统一入口。`npm test` 已匹配 `src/**/*.test.ts`，`test:world-*` 用于本地聚焦，不重复接入 CI；若后续同时运行两者，须在交付报告写明重复是有意的。缺失依赖、未实现脚本、空测试集或跳过必需检查均不得视为基线通过。

`contractDigest` 只覆盖接口生成物：`world-protocol.schema.json`、`api-contract.json`、`trace.schema.json` 和版本声明，使用固定编码及稳定文件集合，排除 manifest 自身、`contract-digest.json`、轨迹数据和环境时间。夹具/向量/SQL 的单文件 SHA-256 写入 `manifest.json` 的 `artifacts`，不参与 `contractDigest`，B 的 pin 只跟接口摘要走；这样改夹具不会要求 B 更新 pin。实际实现须说明字节规则，导出不含当前时间或机器路径。

B 提交 `frontend/src/lib/world-engine/contract-digest.json`，由 A 的导出脚本生成，只含 `{protocolVersion, contractDigest}`，不得手写，并排除在摘要输入之外。CI 在单树内重算摘要并与 pin 比对，不一致即失败；这样 A 改契约未同步 B 会在任一分支失败，无需双 ref checkout。跨提交组合仍按分工文档在 H1/H2 与最终集成时人工记录，`ci.yml` 不新增双 ref 工作流；契约文件只能随同时包含 A 契约与 B 消费更新的 PR 修改，feature 分支禁止单独改契约。

通过标准：干净检出后所有命令可复现；在临时副本中分别把一个生成物改成 CRLF、改动一个响应字段、一个门槛错误处理和一个动态摘要预期，相关检查确实失败；恢复后通过。字节规则由 `--check` 保证，不依赖 `git diff`（后者受 autocrlf 影响）。Windows 本地与 CI Linux 用同一命令得到相同结果。

### IF-08：冻结并交接

A 汇总检查结果和产物清单，B 核对 TS 消费与轨迹结果；更新 v2 README，记录正式接口基线的 Git 提交、契约摘要、运行环境、验收命令和结果。摘要和提交身份在实现完成后填写，不能预先编造。

行为闸门：`failure-cases.json` 每条都有 A2/A3 测试落点；每个错误码都有夹具和 B 的消费分支；未实现的行为只能登记为后续验收，不能留在“待定”。

两人从该提交建立或更新 `world-server`、`world-browser` 开发分支。后续接口变更继续经过双方消费检查，必要时用临时集成 checkout 验证指定 A/B 提交组合。本批记录为“接口基线通过”；状态内核正确性、真实 HTTP、事务恢复及模型质量按 A1～A3、H1/H2 和后续阶段分别验收。

## 五、计划新增的交付文件

| 目录/文件 | 维护人 | 内容 |
|---|---|---|
| `backend/app/schemas/world/v2/` | A | v2 类型、API 登记及轨迹定义 |
| `backend/scripts/export_world_protocol.py` | A | 显式版本、检查及临时目录导出 |
| `backend/scripts/world_trace_expected.py` | A | 手写预期模板实例化及 Python 摘要 |
| `backend/scripts/check_world_interface_baseline.py` | A | 本地/CI 统一检查入口 |
| `backend/tests/test_world_protocol_v2_*.py` | A | 契约、SQL 与轨迹检查，保留 v1 原测试 |
| `design/world-protocol/v2/change-list.md` | A，B 核对 | v1→v2 差异、校验层及测试落点 |
| `design/world-protocol/v2/{world-protocol.schema.json,api-contract.json,trace.schema.json,manifest.json}` | A | 公共协议及一致性清单 |
| `design/world-protocol/v2/{storage-contract.sql,canonical-vectors.json,failure-cases.json}` | A | DDL、独立预期和运行故障规格 |
| `design/world-protocol/v2/fixtures/api/` | A，B 消费 | 每个操作的 request/success/error 夹具与操作清单 |
| `design/world-protocol/v2/fixtures/`、`traces/` | A，B 消费 | 初始世界、候选、状态预期、动态绑定样本及九类轨迹 |
| `.gitattributes` | A | 协议产物 LF 字节规则 |
| `frontend/src/lib/world-engine/contract-digest.json` | A 生成，B 提交 | 消费层 pin 的协议版本与契约摘要 |
| `frontend/src/lib/world-engine/{types,protocol,transport,http-transport,trace-runner,fixture-transport}.ts` 及测试 | B | TS 消费、客户端和固定响应轨迹 |
| `frontend/package.json`、锁文件及 `tsconfig.world-contract.json` | B | 三条检查命令及其依赖/类型检查配置 |
| `.github/workflows/ci.yml` | A | 共同检查接线 |
| `design/world-engine-reports/{server,browser}.md` | 分别 A/B | 本批实现提交、契约摘要及验收证据 |

## 六、验收命令与完成清单

下列命令均已交付；完整结果以统一入口及双方报告为准。依赖分别按后端 requirements 和前端锁文件安装，具体环境记录在交付报告。所有示例从仓库根目录执行，`npm --prefix frontend` 固定前端工作目录。

```powershell
python -X utf8 backend/scripts/export_world_protocol.py --version v1 --check
python -X utf8 backend/scripts/export_world_protocol.py --version v2 --check
python -X utf8 -m pytest backend/tests/test_world_protocol_contract.py backend/tests/test_world_protocol_storage_contract.py -q
python -X utf8 -m pytest backend/tests/test_world_protocol_v2_contract.py backend/tests/test_world_protocol_v2_storage_contract.py backend/tests/test_world_protocol_v2_trace_schema.py backend/tests/test_world_protocol_v2_traces.py -q
npm --prefix frontend run typecheck:world
npm --prefix frontend run test:world-contract
npm --prefix frontend run test:world-traces
npm --prefix frontend test
python -X utf8 backend/scripts/check_world_interface_baseline.py
```

最后一条统一入口依次包含前面各类检查（含 v1 回归），但不含 `npm test`；CI 前端作业另行运行 `npm test`。聚焦测试在 world-interface 作业内由统一入口执行，与前端全套的重叠是有意的。日常可分项定位，基线冻结时统一入口必须通过。CI 另运行项目既有检查，不把本批聚焦检查当作旧功能的全量回归。

- [x] IF-01～IF-08 均有产物与对应验收记录，决策/字段/行为三层闸门均关闭。
- [x] v1 基线以 LF 提交、`--version v1 --check` 字节一致；v2 的数据、schema、SQL 和轨迹独立闭合。
- [x] S1/S2 候选与最终冻结状态明确，B 无需等待运行 API 才能开始 B1。
- [x] 两组动态身份样本及错误匹配反例通过，业务预期和摘要不从实际结果抄取。
- [x] Python、TS、导出和轨迹检查覆盖同一份契约，统一入口本地通过、CI 接线完成（`05c213e` 起远端运行 world-interface 作业且三作业全部 success）。
- [x] 根点、roll、时间锁、暂停、工作消费与复制等服务层行为均有 A2/A3 验收落点。
- [x] H1 普通点 HTTP 与 H2 刷新/接管的输入轨迹已具备，实际联调仍按后续检查点执行。
- [x] 正式基线已记录可独立检出的 Git 提交及契约摘要，双方交付记录一致。

共同前置已按本计划全部验收；实现快照 `e3b197a79f95adfbe215dddf5dfd3f9ed5b12823` 经干净检出及全新 npm ci 后重跑通过。当前可拆开推进 A1/A2 与 B1；后续服务、事务与真实 HTTP 按 A2/A3、H1/H2 验收。正式证据见 change-list 文末和双方报告。
