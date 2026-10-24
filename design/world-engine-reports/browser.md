# B：消费侧核对与共同接口基线交付

日期：2026-10-22。共同接口实现：`e3b197a79f95adfbe215dddf5dfd3f9ed5b12823`；S1：`cabb04c`；v1：`26011c8`。接口摘要：`480d950c0f8062f8fdd75cb0620eb4ac97a6a247ca3f45f2057f6fe9e2ce7062`。本报告及 change-list 在随后文档提交中正式验收该实现；两条开发分支从包含冻结记录的同一提交建立并推送。

环境：Windows / PowerShell；Python 3.12.3、SQLite 3.50.4、Pydantic 2.13.4、jsonschema 4.26.0；Node 22.20.0、npm 10.9.3、TypeScript 5.9.3、Ajv 8.20.0、Vitest 5.0.1。CI 配置 Python 3.12、Node 22；Node 升级匹配现有 Vitest 5 的 engines 要求。

统一验收入口：`python -X utf8 backend/scripts/check_world_interface_baseline.py`。在原工作区和从该提交新建的干净 worktree 中运行，后者先执行全新 `npm ci`，均通过。统一入口覆盖 v1/v2 只读生成核对、Python 426 项（109+317）、TS 类型、契约 38 项、轨迹 65 项，以及四类故意破坏探针。默认 v1 导出仍是原 12 个产物字节；v2 为 5 个生成物，manifest 共 147 项。生成与检查不重写手写夹具，pin 由 Python 生成。

`npm --prefix frontend test` 为 10 文件、165 项通过；S1 JS 复核 60/0；lint 与生产 build 通过，保留既有 useBrowserAutoPlay hook 依赖 warning。额外全量 backend（`python -X utf8 -m pytest -q`）为 **923 passed、0 failed**，此前记录的 `test_campaign_wiring.py` 创建会话与 slot 过滤两例 404 已不存在。frontend 在 `07924f3` 的远端运行中失败于 npm ci；本验收提交 `05c213e` 是首次带 world-interface 作业的运行，backend、frontend、world-interface 三个作业全部 success。

CI 保留既有 backend pytest 与 frontend lint/build，新增 npm test 与 world-interface。统一入口中的聚焦消费测试和 frontend 作业全套有意重叠；空集、缺依赖或跳过必需检查均不计通过。

交付位于 `frontend/src/lib/world-engine/`：手写完整操作类型和判别联合、共享 Ajv2020 校验、transport 接口及可配置 HTTP、严格固定响应、固定模型输出端口、trace 读取/捕获/断言。package.json 提供 typecheck:world、test:world-contract、test:world-traces，隔离 tsconfig 覆盖模块及测试。

32 个操作分别消费共享 request/success/error；18 个错误码均有确定恢复动作。HTTP 处理路径/查询、协议头、请求与响应身份、JSON、HTTP 状态、超时和调用方取消，不自动重试；超时后保留原 requestId/载荷。resume 成功但 canCompute=false 时不调度。restore 从只读来源清单直接构造请求，无客户端目标 attempt；成功结果可读回服务端复制身份。

11 份 T01～T09 轨迹的两组样本分别经过固定响应与受控 HTTP；65 项验证正常消费及错令牌/顺序/作用域、schema 先于捕获、未来/重复/缺失引用、业务预期篡改、epoch 差值及旧摘要。固定响应绝不执行 apply 或补造未声明结果。模型端口按预设 task/key/input 顺序返回隔离副本，可保留 localRef；不分配持久化 ID/roll，不代表真实模型提示词或质量已验证。

消费核对结论：S2 与 IF-05/IF-06 通过，未发现共同接口剩余字段/权限/恢复构造缺口；IF-08 正式验收，B0 前置关闭。下一步 B1 从固定输出实现浏览器调度，H1 用 T01 连 A2；B2/A3 就绪后 H2 用 T07 验证真实刷新/接管。浏览器设备、双心跳、推理取消、模型提示词/质量与页面仍按 B1～B4 后续交付。

## B1 §7 确认后的步骤 2：T01 固定响应控制器验收

日期：2026-10-23。实现基线：B 侧 `38c464d`（含 coverage 2026-10-22 裁决对齐）；A 侧验收分层/preview 要求/digest 策略已在 `server.md「B1 §7 确认」`认可。首版交付 `776b4a2`（`harness.ts` 语料构建＋严格 transport/model 端口＋共享预期断言、`t01.scenario.ts` 场景装配、`harness.test.ts` 双样本正路径＋定向反例；driver 增 `identityAliases` 与 `pendingDecision()`）**未通过步骤 2 评审**：B 复现四个验收缺口（标本世界失真、最终 preview/commit 摘要改错仍过、requestId 比对循环自证且响应身份不对齐、`buildCorpus` 漏装 input 变量）＋一条无断言 DBG 测试。`a7f2e1b` 修复后第二轮评审仍发现独立校验缺口：摘要链只约束跨步引用，无后续引用的 capture 实为自证（s16 `pointProjectionDigest`、录制 s16 `workingState` 的 sanity 篡改均通过）。两项修复见下；当前状态为**修复完成待复审**。

语料来源：共享 `traces/T01.json` 的 sample_1 与 sample_2 全部 20 个共享步骤逐字实例化（request/scope/response 按轨迹自身捕获纪律，input 变量像共享解释器一样预载），响应体仅适配 requestId 回显（见下），业务字段保持录制值；B 自有标本仅一处——`b-preview-after-begin-s6`（begin 后的额外 preview），从同一轨迹录制的 s16 preview（同一点）派生：真实主角/时间/花名册/物品/任务（person_c、11:59:02、person_a 在 lobby），该点 staged entityDeltas 回退到录制 initial positions、projection 的 entityDeltas 置空，仅两个 digest 字段为符合 schema 的 `0`×64 占位值，明确不作摘要证据。preview 位置：begin 后（B 标本）＋ skips 后、seal 前的 s16（共享步骤，即"stage 后"的最终 preview）；纯时间扫描 preview 规则留待 T03，本轮不宣称覆盖。

摘要断言范围（全部 serve 期执行，不再只在 inspect）：①共享独立预期——s21 的 `/data/stateDigest` 对 `expectedDigests.s21`、`/data/state` 对 `expectedProjection` 实例化比对，不从任何实际响应生成预期；②运行时摘要链——构建期从 $var 共享推导「capture 位置→后续引用位置」链接（模板×实例化并行走查，`$map` 按实例化键解析），serve 期断言 served 值等于先前 served capture 值（T01 中 v32 贯穿 s16 workingStateDigest → s18 head.stateDigest 与 s18 data.stateDigest）；③preview↔预期对齐——s16 的完整 served `workingState` 与 `workingStateDigest` 分别对齐 s21 独立 `expectedProjection` 与 `expectedDigests`（两样本已验证录制层面相等），堵住摘要链对无引用字段的盲区；④独立摘要钉——s16 `pointProjectionDigest` 由场景钉表持有（按服务端配方 `canonical_digest(pointProjection)` 用 Python 规范化编码器独立重算、与录制核对一致，语料实例不参与取值），无引用字段不再自证。

