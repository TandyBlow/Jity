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
| R01 | 开局固定地点、物品、人物；运行中只更新登记实体；允许在既有大任务下新增小任务 | 实现中 | `local/world-loader.ts`、`local/static-world-registration.ts`、`local/state.ts:83` | `world-loader.test.ts`、`state.test.ts`；`data/worlds/README.md`；摘要 `3f65452d…` / `6262d5fc…` | 真实模型引用未知实体、非法新实体的正反例；未知实体不能靠叙事变成事实。G2/G5 |
| R02 | 地点嵌套、人物/物品容纳与相对位置；自然语言外貌、任务、个性、理智 | 实现中 | `local/state.ts`、`types.ts`、`world-loader.ts` | 静态世界 26 地点/14 人物/74 物品/73 任务；state 测试 | 嵌套移动、物品移动、地点外貌、相对位置的真实模型场景与页面展示。G2/G5/G6 |
| R03 | 初始外貌与个性不改写；变化保留历史；位置结构化 | 实现中 | `local/state.ts` 的 initial/current、`pointEntityDeltas` | state 测试；静态世界 README | 真模型合法变化、替代引用、原文保留、纯解除分支。G5 |
| R04 | 世界事实由 S₀＋Δ 构成；状态/摘要/检查点可重建 | 实现中 | `state.ts:83/906/952`、`canonical.ts`、`history.ts`、`persistence/` | `state.test.ts`、`history.test.ts`、`session-recovery.test.ts`；Python–TS 冻结差分（`kernel-diff.json`）；restore 接 `verifySessionSnapshot`（`session.ts`、corrupt-chain 测试） | 真实多轮页面回放证据；缓存与模型切换不能改变事实来源。G2 |
| R05 | 同点同实体合并为一份增量 | 实现中 | `state.ts` 的 `applyPoint` 合并、`transport.ts` 的 work 记录 | state、local-transport 测试 | 真实多组与连续阶段的最终投影一致。G2/G5 |
| R06 | 非关联新轮按理智排序；关联点沿用冻结顺序 | 实现中 | `controller.ts`、`schedule.ts`、`local/session.ts` | controller、schedule 测试 | 真实多人物行动与续轮、逐人判断、重排、关联顺序不变。G2/G5 |
| R07 | 骰点驱动被迫行动准入；先冻结全组再统一结算 | 实现中；真实模型未验 | `local/transport.ts` 的 group/work、`turn-execution/`、`controller.ts` | turn-execution 测试；旧脚本候选只作对照 | 模型分析目标、生成反应与共同结果；多级、未准入、环、已冻结成员；不以脚本文本代替。G5 |
| R08 | 已行动人物不重复行动；后续骰点仍影响攻击者结果 | 实现中 | `local/transport.ts` 的 `actedIds`/round、`turn-execution/` | transport、turn-execution、recovery 测试 | 真实模型组场景；恢复不重掷、不重采样。G2/G5 |
| R09 | 位置→外貌→任务→新增小任务→个性→理智；任务与个性全人物覆盖 | 实现中 | `local/state.ts` 的阶段 apply、`turn-execution/`、`game-model.ts` | state 测试；旧六阶段 preview 只作参考 | 真模型候选按依赖逐阶段；任务扫描全人物；任务达成后个性扫描全人物；允许合法不变化。G5 |
| R10 | 仅由大概率发生且与主角关联的后续行动触发自动推进 | 实现中 | `controller.ts`、`schedule.ts`、`local/session.ts` | controller 测试；旧固定 handback 只作对照；G3 计时运行 `artifacts/goal/timing-runs/points-10-rerun.json` | 真模型 continue/handback；G3 十点 0 次 continue：t1 结论请求 `request_malformed`，t2/t3 自动后续在 updates 停止（上下文/重复任务），归 G5；多轮不重复消费输入；预算暂停不伪装 handback。G5 |
| R11 | 每点只读叙事；可省略/暗示/隐藏秘密；不虚构已结算事实 | 实现中；raw-output 边界已定 | `local/point-narration/`、`narration-input/`、`narration-generation/`、`narration-candidates/` | `design/parallel-handoff/01-quality.md:279`（2026-11-11 原样输出）、`02-narration.md`；旧 B3/叙事实验只作参考 | 产品路径正文逐字等于模型返回；20+ 点无硬事实错误；视角/秘密/选择。G6 |
| R12 | 不另维护人物知识状态；模型从当前世界判断认知 | 实现中 | 无独立知识库；叙事只读已提交状态 | `architecture.md` 第 6 节；local 目录无 knowledge store | 确认提示/模型无隐藏知识真值库；可见性投影规则。G6 |
| R13 | 行动描述仅作本次分析；不建长期行动历史 | 实现中 | `local/transport.ts` 的 `actionTexts`、`persistence/` 快照、`history.ts` | transport、persistence 测试 | 原文只按工作态生命周期保存；调试归档与世界存档分开。G2/G4 |
| R14 | 工作职责不等于模型数或调用数 | 实现中 | `game-model.ts` 的 options、`controller.ts` 的 `ModelTask`、`schedule.ts` | `architecture.md` 第 6 节；模型变体清单；G3 逐任务调用记录 `artifacts/goal/timing-runs/points-10-rerun.json` | 按质量/成本选择单/多模型；记录每任务贡献。G3/G6 |
| R15 | 开局生成 | 已改写：静态载入/校验/封存，实现中 | `world-loader.ts`、`static-world-registration.ts`、`data/worlds/` | loader/registration 测试；摘要与计数；2026-11-10 用户澄清 | 静态世界供给与 held-out 决定；开局校验与页面。G1/G2/G4 |
| R16 | 小世界完整可玩；≥20 输入；自动链、共同结算、恢复、历史、删叙事重生 | 未实现 | `world-local/page.tsx`、`frontend/scripts/product-acceptance/accept-world-local.mjs`、`turns-10.json` | 10 轮驱动已存在；没有 20 输入真实模型通过记录 | 20 输入、离线、服务器关闭、两设备分叉、用户签字。G8 |

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
| G3 模型资产与时间包线 | 完成（2026-11-20） | 资产已取并逐字节校验；冷启动 24.7/18.9/19.3 s（isolated、RTX 4060、2×200）；12 个正常点首段 9.4–43.5 s、完成−提交 6.4–13.8 s，全部过 60/300，`timing-baseline.json` 状态 PASS；自动链 0 次归 G5；Change 已归档，tag `goal-g3-model-timing-20261120` |
| G4 单机可玩页面接线 | 完成（有缺口） | 隔离告警、pause/resume、HistoryPanel 只读选中、叙事删除/重生（head+history）、NarrationView/ProgressStatus、空占位清理、构建/e2e/block-api 通过；缺口：WorldStatusPanel 未接、`position_invalid` 与自动轮重复转 G5、无 10 轮全绿运行 |
| G5 非叙事语义验收 | 进行中 | 16 例冻结套件与分类器；run1/2/4/5 共 21 个真实回合、原始调用与重试保留；unknown_entity/context_overflow/stage_unit malformed 已修并复测；run5 s03 仍 330s，deadline cancel 已修（run6 验证）；0 次 continue |
| G6 叙事产品路径与质量 | 进行中 | 原样输出路径已冻结；12 点技术读评 7 个硬错误/4 个复述/1 干净；待 20+ 点与用户读评、G6 后事实门决定 |
| G7 进度同步与跨设备 | 未开始 | 两设备分叉、离线队列、CAS/父链；单用户 Bearer + 本地/内网 |
| G8 交付验收与证据 | 未开始 | 20 输入、manifest、用户签字 |

