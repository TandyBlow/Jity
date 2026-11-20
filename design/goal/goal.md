# Jity Goal v11：浏览器本地完整可玩

状态：active。日期：2026-11-20。基线：`agent@695e6bd4`。

本文是 goal 模式的唯一入口。与其他文档冲突时，以 [`decisions.md`](decisions.md) 为准。架构事实见 [`architecture.md`](architecture.md)，能力账本见 [`ledger.md`](ledger.md)，验收协议见 [`acceptance.md`](acceptance.md)。

## 1. 最终目标

交付一个可在普通笔记本浏览器中从预置静态世界文件开局并连续游玩的 Jity：

- 开局只读取、校验并封存 S₀；不动态生成世界。
- 玩家每次输入后，行动判断、目标识别、被迫反应、骰点准入、组冻结、共同结算、六阶段状态更新、继续推进和中文叙事全部在浏览器内完成。
- 浏览器 TypeScript 内核是运行期唯一的 apply/merge/commit/replay 权威。
- 服务器只存取不透明进度快照；禁用游戏计算端点与保存服务后仍可游玩与本地保存。
- 叙事按用户 2026-11-11 决定原样显示非空模型正文；运行期不检查、不裁改、不程序补写。事实与文风由提示、输入投影、候选、模型或训练在运行前负责。
- 验收以 R01–R16、至少 20 次真实页面输入、60 秒内出现可读流式正文、单点 300 秒内完成、离线、两设备分叉同步和用户本人在目标设备试玩签字为准。

Python v2 内核与 `/world` 规则页降为开发期差分预言机、回归夹具和对照臂，不作为浏览器本地产品的验收证据。

## 2. 非目标

- 不是服务器权威游戏：服务器不执行游戏计算，不保存世界事实，只存取进度快照。
- 不是动态开局生成：R15 已改写为静态载入、校验、封存。
- 不是固定命令或确定性规则模拟器：固定输出、模板和规则结算只能作对照臂或夹具，不能冒充模型能力。
- 不是多用户产品：当前只要求单用户两设备同步；多用户鉴权、GC、分页不在本版。
- 不是通用小说引擎：当前交付世界是 `dragon-raja-free-day`，跨世界泛化按 G1 的 held-out 决定。
- 不是研究原型：只有夹具、只有固定输出、只支持少数命令的路径都不算完成。

## 3. 冲突裁决摘要

详细理由与影响文件见 [`decisions.md`](decisions.md)。

| 决策 | 结论 |
|---|---|
| D-001 运行期权威 | 浏览器 TS 内核唯一 apply/merge/commit/replay；Python 降为差分预言机、金标向量与迁移参考。 |
| D-002 产品路径 | `/world-local` 唯一交付；`/world` 规则页与根 GM 控制台不投入新玩法，保留为冻结对照。 |
| D-003 静态 S0 | R15 改写为静态载入、校验、封存；取消动态世界生成。 |
| D-004 叙事边界 | 2026-11-11 原样输出决定：运行期只判空，不检查、不裁改、不程序补写。 |
| D-005 性能 | 500 ms 退出硬门槛；60 秒首段、300 秒单点是唯一硬门槛。 |
| D-006 验收规模 | 20 次页面输入为硬目标；旧草案参数已于 2026-11-20 全部删除。 |
| D-007 模型身份 | 语义 Qwen3-0.6B + 叙事 Qwen3-1.7B 为当前默认；替换需实测决策，不静默换权重。 |
| D-008 治理 | `agent` 单工作树；按 goal line 提交与打 tag；不 force push；不自动合并。 |
| D-009 文档与证据 | `design/` 跟踪；`docs/` 保持 gitignored 工作区；验收证据放 `artifacts/goal/`。 |
| D-010 设备与分发 | RTX 4060 Laptop 8 GB + Edge；GGUF 走外部下载脚本。 |
| D-011 世界供给 | 本版只做 `dragon-raja-free-day`；跨世界另开一批。 |
| D-012 独立验收与 rubric | 用户本人提供 10 次输入 + 读评；用户读感 + 四类跨回合检查。 |
| D-013 同步部署 | 单用户 Bearer + 本地/内网服务；不做多用户。 |

## 4. 硬目标与已删除草案

### 4.1 硬目标

- 至少 20 次真实 `/world-local` 页面输入，覆盖：自动链、连锁共同结算、暂停恢复、历史查看、删除叙事缓存后重生、合法失败、六阶段依赖、离线、服务器关闭、两设备分叉。
- 正常提交到可读流式正文 ≤60 秒；单点完成 ≤300 秒；超过 5 分钟不可接受。
- R01–R16 每项有代码路径、运行记录和真实页面证据；机制存在不等于能力完成。
- 禁用游戏计算端点与保存服务后仍可游玩与本地保存。
- 两设备从同一快照分叉、选择一支、另一支仍可恢复。
- 用户本人在目标设备完整试玩并签字；未签字不得宣布完成。

