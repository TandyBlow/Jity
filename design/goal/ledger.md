# Jity Goal v11 能力账本（R01–R16）

状态：active。日期：2026-11-20。基线：`agent@695e6bd4`。

本文是 R01–R16 的唯一状态来源。旧文档里的「已有」「已验收」只作来源记录，状态以本表为准。

## 1. 状态词表

| 状态 | 判定 |
|---|---|
| 未实现 | 没有产品路径代码，或只有设计文档 |
| 实现中 | 有代码，但真实模型、真实页面或恢复证据不完整 |
| 固定输出通过 | 仅夹具、脚本、规则或模板通过，不能证明模型能力 |
| 真实模型部分通过 | 真实模型跑过部分场景，仍有未覆盖分支 |
| 真实模型按范围通过 | 指定范围内真实模型、页面与证据齐全，范围写明 |

规则：

- 机制存在不等于能力完成；函数名叫 `generate` 不等于调用过模型。
- 固定输出、模板、规则通过只能记「固定输出通过」，不能记「真实模型通过」。
- 每行必须有代码路径、证据、缺口、归属 G 线；没有证据就写「待 Gx 复核」，不编测试结果。

## 2. R01–R16 主表

| 编号 | 能力 | 状态 | 代码路径@695e6bd4 | 证据 | 缺口 / 归属 |
|---|---|---|---|---|---|
| R01 | 开局固定地点、物品、人物；运行中只更新登记实体；允许在既有大任务下新增小任务 | 实现中 | `local/world-loader.ts`、`local/static-world-registration.ts`、`local/state.ts:83` | `world-loader.test.ts`、`state.test.ts`；`data/worlds/README.md`；摘要 `3f65452d…` / `6262d5fc…`；run39 场景门 `legal_failure_not_enforced` 命中；run40 复跑 5 次：4 次结算判成功、1 次结算 blocked 但叙事写成已发生（5/5 层间失败）；正文门 `unknown_entity_claim` 在 run37/40 的 3/3 个 s06 命中；`settlementUnknownRule` 评估臂 3 次仅 1 次干净；`strictKnownEntities` 默认校验后 s06 结算门 1/3 命中（基线 4/5）；门收紧（2026-11-23）后 run85–90：s06 约 2/5 中止、3/5 宽松轮丢 fact，0.6B 不能稳定产出 blocked fact；门加严（2026-11-23）：动作点名未登记实体时，丢名字的成功 fact 也拒绝或按 blocked 判词改写，run114 s06 合法失败已强制；动作不含「规则」时规则牌事实丢弃，run115 规则填充消失 | 真实模型引用未知实体、非法新实体的正反例；未知实体不能靠叙事变成事实；反例目前失败（结算层，D-022）。G2/G5 |
| R02 | 地点嵌套、人物/物品容纳与相对位置；自然语言外貌、任务、个性、理智 | 实现中 | `local/state.ts`、`types.ts`、`world-loader.ts` | 静态世界 26 地点/14 人物/74 物品/73 任务；state 测试 | 嵌套移动、物品移动、地点外貌、相对位置的真实模型场景与页面展示。G2/G5/G6 |
| R03 | 初始外貌与个性不改写；变化保留历史；位置结构化 | 实现中 | `local/state.ts` 的 initial/current、`pointEntityDeltas` | state 测试；静态世界 README | 真模型合法变化、替代引用、原文保留、纯解除分支。G5 |
| R04 | 世界事实由 S₀＋Δ 构成；状态/摘要/检查点可重建 | 实现中 | `state.ts:83/906/952`、`canonical.ts`、`history.ts`、`persistence/` | `state.test.ts`、`history.test.ts`、`session-recovery.test.ts`；Python–TS 冻结差分（`kernel-diff.json`）；restore 接 `verifySessionSnapshot`（`session.ts`、corrupt-chain 测试） | 真实多轮页面回放证据；缓存与模型切换不能改变事实来源。G2 |
| R05 | 同点同实体合并为一份增量 | 实现中 | `state.ts` 的 `applyPoint` 合并、`transport.ts` 的 work 记录 | state、local-transport 测试 | 真实多组与连续阶段的最终投影一致。G2/G5 |
| R06 | 非关联新轮按理智排序；关联点沿用冻结顺序 | 实现中 | `controller.ts`、`schedule.ts`、`local/session.ts` | controller、schedule 测试 | 真实多人物行动与续轮、逐人判断、重排、关联顺序不变。G2/G5 |
| R07 | 骰点驱动被迫行动准入；先冻结全组再统一结算 | 实现中；真实模型未验 | `local/transport.ts` 的 group/work、`turn-execution/`、`controller.ts` | turn-execution 测试；旧脚本候选只作对照 | 模型分析目标、生成反应与共同结果；多级、未准入、环、已冻结成员；不以脚本文本代替。G5 |
| R08 | 已行动人物不重复行动；后续骰点仍影响攻击者结果 | 实现中 | `local/transport.ts` 的 `actedIds`/round、`turn-execution/` | transport、turn-execution、recovery 测试 | 真实模型组场景；恢复不重掷、不重采样。G2/G5 |
| R09 | 位置→外貌→任务→新增小任务→个性→理智；任务与个性全人物覆盖 | 实现中 | `local/state.ts` 的阶段 apply、`turn-execution/`、`game-model.ts` | state 测试；旧六阶段 preview 只作参考 | 真模型候选按依赖逐阶段；任务扫描全人物；任务达成后个性扫描全人物；允许合法不变化。G5 |
| R10 | 仅由大概率发生且与主角关联的后续行动触发自动推进 | 实现中 | `controller.ts`、`schedule.ts`、`local/session.ts` | controller 测试；旧固定 handback 只作对照；G3 计时运行 `artifacts/goal/timing-runs/points-10-rerun.json`；D-024 评估臂：无自动链 36.9–45.0 s（run37/38），保留一轮自动链 59.8–100.6 s（1/16 ≤60 s）；早交还套件 20/20：18/20 ≤60 s（32.8–70.7 s，中位 44.9 s）；十输入 run92 10/10 ≤60 s（30.3–53.4 s），t6 刷新恢复通过 | 真模型 continue/handback；G3 十点 0 次 continue：t1 结论请求 `request_malformed`，t2/t3 自动后续在 updates 停止（上下文/重复任务），归 G5；多轮不重复消费输入；预算暂停不伪装 handback；自动链与 60 s 口径的取舍待产品决定（D-024）。G5 |
| R11 | 每点只读叙事；可省略/暗示/隐藏秘密；不虚构已结算事实 | 实现中；raw-output 边界已定 | `local/point-narration/`、`narration-input/`、`narration-generation/`、`narration-candidates/` | `design/parallel-handoff/01-quality.md:279`（2026-11-11 原样输出）、`02-narration.md`；旧 B3/叙事实验只作参考；`check-prose-facts.mjs` 新增 `unknown_entity_claim`（3/3 s06 命中）；本地 1.7B LoRA 三轮（run85–90）：v3 探针 2/2 硬错 0、32.8–36.7 s，五回合集仍有未结算事件（规则牌×2、摸规则）与重复句；基座同提示仍复述并写完成（run88）；十输入集（run92）6/9 有正文回合硬错（持枪、张冠李戴、位置矛盾、规则阅读转移），检查器 0 命中；重复句 9/9；4B 十输入部分（run93）复述回归、t3 未结算人物、t4 超 60 s、被内存回收；投影瘦身（run96）仍有 t3/t8/t9 硬错、4/10 超 60 s、细节丢失；DPO v4（run97）滑向否定复读、主角持枪/矛盾/凭空细节，检查器 5 命中，不采用；归因数据 v5（run98）10/10 ≤60 s、重复句消失、硬错 3/9（规则阅读归因×2、未结算移动×1）；v6 加权复训（run99）倒退：结算中止、超 300 s、重复句与位置矛盾回归，恢复 v5；v5 五回合（run100）未达 5/5：s03 归因、s05 凭空动作、s06 结算中止；v7 手工 129 行（run101/102）硬错 ≥4/9、五回合仍不过，恢复 v5；v8 手写 252 行（run105/106）五回合 s02–s05 硬错 0、s06 结算中止；十输入 4/9；结算示例臂（run107）无效果，fact 仍 completed；判词搬移（run108–110）s06 结算打通、5/5 完成，但叙事填充仍致 5/5 质量不过；定向手写 v9（run111）5/5 完成、s02–s05 硬错 0、s06 一处填充；v10 数据备好待训；v11 修正两处提示缺陷（弧廊蓝带/他、钟楼空主语结算）并加 18 条手写样本（328 行，检查器 0/18）；集群训练 276262、构建 276264 完成；run113 5/5、30.7–58.2 s（填充来自 point 1 结算归因）；门加严后 run114 5/5、74.8/37.0/75.1/99.0/65.8 s（1/5 ≤60 s），s06 合法失败已强制；规则事实门后 run115 5/5、31.8–47.6 s（5/5 ≤60 s），规则填充消失，检查器 0，剩余两 point 重复与「故障短讯机」自造；分点收窄后 run117 5/5、38.1–56.8 s（5/5 ≤60 s），动作/结算句重复消失，检查器 0，剩余 NPC 状态重复与正文偏短；KV 量化后 run120 5/5、34.0–49.1 s（5/5 ≤60 s），检查器 0，语义 KV 约少 0.7 GB；v12 手写 10 条（NPC 放置物品不镜像，338 行，检查器 0/10），待训练；v12 训练后 run122 5/5、33.6–48.4 s，但把在场诺诺写成缺席，拒绝并回退 v11；v13 正例对照 10 条（348 行，检查器 0/10），待训练；v13 训练（276368）后 run124 5/5、24.5–58.8 s、检查器 0，缺席回归消失；run125+126 20/20：chunk1/3/4 干净（s13 真机恢复，各 1 input_echo），chunk2 s06 强门中止（已改丢弃）、s07 330 s，chunk5 g8-t2/g8-t3 干净（g8-t2 81.7 s）、g8-t4 结果截断（已抬 results 上限 420→640）；抬上限后重跑 results 成功、updates 报 relative reference 位置错（已修为丢弃关系保留位置）；g8-t4 再跑 COMPLETED、28.8 s、检查器 0；run129 18 回合 + run126/128 补点：20/20 无驱动失败、交还全部 ≤60 s，检查器仅 1 input_echo；s07 330 s 属间歇（D-024） | 产品路径正文逐字等于模型返回；5 回合集 run115/117 按 4.2 人工读 5/5 零硬错、5/5 ≤60 s（评估臂，非默认）；20+ 点未复测；视角/秘密/选择。定向微调未在 20 输入集验证（D-022）。G6 |
| R12 | 不另维护人物知识状态；模型从当前世界判断认知 | 实现中 | 无独立知识库；叙事只读已提交状态 | `architecture.md` 第 6 节；local 目录无 knowledge store | 确认提示/模型无隐藏知识真值库；可见性投影规则。G6 |
| R13 | 行动描述仅作本次分析；不建长期行动历史 | 实现中 | `local/transport.ts` 的 `actionTexts`、`persistence/` 快照、`history.ts` | transport、persistence 测试 | 原文只按工作态生命周期保存；调试归档与世界存档分开。G2/G4 |
| R14 | 工作职责不等于模型数或调用数 | 实现中 | `game-model.ts` 的 options、`controller.ts` 的 `ModelTask`、`schedule.ts`、`runtime/webllm-engine.ts` | `architecture.md` 第 6 节；模型变体清单；G3 逐任务调用记录 `artifacts/goal/timing-runs/points-10-rerun.json`；WebLLM 评估：3B 40–50 s/回合、格式通过、质量未过；4B 可加载但本机连续跑受内存限制；移动模拟 264.9 s；语义模型 KV 缓存 q8_0（12,288 上下文不变，约 1.38→0.69 GB），叙事保持 f16，wllama `cache_type_k/v` 实测可加载 | 按质量/成本选择单/多模型；记录每任务贡献；运行时替换不改善叙事质量（3B 三种候选均不合格）。G3/G6 |
| R15 | 开局生成 | 已改写：静态载入/校验/封存，实现中 | `world-loader.ts`、`static-world-registration.ts`、`data/worlds/` | loader/registration 测试；摘要与计数；2026-11-10 用户澄清 | 静态世界供给与 held-out 决定；开局校验与页面。G1/G2/G4 |
| R16 | 小世界完整可玩；≥20 输入；自动链、共同结算、恢复、历史、删叙事重生 | 技术证据齐；**笔记本档按 v13 默认通过（D-028）；移动档按 60 秒同口径不通过（D-023，2026-11-24）；内核/调度探针（wllama 4.0.0 0.80×、移动 20 输入 137.1–272.1 s 全部超 60）后结论不变** | `world-local/page.tsx`、`frontend/scripts/product-acceptance/accept-world-local.mjs`、`turns-20*.json` | `artifacts/goal/acceptance/summary.json`（20 输入：首段 20/20、回合 20/20、0 失败，9 个 295 s 时限收尾）；离线 2/2；服务器关闭 2/2；两设备分叉 `artifacts/goal/sync/two-device-20261121.json`；移动模拟 run35/36 仅作测量；2026-11-23 run94 当前代码复测 210.5 s（早交还臂），60 秒仍不可达；run103 只压 results 清单 189.1 s，run104 压容器目录反升到 229.9 s（已回退）；2026-11-23 run121 20 输入复测：内存修复后 5 chunk 跑完，18 回合无问题、≤60 s，s13 门误报中止（已修）、s14 330 s、s15 张冠李戴（检查器命中） | G5/G6 质量线未过（结算把未知实体判成 completed；叙事硬事实错误）；移动档未验收；D-024 早交还仅为评估臂（默认 64.9–180.7 s，评估臂 36.9–45.0 s）。G8 |

