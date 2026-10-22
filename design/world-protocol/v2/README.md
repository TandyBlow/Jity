# 世界引擎协议 v2：共同接口基线

日期：2026-10-22。**IF-01～IF-08 已完成，A0/B0 共同前置正式验收。** v1 为 `26011c8`，S1 验收为 `cabb04c`；共同接口实现提交为 **`e3b197a79f95adfbe215dddf5dfd3f9ed5b12823`**。共同前置先在同一棵树完成，再从冻结记录提交拆成 `world-server` / `world-browser`；冻结记录随本轮文档提交推送，两条开发分支自该提交建立并同步远端。

契约摘要：`480d950c0f8062f8fdd75cb0620eb4ac97a6a247ca3f45f2057f6fe9e2ce7062`。双方核对依据见 [共同前置最终验收](change-list.md#共同前置最终验收2026-10-22if-03if-08-通过)、[server 报告](../../world-engine-reports/server.md)、[browser 报告](../../world-engine-reports/browser.md)。运行环境为 Windows、Python 3.12.3 / SQLite 3.50.4 / Pydantic 2.13.4 / jsonschema 4.26.0、Node 22.20.0 / npm 10.9.3 / TypeScript 5.9.3 / Ajv 8.20.0 / Vitest 5.0.1；CI 配置使用 Python 3.12、Node 22。

Python 仍是规范编码与状态计算权威。当前交付可执行 SQL 约束、固定预期、契约轨迹、TS 消费/HTTP 实现与共同检查；内核、真实控制状态机、SQLite 事务及 H1/H2 分别留在 A1～A3。远端 CI 曾于 `07924f3` 首次触发（frontend 失败于 npm ci），`05c213e` 推送的 backend/frontend/world-interface 三个作业全部 success；全量 backend（Windows 须 `python -X utf8 -m pytest -q`）923 passed、0 failed，此前登记的两个 campaign_wiring 失败已不存在。

## 本轮冻结决定

| # | 决定 | 影响与验收入口 |
|---|---|---|
| 1b | pendingGroup 采用 A：checkpoint 的 discover_group 窄写入；只保存模型目标，admission 从固定 roll 与资格基线重算 | 与 5 一起冻结；§5.1、§5.3、§6.2、§9.2–9.4；覆盖 P1 后发现组的崩溃窗口 |
| 2b | checkpoint_revision 只表示控制器位置、游标、组工作态或暂停状态；gate 签发、清空、懒失效及叙事 ready 均不递增 | §5.1、§8.2、§9.2；四个入口执行 resolve_gate 不撤销调用方自身的 revision 前提 |
| 1c | POST /worlds 同事务创建初始推进租约，签发根点 generation=1 的 head claim 与 gate | 根点 advanceId=null、fenceEpoch 非空；narration-jobs 不保留 0→1 首次领取分支 |
| 5 | 一个 point 可容纳多个顺序结算单元，使用 settlementGroups 数组；每项 groupId 唯一，memberIds 是唯一且 ASCII 排序的集合 | 外层顺序进入提交摘要；组内成员排列不改变规范字节；根点为空数组 |
| 4a | 工作表按本点实际消费的 groupId 清理，不按 round 清空 | P1 清 A/B 时保留 C/D；消费、状态提交及清理在同事务完成 |
| 4b | 所有工作表写入、重试和清理检查有效 leaseToken、fenceEpoch 与 checkpoint revision | 先过滤当前 epoch，再取每组每成员最大 attempt；旧 epoch 行保留但不可见 |
| 6 | 合并臂是条件默认；位置影响外貌时必须拆分 | 七单元用例更新调用 7–14 次、总计 26–35 次；阶段 4 数据集同时收可合并样本与强制拆分反例 |
| 5b | 增加持久化 PointWork：settledUnits 与 working 游标/集合；stage_unit 后 settle_group→select_actor，points 才消费 | A 先暂存、B 读 A 输出、P1 合并提交；已提交 cursor/actedIds 不提前变化 |
| 4c | restore_group_work 改为服务端核验已确认来源后原文复制，禁止模型重建 | 清单绑定原文/候选哈希及源 epoch/attempt；普通读取仍隔离旧 epoch；缺失/损坏明确阻断 |
| 7b | begin_point 持久化时间/基线，首次确认时间相关工作后禁止修改；提前的 C/D 通过 prepare_successor 绑定封存前缀 | set_point_time 只能在未锁定且无确认依赖时执行；锁定后改时间须显式 cancel 链再开新链，原 roll 不删除/复用 |
| 2c | resolve_gate 只解析门槛；pause/resume 持久化与计算授权分别判断 | pending 时可暂停，失效后可记录恢复并返回 blockedReasons、canCompute=false；叙事 ready 不自动清暂停 |

## 写入者与权限

| 数据/变化 | 唯一授权路径 | 不允许的副作用 |
|---|---|---|
| 根点及首次 claim/gate | POST /worlds 的创建事务，同时生成初始租约 | 不先留 generation=0 等待另一接口领取；不访问不存在的 round |
| 推进点及首次 claim/gate | points 提交事务，generation=1 | 不把领取工作留给提交后的第二个事务 |
| 点基线与时间 | checkpoint.begin_point/set_point_time | 点身份预分配；确认行动/目标/skip/时间扫描后锁定，不能替换已有冻结工作的时间或基线 |
| 新 pendingGroup、发起者行动及可选同行动输出的目标 | checkpoint.discover_group：select_actor→build_group | 已提交与 working 游标均不变；锁时间、绑定所属点/输入投影，group/trigger ID 必须已分配 |
| 后续源目标、新成员行动与判定引用 | checkpoint.extend_group，仅 build_group | 已确认目标/行动不可改，成员只增不减，不消费组结果 |
| 闭组 | checkpoint.close_group：build_group→settle_group | 必须完成全部目标与判定、frontier 为空；闭组后不得增删成员或改变目标 |
| 单元结果及完整六步候选暂存 | checkpoint.stage_unit：settle_group→select_actor | 只追加 settledUnits、推进 working 字段并清活动 pendingGroup；原文保留，不更新世界或已提交进度 |
| skip 与空点扫描 | checkpoint.record_skip/stage_time_scan | 只推进工作访问游标/保存时间扫描候选，不能伪造已行动人物；都锁定时间 |
| 点前缀封存及后继预约 | checkpoint.seal_point/prepare_successor | 无本点活动组才能封存；封存后不再改前缀，预约只有一个且有固定后继时间/基线 |
| 接管后的工作副本 | checkpoint.restore_group_work，服务端按已确认清单原样复制 | 校验有效租约/revision、来源接受记录、作用域及哈希；不接收替代原文，不改组/时间/phase/revision，以 requestId 幂等及来源清单/目标 epoch 业务去重；目标 attempt 由服务分配并在成功 data 返回 |
| 组消费、actedIds/游标推进及清理 | points，携带 settlementGroups | 不能清整个 round；未消费组原样保留 |
| 叙事 ready/failed | narration 确认，匹配代次、claimToken、签发 epoch | 不改 phase、paused、checkpoint_revision |
| gate 懒失效 | checkpoint/points/round-conclusion/narration-jobs 事务内 resolve_gate | 不递增 revision，不把 failed/cache_missing 当成 ready |
| 认领取回/重领 | narration-jobs：有效认领原样返回，仅失效、重试、重生成才换代 | 不重新执行行动或结算，不影响历史点之外的控制器 |
| 普通暂停/恢复 | checkpoint.pause/resume，可穿过叙事 gate | 仅 paused 实际变化递增 revision；不延长 TTL、不改 phase；恢复成功也须报告 blockedReasons/canCompute |

控制器保留下一计算 phase；暂停使用 paused，叙事等待使用独立 gate，不再有 await_narration、paused phase 或 resumePhase。入口先处理成功幂等重放，再校验绑定/租约，再 resolve_gate；代次与令牌已构成 gate 围栏，无需 gate revision。resolve_gate 返回门槛状态，不能统一拒绝 checkpoint。计算/roll/提交/普通结论要求 ready、gate 已解除且未暂停；pause/resume 和受控副本接续可以穿过 gate。叙事认领/确认也可在暂停时完成，完成后仍保留 paused。

resume 同事务记录 paused=false、实际变化的 revision、失效 gate 清理及响应 blockedReasons/canCompute；claim_expired 不回滚恢复。恢复只记录控制状态，ready 前仍不计算。纯推进被门槛拒绝时可提交已合法完成的失效清理，业务推进不执行；绑定/租约错误不清理。具体权限矩阵见正文 §9.2。

## 多单元工作与提交进度

PointWork 的时间、基线、working 游标/集合/输入消费状态、有序 settledUnits、阶段候选与原文清单全部持久化。工作状态由 Python 从已提交基线应用一次时间，再顺序重放已保存候选得到，浏览器不能上传任意工作状态。以下为 A/B 合并为 P1 的最小路径，初始已提交 cursor=0、actedIds=[]：

| 步骤 | phase / 活动 pendingGroup | settledUnits / working 进度 | 已提交进度 |
|---|---|---|---|
| begin_point(P1) | select_actor / null | []；cursor=0、acted=[] | cursor=0、acted=[] |
| discover/extend/close(A) | settle_group / A | []；cursor=0、acted=[] | 不变 |
| stage_unit(A) | select_actor / null | [A]；cursor=1、acted=[A] | 不变 |
| discover/extend/close(B)，B 读取 A 的输出 | settle_group / B | [A]；cursor=1、acted=[A] | 不变 |
| stage_unit(B) | select_actor / null | [A,B]；cursor=2、acted=[A,B] | 不变 |
| seal_point(P1) → points(P1) | 下一控制位置 + 叙事 gate | [A,B] 按原候选合并、消费 | cursor=2、acted=[A,B] 原子生效 |

stage_unit 校验所属点、冻结组清单、时间、输入投影与完整阶段候选，仅清除活动 pendingGroup 槽位，不删除其文本或结果。响应丢失原 requestId 重放不重复追加，同组换候选拒绝。B 中断后读取已 stage 的 A，不能重生成 A 改掉 B 的基线。skip 经 record_skip 只推进 workingVisitedIds/cursor，已暂存行动也计入 workingActedIds，不能再次行动。空点经 stage_time_scan 保存完整时间检查，仍允许 settledUnits=[]。

## 冻结副本与时间绑定

每次工作确认同事务写服务端接受记录与清单引用，绑定 world/round/point/group/member、sourceEpoch/sourceAttempt、输入投影、时间及完整载荷 contentHash。恢复不能只凭“旧表有这行”或“成员/目标相同”采纳原文。restore_group_work 只读取当前 pendingGroup/PointWork/settledUnits 正在引用且未消费、未废弃的来源；验证接受记录与全部哈希后，将行动 UTF-8 字节、目标、结果与阶段候选原样复制到当前 epoch，记录来源，普通读取仍先过滤当前 epoch。缺行/损坏返回 frozen_work_missing/frozen_work_corrupt，不调用模型重建“推开 D”或“刺伤 D”。活动清单引用的旧行不能在交接/GC 时删除。

begin_point 保存 pointId、kind、基线头/版本/摘要和 timeAdvance。首次确认行动、目标、skip 或时间扫描时锁定时间；rolls 只接收该锁定身份。set_point_time 仅在无已确认依赖且未锁定时修改，清除未确认内存输出并重新 preview；锁定后返回 point_time_locked，原目标与 roll 不失效、不改键。确需改时间使用显式 cancel：同事务废弃当前/预约工作及指针，保留 ID/roll 终止记录，结束链；新执行使用新链身份，不允许刷新自动废弃后重采样。

提前保存 C/D 必须先 prepare_successor：封存 P1 的已保存时间/单元候选/工作进度，绑定预分配 P1/P2、预计 P1 版本与状态摘要、前缀内容摘要、P2 的 instant/0 时间。C 的输入投影必须是预计 P1 状态再应用 P2 时间的结果，不能把按 P1 时间确认的文本后来挪入 P2。前缀摘要排除后继、revision、暂停、gate 和凭证，独立于完整请求幂等摘要。P1 提交逐项匹配后原子提升 successorWork，保留原文与判定；不符拒绝，不重绑、不重掷。默认路径仍是在 P1 ready 后创建 P2，无法提前绑定时不保存跨段冻结工作。

## 崩溃窗口与恢复

1. 源行动经 discover_group 确认后才能调用目标分析；完整目标集（包括空集）经 extend_group 确认后才能 rolls/扩张。同一模型调用同时返回二者可原子确认；未确认且未消费的输出可以重试。
2. 对已保存目标先算 roll，再算 eligibility/admission，一条 INSERT 带最终结果。同判定键复用原行；禁止 NULL admission 的中间行及事后 UPDATE。资格基线与规则固定，组成员去重不反过来改变原资格。
3. roll 已落库、成员扩张尚未保存时，用原目标及原 roll 补做幂等扩张；D 已入组但行动未生成时继续生成。C 的目标集已确认就不能重新采样，即使仍只完成了部分闭组工作。
4. 一个组 stage 后只推进工作游标，下一组从 select_actor 开始；未 stage 的候选可重算，已 stage 的前缀及已冻结原文不变。
5. P1 后才发现 C/D 走普通独立事务；P1 前保存必须有封存前缀及后继时间绑定，P1 不等待全组闭合，提交不能清掉它。gate 阻塞期间不计算后段。
6. 接管只经服务端确认来源后原文复制；同 epoch 刷新复用已确认工作。时间锁不因刷新/接管解除，副本缺失不能变成采样入口。
7. points 先按已保存候选复算，再提升 working 进度；只清本点消费组，后继保留。响应丢失走原 requestId，不再次消费或生成点。
8. pending 时 pause 可以落库；过期后 resume 也可落库，但 blockedReasons 报失效且 canCompute=false。重生成 ready 与 paused=false 都满足后才调度模型。

持久化模型目标解决的是模型采样不可重现；admission 是纯函数，不在 pendingGroup/目标集复制。roll 行保留最终 eligibility/admission 便于校验，恢复重算必须使用该行绑定的资格基线，不能使用刷新时的任意最新状态。

## 已交付的共同前置

| 产物 | 入口 |
|---|---|
| 174 个 schema 定义、32 操作与 18 错误码 | `world-protocol.schema.json`、`api-contract.json`、`fixtures/api/` |
| SQL 约束、21 个规范向量及 32 条事务故障规格 | `storage-contract.sql`、`canonical-vectors.json`、`failure-cases.json` |
| 动态轨迹格式与 11 份双样本轨迹 | `trace.schema.json`、`traces/`；全部操作覆盖，无夹具豁免 |
| 独立完整预期及 Python 摘要工具 | `fixtures/projections/`、`backend/scripts/world_trace_expected.py` |
| TS 类型、运行校验、HTTP、固定响应及模型端口 | `frontend/src/lib/world-engine/` |
| 五个 v2 生成物、147 项 artifact 哈希与前端 pin | `manifest.json`、`versions.json`、`contract-digest.json` |

从仓库根目录安装后端 requirements 与前端锁文件依赖后，运行：

```powershell
python -X utf8 backend/scripts/check_world_interface_baseline.py
npm --prefix frontend test
```

统一入口执行 v1/v2 的只读导出核对、Python 正反例、TS 类型与消费/轨迹检查、四类临时破坏性探针。结果为 Python 426 项、TS 契约 38 项、轨迹 65 项通过；前端全套 165 项、lint/build 通过。空测试集、缺文件、字节/哈希/pin 漂移均失败。生成物按 LF、无 BOM 的 UTF-8 字节写入；普通导出仅重写 `generated:true`，手写夹具只重算/校验哈希。`--check` 不更新 manifest、夹具或 pin。

`contractDigest` 对四个固定接口文件按路径排序，逐文件连接 `路径 UTF-8 + NUL + 字节长度十进制 ASCII + NUL + 原字节` 后做 SHA-256。manifest 自身、pin、SQL、向量、轨迹和环境不参与；手写产物单独列 SHA-256。前端 pin 只能由 `export_world_protocol.py --version v2 --write-pin` 生成。

下一步 A 实现 A1/A2，B 实现 B1。T01 已备作 H1 普通点输入，T07 已备作 H2 接管输入；A3 按 FC01～FC32 实现真实故障验证。阶段 4 的条件合并与强制拆分样本、实际调用统计仍按 B3 交付。