### 4.2 已删除的草案

以下参数已于 2026-11-20 全部删除，不再作为门槛：35 次叙事终验、90% 通过、10 份读评、9 份通过、32-of-35、3 个长输入、18 个新世界族、1 GB 包体上限、6 GiB 内存上限、120 秒冷启动、40 秒预叙事。需要时按实测重新提出，不复活旧草案。

## 5. 目标线 G1–G8

G 编号是标识，不是执行顺序。执行顺序见第 6 节。

### G1 目标与文档基线

范围：建立 `design/goal/{goal,architecture,decisions,ledger,acceptance}.md`、`design/README.md` 与 `design/parallel-handoff/README.md`；改写 `CLAUDE.md`、`AGENTS.md`；给旧文档加 supersede/update 横幅；建 R01–R16 账本 v1；打 `goal-mode-baseline-20261120` tag；向用户一次性提交参数与决策请求。除文档与 tag 外不改代码。

依赖：无。

验收：`design/goal/` 五件套、`design/README.md`、`design/parallel-handoff/README.md` 存在且互相链接；仓库中不再有未标 superseded 的「Python 唯一状态权威」「500 ms 硬门槛」「动态 R15」「A/B/C/D 当前分工」「2026-10-28 latest」；`ledger.md` 有 16 行，每行有状态、代码路径@commit、测试/证据、缺口、归属 G 线；参数表只列已确认硬目标，删除草案；tag 指向 `695e6bd4`；用户决策请求已记录，答案写入 `decisions.md`。

停止条件：文档与 tag 完成即关闭；不等待所有用户答案。

### G2 浏览器状态内核收口

范围：对 `frontend/src/lib/world-engine/local/transport.ts` 的 32 个 v2 操作逐项定案。当前 31 个已实现；决定 `checkpoint_restore_group_work`（`frozen_work_missing`）与 `get_context.recovery:null` 是补实现还是声明非产品语义。把 `local/state-invariants/` 的 point-continuity、任务层级、可见性检查接入 restore；补 linked/instant successor time 路径；用 Python 内核生成冻结差分向量，覆盖 `buildInitialState`、`applyPoint`、`pointEntityDeltas`、`replayWorld`、canonical digest；冻结骰点协议（阈值、程序持有、requestId 去重）；补多标签租约、刷新、重复提交、取消恢复测试。

依赖：G1。

验收：world-engine 下全部 Vitest 文件与两套 typecheck 全绿（当前盘点 89 个文件，G1 复核后固定）；新增差分测试对每个冻结向量断言 TS 与 Python 的 `stateDigest` 逐字节一致，覆盖空列表、0、嵌套位置、物品移动、任务层级、非 BMP 排序和拒绝路径；刷新或崩溃恢复不重掷骰、不重复行动、不重复应用 Δ；corrupt-restore 夹具被 invariants 拦下；`checkpoint_restore_group_work` 与 recovery 的产品语义写入 `decisions.md`；证据 `artifacts/goal/kernel-diff.json` 与 `kernel-ops.md`。

停止条件：差分向量全部通过；未定案的两个操作有明确产品语义，不留「以后再说」。

### G3 模型资产与时间包线

范围：取得或重建产品实际使用的 GGUF 与 tokenizer，覆盖语义 Qwen3-0.6B 与叙事 Qwen3-1.7B（或经实测替换的候选）；产 sha256/bytes/license/获取方式清单；裁决 Qwen3-0.6B 退役只适用于组件候选、不自动适用于产品语义槽；核对加载、warm-up、上下文、串行与叙事重叠、真实流式、取消、阶段计时与内存；目标设备固定为 RTX 4060 Laptop 8 GB + Edge（D-010），模型走外部下载脚本；真实 `/world-local` 页面缓存后跑 3 次冷启动与至少 10 个真实点，含自动链与一个重负载点；不达标时按实测比较单引擎多提示、更小叙事模型、量化或上下文调整，记录决策后复测；记录实际导出/量化链，未采用步骤记 `not_applicable`。

依赖：G1。

验收：`artifacts/goal/timing-baseline.json` 逐点记录 `inputAt`、`pointCommittedAt`、`narrationStartedAt`、`firstReadableAt`、`pointTextFinishedAt`、首 token、最长流式空档、阶段耗时与峰值内存；10 个正常点全部 60 秒内首段、300 秒内完成；冷启动独立报告；未达标则登记失败与下一候选决策，不宣称通过、不进入 G4/G8 的通过路径；模型清单的 bytes/sha256 与页面实际加载一致；三次调度或提示迭代仍不达标时只允许改模型或步骤组合，不得改门槛。