## 3. R15 改写说明

原 R15 要求分批生成初始实体、描述、任务、个性和理智，确认后封存。用户 2026-11-10 明确：初始世界来自预置静态文件，开局只读取、校验并封存，不动态生成世界。因此本版 R15 的交付是：

- 静态 `WorldState`/`WorldInitialState` 文件；
- 严格加载、实体/位置/任务/个性/理智引用校验；
- 从 `initial` 重建 S₀；
- `stateDigest`、`fileSha256Lf`、`initialDigest` 登记与不一致拒绝；
- 页面只加载已登记资产。

动态生成、草稿修订、生成训练不在本版范围。

## 4. G1–G8 状态摘要

| 目标线 | 状态 | 说明 |
|---|---|---|
| G1 目标与文档基线 | 进行中 | 本文档集、索引、横幅、账本 v1、baseline tag |
| G2 浏览器状态内核收口 | 完成（2026-11-20） | 32 操作定案（31 实现、`restore_group_work` 非产品，D-015）；取消恢复与 corrupt-restore 测试通过；restore 接 `verifySessionSnapshot`；差分夹具由 canonical/state/transport 测试逐字节断言；骰点协议冻结；全量 90 files / 1256 passed，两套 typecheck 通过；证据 `artifacts/goal/kernel-{diff.json,ops.md}`；Change 已归档，tag `goal-g2-kernel-diff-20261120` |
| G3 模型资产与时间包线 | 复核不通过（2026-11-20）；D-018 探针通过 | 资产已取并逐字节校验；冷启动 24.7/18.9/19.3 s；原 12 点首段 9.4–43.5 s、正文 6.4–13.8 s，但回合完成门后 7/12 中途停止，`timing-baseline.json` 为 `FAIL_OR_INCOMPLETE`；D-017 维持 judge 下 run17/18 普通回合 295 秒时限；D-018 点级六阶段 + 240 s 预算后 s01 探针 280.1 s 交还（首段 25.1 s、首点 23.0 s），更多回合与全套件待复测 |
| G4 单机可玩页面接线 | 完成（有缺口） | 隔离告警、pause/resume、HistoryPanel 只读选中、叙事删除/重生（head+history）、NarrationView/ProgressStatus、空占位清理、构建/e2e/block-api 通过；缺口：WorldStatusPanel 未接、`position_invalid` 与自动轮重复转 G5、无 10 轮全绿运行；run11 自动链存档刷新曾因 invariants 拒绝，kernel 已修；run15 s03 页面在时限取消后停留 `streaming`（“正在写正文”不消失），已修为提交结束必离开计算阶段 |
| G5 非叙事语义验收 | 已归档（未通过，2026-11-22） | D-018 后代码上 s02–s06 干净复跑（run22/23/24，进度服务停用），驱动 problems 0；技术读评 hard 5/5（`artifacts/goal/narration/read-5-clean-20261121.md`）。事实层定向拒绝生效（s02 识别带 fact 被拒两次），但正文仍写主角识别带/挪他人红痕；generic「看懂了规则牌」fact、judgment/fact 矛盾、事实挂到未行动成员仍是系统性问题。补充：证据未序列化被接受的事实（只有 raw 尝试），fact 级结论待补证据；恢复缺陷（从半取消回合的分叉存档开局）已记 G2/G4；change `goal-g5-semantics-followup` 已归档，tag `goal-g5-semantics-followup-20261122`，2.1 转 G6/D-020 |
| G6 叙事产品路径与质量 | 已归档（未通过，2026-11-22） | 运行期边界与逐字显示已闭（1.1/1.2）；16 例技术读评 hard 13、5 例干净复跑 hard 5/5；29+ 样本入库；微调对照：历史 1.5B 候选公版与产品格式均劣于默认 1.7B，已排除；4.1 已决（D-021：只做开发期检查，运行期保持 D-004；检查器 26 回合报 band 2/echo 5）、4.3 首次微调完成：Qwen3-1.7B+历史 LoRA 产品格式出现镜片细痕/红发转移，不改善；集群流水线跑通，默认仍 raw 1.7B；tag `goal-g6-narration-20261122` |
| G7 进度同步与跨设备 | 完成（2026-11-21） | 页面 startup restore、重连自动 flush、冲突面板与 `sync.choose`；保留本地分支取 store 最新快照并清该世界队列；禁止跨分支重基；两设备端到端证据 `artifacts/goal/sync/two-device-20261121.json`：同一根快照、两设备离线推进、重连上传、启动弹分叉、选一支后 2 分支留存、另一支 200 可读、刷新恢复；单用户 Bearer + 本地/内网（D-013） |
| G8 交付验收与证据 | 技术证据齐（G5/G6 未通过） | 20/20 首段（16.9–39.7 秒）、20/20 回合 <300 秒、0 失败（chunk1 复跑 27.1/19.1/17.4/16.9 秒取代旧四例负载失败；9 个时限收尾）；离线 2/2（首段 16.5/26.5 秒、reload 31.4 秒）；服务器关闭 2/2（首段 40.4/25.0 秒、/api 0 次）；两设备分叉通过（`two-device-20261121.json`）；报告与 manifest 已更新；D-019 取消用户签字；G5 hard 5/5、G6 阈值/事实门未冻结，整体不宣布通过；change `goal-g8-delivery` |

