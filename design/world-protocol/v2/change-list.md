# v1 → v2 差异、决定落点与 S1 核对

日期：2026-10-22。v1 基线 `26011c8`，S1 验收 `cabb04c`。本表保留各轮发现与修订历史；**IF-01～IF-08 共同前置已完成，S2 消费核对通过，完整接口基线正式冻结**。最新依据见文末“共同前置最终验收”；历史的未验收/未放行状态仅适用于对应轮次。实际内核、运行服务与事务恢复分别由 A1～A3、H1/H2 验收。

依据：[正文 v0.4.1](../../browser-world-state-workflow.md)、[11 项冻结决定](README.md#本轮冻结决定)、[实施计划](interface-baseline-plan.md)、[分工](../../browser-world-state-work-split.md)。下文类型相对 `backend/app/schemas/world/v2/`，夹具相对本目录；提及未交付文件或测试时均明确标为目标。

## 版本与交付边界

| 项目 | 取值 / 当前证据 | 后续落点 |
|---|---|---|
| wire / schema 文档身份 | `protocolVersion=2`；`urn:jity:world-protocol:v2` | S1；只影响新增 wire 定义 |
| 世界 / 引擎 / 规范编码 | `schemaVersion=1`；`world-engine-v1`；`world-canonical-v1` | 沿用 v1 世界及编码，不伪造 v2 世界夹具 |
| v1 基线 | 原包导入、导出物与测试保留；首次卫生提交为 `26011c8` | IF-07 补 `--check` / 临时输出及共同入口 |
| 原 S1 (`07924f3`) 产物 | 7 个 Python 模块、2 个导出物、31 操作 × 3 夹具、18 错误夹具、operations 清单，共 112 个 JSON 夹具 | 数量只证明原 registry 内覆盖；本地修订后的数量与验证见文末 |
| SQL / 向量 | v2 尚未交付 | IF-03：`storage-contract.sql`、`canonical-vectors.json` 及对应测试 |
| 轨迹 | v2 尚未交付；`traceFormatVersion=1` 是计划值 | IF-04a/b：trace schema、T01–T09、两组动态样本 |
| 哈希 / pin / CI | manifest、contractDigest、前端 pin 与共同检查尚未交付 | IF-07/08；当前不能声称已有夹具哈希自动门槛 |

## 11 项冻结决定逐条登记

“未决”只登记待补的字段及验收证据；已有业务决定沿用原文。JSON Schema 只验证单份载荷能表达的条件，Python 验证跨字段关系，服务事务验证历史、所有权、实际状态和副作用。

| 决定 | v1 → v2 | 请求 / 响应与 S1 落点 | 校验层、夹具及后续验收 | 字段级未决 / 当前结论 |
|---|---|---|---|---|
| 1b pendingGroup | 不再用整个检查点回传冻结模型工作；discover/extend/close 窄写入，保存目标，admission 由固定 roll 和资格基线重算 | `DiscoverGroupRequest`、`ExtendGroupRequest`、`CloseGroupRequest`；`PendingGroupView` | schema：结构/集合；Python：成员关系；`fixtures/api/checkpoint_{discover,extend,close}_group/`；A2：相位/不可改写；A3：目标确认后崩溃、roll 后扩张前崩溃，T02/T07 | F02 操作分派、F09 冻结载荷读取；roll 响应的最终资格结果见“模型与候选边界” |
| 2b revision | 去掉等待叙事/暂停 phase 与 resumePhase；gate/claim/ready 不递增 revision | `ControlState`、所有 checkpoint/points/conclusion 响应；registry `mutatesRevision` | schema：phase/paused/gate；`checkpoint_pause`、`checkpoint_resume`、`narration_submit` 夹具；A2：四入口 resolve_gate、实际变化才增 revision；A3：事务重放与清理，T05/T06 | F02/F07；`mutatesRevision=true` 表示可能改变，幂等重放和 pause/resume 无变化不能据此强制 +1 |
| 1c 根点 | 创建世界事务直接创建租约、generation=1 head claim/gate；不保留 generation=0 路径 | `CreateWorldRequest`、`CreateWorldData`、`WorldContext`、`GateView` | `fixtures/api/create_world/`；schema/Python：无 round 根点形状；A2：root-ready 前不得启动；A3：创建、租约、claim/gate 原子性；IF-03/04 T01 | F01 启动链入口、F04/F05 claim 凭证、F07 代次边界；不能将合法夹具视为事务已验证 |
| 5 顺序与集合 | `stageCandidates` → `settlementGroups`；外层有序，组内 memberIds 集合排序；根点/纯时间提交为空组列表 | `SettlementGroup`、`CommitPointRequest`、`SettledUnitView.memberIds`、`WorkingProgress` | schema：重复成员/组类型；Python：集合归一化、组身份不重复；`commit_point`、`checkpoint_stage_unit` 夹具；IF-03：成员换序等价、单元换序不等价；A1：合并摘要，T02/T03 | F08 本请求 pointId 一致性；`actorIds` 是行动顺序，不等同于 memberIds 集合 |
| 4a 消费组清理 | 不按整个 round 清工作表，只清本点实际消费 groupId；后继工作保留 | `CommitPointRequest.settlementGroups`；registry `consumes_point_groups` / `clears_consumed_group_work` | `fixtures/api/commit_point/` 仅示例形状；IF-03：引用/DDL 与 `failure-cases.json` 目标；A3：P1 清 A/B 留 C/D、提交失败回滚，T02/T08 | S1 无新增字段决定；清理粒度是 A3 服务验收，当前未实现 |
| 4b 围栏与可见性 | 所有工作写入/重试/清理核对 leaseToken、fenceEpoch、revision；先过滤当前 epoch，再按成员取最大 attempt | `CheckpointRequest`、`RestoreGroupWorkRequest`、registry bindings/preconditions | schema/Python：字段类型；`checkpoint_restore_group_work`、`lease_acquire` 夹具；IF-03：可见性/引用规格；A2/A3：有效期、当前 epoch、迟到写入和清理拒绝，T07/T09 | F04 head 叙事绑定补齐；历史租约真实性不属于 schema 验证 |
| 6 条件合并臂 | 位置影响外貌时强制拆分；七单元更新 7–14 次，总计 26–35 次 | 阶段 4 模型数据集与报告，不进本批 wire 契约 | B3：强制拆分反例、实际调用数、完整六步结果；A1 保持阶段顺序 | 已登记，阶段 4 验收；不新增 S1 字段 |
| 5b PointWork | 工作 cursor/acted/visited/输入消费与已提交进度分离；stage 后回 select_actor，points 才提升 | `PointWorkView`、`WorkingProgress`、`StageUnitRequest`、`RecordSkipRequest`、`StageTimeScanRequest` | schema/Python：phase 与 pendingGroup、单元索引；各同名操作夹具；A1：时间先行、保存前缀重放；A2：B 读取 A 工作态；A3：只在提交提升，T02/T03 | F09 缺冻结顺序/已提交进度、working intent、封存/扫描状态及恢复载荷 |
| 4c 原文接续 | restore 服务端核验已确认来源后按字节复制；禁止客户端替换文本/模型重建 | `RestoreGroupWorkRequest.manifest`（sourceEpoch/sourceAttempt/hash）、`RestoreGroupWorkData` | schema：manifest 结构；Python/服务：成员、接受记录、作用域、所有哈希；`fixtures/api/checkpoint_restore_group_work/`、`fixtures/errors/frozen_work_{missing,corrupt}.json`；A3：原字节相等及非法来源阻断，T07/T09 | F09 原文/候选/来源清单读取字段，F10 requestId 与 attempt 的两层幂等 |
| 7b 时间与后继 | begin 固定基线/时间；首次确认依赖锁时；prepare 封存前缀并绑定后继，不得事后挪用文本 | `BeginPointRequest`、`SetPointTimeRequest`、`PrepareSuccessorRequest`、`BaselineView`、`SuccessorSummary` | 各操作夹具及 `point_time_locked` 错误；schema/Python：时间形状；IF-03：prefix 向量；A2/A3：无确认依赖才能改时、P1 提交逐项匹配/提升，取消后旧身份不复活，T08 | F09 时间扫描/封存状态、后继完整基线和工作读取；服务端计算前缀/状态摘要，客户端不能自报权威基线 |
| 2c pause 与 gate | pause/resume/restore 穿过 gate；恢复成功可 canCompute=false；ready 不自动清暂停 | `PauseRequest`、`ResumeRequest`、`ControlState.blockedReasons/canCompute`；权限矩阵 | `checkpoint_pause` / `checkpoint_resume` / `checkpoint_restore_group_work` 夹具；schema/Python：组合；A2：失效清理可提交但业务不推进，绑定/租约错不清 gate；A3：TTL/事务，T05 | F02 分派、F07 schema 对齐；canCompute 仅为服务响应时刻快照 |

## 其余 wire 变化与交付选择

| 项目 | 采用的口径 | 需要落实的字段 / 检查 |
|---|---|---|
| 操作粒度 | 每个 checkpoint 窄操作独立登记；conclude（continue/handback）与 cancel 分开；叙事 5 操作 | 保留这种粒度；31 不是完整操作数，必须补启动玩家链（F01）并有 wire 分派（F02） |
| 控制状态权威 | commit 不携带完整 checkpoint；下一位置由封存 PointWork 推导 | 接受；服务复核 point/Δ/摘要及下一位置，禁止浏览器回传 `PointWorkView` 代替已存工作 |
| 纯时间单元 | 暂存候选以 `SettlementGroup.groupId=null` 表示；points 的 `settlementGroups=[]`，从已保存扫描重算 | 接受；null 标识的是候选单元，不是可提交的无名行动组；不得跳过时间/任务/个性/理智扫描 |
| 权限 | pause/resume/restore 穿 gate；restore 不改 revision；cancel 要求 ready、允许 paused；conclude 要求 gate cleared 且未暂停 | 沿用 §9.2；正常 conclude 包含 handback（F03），与手动 cancel 不可互相替代 |
| `narrationBlock` 重命名 | 旧字段拆成 `gate` 状态与 `blockedReasons` 枚举数组 | v2 wire/消费端不再使用旧字段；保留 v1 定义仅为兼容，不得把 v1 `RoundCheckpoint` 当成 v2 控制器 |
| 错误枚举 | 18 码；新增 `request_malformed` 对应 400 可省略 control；`contract_mismatch` 仅 CI/pin | 接受；有效他人租约 → `lease_invalid` + `details.reason=lease_held`；未知身份 → `version_mismatch`；固定码元数据两层验证（F07） |
| 公共读包络 | context 用无 requestId 的 `ContextResponse`；其余 3 读操作用 `ReadResult` | 接受；preview 也不生成业务 requestId（F06）；`list_points` 的 after/limit、`get_state` 的 point 查询参数仍须补类型、必填/默认/边界规则，当前 requestSchema=null 的 `{}` 夹具不能验证这些参数 |
| 输入保留与清理 | 正文仅 GET context.activeInput 可读，跨 automatic round 保留，handback/cancel 清理；写响应及幂等记录不缓存正文 | F01/F03 补齐入口；A2/A3 用 T04/T06 验证清理后重放不复活正文 |
| 凭证返回 | context/control/error 不含 token；claimToken 只在授权认领返回，成功重放不带 | F04/F05；lease/head claim 签发 epoch 与绝对时间均须有实际请求字段，history fenceEpoch=null |
| 摘要 | state/request/prefix 使用对应 schema 投影规范字节 SHA-256；contentHash 使用原文 UTF-8 字节 SHA-256；contractDigest 与 artifact hash 各自独立 | IF-03 补投影/向量；IF-07 补 manifest/pin。真实 64 位哈希字符串并不独自证明投影语义正确 |
| 导出/手写产物 | 生成 schema/API/operations 清单；手写请求/成功/错误 JSON 不经重导出改写 | `export_world_protocol.py` 当前会重写 `fixtures/api/operations.json`，因此将它明确归为生成的覆盖清单；其余 111 个手写夹具只读核对。IF-07 补 artifact 哈希检查 |
| 工具链数值边界 | 保留 v1 字节；v2 不得依赖无效的 `ge/le` JSON 键执行边界 | 已复现 generation=0 的 schema 漏检；F07 补有效 JSON Schema minimum/maximum 等约束，不以 Python 已拒绝代替消费校验 |

## 模型、控制器与可提交候选边界

| 输入/输出 | 允许的内容与权威 | S1 位置及缺口 |
|---|---|---|
| 模型行动/目标 | 行动原文、完整目标集；不能生成持久化 ID、骰点或阈值 | discover/extend 接收控制器包装后的数据；行动/目标确认后不可重采样；F09 需可读回已确认内容及完成标记 |
| 程序身份 | advance/input/round/group/task/change/point/trigger 来自 ids，rollId 来自 rolls；worldId 在创建时由服务分配 | `AllocationSlot` / `AllocateIdsData`；创建请求仍复用必含 worldId 的 `WorldInitialState`，需明确新建初始模板与最终已绑定世界的类型边界，不能让客户端猜替换规则 |
| 判定 | 服务固定规则及资格基线，一次落最终 roll/eligibility/admission；原判定键复用 | `RollOutcome` 当前只有骰点结果，未提供最终 eligibility/admission 或资格基线绑定字段；补齐给 B 使用的判定结果形状，真实计算在 A2/A3 |
| 六步候选 | 位置、外貌、任务达成、小任务、个性、理智与覆盖清单；时间先行；个性变化配理智，新增/达成及实体权限由 Python 核验 | `SettlementGroup`；schema/Python：静态组合；A1：固定实体/位置图/任务引用及阶段语义；A2：冻结结果和已存阶段候选须可恢复（F09） |
| preview | 从服务权威基线复算，返回工作态、可提交 pointProjection、合并 Δ 及摘要 | `PreviewData` 当前只有 workingState 和两个摘要，缺可提交投影/合并增量，不能靠 TS 自行生成（F06） |
| points | 绑定已存封存前缀，服务重算、比对候选/摘要并提升进度 | `CommitPointRequest`；F08 补 pointId 自身一致性；真实 apply/提交/清理在 A1/A3 |

## S1 字段闸门修订项

以下是在 `07924f3` 上核对或运行最小反例得到的结果。应先修复 Python、导出物、手写夹具及正反例，再按 registry 做穷尽检查；不能仅增加声明把本表改成通过。以下保留发现时证据；本地候选修订见文末，尚未取得 B 核对与验收。

| 编号 | 优先级 / 证据 | 影响与修订验收 |
|---|---|---|
| F01 | P1：`registry.py` 无启动玩家链操作；`requests.py` 无任何接收 inputText、advanceId/inputId、首 round 冻结顺序的启动请求 | 根点 ready 后无法开始玩家输入。补独立 checkpoint 启动类型/registry/夹具/权限；T01/T04 覆盖无活动链和 ready 门槛。覆盖率测试必须有来自正文的必需操作清单，避免 registry 与夹具同时遗漏仍通过 |
| F02 | P1：同一个 `PUT /worlds/{worldId}/checkpoint` 的所有请求无 operation 判别字段；一份 pause 夹具同时通过 PauseRequest、ResumeRequest | HTTP 无法区别暂停和恢复，多个 point 工作请求也有重叠。给同路径操作加入 Literal 判别字段并导出可分派联合类型；同请求只能选中一个操作；别名/同形字段不能作为分派依据 |
| F03 | P1：`ConcludeRoundRequest.conclusion` 仅为 `ContinueConclusion`；替换为 `{kind:handback,closedBy:model,cancelReason:null}` 被 Python 和 schema 拒绝 | 无法正常交还玩家。采用 continue/ModelHandback 联合；成功副作用按分支表达创建 nextRound 或清正文/到期意图；增加 handback 请求/成功/错误分支，T04 |
| F04 | P1：NarrationClaimRequest、NarrationClaimRenewRequest、NarrationSubmitRequest、NarrationDeleteRequest 均没有 leaseToken/fenceEpoch；registry 却要求 head lease valid | head 操作无从提供约定的租约凭证/签发 epoch。定义 head/history 请求联合，head 必带租约及正确 epoch，history 不借用推进租约；同步 DELETE 查询字段与 bindings；无凭证/旧 epoch 反例必须拒绝 |
| F05 | P1：认领成功设 replayed=true 后删除 data.claimToken，Python/schema 均拒绝；续期成功也因复用 NarrationClaimData 必须返回 token | “重放无 token”与当前成功类型矛盾。区分首次授权认领取回、续期摘要和成功重放载荷；重放前校验信息泄露边界，测试旧请求重放不会返回 token；若采用凭证单独取回，必须给出完整 wire 流程 |
| F06 | P1：preview 无 requestId，但 PreviewPointSuccess 继承要求 requestId 的 OperationResult；现有 success 夹具使用 `request_missing`；PreviewData 无 pointProjection/合并 Δ | 不能凭已有返回值构造要求的可提交 point，也把无幂等操作伪装成写入结果。提供无业务 requestId 的计算结果包络、服务生成的投影/Δ 与绑定摘要，测试 preview→commit 无需 TS apply；32 单元、512 KiB 请求、2 MiB 响应及 2 秒预算检查分别登记服务验收 |
| F07 | P1：五类 controlRequired 错误中，control=null 被 schema 接受但 Python 拒绝；篡改错误 httpStatus/retryable/clientAction 也只被 Python 拒绝；`GateView(status=none,generation=1)` 缺时刻字段却被 Python 接受；generation=0 被 schema 接受 | 这些组合/数值边界可由 schema 表达，应两层一致：control 必为非空对象、错误码绑定常量、none 时所有认领字段为空、pending 代次为正。另补 ready/failed 文本组合与 closed group frontier 为空等同类条件。跨字段 ID 相等/集合包含关系仍只在 Python，历史/租约留服务层 |
| F08 | P1：commit 请求只改顶层 pointId 为 `p_different`，保留 point.id=p1，仍通过 Python | 一份请求指向两个点。Python 加 pointId==point.id，服务再核对当前封存工作；增加自身错绑与服务器陈旧身份两类反例，前者不需要运行服务即可验证 |
| F09 | P1：context/PointWorkView 只有摘要和成员 ID；没有冻结行动原文、逐源完整目标/完成标记、已存结果/阶段候选/接受来源清单；没有冻结 round 顺序/已提交游标、working intent、封存及时间扫描完成状态；successor 只有摘要 | 刷新后控制器无法从服务恢复下一步，原文复制后客户端仍读不到已确认工作。给出受围栏保护的只读恢复载荷及其所属当前/预约 PointWork；不得把这些内容加入永久行动历史或幂等 data。S1 固定字段/读取权限与夹具，A2/A3 才验证实际恢复/原文字节与可见性，T02/T07/T08/T09 |
| F10 | P2：registry 把 allocate_ids/create_rolls 的主 key 写成 allocationKey/judgmentKey，restore 写成 requestId+attempt；计划要求所有世界内写入先以 `(worldId,requestId)` 处理成功重放/冲突 | 区分请求幂等主键与业务去重子键（allocation slot、判定身份、复制 attempt），不能二选一。导出两层机器可读信息，T06 分别验证同 requestId 改操作/内容拒绝、换 requestId 同业务键复用原身份；运行原子性在 A3 |

补充字段核对也必须随 IF-02 关闭：读查询参数、创建世界模板身份、roll 最终资格结果见上表；这几项尚未有完整反例夹具，不能标成已验收。字段修订后逐一对照正文，不以“31 操作已全覆盖”作为停止条件。

## 本轮验证与后续闸门

2026-10-22 从仓库根运行：

```powershell
python -X utf8 -m pytest backend/tests/test_world_protocol_v2_contract.py backend/tests/test_world_protocol_contract.py backend/tests/test_world_protocol_storage_contract.py -q
```

结果：**216 passed**（S1 107 + v1 109）。这证明现有测试通过；F01–F10 表明测试还没有覆盖完整字段闸门。另用 Python 模型和 Draft202012Validator 对同一内存载荷运行上述变异，得到表中结果；未运行实际 world API 或 SQLite 事务。用户报告的 campaign_wiring 两项既有失败不纳入本次结论，本轮没有重跑全量 backend。

另导入现有导出脚本，将 `write` / `write_v2` 临时替换为内存收集函数后分别运行 `build()` / `build_v2()`，按现有 JSON 序列化和 LF 字节规则比对提交文件：v1 的 12 个、v2 的 3 个生成物均无字节漂移；未写回任何产物。这是本轮只读验证，不表示 CLI 已实现计划中的 `--check` 参数。

- IF-01：11 决定、正文补充规则、模型/控制器边界及服务验收落点已登记；A 侧差异表已补齐，等待 B 核对；不把字段缺口称为新业务决定。
- S1：保持未验收；修 F01–F10 及补充字段、补正反例、重导出并再次核对后，B 再据完整字段快照进入 IF-05。B 可继续准备不依赖这些字段的 transport/测试骨架。
- IF-03/04：DDL、向量、failure-cases、trace schema/T01–T09 仍是待交付，不能从本次 schema 测试推断事务或轨迹已通过。
- 轨迹覆盖：当前不授予任何操作 `fixture-only` 豁免；IF-04a 必须遍历修订后的完整 registry，若确需豁免，在本表逐操作补理由及消费验证位置。
- IF-07/08：导出只读/临时目录检查、manifest 哈希、TS/pin/共同 CI 和双方验收完成后才冻结完整基线。


## S1 本地修订候选（2026-10-22，待 B 核对）

本轮已修改 Python、手写夹具及 v2 三个生成物，尚未提交或推送。原 `07924f3` 的问题证据与上轮 216 项只读验证保留，不将本次候选视为双方验收。IF-01 的 B 核对、S1 验收与 IF-05 放行状态均未改变。

| 项目 | 本地修订落点 / 验证证据 | 仍需核对或服务验收 |
|---|---|---|
| F01 | `StartAdvanceRequest/Data/Success`、`checkpoint_start_advance`；接收 inputText、advance/input/round ID 与冻结 order。新增独立于 registry 的正文必需操作清单。registry 现为 32 操作 | A2/A3 验证 ID 分配与人物顺序、无活动链、ready/gate、输入正文清理；T01/T04 |
| F02 | checkpoint 的 14 个操作和 conclude/cancel 均有必填 Literal operation；`CheckpointDispatch` / `RoundConclusionDispatch` 是直接 HTTP body 联合，逐操作验证唯一分派 | B 核对 transport 分派；未提供运行路由 |
| F03 | continue/ModelHandback 判别联合；结论 data.kind 约束 nextRoundId，registry `conditionalSideEffects` 区分 continue 与 handback；新增 handback 请求/成功/错误分支 | A2/A3 实际清正文、到期意图、创建后继及重放不复活正文；T04 |
| F04 | 四类叙事请求各导出 head/history 判别联合；head 必带 leaseToken/正 fenceEpoch，history 只允许空租约字段；DELETE queryBindings 与 bindings 补齐，登记 stale_epoch | schema 只拒绝缺失或非正 epoch，正数旧 epoch 须由服务核验当前租约并拒绝；A2/A3/T09 |
| F05 | 授权认领取回用 `NarrationClaimData`，续期/成功重放用无 token 的 `NarrationClaimSummary`；重放携带 token、首次成功缺 token 均由两层拒绝 | 同 requestId 重放只返回摘要；需取回凭证时使用新 requestId，head 凭有效租约，history 凭有效 currentClaim；过期/围栏时走重新认领。实际授权、TTL 和重放顺序在 A2/A3 |
| F06 | `ComputeResult` 无 requestId/requestHash/replayed；preview 返回 pointProjection、mergedEntityDeltas、原有摘要与工作态。回归直接使用返回 point 构造合法 commit，无需 TS apply | 实际 apply、摘要投影在 A1/IF-03；32 单元、512 KiB 请求、2 MiB 响应、2 秒预算在 A2/A3 验收 |
| F07 | controlRequired 禁止 null；逐错误码固定 HTTP/retryable/clientAction；none gate 禁止部分认领字段；pending 正代次及安全整数边界有效；closed frontier、ready/failed 文本、封存摘要与扫描完成组合补齐 | v2 使用 `WireSchema` 将工具链遗留 ge/le 转为有效边界，v1 输出保持原字节。历史/所有权仍由服务验收 |
| F08 | Python 校验 pointId==point.id；自身错绑反例、合法请求配陈旧服务头/refresh_context 错误夹具均登记 | 陈旧头拒绝是服务预期，未运行实际事务 |
| F09 | round 增冻结 order/已提交进度；work 增 working intent、sealed/prefixDigest、predecessorWorkDigest、timeScanComplete。`ContextResponse.recovery` 返回当前/预约后继完整工作、逐成员原文、targets（null 未确认，[] 已确认空集）、结果、候选及接受来源/哈希。`stage_unit.results` 补结果写入入口，discover 允许尚未确认目标 | 仅 `GET context?includeRecovery=true` 且提供有效 leaseToken/fenceEpoch 才返回 recovery；普通读取 recovery=null；正文仍只在 activeInput。读取过滤当前 epoch、原文字节、来源真实性与 hash 投影在 IF-03/A2/A3；T02/T07/T08/T09 |
| F10 | 所有写入主键统一 scope+requestId；allocation/roll/restore 另列 `businessKey` 与 `businessReplay`，不再替代请求主键 | 同键改操作/内容拒绝、换 requestId 复用业务身份及事务原子性在 T06/A3 |
| 补充字段 | 无 worldId 的 `WorldInitialTemplate`；list_points 的 after 为非负序号、limit 默认 50 且 1–100；get_state 的 point 为可省略 ID（省略取 head）；roll 返回 eligibilityBaselineDigest、eligible、admitted | B 核对查询语义；服务分配世界 ID、固定资格快照与判定在 A2/A3 |

`recovery` 不进入写成功包络或幂等 data。恢复夹具有已 stage 当前点、已预约完整后继和行动已确认/目标未确认三个分支。`WorkManifestItem` 及接受来源显式区分行动、目标、结果和候选哈希；未确认项为 null。哈希投影的固定向量仍在 IF-03，当前字段合法不证明摘要语义或来源真实。

当前交付为 32×3 个操作夹具、18 个错误夹具、8 个补充分支及 operations 清单，共 123 个 JSON。新增 `backend/tests/test_world_protocol_v2_revision.py`，与原 v2/v1 两套契约及存储契约一起运行：

```powershell
python -X utf8 -m pytest backend/tests/test_world_protocol_v2_revision.py backend/tests/test_world_protocol_v2_contract.py backend/tests/test_world_protocol_contract.py backend/tests/test_world_protocol_storage_contract.py -q
```

结果：**264 passed**（v2 155 + v1 109）。内存重建并按 LF/UTF-8 比较：v1 的 12 个产物同时与工作区及 HEAD 一致；v2 的 3 个生成物与修订后的生成器一致。未运行实际 world API、SQLite 故障事务、TS 消费或全量 backend；本次不宣称 IF-03/04/05/07/08 已通过，CLI `--check` 仍待 IF-07。

下一闸门是 B 对本地修订候选逐项核对与 S1 验收；在此之前 IF-05 保持未放行。

## 本地修订候选复核（2026-10-22，仍未验收）

本轮独立复跑上述四份测试，结果 **264 passed**；内存收集生成物并比对，v1 的 12 个产物与工作区及 HEAD 均一致，v2 的 3 个产物与生成器一致。未改候选 Python、测试、夹具或导出物，未提交、未推送。以下是对本地修订的剩余问题，不替代前面的原始发现及修订证据。

| 编号 | 优先级 / 剩余问题 | 复现与影响 | 修订验收 |
|---|---|---|---|
| R01（F09） | P1：接管后缺少可读取的权威来源清单，restore 的输入无法从已定义读取结果取得 | `RestoreGroupWorkRequest` 必带 sourceEpoch/sourceAttempt 和包含各类哈希的 manifest；context.work 仅有单元摘要，完整 acceptedSources 只在 recovery.groups 中。get_context 明确只返回当前 epoch 原文/候选；新持有者 epoch=8、原工作仍在 epoch=7 且尚未复制时，不能先读取旧载荷来取得 manifest。现有 recovery 类型又将目标/结果/候选哈希与载荷同时出现绑定；对 recovery.success 夹具保留 acceptedSources，但将 members 的 actionText/targets/resultText 及 group.candidates 置 null，Python 即拒绝 `target completion differs from accepted source`。现有三个恢复分支均是 lease/recovery epoch=7、来源=7，未覆盖这个接管前置窗口 | 明确可读取的接受记录/来源清单与受 epoch 隔离的原文/候选的区别；或由 restore 从服务端活动引用派生来源，客户端不再提交无法读取的清单。给出新标签页取得 epoch=8 租约 → 取得合法 restore 输入 → 复制 → 读取当前 epoch 工作的字段级完整轨迹；旧原文不得提前暴露，缺失/损坏不得变成模型采样入口。实际事务验证仍留 A3 |
| R02（F09/4c） | P1：restore 的机器可读权限只允许 pointWork=open | `registry.py` 的 checkpoint_restore_group_work 仍是 `_pre("pointWork", "open")`；现有 recovery-successor 分支明确已有 sealed=true 的前驱和已 stage 来源。若 seal/prepare_successor 后租约交接，新持有者就不能复制该封存前缀，亦不能从当前 epoch 读回它；解封/重算会违反前缀不可改规则 | 允许对仍活动引用的 open/sealed 工作做受控复制，继续禁止 consumed/abandoned 来源；不改 sealed、prefix、候选、phase、revision。补 sealed 前驱及后继接管的权限和请求/响应反例；当前字段层即可检查权限表，真实围栏/复制在 A3 |
| R03（F07） | P2：pending gate 的 schema 仍未要求认领字段实际存在 | `GateView` 的 generation/issuedAtEpochMilli/expiresAtEpochMilli 都默认 None；pending 的 if/then 仅有 properties 类型约束，没有 required。实测 `{"status":"pending"}` 和 `{"status":"pending","generation":1}` 均被导出 schema 接受，而 Python 均拒绝。现有 pending_without_generation 反例写入 null，没有覆盖字段缺失 | 在 pending 条件分支要求上述三个字段；分别删除每个字段并在 Python/schema 两层断言拒绝，同时保留合法 pending、合法 none 与 none 部分字段非法的用例 |

复核结论：已交付的修订覆盖了原问题的大部分字段落点，但 F07/F09 尚不能标为关闭。先修 R01–R03，再交 B 核对和 S1 验收；IF-05 继续未放行。本轮未运行实际服务、事务故障或 TS 消费，不能将静态契约复核当作这些行为已通过。


## R01–R03 本地再修订（2026-10-22，待 B 核对）

上节保留独立复核的发现时证据。本轮已修改 Python、权限登记、恢复夹具和 v2 导出，新增 24 项回归；R01–R03 已有如下字段级修订与证据，仍待 B 核对和 S1 验收。未提交、未推送，IF-05 继续未放行。

| 项目 | 本次修订及可复核证据 | 后续行为验收 |
|---|---|---|
| R01 | 新增独立的 `GroupWorkSource` 元数据类型，`PointRecoveryView.restoreSources` 返回仍被当前/预约 PointWork 引用的 pointId/groupId/sourceEpoch/sourceAttempt/manifest。它不携带任何原文或候选，且不依赖当前 epoch 是否已有副本。`RestoreGroupWorkRequest` 复用同一来源类型，可从读取结果直接填入请求；再补当前租约、头/版本/revision、requestId、目标 attempt | 接受记录真实性、来源/载荷哈希、当前租约有效性与实际读写过滤仍由 A3 验证；客户端提交清单不构成授权 |
| R01 的载荷边界 | `payloadStatus=restore_required` 时必须有非空 restoreSources，groups=[] 且 timeScanCandidates=null，保留 work 的已确认/封存/扫描状态；`available` 才携带当前 epoch 原文和候选。旧来源哈希可读，旧正文不提前暴露。已有 `FrozenGroupView` 继续校验完整可见载荷，不使用置空已确认字段的方式伪装尚未完成 | 来源存在但字节缺失/损坏时，保留权威来源引用，restore 明确返回 frozen_work_missing/frozen_work_corrupt；不转成模型重采样入口 |
| R02 | registry 允许 pointWork=[open,sealed]，并新增独立前提 frozenSource=active_reference。PointRecoveryView 在 Python 层校验来源所属点、活动 pending/staged group 引用及成员范围；机器权限与说明排除 consumed/abandoned。复制副作用仅 copies_frozen_work，mutatesRevision=false，无 gate/paused 阻断 | 服务核对真实活动引用，已消费/废弃返回 frozen_work_missing + details.reason=source_not_active；不得解封或改变 prefix/candidates/phase/revision |
| R03 | GateView 的 pending 条件分支补 required=[generation,issuedAtEpochMilli,expiresAtEpochMilli] | 两层均拒绝逐字段删除、只剩 status 以及只剩 status/generation；合法 pending、none（可省略全部认领字段）与 none 部分非空反例保留 |

新夹具 [`fixtures/branches/takeover.json`](fixtures/branches/takeover.json) 是本轮**字段级流程示例**，不是 IF-04 的可执行动态 trace 格式，也不表示事务已通过。它依次给出：

1. 新标签页取得 epoch=8 的 lease_b。
2. 带 lease_b/8 读取 context：封存前驱与预约后继都返回 epoch=7 的 restoreSources，但两者载荷均隐藏。
3. 从该读取结果直接构造封存前驱的 restore 请求并取得成功摘要。
4. 同样构造预约后继的 restore 请求并取得成功摘要。
5. 再次读取 context，得到 epoch=8 可见的原文/目标/结果/候选；原封存、前缀、后继基线、phase、paused、revision 与来源清单保持不变。

该文件还分别为前驱、后继提供缺失、损坏、consumed、abandoned 和旧租约五类失败预期，共十组请求/错误示例；失败快照不改变控制或工作状态。回归验证所有示例通过 Python/schema、restore 输入确实来自复制前的来源清单、隐藏期间不能携带载荷，以及复制后前驱原文/结果 UTF-8 哈希与原夹具一致。这些断言验证字段和预期的一致性，真实复制、原子性、围栏和不重采样留在 A3/T07/T09。

复跑本文同一四文件测试命令：**288 passed**（v2 179 + v1 109）。当前共 124 个 JSON 夹具（原 123 个新增上述流程文件）。内存重建再次按 LF/UTF-8 字节核对：v1 的 12 个产物与工作区及 HEAD 均一致，v2 的 3 个产物与当前生成器一致。`git diff --check` 通过；没有改 v1 契约或生成物。

当前状态：R01–R03 的字段修订已形成待核对候选；IF-01 的 B 核对、S1 验收仍未完成，IF-05 不放行。实际服务、SQLite 故障事务和 TS 消费均未在本轮执行。

## R01–R03 再修订的独立复核（2026-10-22）

本轮按 R01–R03 的原发现与修订验收逐项复核，未发现这三项的新增字段阻塞：

- R01：`GroupWorkSource` 独立表达复制前可读的权威来源元数据，`RestoreGroupWorkRequest` 复用其字段。takeover 夹具给出 epoch=8 新租约、读取 epoch=7 来源、构造前驱/后继 restore 请求和复制后读取的完整字段流程；`restore_required` 隐藏原文及候选，同时保留已确认/封存状态。已检查直接填入请求、禁止夹带旧载荷、来源点/成员范围及活动引用的反例。
- R02：Python registry 与导出 API 权限一致，restore 允许 `[open,sealed]`，同时要求 `frozenSource=active_reference`；副作用仅复制工作，revision 不变，gate/paused 不阻断。封存前驱与预约后继的示例和 consumed/abandoned 失败预期均已覆盖。
- R03：pending 分支已要求 generation、issuedAtEpochMilli、expiresAtEpochMilli 实际存在；逐字段缺失及组合缺失由 Python/schema 两层拒绝，合法 pending/none 和 none 部分字段非法的检查保留。

独立运行本文四文件定向回归：**288 passed**。将生成器写函数替换为内存收集后核对 LF/UTF-8 字节：v1 的 12 个产物与工作区及 HEAD 一致，v2 的 3 个产物与当前生成器一致；`git diff --check` 通过。复核未修改 Python、测试、夹具或生成物，未提交、未推送。

结论限于 **R01–R03 字段级复核通过**。来源真实性、实际租约/围栏、复制原子性、旧 epoch 隔离及失败不重采样仍在 A3/T07/T09 验收；字段流程夹具不等于已运行服务事务。IF-01 的 B 核对及 S1 验收仍待完成，IF-05 继续未放行。

## B 消费侧核对结论（2026-10-22：不通过）

本节是按浏览器调用方职责进行的 B 侧核对，包含独立 JavaScript 消费检查，不以 Python 的 288 项通过替代验收。**当前 S1 不通过：剩余一个 P1 字段来源问题 B01，正式验收及 IF-05 放行条件尚未满足。** 原 F01–F10、R01–R03 的历史记录保留；R01 的来源清单与隐藏载荷修订有效，但完整 restore 请求还需要一个未定义取得方式的目标 attempt。

### 可复现的消费检查

新增 [`frontend/scripts/review-world-s1.mjs`](../../../frontend/scripts/review-world-s1.mjs)，由 Node 22.20.0 / Ajv 8.20.0 直接读取本目录 schema、API 与夹具；不导入 Python，不计算 apply、admission 或规范摘要，不访问运行 API。

```powershell
npm --prefix frontend run review:world-s1
```

本轮结果：**58 个检查通过，2 个检查失败，进程退出码 1**；两个失败均来自 B01，分别是封存前驱和预约后继的 restore 请求构造。脚本编译了全部 **173 个 schema 定义**，按独立手写的正文操作清单核对 **32 个操作**，逐个消费 request/success/error，检查 JSON 往返、成功身份关联、路径/查询参数/协议头组装与全部 **18 个错误码**的客户端动作。另核对计算门槛、pause/resume/restore/cancel 例外、无 token 重放、preview→commit、正常 handback 与接管前后字段保持。

Ajv 使用 Draft 2020-12 类；不修改、补默认值或强制转换载荷。Pydantic 的 OpenAPI discriminator mapping 作为注解读取，由 JSON Schema 的 oneOf/const 校验联合；其余未知 schema 关键字仍拒绝。后续 IF-05 仍须交付正式 TS 类型、运行时适配、受控 fetch/超时/非法 JSON 测试，当前脚本不是完整 transport 或 IF-04 动态 trace runner。校验器选型依据见 [Ajv schema 版本说明](https://ajv.js.org/json-schema.html#draft-2020-12-breaking)。

### 11 项决定核对

| 决定 | B 的消费判断 | 结论 |
|---|---|---|
| 1b pendingGroup | discover/extend/close 有可分派请求；原文和目标完成状态可读回，判定由服务端返回 eligible/admitted，B 不重算资格 | 字段可消费；实际冻结/判定在 A2/A3 |
| 2b revision | 所有成功结果可读 control.revision；gate/claim/叙事不被当作 revision 变化的依据 | 字段可消费；实际递增/重放在 A2/A3 |
| 1c 根点 | create 返回租约、无 round 的根点与 generation=1 gate；B 后续显式取得认领，不能从 context 猜 token | 字段可消费；创建原子性在 A3 |
| 5 顺序与集合 | 外层 settledUnits/settlementGroups 顺序在 JS JSON 往返中保留；memberIds 等集合按服务规范值消费，B 不自行重排行动顺序 | 字段可消费；规范向量在 IF-03 |
| 4a 清理粒度 | points 请求列明本点消费组；后继仍有独立工作身份与读取投影，B 不发整 round 清理 | 字段可消费；真实保留/清理在 A3 |
| 4b 围栏/可见性 | 写入携带租约/epoch/revision，受保护读取用当前租约；sourceEpoch 与当前 epoch 分开，旧载荷隐藏状态明确 | 字段可消费，但目标 attempt 的分配权见 B01 |
| 6 条件合并臂 | 不增加 wire 字段；B3 数据集必须记录位置影响外貌的强制拆分与实际调用数 | 阶段 4 验收，不阻塞 S1 字段核对 |
| 5b PointWork | committed 与 working 进度分开；sealed、扫描完成、原文/候选与当前/预约工作可区分，不用工作游标提前覆盖已提交进度 | 字段可消费；实际推进在 A2/A3 |
| 4c 原文复制 | 复制前 source metadata 可读取，复制后才能读当前 epoch 原文；open/sealed 权限足够；但不能仅从服务返回值构造合法 restore 请求 | **不通过：B01** |
| 7b 时间与后继 | 点基线/锁定时间、封存前缀、预计前驱状态及后继工作均有字段；改时间走显式 cancel，新链不复用原判定 | 字段可消费；前缀复算与事务提升在 A1/A3 |
| 2c pause/gate | resume.success 中 paused=false 与 canCompute=false 可同时读取；blockedReasons 明确要求等待/重领；ready 不被当作清暂停 | 字段可消费；真实 TTL/事务门槛在 A2/A3 |

### 32 个操作核对清单

以下“通过”仅表示字段、机器权限和夹具具备消费入口，不表示服务行为或 IF-05 实现已完成。restore 的已有请求夹具本身合法，失败发生在 B 从响应组装该请求时。

| 操作 | 字段/权限与消费结论 |
|---|---|
| create_world | 通过：无 worldId 初始模板，返回世界/根点/租约 |
| get_context | 通过：无 requestId；普通投影与带租约的 recovery 读取分开 |
| checkpoint_start_advance | 通过：分配身份、输入正文、冻结顺序；要求无活动链、ready/gate cleared |
| checkpoint_begin_point | 通过：point/kind/time，工作不存在时创建 |
| checkpoint_set_point_time | 通过：timeLocked=false 且无确认依赖；锁定错误明确 |
| checkpoint_discover_group | 通过：行动、目标未确认/已确认空集有区别，select_actor→build_group |
| checkpoint_extend_group | 通过：完整目标集或准入成员联合，build_group 内写入 |
| checkpoint_close_group | 通过：闭组身份与完成状态，build_group→settle_group |
| checkpoint_stage_unit | 通过：结果/完整候选与 working 进度，结算后回 select_actor |
| checkpoint_record_skip | 通过：槽位身份与 working 进度，不伪造已行动集合 |
| checkpoint_stage_time_scan | 通过：无名纯时间候选单元与完成标记 |
| checkpoint_seal_point | 通过：prefixDigest、sealed，封存后候选只读 |
| checkpoint_prepare_successor | 通过：预分配后继身份、预计基线、锁定时间及 prefix 绑定 |
| checkpoint_restore_group_work | **不通过 B01**：目标 attempt 必填，但没有合法取值入口；其余来源清单/open/sealed/gate/paused 权限可消费 |
| checkpoint_pause | 通过：可穿 gate，paused 与 control 分开读取 |
| checkpoint_resume | 通过：恢复成功不代表可以计算，实际夹具为 canCompute=false |
| round_conclusion_conclude | 通过：continue/handback 联合及按分支的副作用 |
| round_conclusion_cancel | 通过：要求 ready、允许 paused，显式废弃未提交工作 |
| lease_acquire | 通过：返回 token/epoch/expiry，lease_held 用明确错误动作 |
| lease_renew | 通过：匹配 token/epoch，返回续期摘要 |
| lease_release | 通过：查询参数与协议头可组装 |
| allocate_ids | 通过：稳定 slot 分配，requestId 幂等与业务去重分开 |
| preview_point | 通过：无业务 requestId 的包络，Python 投影可填入 commit，不需要 TS apply |
| create_rolls | 通过：判定键、规则与最终资格/准入结果；B 不自行掷骰或算 admission |
| commit_point | 通过：point/组候选与绑定，服务所有控制状态；要求 sealed/ready/gate cleared |
| list_points | 通过：after/limit 查询类型与无 requestId 读结果 |
| get_state | 通过：可选 point 查询与重建状态摘要 |
| narration_claim | 通过：head/history 联合，fresh 授权返回 token，成功重放只有摘要 |
| narration_claim_renew | 通过：认领与租约围栏字段，返回无 token 摘要 |
| narration_submit | 通过：ready/failed 载荷，head/history 围栏与不改 revision 的约定 |
| narration_get | 通过：状态/代次/文本，非 ready 不接受旧文本 |
| narration_delete | 通过：查询携带认领与适用租约绑定，明确失效代次 |

### 剩余问题及正式结论

**B01（P1）：restore 的目标 attempt 仍由客户端填写，与服务端分配规则矛盾，且 B 没有取得入口。** `RestoreGroupWorkRequest.attempt` 为必填；context 的 restoreSources 只提供旧来源的 sourceEpoch/sourceAttempt/manifest；lease、ids 和 restore 成功结果也不返回预分配的目标 attempt。正文 §9.4 明确“attempt 由服务端单调分配”。本轮检查使用新租约、context 的头/版本/revision、完整 source metadata，加上客户端自行生成的 requestId 构造请求，前驱/后继两者都被 Ajv 拒绝 `must have required property 'attempt'`。现有 takeover 手写请求中的 attempt=2 不是服务响应，不能当作该字段的来源证明；B 不能猜 1、sourceAttempt+1 或跨 epoch 最大值。

建议 A 保持服务端分配权：请求不要求客户端指定目标 attempt，由 restore 事务分配，并在成功 data 返回已接受的复制身份/attempt；同步修改业务去重键，使它绑定源引用与目标 epoch，而非客户端未知的 attempt。若选择单独预分配入口，必须补齐真实字段与读取/重试语义。修订验收是本脚本直接从服务返回值构造两份合法请求，不从手写请求抄 attempt；重发同 requestId 与换 requestId 的业务去重仍在 A3 验证。

本轮正式 B 结论：**不验收当前 S1，不放行 IF-05，不执行“验收后整理提交”步骤。** A 先修 B01，再复跑 B 消费检查与必要 Python 回归并更新明确结论。A 的 IF-03/04a 和 B 的正式 IF-05 交付状态未被本轮核对改成完成；运行 API、事务与 TS transport 的后续验收边界不变。

补充验证：本轮重新运行四份 Python 定向测试，**288 passed**；前端既有 `npm --prefix frontend test` 为 **8 个文件、62 项通过**。内存重建的 v1 12 个产物与工作区/HEAD 一致，v2 3 个生成物与生成器一致。这些绿色结果不覆盖 B01，不能覆盖或抹去 JS 消费门槛的两个失败。前端增加固定开发依赖 Ajv 8.20.0 与 `review:world-s1` 命令；npm 同时补齐锁文件中原已声明的 onnxruntime-web 依赖记录，未改变它的 package.json 版本要求。本轮没有修改候选 Python、夹具、导出物或运行服务，也没有提交/推送。


## B01 的 A 侧修订候选（2026-10-22，待 B 重新核对）

B01 属实：此前 takeover 手写请求的目标 attempt 没有服务返回来源，Python 的合法夹具检查没有覆盖浏览器真实组装。本轮保留 B 的不通过记录与复现，不以 A 运行消费检查代替 B 的再次核对或正式 S1 验收。修订仍未提交、未推送，IF-05 未放行。

采用 restore 事务直接分配的方案，不增加预分配操作：

- `RestoreGroupWorkRequest` **删除目标 attempt**，并由 extra=forbid 在 Python/schema 两层拒绝客户端夹带该字段。请求保留从 restoreSources 读取的 sourceEpoch/sourceAttempt/manifest，以及当前租约、头/版本/revision 和客户端 requestId。前驱、后继均不需要预测任何目标 attempt。
- `RestoreGroupWorkData` 新增 **pointId、fenceEpoch、attempt**。结合外层 worldId 与原有 groupId，完整复制身份为 `(worldId,pointId,groupId,fenceEpoch,attempt)`；sourceEpoch/sourceAttempt/restoredMemberIds 保留，区分来源与新副本。
- 权威与来源校验通过后，服务事务在 `(worldId,pointId,groupId)` 范围内跨 epoch 单调分配正 attempt，并将全部复制行、来源记录和结果身份原子提交。attempt 是成功返回的服务端值，客户端不能按 1、sourceAttempt+1 或自己扫描 max 计算。示例返回值只表示预设服务结果，不是分配算法。
- 请求幂等仍先使用 `(worldId,requestId)`：同键变操作或变规范内容拒绝；成功重放复用首次 data。业务去重改为世界内的 `(pointId,groupId,fenceEpoch,sourceEpoch,sourceAttempt,manifest)`，manifest 按 memberId 排序投影并包含全部来源哈希。**同一来源清单和目标 epoch 换 requestId 也复用已接受复制身份及 attempt，不再次分配**。来源/哈希篡改仍须经过权威校验；不能以新业务键绕过它。不同源批次可分别复制，不按一个未知目标 attempt 去重。

registry 的 businessKey 与说明、正文 §9.2/9.4、README、计划及所有 restore 夹具已同步。`fixtures/branches/takeover.json` 的前驱/后继请求及十个失败请求均无目标 attempt；两个成功响应明确返回分配结果。既有的封存/前缀/phase/revision、旧载荷隔离与 active_reference 约束保持，复制 data 不含原文。

复用 B 的 `review:world-s1`，保留原来的两条“仅从服务返回值构造请求”检查，并增加返回复制身份断言；未从手写请求复制 attempt，也未放宽校验器。独立操作清单中的 restore 成功必需字段补齐 pointId/fenceEpoch/attempt。

本轮由 A 运行：

```powershell
npm --prefix frontend run review:world-s1
python -X utf8 -m pytest backend/tests/test_world_protocol_v2_revision.py backend/tests/test_world_protocol_v2_contract.py backend/tests/test_world_protocol_contract.py backend/tests/test_world_protocol_storage_contract.py -q
npm --prefix frontend test
```

结果：**JS 消费检查 60 通过、0 失败；Python 300 通过（v2 191 + v1 109）；前端既有 8 文件、62 项通过**。新增 12 项 Python 回归覆盖前驱/后继从服务值组装、拒绝客户端指定 attempt、成功身份必填、返回 attempt 的正安全整数边界及去重键登记。

内存重建 LF/UTF-8 字节比对：v1 12 个生成物与工作区及 HEAD 一致，v2 3 个生成物与当前生成器一致；共 124 个 JSON 夹具，`git diff --check` 通过。没有运行 API 或 SQLite 事务，因此单调分配、并发、同 requestId 重放、换 requestId 业务去重及失败回滚的实际行为仍在 A3/T06/T07/T09 验收；本轮只交付这些行为的字段契约与消费证据。

当前状态：**B01 已形成 A 侧修订候选，待 B 重新核对；S1 沿用未通过/未验收状态，IF-05 未放行。** B 复核通过并明确验收后，才整理可检出提交及启动后续放行步骤。

## B 最终复核与 S1 正式验收（2026-10-22：通过）

本节更新最终状态，上文“不通过”“待核对”“未放行”均为对应轮次的历史记录。B 按上一轮 B01 原始复现再次检查当前候选，未发现剩余的 S1 字段/消费阻塞；**正式验收 S1，关闭 IF-01 的 B 核对与 IF-02 的字段闸门，放行 IF-05**。

B01 已关闭，依据如下：

1. restore 的输入只包含 source metadata、当前世界头/版本/revision、租约/epoch 与客户端 requestId；请求类型没有目标 attempt，Python/schema 的 extra=forbid 拒绝夹带它。
2. 封存前驱和预约后继的两条原始 JS 失败检查均直接从响应构造请求，现均通过；没有从手写请求补 attempt，也没有放宽校验器。
3. 成功 data 返回 pointId/groupId/fenceEpoch/attempt，外层 worldId 与其组成明确的复制身份；来源 epoch/attempt 与目标身份分开。
4. 请求幂等仍为 `(worldId,requestId)`；业务去重登记绑定点、组、目标 epoch 及完整源清单，包含排序后的来源哈希，不再依赖客户端未知的 attempt。服务端单调分配、并发重试和换 requestId 复用同一复制身份已明确归入 A3/T06/T07/T09，未宣称事务已运行。

### 11 决定与 32 操作的最终结论

| 范围 | 最终 B 结论 | 证据与后续边界 |
|---|---|---|
| 1b、2b、1c、5、4a、4b、5b、7b、2c | S1 字段及消费核对通过 | 沿用前文逐决定、逐操作核对；来源 attempt 与目标分配的最后缺口已消除。服务状态/资格/围栏/清理行为仍在 A1～A3 |
| 4c 原文复制 | S1 字段及完整调用输入核对通过 | 可先取得来源元数据，再构造 open/sealed 当前/预约工作的 restore；旧载荷隔离、失败阻断及复制身份可消费；真实原子性在 A3 |
| 6 条件合并臂 | 规格登记通过，按计划留阶段 4 | B3 数据集及调用统计的要求没有转成 S1 运行实现承诺 |
| 32 个操作 | 全部字段/权限/夹具具备消费入口 | 前文 32 行清单继续有效；checkpoint_restore_group_work 的 B01“不通过”已由本节改为通过。独立 JS 操作清单、173 个 schema 定义及 18 错误码穷尽检查全部通过 |
| F01–F10、R01–R03、B01 | S1 层修订与消费复核关闭 | 不将 schema/夹具测试当作 apply、HTTP、SQLite 故障、实际分配或去重已经通过 |

### 独立复跑与交付

```powershell
npm --prefix frontend run review:world-s1
python -X utf8 -m pytest backend/tests/test_world_protocol_v2_revision.py backend/tests/test_world_protocol_v2_contract.py backend/tests/test_world_protocol_contract.py backend/tests/test_world_protocol_storage_contract.py -q
npm --prefix frontend test
```

本轮由 B 独立复跑：**JS 60 通过、0 失败；Python 300 通过（v2 191 + v1 109）；前端既有 8 文件、62 项通过**。内存重建 LF/UTF-8 字节比对：v1 12 个产物与工作区及提交前 HEAD 一致，v2 3 个生成物与当前生成器一致；`git diff --check` 通过。

验收快照随本节同提交纳入 Python 源、v2 导出物、124 个 JSON 夹具、两份 v2 契约/修订测试、JS 消费入口、Ajv 固定依赖及锁文件、决定表与同步设计文档。原 v1 导入/产物不变；`CLAUDE.md` 与 `.planning/STATE.md` 只本地同步。检出该提交并安装既有依赖后可用上述命令复核，验收提交主题为 `feat(world): accept S1 v2 contracts after B review`。

下一步：**A 推进 IF-03/IF-04a，B 可正式开始 IF-05**。正式 TS 类型/运行时校验/transport、DDL/规范向量、动态 trace schema/轨迹、统一检查/manifest/pin/CI 仍按各自任务交付。当前验收只关闭 S1 字段闸门，不等同于 IF-08 完整接口基线冻结，也不等同于 A3 事务验收；本轮只创建本地验收提交，不推送。

## 共同前置最终验收（2026-10-22：IF-03～IF-08 通过）

按用户“共同前置一起收尾，再分开做”的安排，将 A/B 的剩余接口工作在同一棵树交付。S1 保留 `cabb04c`；S2/共同接口实现提交为 **`e3b197a79f95adfbe215dddf5dfd3f9ed5b12823`**，本节及双方报告登记其正式验收。本节、双方报告与冻结记录随验收文档提交推送；尚未执行后续内核、控制器或事务服务开发。

契约摘要：`480d950c0f8062f8fdd75cb0620eb4ac97a6a247ca3f45f2057f6fe9e2ce7062`。只对四个接口文件按排序后的 `路径 UTF-8 + NUL + 字节数十进制 ASCII + NUL + 原文件字节` 连续做 SHA-256；路径是 `api-contract.json`、`trace.schema.json`、`versions.json`、`world-protocol.schema.json`。manifest、前端 pin、夹具、向量、SQL 及环境信息不进入此摘要。

| 任务 | 交付及核对结论 | 后续验收位置 |
|---|---|---|
| IF-03 | SQL 装载及 50 项正反例通过；当前 epoch 先过滤再 max attempt；纯规范编码与完整前缀/独立状态的 21 个向量通过 | TTL、跨表原子性与真实复制见 A3/FC01～FC32 |
| IF-04a | trace schema、结构化 `$var`/`$map`、单次捕获与 Python 预期工具通过；先验证响应 schema 再捕获/断言 | A2 从同一格式运行服务轨迹 |
| IF-04b / S2 | T01～T09 共 11 文件、185 步，包含空 linked 和同点任务/外貌折叠分支；每份两组 ID/token/epoch/clock 样本，独立完整投影与摘要通过 | T01 是 H1 输入，T07 是 H2 输入；完整运行验收仍在 A2/A3 |
| IF-05 | 手写 TS 类型、共享 Draft 2020-12 schema 校验、32 操作 HTTP request/success/error 全消费；18 错误码均有消费动作，resume 不越过 canCompute；固定模型输出端口不分配 ID/roll | B1 实现调度；真实浏览器 HTTP 在 H1 |
| IF-06 | 固定响应与受控 HTTP 均消费两组样本；65 项通过；错令牌、次序、身份、捕获、业务答案和摘要均明确失败 | 固定响应端口只返回预设值，运行服务在 A2/A3 |
| IF-07 | 默认 v1 保持兼容；v1 12 个、v2 5 个生成物字节核对；147 项 manifest、LF/no-BOM、生成 pin、统一入口及四类破坏性探针通过；CI 接线完成 | Linux 远端 CI 于推送后首次运行，结果未纳入验收 |
| IF-08 | 候选提交经干净 worktree 检出、全新 npm ci 和同一统一入口复跑通过；双方报告使用相同实现提交与摘要；正式验收共同接口基线 | 完成记录后从同一冻结提交建立 world-server/world-browser，进入 A1/A2 与 B1 |

本次补核发现并关闭一个 SQL 预约边界：后继的基线可以是尚未提交的封存前驱工作，不能直接外键到已提交点表。现由封存/活动前驱引用与独立约束测试验证；真实 P1 提交匹配和原子提升保留 A3/FC25。

S2 没有 fixture-only 操作豁免：32 个操作全部出现在轨迹中。业务预期来自手写投影/规范字节，Python 工具只实例化身份并计算预期摘要，不调用 apply、不接受 actualState/actualDigest；TS 只读取预期摘要。完整请求哈希随实例化请求重算并在 Python 侧核对。故障规格逐条给出具体 arrange、请求夹具、场景、故障位置、预期与命名 A3 测试位置，未把规格当作真实事务通过。

```powershell
python -X utf8 backend/scripts/check_world_interface_baseline.py
npm --prefix frontend run review:world-s1
npm --prefix frontend test
npm --prefix frontend run lint
npm --prefix frontend run build
```

结果：统一入口 **Python 426 项（v1 109 + v2 317）、TS 契约 38 项、TS 轨迹 65 项及类型检查全部通过**；四类临时破坏（CRLF、缺失响应字段、反转 canCompute、动态摘要过期）全部被拒绝。JS S1 复核 **60/0**；前端全套 **165 项**，lint/build 通过。既有 useBrowserAutoPlay 的 hook 依赖 warning 保留。

额外全量 backend 检查为 **921 passed、2 failed**，仍是已记录的 `test_campaign_wiring.py::test_create_session_with_campaign` 与 `::test_list_slots_filters_by_session_id`（创建会话返回 404）。共同接口检查全部通过；不把整个仓库 CI 报成全绿。CI 保留原后端 pytest 和前端 lint/build，新增 npm test 和 world-interface；完整 npm test 与聚焦检查在两个作业中有意重叠。Node 升至 22，匹配锁定的 Vitest 5 对 Node >=22.12 的要求。

**结论：共同接口基线验收通过，A0/B0 的前置工作关闭，可以分别推进 A1/A2 与 B1。** 冻结记录随验收文档提交推送，`world-server` / `world-browser` 分支自该提交建立。实际分配/去重、崩溃恢复、真实 HTTP H1/H2、真实模型与页面继续按原后续阶段验收。环境、具体文件及复跑入口见 [server](../../world-engine-reports/server.md) 和 [browser](../../world-engine-reports/browser.md)。