身份与命令：requestId 生命周期独立于 driver memory——录制请求 ID 在构建期校验回显一致（response echo == request requestId）后从语料剥离，transport 强制带 ID 操作每次携带从未用过的新 ID（同前端 `retry_same_request` 的合法重放经 frontRequestId 容忍）、无 ID 操作（preview/reads）不得泄漏 requestId，serve 时回显改写为 driver 实发 ID；driver 复用同 ID 或语料回显损坏分别被定向反例拒绝。allocate 响应按 slotKey 落入 `ids`，调度键经 `identityAliases` 绑定。`initial`/`pointPlan`/`action`/`targets`/`results`/`updates`/`narration` 全部经模型端口执行并严格核对 task/key/完整 input/顺序；expected input 一律从声明的响应与标本推导。控制器段由真实 `ControllerDriver` 运行：transport 只核对驱动器推导出的请求，夹具不投喂预期请求、不逐步修改 memory。

分段与结束边界：T01 无 command/probe 场景，不计覆盖。controller 段 s1–s20；s21–s23（get_state/list_points/narration_get）为 inspect，由 harness 直发；s20 后真实 phase 为 `assess_continuation`，harness 在声明的停止边界断言驱动器待决决策恰为 continuation 模型调用（`pendingDecision`）后结束场景，不伪造 complete/round_points_exhausted，不额外调用 continuation 模型。

结果：双样本正路径通过（transport 24 次调用 = controller 21 次 + inspect 3 次全序列逐字核对；模型 8 次调用 task/key/input 全等；schema 先于消费；正路径另以整体相等断言钉死 T01 标本对录制的写实——protagonist/时间/person_a 在 lobby/物品任务/roundId）；十三条定向反例全部按预期拒绝——身份绑定断裂（组键无别名→s7 请求失配）、声明请求篡改（s4 allocationKey）、声明 scope 篡改（s7）、模型输入不符（action actor）、未声明 preview（删除标本后 preview_point 撞 discover 声明）、共享摘要篡改（s21 expectedDigests，serve 期拒绝）、s16 workingStateDigest 链断裂、s18 data.stateDigest 链断裂、s16 pointProjectionDigest 钉失配、录制 s16 workingState 篡改（sanity 10→11）经 s21 对齐拒绝、driver 恒复用同 requestId、录制回显损坏（构建期拒绝）、T02 语料构建（input 变量预载回归）。前端全套 13 文件 260 项通过（含既有 65 项共享轨迹逐字消费，共享轨迹/schema/manifest/digest pin 零改动）；`typecheck:world` 与统一验收入口 PASS。

**结论：T01 固定响应控制器验收两轮评审缺口已全部修复，待复审放行。** 真实 API 序列化与真实服务摘要一致性由 H1 验证；T02 组扩张在放行后推进（错误/恢复步骤的语料表达与 recovery hop 的 requestId 生命周期是 T02 设计项）。

## T02 前置设计：错误步骤消费与 requestId 生命周期

日期：2026-10-23。应步骤 2 放行条件而作；机制已落地于 `harness.ts`（线性消费 + `requestIdExpectation`），T08/T09 场景启用。

**错误步骤线性消费**：每个录制步骤 = 一次 HTTP 交换。错误步骤 serve 一次（validateError → WorldApiError 抛给 driver）后 index 前进，错误响应体同样跑 captures/摘要链/独立钉——T06 的错误响应携带 capture 变量供后续引用，运行时链对它们一视同仁。driver 的反应必须落在下一个声明步骤上：`request_in_progress`（与 driver 观测的超时）按 `retry_same_request` 原样重发（同 ID 同载荷），落在下一个声明步骤——即场景显式声明为 `continue` 的那一步；其余确定性拒绝按 clientAction 走 followup；`fix_request`/`none`/`pause` 到达 driver 终止（声明停止边界）。

**requestId 生命周期**（driver 契约，transport 独立校验、不读 driver memory）：
- `retry_same_request`：同 ID 同载荷。**重试是显式声明**（`buildCorpus` 的 `retries: {stepId, kind}`）——录制中相邻 ID 复用绝不推断为重试。`continue` 声明在构建期对照录制校验（复用前一录制调用的 ID 且 operation/scope/载荷逐字相等，否则要求改声明为 probe），运行期强制同 ID 且 **operation、scope、完整请求体与上一次带 ID 调用逐一相等**（同 ID 换 holderId 之类的载荷漂移即拒，见步骤 3 评审缺口 2 的复现）。`probe` 声明（蓄意重放已 serve 的 ID 触发 request_id_reused 之类示教，载荷允许不同）构建期要求载荷确有差异（逐字重发应声明 retry）、运行期要求该 ID 确曾 serve 过。未声明的录制 ID 复用构建期直接拒绝。transport 仍容忍同前端重放（frontRequestId）。
- 其余确定性拒绝：driver 先铸一个新 ID 再发 followup（`get_context` 不携带 ID 但消耗一个；`lease_acquire`/`checkpoint_pause` 携带）；`refresh_context` 与 `lease_acquire` 在 followup 成功后再铸一个——因此 ID 允许被跳号消费，freshness 规则（每带 ID 操作一个从未用过的 ID、无 ID 操作不得泄漏）不受影响；被拒 ID 永久退役。
- 无 ID 操作（preview/reads）禁止携带 requestId，双向强制。

**时间扫描候选与 preview（A §7：同一列表、无独立通道）**：driver 在 `checkpoint_stage_time_scan` 后把扫描候选保存为 `memory.stagedTimeScan`，其后本点每次 preview 将其并入 settlementGroups（普通 staged 组之后）；`commit_point` 的 settlementGroups 保持普通命名组语义（T02-empty s23 录制 `[]` 证实扫描候选不进 commit），commit 后随 staged 一并清空。

**轨迹分层**：T06 是契约层示教序列（`req_inflight` 等非 driver 形状 ID 的 request_id_reused/in_progress/stale_epoch 演示），不是 driver 会话材料——其恢复语义由 **B 自有 fault transport**（受控注入 request_in_progress、驱动器观测超时等故障）覆盖，属 B 责任。T07（checkpoint_restore_group_work 恢复/接管）仍属 **B2/H2**，不因轨迹分层划归他方，B 的恢复验证责任不取消。已知缺口：T08 s9（commit version_mismatch→refresh_context）与 s10（新 ID 重试成功）之间录制省略了 `get_context` 交换——届时用 B 桥接步骤补齐（从录制捕获态派生、显式标注为桥），同步登记为语料适配。

## B1 步骤 3：T02 组扩张与空 linked 时间扫描验收

