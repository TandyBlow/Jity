# Jity Goal v11 决策日志

状态：active。日期：2026-11-20。

本文是冲突裁决的唯一权威。记录格式：

- 状态：`proposed`（提出，未生效）、`signed`（已确认）、`pending-user`（等待用户决定）。
- 每条写：日期、决定、理由、取代对象、影响文件。
- 新决定追加编号，不覆盖旧记录；被取代的旧决定标 `superseded` 并指向新编号。

## 冲突裁决

当前仓库存在五组直接冲突。本文逐条裁决；旧文档保留原文，但运行期含义以本文为准。

| 冲突 | 旧文档说法 | 本版裁决 |
|---|---|---|
| 运行期状态权威 | `CLAUDE.md`、`AGENTS.md`、2026-10-28 方向：Python 独占 apply/merge/preview/replay | D-001：浏览器 TS 内核唯一运行期权威；Python 降差分预言机 |
| 开局世界 | 原设计 R15：分批生成、修订、封存 | D-003：静态文件载入、校验、封存；不动态生成 |
| 产品页面 | `/world` 规则页、根 GM 控制台 | D-002：`/world-local` 唯一交付；其余冻结对照 |
| 性能门槛 | 500 ms 完整非叙事计算 | D-005：60 秒首段、300 秒单点；500 ms 仅局部诊断 |
| 工作方式 | A/B/C/D 分线与工作树、goal/local-* 分支 | D-008：`agent` 单工作树；按 goal line 提交与 tag |

另有一组边界冲突：

| 冲突 | 说法 | 本版裁决 |
|---|---|---|
| 叙事运行期检查 | GM-1 提案：事实门 + 一次重生成 | D-004：维持 2026-11-11 原样输出决定；运行期只判空，不检查、不裁改、不程序补写 |

## D-001 运行期状态权威

- 状态：`signed`（2026-11-20，用户在 Goal v11 选择中确认）。
- 决定：浏览器 TypeScript 内核唯一负责运行期 apply、merge、commit、replay；Python v2 内核只作开发期差分预言机、金标向量与迁移参考。
- 理由：最终产品要求所有游戏推理、调度、状态计算与校验在浏览器内完成，服务器只存取进度；浏览器本地垂直切片已在 `agent` 树中存在，收口比换架构更短。
- 取代：`CLAUDE.md` 的「State authority」段、`AGENTS.md` 的状态权威段、`design/world-engine-reports/full-design-implementation-direction.md` 的 Python 权威段、`design/browser-world-state-workflow.md` 的 Python 权威段。
- 影响文件：`design/goal/architecture.md`、`design/goal/ledger.md`、`frontend/src/lib/world-engine/local/transport.ts`、`backend/app/world_app.py`（仅作预言机）。

## D-002 产品路径

- 状态：`signed`（2026-11-20，用户在 Goal v11 选择中确认）。
- 决定：`/world-local` 是唯一交付页；`/world` 规则页、根 GM 控制台、Python CAMP/DeepSeek 栈不投入新玩法，保留为冻结对照或历史。
- 理由：goal v10 要求浏览器本地完整可玩；`/world` 的 20 输入或 Python 服务证据不能证明浏览器本地链路。
- 取代：`design/world-engine-reports/full-design-implementation-direction.md` 的 `/world` 产品化安排；`CLAUDE.md` 的 Active project 段。
- 影响文件：`frontend/src/app/world-local/page.tsx`、`design/goal/acceptance.md`、`design/README.md`。

## D-003 静态 S0

- 状态：`signed`（2026-11-10，goal v10 记录的用户澄清）。
- 决定：初始世界来自预置静态文件；开局只读取、校验实体/位置/任务/个性/理智引用并封存 S₀；不开发「设定→世界草稿」的动态生成或修订流程。R15 改写为静态载入、校验、封存。
- 理由：用户明确取消动态开局生成；静态世界足以支撑完整可玩与 20 输入验收。
- 取代：原 R15 动态生成；`design/final-browser-game-design.md` 中「生成完整初始世界状态」的运行期歧义。
- 影响文件：`frontend/src/lib/world-engine/local/world-loader.ts`、`local/static-world-registration.ts`、`data/worlds/dragon-raja-free-day.world.json`、`design/goal/ledger.md` 的 R15 行。

## D-004 叙事运行期边界

- 状态：`signed`（2026-11-11 原样输出决定；G1 请求用户复核，改动需新决策）。
- 决定：运行期原样显示非空模型正文；只判断空值与全空白；不检查、不裁句、不替换、不降级、不程序补写；不把历史正文、摘要或 priorText 喂回下一次调用；正文不参与结算。质量由提示、输入投影、候选、模型或训练在运行前负责。
- 理由：用户 2026-11-11 明确删除运行时审查；GM-1 的「事实门 + 一次重生成」违反该边界，不采用。删检查不等于质量提升；质量失败应回用户或改模型/数据，不偷偷加运行时门。
- 取代：`design/parallel-handoff/01-quality.md` 中旧运行时检查方案；`design/world-engine-reports/full-design-implementation-direction.md` 中「当前模板门继续使用」作为产品路径的部分（模板只留开发对照）。
- 影响文件：`frontend/src/lib/world-engine/local/game-model.ts`、`local/point-narration/`、`local/narration-generation/`、`design/goal/acceptance.md`。
- 复核提示：若用户允许「一次事实门重生成」，这是新决定；在用户明确改口前，按本决定执行。

## D-005 性能门槛