- **组件评审**：`arch-component-review-20261122` 完成并归档；结论是分层正确、回合延迟是串行调用与 prefill（占 2/3）、拆分不能解决；已删死模块 `action-execution/` 并纠正 Python 两套语义的文档。写放大（2.1）、IndexedDB 测试（2.4）、结构拆分（2.5）标记 deferred，等范围批准。prefill 实验：batch 调参（512/128→2048/512）无收益；静态块前置把提示缓存份额 22%→40%，但回合墙钟无改善（257.8→279.7 s / 295.5→289.0 s，噪声更大），已回退。

## 5. 开放任务

按 G 线列，作为唯一进度来源；不另建 progress 文档。

- **G1**：确认文档集与 tag；用户决策已记录（D-004/D-006/D-010–D-013）；当前无 `pending-user`。
- **G2**：完成。32 操作按 D-015 定案；取消恢复回归（`local-transport.test.ts`）与 corrupt-restore 拒绝通过；restore 已接 invariants；冻结差分夹具（LF sha `7d68a392…f977`）由 canonical/state/transport 测试消费；骰点协议见 `kernel-ops.md`；全量 1256 passed / 17 skipped，两套 typecheck 通过。failed head 的 cancel 已在 G4 放宽为 ready|failed。
- **G3**：复核不通过。原 `timing-baseline.json` 只统计已提交首点的朗读时钟，未提交的尾点不可见；加回合完成门后 12 个计分点中 7 个回合中途停止（`t1/t3/t5/t9/t12/e1/e3`），状态改为 `FAIL_OR_INCOMPLETE`。60 秒首段（最差 43,526 ms）与单点正文（最差 13,772 ms）本身仍通过；G5 run10–15 显示普通回合 250–330 s：每组合都跑六阶段 updates 是主因，首段 40–90 s 也会超 60。t4/t11 结算失败、t6 刷新保留为失败证据；自动链已有 automatic 点（run11/13）但 0 次干净 continue 结论完成整链。修正见 D-016；原 change 已归档、tag 保留。
- **G4**：完成（有缺口）。隔离、pause/resume、历史只读、叙事删除/重生、NarrationView/ProgressStatus、空占位清理；构建、1257 passed、e2e（含重生）与 `--block-api` 通过。缺口：WorldStatusPanel 未接；`position_invalid`（t4 `lu receives conflicting positions`）与自动轮重复转 G5；尚无 10 轮无停止的整轮运行；自动链（4 点含两个 automatic）在刷新时被 invariants 拒绝，恢复失败转 G4/G5。
- **G5**：技术自检不通过（2026-11-21 二次复核），用户抽检豁免；change `goal-g5-semantics-followup`。s02–s06 干净复跑（run22/23/24）：s02 285.6 s、s03 291.7 s、s04 290.0 s、s05 257.8 s、s06 295.5 s，驱动 problems 0。技术读评 hard 5/5（`read-5-clean-20261121.md`）：正文仍把识别带/红痕/枪/物品写成不属于该角色的状态；「看懂了规则牌」泛句与 judgment/fact 矛盾反复出现；s07 双挂已加收窄回归。证据限制：回合记录只有 results 的 raw 尝试，没有序列化被接受的事实，fact 级判定待补。原 change 已归档、tag `goal-g5-semantics-20261121` 保留为历史。
- **G6**：进行中（D-020：用户选择 HPC 微调对照；微调前基线已在产品同栈完成：5 题 × 3 次，事实 1.4/风格 1.8/回声 2.2/完成度 1.6，回声与凭空细节为主；1.1/1.2 已闭（页面正文与回合记录逐字一致、运行期不 import 质量门）；4.2 候选项核对完成（默认 raw 1.7B）；4.1 事实门未决（D-004 继续生效）、4.3 微调被集群 Slurm 控制器 DOWN 阻塞；集群登录可达（SSH 到登录节点正常）但 Slurm 控制器服务处于 DOWN（`scontrol ping` 报主备 hpcmgt/hpcmgt1 均 DOWN，登录节点 `slurmctld` failed），微调待集群管理员恢复）。原样输出路径保持；12 个 G3 样本技术读评 7 硬/4 复述/1 干净；2026-11-21 的 16 例技术读评（16/16）hard 13、style 3、clean 0（`artifacts/goal/narration/read-16-20261121.md`、`audit-16-raw-20261121.txt`、`audit-16-followup-raw-20261121.txt`）；已修 t5 地点冲突、物品归属 prompt、仅结算动作才算发生、占位句、识别带矛盾；未修：投影清单原句复述（系统性文风）、凭空短枪在叙事层仍需真机验证、s03/s06 上游。用户无法逐段读评（抽检豁免），阈值与事实门待实测。
- **G7**：完成（2026-11-21）。页面已接「本地优先、无本地时拉远端头并落盘」、重连自动 flush、冲突面板（远端头/分支 + 保留远端/保留本地并分叉）；选择本地分支时上传 store 最新快照并清空该世界队列；队列依赖只在前一条确实成为 head 时重基，否则保留原始 CAS 报 409；后端合并 `LOCAL_PROGRESS_CORS_ORIGINS`。证据 `artifacts/goal/sync/two-device-20261121.json`（PASSED）：A1 根快照共享、B1/A2 离线保存、A2 重连上传分支、B2 启动弹面板、保留本地后 2 分支、另一支 200 可读、刷新恢复 1 次行动。缺陷样本 `two-device-20261121-graft-defect.json` 保留。
- **G8**：进行中（change `goal-g8-delivery`）。生产构建通过、`next start` 服务；`turns-20.json` 拆 5 个四回合 session。chunk1 四例首段 63.5/154/73/112 s（宿主负载，全超 60），收尾被回收；chunk2 四例首段 18.0/18.1/39.7/34.5 s、accepted 19.9/27.4/52.9/42.8 s、reload restore 4/4、failures 0（`g8-chunk2-20261121.json`）；chunk3 三例（s09–s11）首段 34/17/20 s、s11 有页面内部注记（`g8-chunk3-20261121-partial.json`）；chunk3b（s12–s16）在跑。剩余：chunk5（g8-t1..t4）、离线、服务器关闭（`--block-api`）、两设备分叉（`artifacts/goal/sync/`）、manifest 与验收报告；D-019 取消用户签字与独立输入。

