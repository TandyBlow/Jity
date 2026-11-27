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

- 场景回归（2026-11-26）：8 场景 COMPLETED/0 failures，等待 59.8/75.6/95.0/79.7/62.6/60.2/78.3/81.2 s（均值约 74 s，基线约 109 s），turn1 59.8 s；地点轨迹正确；任务仍全 pending；turn5 的 program_text_not_model 消失，turn5/7/8 仍有 prose_not_identical_to_record。决策 D-041 更新。

- 语义理解优先（2026-11-26）：场景指标 39/48 状态、11/14 任务、3 回合叙事问题、均值 74.1 s；COMPLETED 不等于质量通过。已修跨人物证据（proposer 判断所有 pending 任务）、路线 decision 条件、物品嵌套容器目的地与两字槽位；对话场景期望改为等待回答。下一步 results 结构化事实、信息/承诺/环境/物品/复合条件、四类微型模型与泛化数据。决策 D-043。

- 语义修复追加（2026-11-26）：跨人物任务证据、路线 decision、物品嵌套目的地、目标回应归因、否定确认；scenario-4 回归运行中。决策 D-043 更新。

- 语义回归（scenarios-5）：状态 42/48、任务 14/14、叙事问题 3 回合、均值 76.8 s；路线/跨人物修复生效，剩余物品容器与环境外观。micro transfer guard 已支持物品容器/开放来源，scenarios-6 运行中。决策 D-043 更新。

- 微型生成阶段（2026-11-26）：scenarios-5 唯一任务 1/1、false 0、missed 0、状态 42/48、叙事问题 3、均值 76.8 s；14/14 是 11 个 pending + 3 个路线检查，不代表多类任务。冻结场景集 sha256 8a52c6ae…；指标已分开统计唯一任务/false/missed。下一阶段结构化事件（意图/结果/信息/环境/承诺/决策/因果）+ 微型生成模型 + 五臂对比；scenarios-6b 运行中。决策 D-044。

- scenarios-6b（2026-11-26）：状态 46/48、唯一任务 1/1、false 0、missed 0、叙事问题 3、均值 76.3 s；嵌套物品通过，剩环境外貌 anyOf 与 prose 标记。决策 D-044。

- 微型生成试点（2026-11-26）：从零 5M/15M/30M Encoder-Decoder，条件与事件两任务，380 行、留出 15 任务/3 角色；测试字段召回 conditions 0.21–0.36、events 0.35–0.60，整串精确 0–0.22；独立 15M 事件 0.60 最好，5M 0.35、30M 0.45；多任务/共享编码器不优于独立；15M 事件仅 `result` 1.0，实体 `target/item/dest` 为 0；int8 6.6/19.8/44.7 MB，15M GPU p50 30–41 ms、CPU 66 ms（浏览器未测）。不接入生成臂，先做人工数据 + `result` 混合头 + 实体链接，再在冻结场景集上五臂比较。决策 D-045，报告 `design/goal/micro-generative-pilot.md`。

- 微型生成 v2/v3（2026-11-26）：去重 95 行训练 + 24 条手写测试（含 `mistport` 新世界）。自由 ID/`<pN>` 索引 2×2：BERT 自由字段 0.231、实体 0.259；`<pN>` 0.179/0.111；新世界实体全 0。候选评分指针：BERT 字段 0.244、实体 0.333、新世界实体 0.200；从头 0.205/0.296/0.000。result 分类器 0.583，生成 result 0.583/0.500，无生成优势；开放字段仍 0；数据是瓶颈。独立 5M/15M/30M ONNX 补测 int8 6.57/19.84/44.66 MB、CPU p50 54–106 ms，15M 条件 0.417/事件 0.50。后续采用候选指针 + 冻结 MiniRBT 处理实体、分类器处理 result，先扩手写训练数据再接产品五臂。决策 D-046，报告 `design/goal/micro-generative-v2.md`。