## 5. 开放任务

按 G 线列，作为唯一进度来源；不另建 progress 文档。

- **G1**：确认文档集与 tag；用户决策已记录（D-004/D-006/D-010–D-013）；当前无 `pending-user`。
- **G2**：完成。32 操作按 D-015 定案；取消恢复回归（`local-transport.test.ts`）与 corrupt-restore 拒绝通过；restore 已接 invariants；冻结差分夹具（LF sha `7d68a392…f977`）由 canonical/state/transport 测试消费；骰点协议见 `kernel-ops.md`；全量 1256 passed / 17 skipped，两套 typecheck 通过。failed head 的 cancel 已在 G4 放宽为 ready|failed。
- **G3**：完成。资产与冷启动完成；12 个正常点全部过 60/300（最差首段 43,526 ms、最差完成−提交 13,772 ms），`timing-baseline.json` PASS；t4/t11 结算失败与 t6 刷新保留为失败证据；自动链 0 次归 G5。
- **G4**：完成（有缺口）。隔离、pause/resume、历史只读、叙事删除/重生、NarrationView/ProgressStatus、空占位清理；构建、1257 passed、e2e（含重生）与 `--block-api` 通过。缺口：WorldStatusPanel 未接；`position_invalid`（t4 `lu receives conflicting positions`）与自动轮重复转 G5；尚无 10 轮无停止的整轮运行。
- **G5**：进行中。`turns-semantics-16` + 分类器；证据 `artifacts/goal/semantics/`（run1 9 点、run2 4 点、run4 5 点、run5 3 点）；修复：任务 characterId/basis 提示、行对象修复、fact id 归属、上下文 11,600、stage_unit 诊断、295s 引擎中止与 `turn_deadline` 放弃 pending 叙事；run6 验证 300s 上限；自动链仍 0 次，需真实 `continue` 或明确记为未达成。
- **G6**：进行中。原样输出路径保持；12 个 G3 样本技术读评：7 个硬事实/视角错误、4 个事实清单复述、1 个干净（`artifacts/goal/narration/read-technical-20261120.json`）；样本与投影提示已收（`samples.json`）；待 20+ 点与用户读评，G6 后按实测决定事实门。
- **G7**：接 `sync.restore()`/`choose()`；离线队列、重连 flush、CAS/父链/修订号；两设备分叉；单用户 Bearer + 本地/内网服务（D-013）；产 `artifacts/goal/sync/`。
- **G8**：扩 `accept-world-local.mjs` 与 turns 文件；20 输入（含用户本人 10 次独立输入）；不加 held-out 世界（D-011）；四类跨回合检查、输入依赖配对、评测器自检、泄漏/锚定、基座回归；产 manifest 与验收报告；用户签字。

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
