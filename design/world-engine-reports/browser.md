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

语料来源：共享 `traces/T01.json` 的 sample_1 与 sample_2 全部 20 个共享步骤逐字实例化（request/scope/response 按轨迹自身捕获纪律，input 变量像共享解释器一样预载），响应体不做任何改写；B 自有标本仅一处——`b-preview-after-begin-s6`（begin 后的额外 preview），从同一轨迹录制的 s16 preview（同一点）派生：真实主角/时间/花名册/物品/任务（person_c、11:59:02、person_a 在 lobby），该点 staged entityDeltas 回退到录制 initial positions、projection 的 entityDeltas 置空，仅两个 digest 字段为符合 schema 的 `0`×64 占位值，明确不作摘要证据。preview 位置：begin 后（B 标本）＋ skips 后、seal 前的 s16（共享步骤，即"stage 后"的最终 preview）；纯时间扫描 preview 规则留待 T03，本轮不宣称覆盖。

摘要断言范围（全部 serve 期执行，不再只在 inspect）：①共享独立预期——s21 的 `/data/stateDigest` 对 `expectedDigests.s21`、`/data/state` 对 `expectedProjection` 实例化比对，不从任何实际响应生成预期；②运行时摘要链——构建期从 $var 共享推导「capture 位置→后续引用位置」链接（模板×实例化并行走查，`$map` 按实例化键解析），serve 期断言 served 值等于先前 served capture 值（T01 中 v32 贯穿 s16 workingStateDigest → s18 head.stateDigest 与 s18 data.stateDigest）；③preview↔预期对齐——s16 的完整 served `workingState` 与 `workingStateDigest` 分别对齐 s21 独立 `expectedProjection` 与 `expectedDigests`（两样本已验证录制层面相等），堵住摘要链对无引用字段的盲区；④独立摘要钉——s16 `pointProjectionDigest` 由场景钉表持有（按服务端配方 `canonical_digest(pointProjection)` 用 Python 规范化编码器独立重算、与录制核对一致，语料实例不参与取值），无引用字段不再自证。

身份与命令：requestId 生命周期独立于 driver memory——录制请求 ID 在构建期校验回显一致（response echo == request requestId）后从语料剥离，transport 强制带 ID 操作每次携带从未用过的新 ID（同前端 `retry_same_request` 的合法重放经 frontRequestId 容忍）、无 ID 操作（preview/reads）不得泄漏 requestId，serve 时回显改写为 driver 实发 ID；driver 复用同 ID 或语料回显损坏分别被定向反例拒绝。allocate 响应按 slotKey 落入 `ids`，调度键经 `identityAliases` 绑定。`initial`/`pointPlan`/`action`/`targets`/`results`/`updates`/`narration` 全部经模型端口执行并严格核对 task/key/完整 input/顺序；expected input 一律从声明的响应与标本推导。控制器段由真实 `ControllerDriver` 运行：transport 只核对驱动器推导出的请求，夹具不投喂预期请求、不逐步修改 memory。

分段与结束边界：T01 无 command/probe 场景，不计覆盖。controller 段 s1–s20；s21–s23（get_state/list_points/narration_get）为 inspect，由 harness 直发；s20 后真实 phase 为 `assess_continuation`，harness 在声明的停止边界断言驱动器待决决策恰为 continuation 模型调用（`pendingDecision`）后结束场景，不伪造 complete/round_points_exhausted，不额外调用 continuation 模型。

结果：双样本正路径通过（transport 24 次调用 = controller 21 次 + inspect 3 次全序列逐字核对；模型 8 次调用 task/key/input 全等；schema 先于消费；正路径另以整体相等断言钉死 T01 标本对录制的写实——protagonist/时间/person_a 在 lobby/物品任务/roundId）；十三条定向反例全部按预期拒绝——身份绑定断裂（组键无别名→s7 请求失配）、声明请求篡改（s4 allocationKey）、声明 scope 篡改（s7）、模型输入不符（action actor）、未声明 preview（删除标本后 preview_point 撞 discover 声明）、共享摘要篡改（s21 expectedDigests，serve 期拒绝）、s16 workingStateDigest 链断裂、s18 data.stateDigest 链断裂、s16 pointProjectionDigest 钉失配、录制 s16 workingState 篡改（sanity 10→11）经 s21 对齐拒绝、driver 恒复用同 requestId、录制回显损坏（构建期拒绝）、T02 语料构建（input 变量预载回归）。前端全套 13 文件 260 项通过（含既有 65 项共享轨迹逐字消费，共享轨迹/schema/manifest/digest pin 零改动）；`typecheck:world` 与统一验收入口 PASS。

**结论：T01 固定响应控制器验收两轮评审缺口已全部修复，待复审放行。** 真实 API 序列化与真实服务摘要一致性由 H1 验证；T02 组扩张在放行后推进（错误/恢复步骤的语料表达与 recovery hop 的 requestId 生命周期是 T02 设计项）。