## 6. 证据索引

当前可作为来源的：

- `artifacts/world-page/`：`/world` 552148c 验收，历史参考。
- `artifacts/a3-2-signoff-d1d2de0.md`、`artifacts/h2-freeze-d1d2de0.json`、`artifacts/h2-integration-d1d2de0/`：H2/A3-2 冻结范围，独立有效，不作浏览器本地验收。
- `artifacts/narration-eval/`：叙事批次记录，历史参考。
- `artifacts/world-components/`：组件/模型实验，历史参考。
- `docs/tasks/full-merge-20261120.md`：合并记录；backend 1470 passed、frontend 602 passed / 17 skipped 是当时的记录，不是本版重跑结果。

G1 之后新增：

- `artifacts/goal/timing-baseline.json`
- `artifacts/goal/kernel-diff.json`、`kernel-ops.md`
- `artifacts/goal/semantics/`
- `artifacts/goal/narration/`
- `artifacts/goal/sync/`
- `artifacts/local-game-delivery/manifest.json`
- `design/world-engine-reports/local-game-acceptance.md`

大文件、权重、原始日志不入 git；在仓库内保存清单、哈希、取得方法与必要证据。

## 7. 微型工作流补充（2026-11-25）

- R10 continuation：结构化事件记录 + 四头微型模型已接入 `?micro=1`（`microContinuation=0` 退回上一版微型工作流，`microContinuation=rule` 直接跑规则作对照）。seed 11 四臂：LLM-only 257.7 s（本轮未到 continuation 即 turn_budget）、micro 无 continuation 150.8 s、micro 直接规则 153.6 s、micro 四头 99.2 s；seed 17 三臂：无 continuation 153.7 s、直接规则 95.7 s、四头 91.5 s。两 seed 四头 vs 规则合计 −29.3 s，但差异来自 seed 11 的额外自动点，seed 17 状态相同、只差 4.2 s——规则 vs 四头尚无稳定优势；四头相对 LLM continuation 两 seed 省 51.6/62.2 s；直接规则 seed 17 省 58.0 s、seed 11 因轨迹更慢 +2.8 s。每次玩家操作微型推理 137 次共享编码、488 个头输出（前者才是推理规模）；continuation 3 次调用/17 编码/68 头输出；接受任务来源未标注 0，10 次 model attempt 单列。reaction 微型工作流已接入（触发分类 + 意图候选 + judge 三头 + 合理性门；真实威胁回合 source=micro）；仍待专用反应头、多输入/多 seed、独立盲评与移动端。证据 `artifacts/goal/micro-workflow/continuation-ab-report.json`、`conclusion-20261125.md`、`continuation-training-report.json`；决策 D-033。

