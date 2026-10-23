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