停止条件：时间包线有结论，通过或明确失败；失败不阻塞 G2，但阻塞 G4 的通过路径。

### G4 单机可玩页面接线

范围：把 `LocalGameSession.pause()/resume()`、`HistoryPanel` 选中/`onRegenerate`、transport 的 `narration_delete` 与重声明、状态/进度展示、错误与重试、刷新恢复、租约提示接到 `frontend/src/app/world-local/page.tsx`；把 `components/world-local` 的 controls/history/status/progress 组件真正用于页面；加 `crossOriginIsolated` 自检与持久告警（`next.config` 已有 `/world-local` COOP/COEP 头）；清理 `page.tsx:5,1517` 的 localStorage/0.5B 过期注释，写清 IndexedDB、Qwen3-1.7B、无 HTTP 游戏 API；修 4b1e 暴露的 `position_invalid`、narration 失败后 `turn_in_progress`、自动轮重复、空占位回合；确认禁用服务器时只依赖静态资源与本地模型；重生只读已提交的 S_{t-1}/Δ/S_t，不读旧正文。

依赖：G2、G3。

验收：新增 `frontend/e2e/world-local.spec.ts`：启动→3 次输入→暂停→刷新→继续→历史→删除叙事→重生成→状态不变；`window.__worldTurns/__worldArm` 可读出逐点计时与模型身份；网络记录只有静态资源与可选 `/local-progress`；服务器关闭运行通过；`npm run build`、两套 tsconfig、lint 全绿；页面无过期引擎/存储注释；10 轮运行无 `position_invalid`、`turn_in_progress`、`stalled:*` 停止。

停止条件：页面能单机连续游玩；未通过的交互有明确缺口记录。

### G5 非叙事语义验收

范围：为 action/skip、目标识别、被迫反应、共同结算、六阶段候选、继续判断建立冻结场景套件（12–20 例，覆盖 R06–R10 与合法失败、部分成功、未准入、已行动不重复、自动链与 handback）；每任务记录原始模型输出、结构错误、语义错误、重试、回退与实际耗时；禁止产品路径固定 handback、固定 targets 为空或预写结果；重试/失败预算与用户等待预算对齐；本版只做 `dragon-raja-free-day`，跨世界泛化另开一批（D-011）。

依赖：G2、G3。

验收：冻结场景套件在真实浏览器模型上跑完，逐例有输入、原始输出、内核校验、最终决定；技术自检 + 用户抽检确认无硬语义违规（D-012：目标错误、结果与骰点不符、六阶段顺序/覆盖面错误、非法新实体、越权 handback）；所有失败与重试保留；证据 `artifacts/goal/semantics/`；不得用固定输出用例凑通过。

停止条件：套件全部有结论；未通过项进入问题清单，不删场景。

### G6 叙事产品路径与质量

范围：在 2026-11-11 用户 raw-output 决定下冻结产品叙事路径：`LocalGameModel` 原样写入器或某个 `productDefault:true` 候选；运行期只判断空/全空白，不检查、不裁改、不润色、不程序补写，不把历史正文喂回后续模型；先按原样输出跑 G6，G6 后用 20+ 点实测决定是否加事实门（D-004）；质量通过提示、输入投影、候选、模型或训练解决；核对 02 beats、04 constrained、03 instruct、Qwen2.5-1.5B+LoRA、Qwen3-1.7B、Randeng-T5 的真实状态；`narration-quality/gate` 只留开发期；用 20+ 个已提交点做事实与文风读评；微调时先在 HPC 上做 5 条公开中文续写前后对照；记录模型/程序/检索/模板/编辑/重试贡献。

依赖：G3、G5。

验收：产品实际路径的正文逐字等于模型返回（页面可核对）；20+ 个真实点无已确认硬事实错误（人物对调、方向反转、数字/时长错误、无依据往事/新事件、视角泄露），四项读感达到冻结阈值；若无候选达标，登记失败、保留原门槛并继续模型/提示/训练，不降级为运行时检查或程序叙事；连续三轮无改善时只能做一次有证据的模型/数据变更并交用户决定；证据 `artifacts/goal/narration/`（样本、原始输出、评审记录、时间）。

停止条件：产品路径冻结并有 20+ 点证据；未达标项保留为未完成，不宣布叙事完成。

### G7 进度同步与跨设备

范围：页面启动时接 `sync.restore()`（本地存档优先，否则远端头）；冲突时展示分叉并接 `sync.choose('keep-remote'|'keep-local-fork')`；补离线队列、重连 `flush()`、CAS/父链/单调修订号核对；服务器只存不透明快照；`status().localRevision` 不再恒为 `null`；单用户 Bearer + 本地/内网服务，不做多用户、GC、分页（D-013）。