日期：2026-10-23。实现基线：T01 放行版 `1443b49`（T01 全部验收强度保留：严格 transport/model 端口、serve 期摘要链、独立预期、ID 生命周期、停止边界断言）。交付：`t02.scenario.ts`（双轨迹通用装配）、`t02.scenario.test.ts`（双轨迹×双样本正路径 + 2 反例）、harness 增错误步骤线性消费与 `requestIdExpectation`。

会话形态：T02/T02-empty-linked 均无 create_world/allocate/start_advance——session 以 s1 `get_context` 打开（harness 直发的 bootstrap inspect），driver 以录制上下文、输入型 ownership 变量（租约 token 客户端自持）与录制组身份（discover 请求的 groupId 按 `group:<actor>` 播种）构建；首个控制器操作即 begin_point。轮内三点连续推进（T02：p1 normal +2s、p2 instant +0、p3 linked +3s；empty-linked：p2 大组 +0、p3 空 linked +0），全程无 continuation 中断，s41/s25 后 phase=assess_continuation，停止边界断言待决 continuation 模型调用后结束，s42/s26 get_state 为收尾 inspect。

preview 标本：两条轨迹的契约层录制都不含 preview，但 driver 在每个 begin/stage 锚点后需要新鲜工作态——标本插于全部锚点之后（T02 7 处、empty-linked 4 处），digest 按纪律占位。工作态来源：两条会话的 commit entityDeltas 全空，状态体贯穿会话恒定，故标本 = 该轨迹自己录制的终态（get_state 的 /data/state）+ 该点 staged 后继时间；时间规则 = 有推进（amount>0）则 dateTime 前进且 ordinal 重置 0、零时长 instant 递增 ordinal（与冻结的五锚点结论一致）。每个不同的点状态在编写期以规范化 sha256 对照录制 commit head digest 验证：T02 双样本 32256da8/9dd127b0/85848d51、empty-linked 双样本 9dd127b0/312f65d3，全部一致。pointProjection 取自录制 commit 请求的 point；preview 请求携带锚点前已 staged 的 settlementGroups（driver 语义）。末位 preview 经 serve 期对齐绑定到收尾 get_state 的独立预期——占位 digest 不作摘要声明，故 digest 腿仅对录制 preview 生效（T01 s16 双腿全绑定不变）。

模型期望由遍历录制生成，不做手工清单：discover→action、targets 形 extend→targets（规则取自 create_rolls）、admit 形 extend→reaction、stage_unit→results+updates（T02 组差量全空，updates 输出空数组）、stage_time_scan→`time_scan:<pointId>` updates、narration_submit→narration。覆盖面：T02 每样本 24 次模型调用（action×4、targets×6、reaction×2、results/updates×4、narration×3、pointPlan×1），p2/p3 各含拒绝卷（person_a/person_e/person_c 三次 admitted=false）与准入深链；empty-linked 每样本 14 次，c→d→e→f 全准入 DFS 深链（c 的三次 reaction）+ f 空 targets 收组 + 空 linked 点时间扫描。序列化适配仅一处：admit 形 extend 的录制 `targets: null` 归一为省略键（driver 形状），业务字段保持录制值。

结果：四条正路径全过（T02 每样本 42 次传输调用 = bootstrap 1 + controller 40 + 收尾 inspect 1，empty-linked 26 次；模型调用全序列 task/key/全 input 相等；schema 先于消费；标本时间/体/投影断言全过）。反例：终态摘要篡改在收尾 inspect 的 serve 期拒绝；末位 preview 体篡改经 s42/s26 对齐拒绝。

**步骤 3 评审（对 0c85106）两项缺口及修复**：①时间扫描候选未进入后续 preview——driver 的 `checkpoint_stage_time_scan` 不落 memory、场景 `stagedAt` 漏收 `stage_time_scan`，empty-linked 扫描提交 `groupId=null` 候选后紧随的 preview 却发 `settlementGroups=[]`，违反 A §7（同一列表、无独立通道）；修复为 driver 增 `memory.stagedTimeScan`（preview 同列表携带、commit 保持普通命名组语义、commit 后清空）+ 场景 `stagedAt` 纳入扫描候选。本轮扫描无状态差量所以预设响应未暴露；T03 的非空扫描（task_wait_noon 达成等）会受影响，T03 场景装配时按同一机制走。②`continue` 只约束同 ID 不约束同载荷——同 ID 换 `holderId` 被认证为合法重试；修复为重试显式声明（构建期对照录制校验、未声明的录制 ID 复用直接拒绝、probe 另行声明）+ 运行期 operation/scope/完整请求体逐一相等校验，并以 T06 语料补三回归（构建期拒绝推断、probe/retry 声明互斥校验、载荷漂移拒绝+错误步骤线性消费证明）。文档责任边界同步修正：T06 归 B 自有 fault transport 覆盖；T07 仍属 B2/H2，B 的恢复验证责任不取消。前端 14 文件 **269** 项通过；`typecheck:world` 与统一验收入口 PASS。

**结论：T02 组扩张与空 linked 时间扫描验收按步骤 3 评审意见修复完毕，待复审。** 后续：T03/T03-collapse（时间扫描与 collapse 合法重叠）按同一装配器扩展；T08/T09 启用错误步骤机制时补 B 桥接步骤。

## B1 步骤 4 第一段：T03 非空时间扫描与 T03-collapse

日期：2026-10-23。接续 `0e49299` 后未完成的 `t03.scenario.ts` / `t03.scenario.test.ts`，完成两条轨迹各两个样本的固定响应控制器验收。本段保留 T01/T02 的严格请求、scope、模型输入、运行时摘要链、独立终态预期与 continuation 停止边界；不改变共享轨迹、schema、manifest 或 digest pin。

会话从 s1 `get_context` 打开，预置录制租约与组身份。T03 控制器执行纯时间点：begin → preview → 非空 stage_time_scan → preview → seal → commit → narration；扫描候选以 `groupId=null` 进入后续 preview 的 settlementGroups，commit 的命名组列表仍为空。T03-collapse 执行 automatic round 内的单人组：begin → preview → discover/extend/close/stage_unit → preview → seal → commit → narration。它的 s2 `allocate_ids` 是 harness 发出的 bootstrap 交换，使用独立新 requestId、经过相同 schema/请求/回显校验；本段不据此宣称驱动器已实现自动轮入口的预分配。最终 get_state 同样由 harness 发出；每样本分别 10 / 14 次传输调用，模型分别 3 / 6 次，结束时待决调用为 continuation。

preview 每条轨迹两处，均标注占位 digest。begin 标本取匹配 T02 样本的共享基线体，应用本点后继时间，entityDeltas 与 mergedEntityDeltas 为空；stage 后取本轨迹录制终态，投影与 mergedEntityDeltas 使用录制 commit 的折叠结果。模型输入只能读取严格早于当前步骤、已经送达的 preview，修正 T02 装配器原先使用 `<=` 的锚点边界。末位 preview 体在 serve 期对齐最终独立 expectedProjection。另用 A 的 Python canonical 工具复核四组起始体摘要与 s1 head 一致、四组最终独立预期摘要与 commit head/expectedDigests 一致；浏览器未新增摘要实现。