- ONNX 形状补测（2026-11-26）：legacy exporter 的动态轴是名义的；独立 int8 图只在 `src=55,tgt=18` 可跑，54/56/96×64 都失败。固定 96×64 导出可跑，5M int8 7.86 MB、单次 forward CPU p50 3.3 ms；不是逐 token，也不是浏览器。浏览器臂需固定 padding + encoder/decoder-step 分图或 dynamo；当前不宣称浏览器通过。决策 D-047，报告 `design/goal/micro-generative-pilot.md`。

- 手写训练种子（2026-11-26）：28 条手写（12 条件 + 12 事件 + 4 条 `frost`），与 24 条测试不重叠；v3 训练 123 行。BERT 候选指针 0.346 字段 / 0.481 实体 / 0.400 新世界实体 / 0.083 精确；95 行时为 0.244/0.333/0.200/0.042。从头候选 0.295/0.333/0.200。`info/env/promise/cause/neg` 仍 0；result 不稳定（BERT 0.5、从头 0.75、分类器 0.583）；p50 约 94 ms。数据有响应，继续扩手写训练；不接产品。决策 D-048。

- 数据规模与开放字段（2026-11-26）：固定 BERT 候选指针，123 基础 + 877 模板 = 1000；250/500/1000 热启动。字段 0.333/0.333/0.359、实体 0.370/0.333/0.481、mistport 实体全 0；28 条手写种子 0.346/0.481/0.400，模板扩容没有迁移到新世界。开放字段生成 info/env/promise/cause 全 0，存在性分类 F1 0.31–0.73；span 子串率 env/cause 0、info 0.17，需专用短序列提取。result 未加权 0.667 vs 加权 0.333，保留未加权。浏览器 5M 逐 token：encode 33.8 ms、9.61 ms/token、12 token p50 118.1 ms；v3 浏览器未测。决策 D-049，报告 `design/goal/micro-generative-scale.md`。

- 真实语义数据流程（2026-11-26）：20 条真实输入 + 8 条场景，DeepSeek pro 提 info/env，子串 + 状态外观 + 移动/转移 + 行动摘要规则核验，生成 dataset 与 spot-check；首批暴露移动/转移写成 env、NPC 行动写成 info，均被拒绝；sc01 no-answer info=false、sc05 观察保留。缓存 5/28，三任务与 held-out 状态补丁未训，未达“多模型共同改状态”。决策 D-050，报告 `design/goal/real-semantic-pipeline.md`。

- 语义数据四态（2026-11-26）：按用户核查修正为回合前/后快照差分、四态 present/absent/insufficient/conflict、8 场景整体 test-only/20 输入 train；未核验不再当负例。7 条缓存：sc01 info absent、env insufficient；sc02/sc04 insufficient；sc03/sc05/sc07 info present；sc06 env conflict（旧状态未提交检修盖外观）、info insufficient（误标路线决策）；sc08 未缓存。旧标签器已停，未训练。决策 D-051。

- 独立审计未通过 + v3/KV 浏览器（2026-11-26）：审计 pass=false：未核验仍写 present=false、7 条缓存全来自旧 prompt（含 checks 污染）、env absent 依赖空外观差分、`superseded` vs `supersedes`、意图被当支持、差分漏 characters/positions/tasks；不训练。浏览器 v3 候选指针 fixed full 171.1/178.3 ms、12.91 ms/token；KV full 68.5/94.5 ms、3.09 ms/token、prefill 23.1，2.5×/4.91×；输出一致，模型 14.8M，权重留本地。决策 D-052，报告 `design/goal/real-semantic-pipeline.md`。

- 六条件验收门（2026-11-26）：`validate_real_semantic.py` 拒绝未核验/冲突进 train、旧缓存、scenario 进 train、意图回显当支持、缓存缺 hash/版本/模型/证据、非 scenario test；流水线补三值 target/trainable、全状态差分、版本化缓存、settled 去命令回显。旧 7 条数据集 pass=false（27 failures），后台用 v2 prompt 重标 20+8；过门前不训练。D-053。

- 验收门五洞与反例单测（2026-11-26）：修 environment_keys（未动物品不算）、env absent（只认明确否定）、20+8 覆盖、模型标签元数据、raw/train 分离按字段过滤；`test_real_semantic_gate.py` 11 条全过；`train_micro_semantic.py` 先验 manifest 哈希再过门。当前缓存 7 旧 + 1 v2，训练覆盖缺失，仍不训练。D-054。