依赖：G4。

验收：两浏览器配置从同一快照出发、各自离线推进、并发上传→检测分叉→选择一支→另一支仍可恢复；重复上传幂等；重试不重复结算、不重掷骰；服务器关闭仍可本地推进与保存；请求日志只有进度操作；证据 `artifacts/goal/sync/`（两端快照、父链、修订号、选择记录）。

停止条件：两设备分叉场景通过；多用户需求明确排除在本版外。

### G8 交付验收与证据

范围：固定验收驱动：Playwright 或 Node 驱动真实 `/world-local`，扩展 `frontend/scripts/product-acceptance/accept-world-local.mjs` 与 `turns-10.json` / 新增 turns 文件，而不是重写；20 次真实页面输入（脚本夹具标注；用户本人提供的 10 次独立输入纳入）；本版只做 `dragon-raja-free-day`，3 组连续回合按需，不加 held-out 世界（D-011）；覆盖自动链、共同结算、暂停恢复、历史、删叙事重生、合法失败、六阶段依赖、离线、服务器关闭、两设备分叉；四类跨回合检查、输入依赖配对诊断、评测器正反例自检、泄漏/锚定检查（若启用独立参考叙事）、基座回归；产出 `artifacts/local-game-delivery/manifest.json` 与 `design/world-engine-reports/local-game-acceptance.md`；从 clone 加资产获取步骤复现。

依赖：G4、G5、G6、G7。

验收：goal v10 完成条件 1–5 逐条有证据；20 次输入全部记录输入、前后状态、Δ、原始叙事、计时；60/300 秒全过；离线与服务器关闭通过；R01–R16 账本全绿或明确未完成；manifest 列代码/数据/模型/权重哈希与复现命令；用户实际游玩并签字；未签前不得宣布完成。

停止条件：用户签字；或用户明确拒绝验收并给出问题清单。

## 6. 执行顺序

1. **G1**：写文档、改协作说明、加横幅、建账本、打 tag，向用户一次性发决策请求。
2. **G3**：按 RTX 4060 Laptop 8 GB + Edge、外部下载脚本先测模型资产与 60/300 时间包线。现有 10 轮记录未证明 60/300 通过（其中一条页面记录为 `readyMs=167917`、`turnMs=503844`），这是头号风险；不达标先改模型/调度，不带病进入页面和验收。
3. **G2**：用 Python 预言机生成冻结差分向量，收口 TS 内核的 32 个操作、restore、invariants 与骰点恢复。
4. **G4**：接页面交互与 e2e，修 `position_invalid`、`turn_in_progress`、自动轮重复、空占位回合。
5. **G5 与 G6 并行**：G5 跑非叙事冻结场景；G6 冻结 raw-output 叙事路径并做 20+ 点事实与文风读评。质量问题回流提示、输入、模型、训练，不加运行时检查。
6. **G7**：接两设备分叉、离线队列、CAS/父链。
7. **G8**：跑 20 次真实页面输入，产交付 manifest 与验收报告，用户试玩签字。

## 7. 连续执行规则

- 不按阶段报告停工；除用户决策点与真实外部阻断外，按 goal line 连续推进。
- 每个 goal line 都要有可复现证据；失败、重试、回退如实保留，不静默删场景或降门槛。
- 固定输出、模板、脚本和规则只作对照臂；不得把夹具通过写成模型能力完成。
- 每笔改动按明确路径提交；每个 goal line 打 tag；不 force push；不自动合并。
- 新决策未答时标 `pending-user`；只推进不依赖该答案的工作，不重复追问。
- 发现文档冲突时，先改 `decisions.md`，再同步受影响文档；不以日期新旧猜权威。

## 8. 完成判定与用户签字

G8 验收通过、R01–R16 账本关闭、20 次输入与计时证据齐全、用户本人在目标设备完整试玩并签字，才算 goal 完成。未签字不等于通过；技术自检和用户验收分别署名，不互相代填。

## 9. 相关文档

- [`architecture.md`](architecture.md)：运行期权威、产品路径、静态 S0、模型资产、七项职责、持久化与同步。
- [`decisions.md`](decisions.md)：D-001–D-013、理由、取代对象、已确认项。
- [`ledger.md`](ledger.md)：R01–R16 唯一状态账本与开放任务。
- [`acceptance.md`](acceptance.md)：20 输入协议、计时、叙事读评、离线、两设备、证据格式。
- [`goal-mode-short.md`](goal-mode-short.md)：≤4000 字短 goal，设置入口。
- [`goal-mode-prompt.md`](goal-mode-prompt.md)：goal 模式长文任务书。
- [`../README.md`](../README.md)：design 文档索引与 active/reference/historical/superseded 标签。