业务断言覆盖：T03 从 11:59:00 推进到 12:00:00，task_wait_noon pending→achieved、个性变化来源为本点、理智 30→35；T03-collapse 到 11:59:07，同点新增 parent/child，候选中的 child 为 pending 且被 tasksAchieved 引用，最终投影只保留 achieved 的 child 新增，不重复输出 tasksAchieved，外貌变化保留实际 change/point 身份。两个样本的动态 point/group/task/change 身份分别验证，stage 前模型输入保留未结算基线，commit 后 staged 与 stagedTimeScan 清空。

已登记的 coverage 偏差仅在 B 自有场景适配：T03-collapse 原录制 personalityCoverageIds=['person_c'] 改为任务达成时的世界全员，stage/preview/commit 请求一致；适配器只接受该已知形状或已合规字段，拒绝其他未登记偏差。原共享轨迹保持原字节；真实成功联调前仍须按分工文档 §2.2 更新共享夹具，不能把本段视为 H1 或 A 侧内核运行验收。

结果：四条正路径、四条丢失已 stage 候选反例、四条提前泄漏 post-stage 状态的模型输入反例、终态摘要篡改与末位 preview 体篡改反例，共 14 项通过。前端全套 15 文件 **283 项通过**；`typecheck:world` 与共同接口统一入口 PASS（Python 109+317、契约 38、轨迹 65、四类破坏探针全部拒绝）。修正既有 controller.test.ts 一处 prefer-const 错误，生产 build（含 lint 与全前端类型检查）通过，保留已有 hook 依赖及未使用变量 warnings。

**复审结论：`1f50cdb` 的 T03/T03-collapse 段已获通过。** 复审方复跑 283 项、类型检查、共同接口验收和生产构建，并用 Python 复核四组摘要及补跑 8 个 commit 摘要/最终状态篡改探针，全部通过。该结论限于该提交，以下继续推进步骤 4 剩余内容。

## B1 步骤 4 第二段：T04、自动轮入口与 T08

日期：2026-10-23。在通过复审的 `1f50cdb` 上推进，新增 `t04.scenario.ts/test.ts`、`t08.scenario.ts/test.ts`，扩展轮入口分配及 harness 分段/重放。共享轨迹、schema、manifest、digest pin 保持原字节；preview 仍为 B 自有标本与占位摘要，终态仍由共享独立预期和运行时摘要链校验。

**自动轮预分配**：memory 的 `roundAllocations[roundId]` 声明该轮的 allocationKey/slots，调度器在 pointPlan 前自行调用 allocate_ids；成功后按 slotKey 保存 ID/identityAliases，并记录已确认的 allocationKey。已有旧槽位值不代表本轮分配完成；返回槽位缺失、重复或不匹配时，停止在模型调用前。T03-collapse 的 s2 从 bootstrap inspect 移到 controller 段，只有 s1 get_context 仍由 harness 发出；取消 group ID 预播种，组身份实际来自 allocate 响应。原有 coverage 适配保持原边界。补回归验证单次分配、旧槽位覆盖和非法槽位拒绝，并以独立 driver 测试覆盖 player conclude → automatic round → 分配 → pointPlan，轮间没有 harness 修改 memory。allocationKey/slot plan 仍为场景配置，动态需求发现与真实服务 ID 分配属于后续生产装配/H1。

**T04**：双样本完整执行 continuation 模型 → continue → automatic round 的 pointPlan/action/targets/results/updates → begin/stage 两次 preview → seal/commit/narration → continuation 模型 handback。continue 退休上一轮 plan/planIndex，handback 清空本地轮工作缓存。s1/s3 是 harness context 读取，s14 是清理后读取，s15 是显式幂等重放、s16 独立终态读取、s17 lease_release 是会话收尾；它们不计作调度推导。s15 显式声明 continue 重试，沿用驱动器实际发出的 s13 requestId 和完整载荷，额外读请求不改变上次写请求身份，篡改载荷会被拒绝。s1/s3 的 activeInput 全等，handback 后 s14.activeInput=null、重放响应 inputAvailable=false，data 保持原值且不带输入正文。T04 本身没有 allocation 录制，point/group/nextRoundId 仍按输入种子装配；不把这条种子会话宣称为运行时 ID 分配验收。

**T08**：两个样本各跑 normal 与 commit_conflict 两种场景。pointPlan 把其余角色放入预约 successor，控制器不伪造 skip；前驱 stage 后先刷新 preview，再由 time 模型决定后继时间。prepare_successor 返回 sealed 前驱与预约绑定，调度器直接提交前驱，不重复 seal；成功后清除本次 prepareSuccessor/successorTime。前驱叙事 ready 后，在 successor 首次计算前注入真实 cancel 命令；context 与本地 transient memory 均清理，最终时间保留 11:59:02，未提交的 instant successor 不推进 ordinal。

T08 语料适配逐项登记：①s8 是把已锁定时间从 2s 改成 3s 的故意非法请求，标为 probe，由 harness 直接发出并断言 point_time_locked/fix_request，控制器 memory 在探针前后完全相同；②normal 场景不执行错误时间的 s9，直接由控制器发合法 s10；原 s9 仍由共享契约套件逐字消费；③commit_conflict 场景用 B 标本 `b-t08-legal-commit-conflict` 替代 s9——请求复制合法 s10 的 2s 载荷，响应使用录制 version_mismatch（不把原非法 3s 请求计作 driver 行为），随后插入 `b-t08-refresh-after-conflict` get_context 桥；桥从拒绝时的 world/control/work 与已有 activeInput 声明派生，不执行 apply；驱动器真实走 refresh_context，再以新 requestId 重发完整相同的合法载荷。模型调用仍恰为 pointPlan/action/targets/results/updates/time/narration，无重复 action/results/updates，也不计算 successor。

**harness 加强**：`driveControllerSlice` 只运行到显式 inspect/probe/command 边界，并限制最多 500 步；既有 `driveControllerSegment` 仍要求该段模型声明全部消费。preview 构建结果深拷贝，避免复用标本对象同时改写模型输入预期；有定向反例证明篡改 begin preview 会在 action 的 input 核对处被拒绝。T04/T08 的合法响应仍在 serve 期执行 schema、捕获/摘要链、独立预期与最终 preview 体对齐；commit 摘要与终态状态篡改均有反例。

验证：前端全套 **17 文件 309 项通过**，`typecheck:world` 与生产 build（含 lint/全前端类型检查）通过，保留既有 hook 依赖及未使用变量 warnings；共同接口统一入口通过（Python 109+317、契约 38、轨迹 65、四类破坏探针全部拒绝）。另以 A 的 Python WorldState/canonical 工具复核 T04/T08 四组 baseline/独立终态摘要及 commit head，一致；TS 不实现另一套摘要算法。