- tasks/subtasks 补充（2026-11-25）：条件分解 + 80 对 hand-authored pilot（relevance 18/20、satisfaction 9/15）已实现但**不作为默认**；`?taskVerifier=micro` 才启用，低置信回退 LLM。真实回合 tasks 阶段两次空 achieved，说明当前瓶颈是"不提出达成候选"而不是核验器。子任务新增父任务/现有任务同文拒绝。证据 `task-match-report.json`、`conclusion-20261125.md`；决策 D-034。

- 状态/叙事一致性补充（2026-11-25）：单动作转移根因在 updates projection/programScene，不在 action structure；已修并加单测，transfer-single9 状态与正文一致。叙事新增在场/物品归属守卫与一次事实草稿重写；任务核验改为条件覆盖，不再把「达到目的」直接当任务完成。仍待多回合台账泄漏、空移动与 program 回落。证据 `conclusion-20261125.md`；决策 D-035。

- task proposer 补充（2026-11-26）：tasks 批原先只读最后一个 plan point 的 `staged`，玩家点 results 在提交时被清空，护目镜任务永远没有输入（micro4 `facts=12` 全 NPC）。现按回合合并 `roundResults`；proposer 用条件台账跨回合累计，`satisfied` 前加 action/confirmation 程序下限，support 带条件标签给微型核验器；personality 把 `<f1>`/`<人物id>` 解析为事实人物或唯一触发人物，避免格式错误让整点失败。micro7：下限后 turn1 1/3、turn2 2/3、turn3 3/3 + verifier yes，kit 误判消失；personality 写 `<人物id>` 仍 turn_failed。占位符映射有单测；micro8 真机复跑在首回合前被宿主机内存低停止；micro9 完成三回合验收（COMPLETED、0 failures）：护目镜 1/3→2/3→3/3、verifier yes、快照 `task_lu_goggles=achieved`、回合后待办列表已移除该任务，personality 的 `<f1>` 复述行被独立拒绝。回合等待 123.5/107.7/121.4 s。带 goal 输入的 v2 条件模型留出 73.7%、真实行确认召回失败，不部署。证据 `evidence-task-accum-micro4/6/7.json`、`task-condition-goal-report.json`；决策 D-036。