- 28 条标签完成但有效样本不足（2026-11-26）：验收门 pass=true、raw 28/train 20/test 8；字段计数 info 25 present/1 absent/2 insufficient，env 27 insufficient/1 conflict/0 present/0 absent；训练导出只有 20 条 info:pos，info 负例 0、env 字段 0。形式过门不等于可训练；不训练。修 conflict 取输入/叙事、info 新事实约束、状态差分、最小正负样本门、补采 env/info 负例。D-055。

- 环境状态补丁与语义场景（2026-11-26）：新增 `环境=实体:状态` 通道，micro results 动词表生成、updates 在 appearance 前写 add 记录、projection 纳入标签实体；真实回合 hatch_cover 记录「已被部分提开」，fact 与快照一致，驱动无报错。叙事草稿剥离结果台账（`（达到目的）`、行首冒号）与结构化标记。语义场景 32 回合（info-1/env-1 train、mix-1 test），labeler 从 updates prompt 取事实、用初始快照补首回合 diff，env 负例按明确失败/无环境动词判定，info 重复/已知按先前文本判定。决策 D-056。报告 `docs/tasks/semantic-env-channel-2026-11-26.md`。

- 语义数据首轮（2026-11-26）：env-1 + info-1 完成，验收门 pass=true，raw 52 / train 28 / test 8；字段计数 info 16 pos / 2 neg、env 3 pos / 19 neg，trainingReady=false。事件级 env 导出 151 条（3 正/148 负）。env 正例仍是瓶颈；新增 env-4/env-5 复合操作路线与 info-4 观察、info-5 重复/失败路线。决策 D-056/D-058。

- 冻结八场景（2026-11-26，scenarios-8）：状态 48/48、任务 14/14、唯一任务 1/1、false 0、missed 0、prose 问题 1 回合、均值 63.5 s、max 83.0 s。sc06 检修盖与 sc08 长桌环境外观均通过；6b 的 46/48 与 3 回合 prose 问题已改善。决策 D-061。

- 语义数据第二轮（2026-11-26）：env-2（前 8 回合有效）+ env-4 完成并标注；验收门 pass，train 64 行；字段计数 info 25 pos / 3 neg、env 12 pos / 22 neg（trainingReady=false）。失败词改为只看带 `环境=` 的事实，避免 instant 叙事的「没有」污染；env-5/info-4/info-5 采集中。决策 D-056/D-058/D-061。

- 第三轮数据（2026-11-26）：env-6 完成，记录检修图/工作台/医护箱/空床/保温毯/备用护目镜/领用簿/弹药箱/长椅/石花槽；标注后 info 35 pos/6 neg、env 29 pos/47 neg。门控 pass；控制室移动在真实回合未提交（结构 destination=null，单测同文本通过，待查）。env-7 与 info-6/7（LLM results 臂）采集中。D-061/D-062。

- env-7（2026-11-26）：12 回合记录 16 类物品/地点；保存时 Windows EPERM rename 使 status=FAILED，但 12 回合数据完整并可用。标注后 info 35 pos/7 neg、env **40 pos/48 neg**。env-8（复合）与 info-9（读取观察）待跑；env 事件导出接近 50 正例后可训存在性头。D-062。

- env 存在性头首训（2026-11-26）：turn 级 env 52 正/65 负过门；修掉两处标签泄漏（`环境差分` 行、事实里的 `环境=` 标记）并补 rowId，`--holdout sm6-` 才真正生效；MiniRBT-H256 30 轮 loss 0.7348→0.0003，留出 9 条 8 对（7/8 正例、1/1 负例），样本小，不宣称泛化。info 去噪后 23 正/63 负；程序内容抽取通道已加（D-067），info-9 实跑验证中。D-066/D-068。

- 信息通道（2026-11-26）：`信息=entity:外貌分句` 由程序在读取动作上抽取（话题词匹配、同房间、单物品），标签器作硬证据，叙事把标记写成「看清了…上的内容：…」。7 条 TS + 3 条 Python 测试通过；info-9 实跑验证待做。D-067。