**本段复审 P2 修复：conclude 响应的输入生命周期。** 复审方证实原检查只覆盖后续 context/重放；单改 s2.inputAvailable=false 或 s13.inputAvailable=true 仍能通过，属于验收缺口，尚未证明控制器业务错误。harness 现支持独立的逐响应 businessAssertions，先经 schema 校验，再断言业务字段，全部通过才交驱动器消费。T04 用显式常量约束 s2 `/world/advance/inputAvailable=true`、s13 同路径为 false，两者 `/world/advance/intentStatus=consumed`；预期不从被测 conclude 响应读取。双样本各补两条 inputAvailable 篡改反例，断言拒绝发生在对应 s2/s13，后续 context、重放与终态读取尚未发生，错误响应也未计入已消费 conclude。全套 17 文件 **313 项通过**，类型检查与共同接口统一入口复跑通过；本修复只增强验收，未因该发现修改控制器业务逻辑。

**复审结论：T04、自动轮入口与 T08 本段通过，原 P2 验收缺口已关闭，未发现新增阻塞问题。** 复审方实际复跑 313 项、类型检查与共同接口验收全部通过，并确认双样本四条篡改反例在对应 s2/s13、响应交给驱动器前拒绝，不依赖后续响应。该批随后单独提交为 `159ad03`，固定步骤 4 基线。完整 B1 仍待 T05、B 自有 fault transport 的其余 T06 语义，以及 H1 真实 HTTP；T07/T09 恢复接管仍归 B2/H2。本段不宣称真实服务事务、动态模型需求发现或中间 preview 摘要已经验收。

## B1 步骤 5 第一段：T05 暂停与叙事

日期：2026-10-23。按本轮范围，先将已复审通过的步骤 4 单独提交为 `159ad03`（313 项基线），再新增 `t05.scenario.ts/test.ts`，仅交付 T05 固定响应双样本及定向反例。本轮 T05 改动复审通过后提交为 `9dc52f3`；未推进 T06/H1。共享轨迹、schema、manifest 与 digest pin 均未修改。

**分段与实际执行者**：s1 get_context、s9 get_state 属 inspect；s2 pause、s5 resume、s6 pause 属 command，由 harness 注入 pause/budget_exhausted/resume 事件、真实驱动器构造请求；s3 lease_renew 与 s4 narration_claim_renew 明确标为 heartbeat，由 `runHeartbeat` 直发声明交换并通过同一严格 transport 的顺序、作用域、requestId/回显、schema、捕获链与业务断言。它们使用 harness 独立请求 ID，不触发 driver 请求工厂、模型调用或 memory 修改；随后 s5 的实际响应带回续租后的服务快照。真实心跳定时、并发取消及运行时 TTL 管理仍属 B2，不把这两次受控交换算作调度器自动发出的心跳。s7 narration_claim 与 s8 narration_submit 由 driver 推导，之间恰有一次 narration 模型调用。

**旧 claim 的恢复与暂停边界**：会话以录制的客户端自持 lease token、旧 claim token/generation=1/issuedAt 打开，不从下一步成功响应偷播新 claim。s5 resume 虽成功、paused=false，但 canCompute=false、blockedReasons=['claim_expired']；驱动器此前未退休旧 claim，会直接继续生成，现改为采用该控制状态时退休旧 claim 与旧模型输出，下一决策是 narration_claim，不能启动 action/targets/results/updates/continuation。随后注入 s6 再暂停，driver 仍须重新领取 generation=2、使用新的 issuedAt 完成 narration。s8 ready 时 paused=true、canCompute=false、gate=none；结束边界是等待暂停命令，连续再调两次 driver.step 都返回 await、不额外 resume、不调用状态模型或 preview、不推进世界。

**本地预算与外部暂停**：两个样本各跑 external 与 budget 两种命令来源，均预置 used=0/max=0，证明耗尽预算不能阻塞 narration。首次实跑复现外部 pause 因数值预算已耗尽而被误标本地的缺陷；现优先以发起操作时捕获的命令判定来源：显式 pause 为外部，budget_exhausted 为本地，无命令时由预算检查发起的 pause 仍为本地。resume 成功清除 localPause；s6 按本轮来源重新建立标记。ready 后分别等待 paused_externally/local_budget_pause。另各跑一条 budget_exhausted 且 max=null 的路径，验证预算事件不依赖数值上限也能标记本地暂停。

**独立验收规则**：s1～s8 均在 serve 期校验显式生命周期常量，包括 phase、paused、canCompute、gate.status、blockedReasons、head narrationStatus/version、输入 pending/可用及 round cursor/acted/visited 不推进；pause/resume 同时校验 data.paused，新的 claim/submit 校验 generation=2，submit data.narrationStatus=ready。规则不从被测响应反推；后续固定快照不能掩盖错误的中间响应。s9 对共享独立 expectedProjection/expectedDigests 校验实际终态。本段不需要 preview 标本，不生成状态或摘要；另用 A 的 Python WorldState/canonical 工具确认双样本独立终态摘要等于 s1 root head，证明暂停/叙事未改变世界状态。

结果：共 22 项 T05 测试，包含双样本 × 两种暂停来源的 4 条完整正路径、2 条无数值上限的预算事件路径，以及 16 条定向反例。每条完整正路径 9 次传输调用（driver 写请求 5 次、harness 心跳 2 次、inspect 2 次），模型恰为 narration 1 次，所有声明消费完毕。反例覆盖 s2 错误 paused、s5 coherent 的 canCompute=true 且清空 blockedReasons（由独立业务断言拒绝）、s8 ready 后错误解除暂停、s8 paused/compute-enabled 的 schema 矛盾、心跳 fence 篡改、新 claim 使用旧 generation、终态 digest 与状态体篡改；均在对应消费步骤拒绝。前端全套 **18 文件 335 项通过**，`typecheck:world`、共同接口统一入口（Python 109+317、契约 38、轨迹 65、四类破坏探针）与生产 build（含 lint/全前端类型检查）通过；保留既有 hook 依赖及未使用变量 warnings。

**复审结论：T05 通过，未发现阻塞问题。** 复审方实际复跑 335 项、类型检查、共同接口验收及生产构建全部通过，双样本独立终态摘要一致；确认旧 claim 退休、暂停来源判定两处修复有效，resume 后仍受阻、暂停中完成叙事、ready 不解除暂停均有独立断言和反例，心跳限于 harness。下一段先补 B 自有 fault transport 的 T06 语义：响应丢失后的同 ID/同载荷重发、成功重放不重复推进、确定性拒绝后新 ID、重试上限与恢复状态；A2 就绪后再以 T01 运行 H1，核对真实 HTTP 动态身份、preview、commit 与独立摘要。T07/T09 继续留 B2/H2，完整 B1 尚未验收。

## B1 步骤 5 第二段：T06 故障语义