- task 台账持久化补充（2026-11-26）：`LocalGameSnapshot.taskLedger` 随本地存档/同步保存；`taskLedgerOf`/`onRestoreTaskLedger` 在保存/恢复时导入导出，`seenFacts` 去重，物品条件按持有链失效/恢复，其他条件保持历史成立。`evidence-task-accum-refresh1.json`：第 2 回合后刷新 restored=true，第 3 回合仍以 3/3 完成护目镜任务并 `achieved`；第 3 回合 accepted 139.5 s，仍是 60 s 门槛问题。决策 D-037。

- 共享 runtime/批推理补充（2026-11-26）：ORT session 按 URL 共享、refcount，task proposer 条件行 padding 成批一次推理；`evidence-task-accum-batch1.json` proposer 17 行 344 ms（旧 18 行 721 ms，−52%），但 8/11 行小批 90/66 ms 比旧的 72/47 ms 慢，需按行数阈值；回合等待 84.2/90.0/124.9 s，任务仍 achieved，heap 149/137/128 MB。自动空闲驱逐与端口 release 未做；GGUF 仍是内存主项。决策 D-038。

## 8. 完整工作流性能优化（2026-11-26 起）

研发重心从逐端口建设转到一次玩家操作的协同效率。入口证据：micro9 / refresh1 / batch1 的完整回合仍 84–147 s；task proposer 已进入回归维护。