- 信息硬证据与去假（2026-11-26）：info-9 实跑 12 回合无 problems，`信息=rules:医护白线禁射` 进入事实与正文；标签器改为只认结算事实、要求内容信号、拒绝动作复述，重标后 info 3 正/84 负（去假），env 52/77。叙事把识别带颜色写错，alignment 未拦截，记为产品缺陷；info-10（读取/人物/复合移动共 12 回合）补正例。D-067/D-069。

- 读取话题与控制室命名（2026-11-26）：`关于X的说明` 用 X 的重叠挑分句，位置词「图上」不再算话题；「控制室」从未登记，真实地点是「演习观察席」，路线文本已全改并补反例单测，info-13 重跑。info 17 正/89 负；info-14/15 与 info-16..19 待跑。D-070。

- 内容抽取头（2026-11-26）：`semantic-extraction.jsonl` 28 对（动作+外貌+分句+偏移，逐字校验）；候选指针头 20 轮 loss 0.68→0.12，组留出 top1 3/6（样本少，仅链路证据）。D-071。

- info 批次（2026-11-26）：info-11..19 完成并标注，turn 级 info **42 正/91 负**、env 53/135；事件级 info 43 正。抽取数据 40 对，候选头 25 轮 loss 0.67→0.20，留出 3/8。info-20..23 运行中。D-072。

- 双字段过门与三臂（2026-11-26）：info 57/92、env 53/153，门控 trainingReady 双 true；env 头留出 8/9、info 头留出 9/10（各 9-10 条，噪声大）；抽取头 55 对留出 6/11。规则臂 vs 标签：env 98.5%（P1.0/R0.943）、info 98.7%（P0.982/R0.982）；留出集规则 env 9/9、分类器 7/9；info 两者 9/10。生成式/混合/LLM 臂未测。D-073。

## D-074 冻结八场景无回归（2026-11-26）

- 状态：`signed`（2026-11-26）。
- `evidence-independent-scenarios-11.json`（micro 臂、seed=11）：状态 **48/48**、任务 14/14、达成 3/3、false 0、missed 0、prose 问题 0 回合、均值 64.7 s、最大 88.9 s，与 scenarios-8 的 63.5 s 同水平；今天的子任务守卫、信息通道与叙事标记转换没有破坏冻结场景。
- 无 micro 查询的同场景运行（scenarios-10）单回合 250 s、第 3 回合渲染进程崩溃（LLM 臂压力），说明五臂里的 LLM 臂需要单独的资源与超时治理，不能与产品臂共用同一浏览器条件。

- 影子接入（2026-11-26）：`?existenceShadow=1` 在结果端口记录 env/info 存在性分数，不改判定；4 回合真实页面 env 0.984/0.945 vs ~0.007，分类器臂有第一份页面证据。ONNX int8 10.55MB/字段，本地保留、manifest 记哈希。D-075。

- LLM 臂同输入（2026-11-26）：环境标签写成 `环境=<弹药箱>:…`（显示名，不可用），另一成功漏标，第三回合崩溃；270/258 s。规则/混合臂同回合 2/2 正确、70-88 s。五臂前需 id 化提示与资源治理。D-076。

- 显示名解析 + LLM 臂二次（2026-11-26）：`环境=` 支持 id/精确名/唯一短名解析，歧义名不猜；LLM 臂两回合 267/247 s、均无环境标签、状态无变化，规则/混合臂 2/2。D-077。

- 移动代理与断 API（2026-11-26）：4× CPU 节流 + gpu-lite 两回合 277/278 s、首段 33/28 s（满足首段≤60、单点≤300；不满足移动整回合 60 s，且不是真机）；`--block-api` 两回合 77/87 s 全部完成、无 /api 请求，驱动记录 blockApi=true。D-078。

- 刷新与两设备（2026-11-26）：刷新前后任务快照一致（5/5）、历史 2/2、整体恢复 true；progress-sync 协议实跑（CAS/幂等/分叉/选支）通过并存证，服务已停。D-079。

## 4. 2026-11-27 补充证据（按验收节次，不重写历史行）