- 状态：`signed`（goal v10 的用户要求；2026-11-20 文档基线确认）。
- 决定：正常提交到可读流式正文 ≤60 秒；单点完成 ≤300 秒；超过 5 分钟不可接受；按阶段记录计时。500 ms 退出硬门槛，只作局部诊断参考。
- 理由：用户体验要求以完整链路计；旧 500 ms 指标不能替代首段可读与单点完成。
- 取代：`AGENTS.md` 的 500 ms 段、`CLAUDE.md` 的历史性能表述、旧 d19 指标。
- 影响文件：`design/goal/acceptance.md`、`frontend/src/app/world-local/page.tsx`、`artifacts/goal/timing-baseline.json`。

## D-006 验收规模

- 状态：`signed`（20 次输入为硬目标）；草案参数 `pending-user`。
- 决定：至少 20 次真实 `/world-local` 页面输入为硬目标；35 次叙事、90%、10 份读评、9 份通过、32-of-35、3 个长输入、18 个新世界族、1 GB、6 GiB、120 秒冷启动、40 秒预叙事均为待冻结草案，不自动成为门槛。
- 理由：旧草案参数未获用户最终确认；执行中自行缩小或放大都会破坏验收口径，必须 G1 一次性冻结或删除。
- 取代：旧 goal 文档中把草案写成验收前提的段落。
- 影响文件：`design/goal/acceptance.md`、`design/goal/goal.md` 第 4.2 节。

## D-007 模型身份与替换

- 状态：`proposed`（G3 实测后确认）。
- 决定：当前默认是语义 Qwen3-0.6B + 叙事 Qwen3-1.7B（`world-local/page.tsx` 的 `NARRATION_MODELS` 默认 `qwen3-1.7b`）；`qwen25-1.5b-narr` 为备选。Qwen3-0.6B 退役只适用于组件候选，不自动适用于产品语义槽。替换模型必须记录 sha256、bytes、license、获取方式与前后实测；不静默换权重。
- 理由：模型选择要以目标设备的质量、时间、内存和事实表现为依据；旧组件实验的退役结论不能直接套到产品槽。
- 取代：旧文档中「0.5B 叙事」「Qwen3-0.6B 一律退役」等笼统说法。
- 影响文件：`design/goal/architecture.md` 第 5 节、`artifacts/goal/timing-baseline.json`、`artifacts/local-game-delivery/manifest.json`。

## D-008 单树与治理

- 状态：`signed`（2026-11-20，工作树合并完成）。
- 决定：单一工作树 `D:/others/Jity`，所有开发在 `agent` 分支；原 A/B/C/D 与 `goal/local-*` 线已合并，不再新开工作树或按线分分支；按 goal line 提交与打 tag；不 force push；不自动合并；大文件、权重、缓存不入库。
- 理由：分线工作树已造成文档与基线漂移；单树加 goal line 提交/tag 足够保留状态。
- 取代：`design/world-engine-reports/worktree-coordination.md`、`design/browser-world-state-work-split.md`、`design/parallel-handoff/*` 中的分支/工作树指令。
- 影响文件：`AGENTS.md`、`design/README.md`、`design/parallel-handoff/README.md`。

## D-009 文档与证据路径

- 状态：`proposed`（随 G1 文档生效）。
- 决定：`design/` 跟踪、作为权威文档；`docs/` 保持 gitignored 工作区（任务记录、记忆快照、changelog）；验收证据放 `artifacts/goal/`；旧 `artifacts/` 保留历史证据但不自动升级为当前验收。
- 理由：当前证据散落在 gitignored 的 `.local` 与旧 artifacts，新克隆无法复现；必须把验收证据放进可跟踪路径并哈希固定。
- 取代：把 `.local` 当唯一证据来源的做法。
- 影响文件：`design/goal/acceptance.md`、`design/README.md`、`artifacts/goal/`。

## 待用户确认（pending-user）

以下问题不阻塞 G1 文档；执行中只推进不依赖答案的工作，不重复追问。

1. **D-004 复核**：2026-11-11 原样输出决定是否仍是绝对边界？若允许一次事实门重生成，G6 质量风险会下降，但需要新决定。
2. **D-006 参数**：35 次叙事、90%、10 份读评、9 份通过、32-of-35、3 个长输入、18 个新世界族、1 GB、6 GiB、120 秒冷启动、40 秒预叙事，一次性确认或删除？
3. **目标设备/浏览器**：固定为 RTX 4060 Laptop 8 GB + Chrome 或 Edge（二选一）？量化、包大小、内存上限有无硬约束？
4. **静态世界供给**：只交付 `dragon-raja-free-day` 一个开发世界，还是需要 held-out 世界族？若需要 18 个世界族，作者、成本与生成方式（脚本/人工/模型辅助后人工确认）由谁定？
5. **独立验收**：谁提供至少 10 次独立输入与 10 份读评？独立性如何界定？最终是否只以用户本人在目标设备完整试玩签字为准？
6. **两设备同步与部署**：单用户 Bearer 是否足够？服务器部署在哪、是否要求公网？是否需要多用户鉴权、GC 或分页？
7. **模型资产分发**：Qwen3-0.6B 与 Qwen3-1.7B 的 GGUF 许可证与分发方式是否允许随仓库发布，还是必须外部下载脚本？目标机器首次获取是否可联网？
8. **叙事风格 rubric**：`风格接近训练材料`如何冻结？是否需要与训练范文做盲评对照，还是用户个人读感即可？