日期：2026-10-23。接续上轮：T05 已通过复审并提交为 `9dc52f3`（335 项基线），本轮新增 `fault-transport.ts`、`t06.scenario.ts/test.ts` 三文件，交付 B 自有 fault transport 的 T06 故障语义；控制器与 harness 零改动，重试与恢复行为沿用 T04/T05 已验收实现。共享轨迹、schema、manifest 与 digest pin 均未修改。本轮改动已提交为 `3e14200`；未推进 H1。

**故障面与账本分离**：FaultTransport 包装 T01 的严格 ScenarioTransport——被接受的响应永远来自语料本体，故障层自身不 apply、不掷骰、不推哈希、不发明成功；T01 oracle 保留全部业务断言、模型脚本与独立终态投影/摘要。三次观察互相独立：attempts 记录每次 execute 的操作/请求/作用域/结局，acceptances 只记 oracle 实际接受的交换，丢失响应只能重放真实接受过的原 `data`（附重新推导的 world/control/work 快照、`replayed=true` 与回显 requestId），narration_claim 重放剥离 claimToken（摘要不能复活令牌）。故障脚本按 stepId（可选限定 operation）有限显式、按序消费，`assertFaultsConsumed` 强制全部耗尽，防止静默放过未触发注入。

**requestId 台账与退役**：首次出现的写请求按 `(worldId, requestId)` 登记绑定 stepId——超时前注入同样先登记，重试不漂移绑定；同键换操作/作用域/载荷以服务器形状返回 `request_id_reused`；确定性拒绝（`request_in_progress` 除外）退役登记项，退役后复用属驱动器缺陷，直接 ProtocolError。共享 T06 轨迹的 request_id_reused/request_in_progress/stale_epoch 台账示教仍归契约套件，B 侧只保证控制器永不走到这些形状。

**context 桥**：`refresh_context` 类拒绝（revision_mismatch/version_mismatch/phase_invalid）注入在 s18 commit_point。桥响应由 B 显式声明的拒绝后状态构造（world/control/work 快照，activeInput 随 `advance.inputAvailable` 给出），仅允许跟随 refresh_context 的空请求 get_context 消费一次，且作用域必须与桥世界一致——它是声明的拒绝后状态，不是 apply，不产生业务差量。断言重试 commit 换新 requestId 且载荷其余字段逐一相等、get_context 恰一次、action/results/updates 模型调用各恰一次（已确认工作不重采样）。

**重试上限与共享恢复预算**：默认 retryLimit=3 与 T01 相同。同一条调用链共享一份预算——重试、恢复跳转、后续调用同账本，恢复链不能活得比 retryLimit 更久。三类故障（timeout_before_send/request_in_progress/lose_response）三连注入触限时终态 error 并明示操作名，memory 与模型调用逐字节冻结；终态后驱动器仍可调度：下一步从保留 memory 重新推导同一写入（无模型重采样），脚本耗尽后以原 ID 原载荷成功，会话照常完成且该 stepId 恰一次 acceptance。恢复跳转同预算：commit version_mismatch 后 get_context 连续两次超时以 `retry limit exceeded on get_context` 终止，planIndex 与 nextStepId 停在 s18，故障脚本全部耗尽。

结果：共 26 项 T06 测试（双样本 × 13）：s4 allocate_ids、s5 start_advance、s10 stage_unit、s18 commit_point、s20 narration_submit 五个写入步骤的丢失重放；s10 超时+in_progress 原样重发；3 类确定性拒绝换 ID 重试；3 类故障触限后恢复；1 条恢复跳转预算。丢失重放断言结局序列恰为 lost_response→replayed、多次尝试同 ID 同操作同作用域同载荷、该 stepId 恰一次 acceptance、oracle 对该操作种类的调用数等于 T01 流程固有次数（narration_submit 计 2 属 s3/s20 两个固有提交，非重放重复推进）。前端全套 **19 文件 361 项通过**，`typecheck:world`、B 侧 `review:world-s1`（60 项）、共同接口统一入口（Python 109+317、契约 38、轨迹 65、四类破坏探针全拒，PASS）与生产 build（含 lint/全前端类型检查）通过；保留既有 hook 依赖及未使用变量 warnings。

**复审结论：T06 语义通过，无代码阻塞。** 复审方复跑 26/26、全套 361 项（世界引擎 11 文件 299 项 + T06 26 项在 `--sequence.shuffle` 下同样通过，无顺序耦合）、`typecheck:world`、`review:world-s1`（60 项）、统一验收入口（Python 426、契约 38、轨迹 65、四类破坏探针全拒）与生产 build 全部通过；新三文件零 lint 告警、无 `as any`/`@ts-ignore`；根因独立复现（把 error 体白名单改回 `...entry` 展开即 12 failed/14 passed）；确认 `controller.ts`/`harness.ts` 零改动、s20 的 2 次 narration_submit 属 T01 流程固有（s3/s20）。交付提交为 `3e14200`。accept 提交按复审意见修正三处记录（两处「保持未提交」措辞与 T05 段同款措辞、统一入口数字误引 B 侧 review 数）并补强：

- **加强断言（复审第 5 条，二轮修正）**：首轮实现把抬高的 revision 同时放进了错误信封与桥（同一 snapshot 双通道），驱动器在 catch 时即采纳错误信封，「跳过或无视 refresh hop」的控制器照样过——复审方复现该盲区，结论成立。修正为 error 动作新增独立 `bridge` 字段：错误信封走 latest（revision 保持 recorded），仅桥带抬高值；断言重试 commit 的 `expectedCheckpointRevision` 必须为 recorded+1，绑 recorded 即失败。篡改实验钉死区分力：临时注释 refresh 分支的 `adoptState(outcome.response)`，恰好且仅有该测试双样本转红，其余 35 项不受扰。桥快照缺 `world.advance` 时以 ProtocolError 拒绝，不再 TypeError。
- **负例补齐（复审第 6 条）**：同 ID 换操作的 `request_id_reused` 服务器形状、退役 ID 同载荷复用的 ProtocolError、narration_claim 重放剥离 claimToken（acceptance 原件带 token 对照）、桥 scope 失配守卫、`assertFaultsConsumed` 未耗尽脚本负例——文档已声明的行为全部有测试钉住。
- **类型根治（复审第 4 条）**：`ErrorCatalogEntry` 补 `controlRequired` 必填字段，新增 `errorBodyFor(code, details)` 作为错误体唯一构造器——内部目录字段在类型与构造两层都无法进入响应信封；顺带清除 `t06.scenario.ts` 死参数（复审第 7 条）。

结果（accept 后）：T06 37 项（双样本 × 18 + 1 条传输守卫独立测试），前端全套 **19 文件 372 项通过**，`typecheck:world`、`review:world-s1`（60 项）、统一验收入口（Python 109+317、契约 38、轨迹 65、四类破坏探针全拒，PASS）与生产 build 重新全部通过。完整 B1 仍待 A2 就绪后以 T01 运行 H1；T07/T09 继续留 B2/H2。