- 第 2 节 R09/R16：`evidence-independent-scenarios-11.json`（micro 臂、seed=11）状态 48/48、任务 14/14、达成 3/3、false 0、missed 0、prose 问题 0 回合、均值 64.7 s、最大 88.9 s；子任务守卫（拒绝他人主语「路明非…」与复述结算事实）与信息标记转换没有破坏冻结场景。D-074。
- 第 5 节状态/回放：`refreshRestore` 增加刷新前后任务快照比较；两回合实跑 tasksStable=true（5/5）、历史 2/2、overallRestored=true、刷新 37.1 s。D-079。
- 第 6 节服务器关闭：`evidence-no-api-1-*.json` 在驱动拒绝 `/api/**` 时 2/2 完成、76.7/87.0 s、无持久化请求；驱动记录 `blockApi=true`。D-078。
- 第 7 节两设备：`evidence-two-device-sync-1.json` 协议级实跑（root、幂等重放、陈旧 CAS 拒绝、设备 B 分叉、两分支可读、显式选支）；不是两台真机页面，服务测试后停止。D-079。
- 第 3 节计时：移动代理（4× CPU 节流 + gpu-lite，非真机）两回合整回合 276.7/278.1 s、首段 33.1/27.7 s；首段≤60 s、单点≤300 s 满足，移动端整回合 60 s 不满足。D-078。
- 第 4 节叙事：info-9 实跑出现与人物外观矛盾的颜色（唐骁识别带写成黑色，状态是红色），alignment 未拦截，记为产品缺陷；标签器改为只认结算事实，叙事句不再作训练支持。D-069。
- 新能力（非 R 编号）：info/env 存在性头与内容抽取通道，turn 级 info 57 正/92 负、env 53 正/153 负，双字段 trainingReady；头留出 env 8/9、info 9/10；抽取候选头 55 对留出 top1 6/11；影子分类器臂真实页面 env 0.984/0.945 vs ~0.007。D-066/D-068/D-073/D-075。

- 离线（2026-11-26）：`--offline` 两回合 2/2、刷新恢复通过（任务稳定、历史 2/2）；但整回合 212/231 s vs 在线 77/87 s，离线路径掉速约 2.5 倍，待查网络等待。D-080。

- 离线预热（2026-11-26）：断网前建共享 ORT 会话 + 分词器；离线两回合 76/87 s（原 212/231 s）、生成 25/55 与在线一致，刷新恢复通过。代价约 90 MB 常驻。D-081。

- 决策臂与质量审计（2026-11-26）：`semanticDecide=1` 四回合实跑，NPC 读取各选到合理分句，主角四次全部弃权（存在性 0.41-0.5 / margin 不足）；抽取头外貌级留出 9/14、二元组基线 12/14（头不如词面基线）；支持头 env 15/16、info 4/10（info 不可用）。程序仍为默认决策。D-084。

- ONNX 修复与校准（2026-11-26）：导出只复制所选字段头，torch↔ONNX 9/9、10/10；固定事件 env 规则 9/9/头 8/9、info 规则 9/10/头 9/10；真 info 头校准 正例 0.86-0.94/负例≤0.69，门改第一人称、minExistence 0.75；无问项读取加守卫后 0 决定。D-085。

- 移动耗时构成（2026-11-26）：代理两回合的增量 98% 是单次调用变慢（prefill 57%、decode 38%），调用数没有增加；tasks/subtasks 提示 prefill 是最大单项，但全名册扫描不可缩。抽取审计：外貌级留出头 9/14 vs 二元组 12/14，覆盖缺口大。五臂固定事件集已冻结。D-086。

- 部署一致性门（2026-11-26）：torch↔ONNX 全头通过（存在性 env 206/206、info 149/149；提取 203/203、组 top1 55/55；支持 env 106/106、info 151/152 无硬翻转）；发现并修复提取头 ONNX 旧权重。D-088。

- 信息事件重构（2026-11-26）：独立标注 229 回合，102 有信息/127 无，148 条中 147 novel；multi 76/open 43/specified 29/inference 0；与规则标签一致仅 45%（规则多标 40、少标 85）。内核事件模型与知识账本路线已定，尚未实施。E06/D-089。