- **回合时间轴**：记录模型加载、提示处理、生成、等待、重试与阶段依赖，定位真正阻塞玩家操作的计算（脚本：`artifacts/goal/micro-workflow/turn_timeline.py`，待补）。
- **剩余 LLM 语义**：优先用微型模型替代高耗时 tasks/subtasks/personality/sanity；完成后续子任务提案与专用反应头。
- **批/并行与复用**：独立微型任务并行；同一状态+事实的重复核验复用已验证结果；避免重复编码。小批量阈值不再是重点。
- **GGUF 驻留/上下文/调度**：模型加载、驻留、上下文长度、空闲释放；共享会话缓存没有重复 session 可省，内存主项是 GGUF。
- **独立场景集**：物品交互、移动、对话、冲突、任务推进、环境变化六类，不再集中于护目镜。
- **桌面/移动完整回合**：持续测 30/60 s 阶段目标，保持状态与质量。

- 整回合性能补充（2026-11-26）：时间轴 9 回合均值 107.6 s；action 24.1 s（97 次语义、41 次重试 70.5 s）、position 14.9 s、tasks+subtasks 22.0 s、正文尾 26.5 s。动作任务目标照抄改为首次拒绝后模板回退：action1 等待 69.2/85.3/100.8 s，action LLM 8 次、attempt 6-7、action 28.9-42.3 s，任务仍 achieved。verifier 同 prompt 温度 0 memo（32 条、只存成功）；叙事 ctx 2048、停止保留 GGUF Blob（最多省 1.4 GiB）；独立场景集 8 回合六类。perf1 复测中；空闲 worker 释放、narration 双跑未做。决策 D-040。

- perf1 复测（2026-11-26）：等待 68.0/88.2/119.2 s，action 8 次 LLM/6-7 attempt，护目镜 `achieved`；verifier memo 0 命中；叙事 ctx 2048/不保留 Blob 是内存优化，不降时间。空闲 worker 释放已接入（隐藏且非 busy），真机未测。决策 D-040。

- 独立场景基准（2026-11-26）：8/8 完成；地点轨迹正确；状态 FAILED（turn5 program_text_not_model，turn7/8 prose_not_identical_to_record）；全部任务 pending，对话事实只到「只完成一部分」，route 地点条件未成立；等待 139.6/111.5/144.1/118.1/86.2/79.9/95.9/95.1 s。action 回退改用 judge 排序；position 三分类（确定移动/确定无移动/不确定）已提交，场景回归运行中。决策 D-041。