**盲区复核关闭（同日，对 `591d818`）**：复审方独立实跑确认——正常 37/37；注释 refresh 分支 `adoptState` 后恰好双样本专用测试失败（2 failed / 35 passed，实际 revision=12、预期 13）；还原后 37/37、工作树干净。针对 a569261 双通道泄漏的 P2（revision 断言盲区）撤回关闭。保留三条原有 refresh 测试的决定经复核认可：专用区分性测试已钉住 refresh 共用分支的采纳语义，无需逐条重复补强。T06 至此关闭：交付 `3e14200` → accept 补强 `a569261` → 盲区修正 `591d818`。

## B2 批次一：fetch 绑定修复 + 串行推理队列、取消与结构化输出

日期：2026-10-24。T06 关闭（`477e878`）后按用户指令推进 B2 运行层，不等 A。批次范围：HTTP transport 默认 fetch 绑定修复（`83dbe3b` 已单独提交，A 联调的浏览器 `Illegal invocation` 即此）、串行推理队列、取消语义、结构化输出校验、引擎接口 + wllama 适配器、模型端口（占位编码器）。双心跳与失效处理、设备探测接线、真实提示词与质量评测、真实模型浏览器计时 harness 均不在本批（计时埋点已就位，实测随长推理/心跳批）。设计层补充见 [b2-runtime-design.md](b2-runtime-design.md)。

**fetch 绑定**：默认 fetcher 原为未绑定的 `fetch`——Chromium 原生 fetch 拒绝非全局接收者，`this.fetcher(...)` 把 transport 实例当 `this` 即抛 `Illegal invocation`；undici 不挑接收者、既有测试全部显式注入 fetcher，故 Node 侧从未暴露。修复为 `fetch.bind(globalThis)`，注入语义不变。测试用严格接收者桩在 Node 复现 Chromium 契约（接收者非 undefined/globalThis 即抛），篡改实验（还原未绑定默认）确认恰好转红。

**串行队列（runtime/inference-queue.ts）**：单一约束是同一时刻至多一个推理在跑（端侧内存不允许并发解码），FIFO。取消三层：排队中取消立即 AbortError 定局且从未触达引擎；调用方取消（或 dispose）**即刻**定局调用方 promise，引擎只收到 linked signal——调用方永远不被要求等引擎响应中止（镜像 http-transport「超时必须定局即使实现忽略 abort」规则）；引擎 promise 的迟到 settle 由前挂 handler 吞掉，既不产生 unhandledrejection 也不覆盖 AbortError。**运行槽位只随引擎 settle 释放，不随调用方取消释放**——下一个推理必须等设备真的停下来。计时 `{queuedMs, runMs, totalMs}` 与加载/推理测量共用同一埋点。手控 deferred 确定性测试 8 项覆盖 FIFO、排队取消不触引擎、运行取消先定局后让槽、迟到 resolve/reject 丢弃、dispose、预中止 signal、引擎自发 AbortError 归一、计时分离。

**结构化输出（runtime/structured-output.ts）**：十类 ModelTask 各一 codec。JSON 任务（action/targets/results/updates/continuation/initial/time/pointPlan）容忍 ```json 围栏与首尾空白后严格校验，形状全部钉自 schedule/controller 既有消费点（action `{kind:act,text}|{kind:skip}`、targets 闭集 ruleVersion、updates 六阶段闭集、continuation 强制 closedBy=model、initial 顶层契约+版本常量——深层由 create_world 的 wire schema 复检，与内存驻留型输出区分）；narration/reaction 是文本任务：非空原样，绝不 JSON 解析（叙事 JSON 契约对 0.6B 是毒药的结论不因校验层回潮）。失败抛 `StructuredOutputError{task,reason,raw}`，本批不做修复重试——质量与重试策略归 B3。正反例 11 项。

**引擎与端口（runtime/engine.ts + wllama-engine.ts + model-port.ts）**：`InferenceEngine` 接口（load/complete/dispose/info，取消是契约一部分）；wllama 适配器映射 `createCompletion` 的 max_tokens/temperature/seed/stop/abortSignal，工厂可注入——Node 测试只验参数映射不触 wasm；`RuntimeWorldModelPort implements WorldModelPort`（三参接口 + 可选第四参 signal，结构类型兼容，controller 零改动），encode 为标注 B3 替换的确定性占位，decode 即本批真交付；模型加载本身走队列（load 与推理共享设备槽，引擎侧幂等）。端口测试 5 项：九类任务往返（loads 幂等一次）、形状违规即 StructuredOutputError、并发调用严格串行、abort 到达引擎（linked signal）且迟到 settle 不外泄、encodePrompt 确定性。

结果：前端全套 **24 文件 403 项通过**（372 + fetch 2 + 运行层 29），`typecheck:world` 干净、`review:world-s1` 60 项、统一验收入口 PASS、生产 build 通过。运行层无真实模型浏览器实测——计时埋点就位，实测 harness 随长推理/心跳批交付；真实 HTTP 链路仍属 H1/H2。

### B2 批次一修复轮（对 977c82a 复审六项）

日期：2026-10-24。复审对 `83dbe3b` 通过；对 `977c82a` 列 6 处可复现问题（2×P1、4×P2），全部确认成立并已修，修复提交随本条：

1. **updates 双形态（P1）**：校验器只收数组，挡掉了拆分模式的合法单调用输出。现在批量数组与拆分单调用均合法且不归一化穿透（controller consumeModelOutput 按 mode push 是消费端事实），既有逐调用校验不变。
2. **空 actor 点（P1）**：pointPlan 的 actorIds 非空约束撤回——T03 无行动时间扫描点与空 linked 点计划零 actor 是已验收形状，仍校验元素类型。
3. **delta 内层形状（P2）**：EntityDelta 闭集逐字段校验（positionSet/Position、appearance/personalityChanges/Change、sanitySet、tasksAchieved、subtasksAdded/Task 含 status 闭集），未知字段拒绝——`subtasksAdded:7` 这类让 mergeUpdatesStages 抛 TypeError 的形状在 codec 层即拒。
4. **加载取消转发（P2）**：load 的调用方 signal 经引擎自有 AbortController 传入 `loadModelFromUrl` 原生支持的 signal；下载中取消即通知底层，fake 侧断言转发信号随调用方中止。
5. **加载中 dispose 复活（P2）**：dispose 改为终态且中途安全——在途下载先 abort，落地实例（哪怕在 dispose 之后才完成）走 disposed 检查立即 exit、不登记；探针形状（modelId 残留、exit 0 次）不可能再出现。两分支各有测试：download 遵约中止 → exit 0；无视中止落地 → exit 1 且 modelId 为 null。
6. **同步抛错滞留（P2）**：`start()` 同步 throw 进入统一失败清理——释放槽位并定局调用方，后继照常泵入，专项测试钉住。

结果：前端全套 **24 文件 407 项通过**（403 + 4 净增：队列同步抛错、加载取消转发、中途 dispose 两分支），`typecheck:world`、`review:world-s1`（60 项）、统一验收入口与生产 build 通过。b2-runtime-design.md 已同步三处语义（加载转发与 dispose 终态、同步抛错清理、updates 双形态/空 actor/delta 校验）。

### B2 批次一修复轮二（对 56e42d9 复审两处 P2）

日期：2026-10-24。前六项经复审独立确认修复；两处新增 P2 确认成立并已修：

1. **updates 模式失配（P2）**：codec 校验双形态但不区分当前调用模式——拆分调用返回数组放行后控制器报 "Out-of-order/duplicate updates stage"，批量调用返回单对象放行后 merge 抛 TypeError。现在 `decodeTaskOutput` 接受逐调用约束 `{updatesSplitMode}`，端口从声明输入推导（`input.stage` 存在即拆分，schedule.ts:671/672 是判别字段），错误形态在 codec 层拒绝，合法输出原样穿透；无约束的独立校验仍接受双形态。
2. **取消的加载永久阻断（P2）**：`loading` memo 永久缓存失败 promise——首次加载遵约响应取消后，后续全新调用立即复放旧 AbortError 且底层不重试。现在失败（memo 原样拒绝被侧信道 catch 标记为已处理）后清除 memo，下一次调用真正重启下载；同一次加载的并发调用方仍共享同一命运，dispose 终态不变。篡改实验钉死：还原永久 memo，恰"取消后可重试"一条转红。

结果：前端全套 **24 文件 409 项通过**（407 + 2 净增），`typecheck:world`、`review:world-s1`（60 项）、统一验收入口与生产 build 通过。

**复核闭环（同日，对 `d76ef58`）**：两处 P2 关闭、未发现新增阻塞问题。复审独立实跑确认：两种模式错配均在端口拒绝且合法输出保留原形态；并发加载共享取消结果、失败后能重新加载并完成生成；dispose 终态、迟到实例清理不复活；409/409、typecheck、review 60/60 与 5 条独立探针全过。**B2 批次一关闭**：提交链 `83dbe3b → 977c82a → 56e42d9 → d76ef58`。下一批按计划推进双心跳与失效处理；真实浏览器模型实测与 H1/H2 单独验收。

## B2 批次二：双心跳与失效处理

日期：2026-10-24。批次一复核闭环（`e5aac89`）后按计划推进。交付 `runtime/heartbeat.ts`：lease 续租与 head claim 续期两条独立心跳（`HeartbeatScheduler`），时钟注入（`HeartbeatClock`，系统实现 `SystemHeartbeatClock`，测试用 `ManualClock` 确定性推进）。设计层补充见 [b2-runtime-design.md](b2-runtime-design.md) §7。

**调度依据是服务端回执的过期时间**：lease 取响应信封 `world.lease.expiresAtEpochMilli`（续租成功取 `data`），claim 取领取/续期响应 `data.expiresAtEpochMilli`——`CurrentClaim` 不带过期字段，控制器 memory 单独推不出调度基准，这是会话层必须保留领取回执的原因。续租在 `expiry − leadMs` 触发；`updateLease/updateClaim`（任何响应观察到更新鲜的 token/epoch/expiry）重排定时器并以 cycle 计数作废为被替换状态在途的续租——迟到回执的采纳被丢弃，不会用旧 token 续出脏结果。

**心跳是 transport 调用，不走推理队列**——与引擎调用并发，即长推理期间保活的实现方式（测试钉住：生成持锁期间续租完成）。超时与可重试拒绝（目录 `retryable=true`，如 request_in_progress）以同一 requestId 退避重试（renew 幂等 replay original_data，同 ID 重发安全）；不可重试的确定性拒绝（stale_epoch/lease_invalid/claim_expired/claim_fenced/version_mismatch 等）即失效——`onLost({kind, code, response})` 上报并停该条心跳；意外非 API 错误按瞬态退避重试。requestId 每续租周期铸新、超时重试沿用同 ID，与控制器约定一致。**失效取消**：会话层把 onLost 接到生成的 AbortController——批次一队列的迟到丢弃保证失效后的引擎结果不可达（集成测试钉住全链路：stale_epoch → abort → 调用方 AbortError → 迟到 resolve 仍被丢弃）。真实接管正确性留 H2。

结果：共 9 项心跳测试（触发时机±lead/请求形状与 scope 全字段/同 ID 超时重试/确定性失效即停且只报一次/claim 失效不影响 lease/状态更新作废在途续租/stop 永久取消/持锁期间保活/失效取消+迟到丢弃集成）。前端全套 **25 文件 418 项通过**，`typecheck:world`、`review:world-s1`（60 项）、统一验收入口与生产 build 通过。B4 会话装配（把 HeartbeatScheduler 接进 driver 循环、从响应信封喂 updateLease/updateClaim）与真实定时/TTL 属后续批次；H1/H2 单独验收。

### B2 批次二修复轮（对 9323d46 复审两处 P2）

日期：2026-10-24。两处确认成立并已修：

1. **回退观察覆盖新凭证（P2）**：`update()` 无条件替换状态——迟到信封（旧 epoch/旧 token/旧过期）能把调度推回死凭证。现在两条心跳各注入单调比较器：lease `(fenceEpoch, expiresAtEpochMilli)`、claim `(generation, issuedAtEpochMilli, expiresAtEpochMilli)` 字典序，`update()` 只接受严格更新的观察；`start()` 保持无条件（会话显式重启用，重取租约的新 epoch 天然更新）。篡改实验（还原无条件替换）恰两条守卫测试转红——其中 claim 守卫的首版测试对回退不敏感（回退观察恰同值），已换 stale-token discriminator 补强。
2. **补齐 `updateClaim`（P2）**：文档承诺的对称入口已交付，含同代新过期接受、同代旧过期/stale token 丢弃、跨代（generation 抬升）替换的回归测试。

另按复审建议把失效取消测试改为因果接线——`onLost` 回调内直接 `session.abort()`（丢失报告即取消原因），并断言槽位随引擎 settle 释放。

结果：前端全套 **25 文件 421 项通过**（418 + 3：回退 lease 观察丢弃/同代新过期重排/updateClaim 对称守卫），`typecheck:world`、`review:world-s1`（60 项）、统一验收入口与生产 build 通过。b2-runtime-design.md §7 已同步守卫语义。

**复核闭环（同日，对 `d95f2d7`）**：两处 P2 关闭、未发现新增阻塞问题。复审独立验证：旧 epoch/旧 expiry 丢弃、updateClaim 正确替换新代并作废旧代在途回执、同值观察不误丢失效报告、onLost 取消接线通过；撤回比较器恰 2 failed/10 passed、还原后 12/12；421/421、typecheck、review 60/60 与三条独立探针全过。**B2 批次二关闭**：提交链 `9323d46 → d95f2d7`。B4 会话装配、真实定时/TTL 与 H1/H2 按原边界单独验收。
