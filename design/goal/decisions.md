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

- 状态：`signed`（2026-11-11 原样输出决定；2026-11-20 用户确认：先按原样输出跑 G6，G6 后用实测决定是否加事实门）。
- 决定：运行期原样显示非空模型正文；只判断空值与全空白；不检查、不裁句、不替换、不降级、不程序补写；不把历史正文、摘要或 priorText 喂回下一次调用；正文不参与结算。质量由提示、输入投影、候选、模型或训练在运行前负责。
- 理由：用户 2026-11-11 明确删除运行时审查；GM-1 的「事实门 + 一次重生成」违反该边界，不采用。删检查不等于质量提升；质量失败应回用户或改模型/数据，不偷偷加运行时门。
- 取代：`design/parallel-handoff/01-quality.md` 中旧运行时检查方案；`design/world-engine-reports/full-design-implementation-direction.md` 中「当前模板门继续使用」作为产品路径的部分（模板只留开发对照）。
- 影响文件：`frontend/src/lib/world-engine/local/game-model.ts`、`local/point-narration/`、`local/narration-generation/`、`design/goal/acceptance.md`。
- 后续：G6 用 20+ 点实测硬错误率；若错误率不可接受，再由用户决定是否加事实门（新决定，不改本决定的历史记录）。

## D-005 性能门槛

- 状态：`signed`（goal v10 的用户要求；2026-11-20 文档基线确认）。
- 决定：正常提交到可读流式正文 ≤60 秒；单点完成 ≤300 秒；超过 5 分钟不可接受；按阶段记录计时。500 ms 退出硬门槛，只作局部诊断参考。
- 理由：用户体验要求以完整链路计；旧 500 ms 指标不能替代首段可读与单点完成。
- 取代：`AGENTS.md` 的 500 ms 段、`CLAUDE.md` 的历史性能表述、旧 d19 指标。
- 影响文件：`design/goal/acceptance.md`、`frontend/src/app/world-local/page.tsx`、`artifacts/goal/timing-baseline.json`。

## D-006 验收规模

- 状态：`signed`（2026-11-20 用户确认：硬目标保留，草案参数全部删除）。
- 决定：至少 20 次真实 `/world-local` 页面输入为硬目标；35 次叙事、90%、10 份读评、9 份通过、32-of-35、3 个长输入、18 个新世界族、1 GB、6 GiB、120 秒冷启动、40 秒预叙事全部删除，不再作为门槛。需要时按实测重新提出，不复活旧草案。
- 理由：旧草案参数未获用户最终确认；2026-11-20 用户决定全部删除，避免把草案当成门槛。
- 取代：旧 goal 文档中把草案写成验收前提的段落。
- 影响文件：`design/goal/acceptance.md`、`design/goal/goal.md` 第 4.2 节。

## D-007 模型身份与替换

- 状态：`signed`（2026-11-20，G3 实测；资产哈希见 `artifacts/goal/model-manifest.json`）。
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

## D-010 目标设备与模型分发

- 状态：`signed`（2026-11-20）。
- 决定：G3/G6/G8 的目标设备固定为 RTX 4060 Laptop 8 GB + Edge（wllama）。Qwen3-0.6B 与 Qwen3-1.7B 的 GGUF 通过外部下载脚本获取；仓库只存 sha256/bytes/license/获取方式清单与脚本，不直接托管权重。目标机器首次获取允许联网。
- 理由：固定设备与浏览器便于复现 60/300；外部脚本避免大文件入库和许可证再分发风险。
- 取代：`architecture.md` 中「目标设备待确认」与「模型分发待确认」的段落。
- 影响文件：`design/goal/architecture.md` 第 5 节、`design/goal/acceptance.md` 第 2/10 节、`artifacts/goal/timing-baseline.json`、`artifacts/local-game-delivery/manifest.json`。

## D-011 静态世界供给

- 状态：`signed`（2026-11-20）。
- 决定：本版只交付 `dragon-raja-free-day` 一个静态世界；不新增 held-out 世界族，不冻结 18 个世界。跨世界泛化另开一批，不阻塞 20 输入与 R01–R16 交付。
- 理由：先收口单世界完整可玩；旧草案的 18 世界族成本高且未获确认。
- 取代：`goal.md` G5/G8 中「若冻结跨世界验收」的条件分支；`acceptance.md` 的跨世界可选描述。
- 影响文件：`design/goal/goal.md` G5/G8、`design/goal/acceptance.md`、`design/goal/ledger.md`。

## D-012 独立验收与叙事 rubric

- 状态：`signed`（2026-11-20）。
- 决定：用户本人提供 10 次独立输入与读评；独立性按「未看调试记录、候选和提示」界定。叙事验收用用户读感 + 四类跨回合检查（状态一致、无捏造、视角/秘密、文风/自然度）；四项阈值在 G6 冻结。不要求与训练范文盲评对照。
- 理由：用户是最终验收人；盲评对照成本高，且当前没有冻结对照集。
- 取代：`acceptance.md` 中「若冻结草案要求 10 次独立输入」的条件分支；旧草案的 10 份读评/9 份通过门槛已删除。
- 影响文件：`design/goal/acceptance.md` 第 4/9 节、`design/goal/goal.md` G6/G8。

## D-013 两设备同步部署

- 状态：`signed`（2026-11-20）。
- 决定：两设备同步使用单用户 Bearer + 本地/内网服务；服务器只存不透明进度快照；不做多用户鉴权、GC、分页或公网部署。服务器不可用时用本地 IndexedDB，仍可游玩与本地保存。
- 理由：goal v10 只要求两设备同步，不要求多用户；单用户 Bearer 足够本版，减少部署与安全问题。
- 取代：`architecture.md` 第 7 节与 `goal.md` G7 中「单用户 Bearer 是否足够」的待确认项。
- 影响文件：`design/goal/architecture.md` 第 7 节、`design/goal/acceptance.md` 第 7 节、`design/goal/goal.md` G7。

## D-014 G3 时间包线与恢复阻塞

- 状态：`signed`（2026-11-20，实测结论）。
- 决定：60/300 门槛不变。修复恢复缺口后实测 12 个正常点（`points-10-final4` 8 点 + `points-extra-2` 的 t12 + `points-extra-4` 的 e1–e3）：首段 9.4–43.5 s，完成−提交 6.4–13.8 s，全部通过，`timing-baseline.json` 状态 PASS；冷启动 24.7/18.9/19.3 s（`crossOriginIsolated=true`，RTX 4060，2×200）。t4/t11 结算失败、t6 刷新不计入；自动链 0 次（结论请求 `request_malformed` 或自动后续在 updates 停止），归 G5。G3 以时间包线通过关闭，不降门槛、不删输入。
- 理由：时间数据已排除「纯模型速度不达标」，阻塞在内核取消/恢复与页面交互；先修 G2 的取消恢复，再补测十点。
- 取代：无；细化为 D-005/D-007 的实测记录。
- 影响文件：`design/goal/ledger.md` G2/G3、`artifacts/goal/timing-baseline.json`、`artifacts/goal/timing-runs/`、`frontend/src/app/world-local/page.tsx`（`e75cd4a6`）、`frontend/src/lib/world-engine/local/session.ts`（待 G2）。

## D-015 两个 v2 操作的定案

- 状态：`signed`（2026-11-20，G2）。
- 决定：`checkpoint_restore_group_work` 声明为**非产品语义**——产品恢复只走本地 checkpoint 与 `__worldRestore`，不使用「恢复组工作」；保留 `frozen_work_missing` 拒绝，不补实现。`get_context.recovery` 保持 `null`——本地恢复不依赖服务端 recovery，`null` 表示没有服务器恢复信息，不是缺失。两者都有明确语义，不留「以后再说」。
- 理由：运行期无服务器游戏计算，补一条未使用的恢复路径只会增加状态面。
- 影响文件：`frontend/src/lib/world-engine/local/transport.ts`、`artifacts/goal/kernel-ops.md`、`design/goal/ledger.md` G2。

## D-016 G3 时间包线复核（回合完成门）

- 状态：`signed`（2026-11-20，证据复核）。
- 决定：时间门同时要求「回合完成」与「单点计时」。`summarize-timing.mjs` 增加 `turnCompletion`；含 `本轮停止`、`submit_refused`、`settlement_failed`、`AbortError` 或 295 秒时限的回合不计为通过。重算原 12 个计分点：60 秒首段（最差 43,526 ms）与单点正文（最差 13,772 ms）仍通过，但 7/12 回合在首点正文后停止（`t1/t3/t5/t9/t12/e1/e3`），`timing-baseline.json` 状态改为 `FAIL_OR_INCOMPLETE`。`acceptance.md` 的 60/300 定义不变；新增门对应 `goal.md` 的「超过 5 分钟不可接受」。
- 理由：旧门只统计已提交点的朗读完成时间；玩家轮的 instant 尾点未提交时没有记录，导致中途停止的回合被算作通过。G3 的 PASS 结论因此不成立。
- 取代：D-014 的「12 个正常点全部过 60/300、状态 PASS」表述；门槛 60/300 不变。
- 影响文件：`artifacts/goal/timing-baseline.json`、`frontend/scripts/product-acceptance/summarize-timing.mjs`、`design/goal/ledger.md` G3/G5；G3 重开，G5 修复整轮结算与 `request_malformed`。

## D-017 场外 actor 的结算策略

- 状态：`signed`（2026-11-21，用户选择「维持 judge」）。
- 背景：`action` 默认 `offscreenPolicy='judge'`，场外 actor 由模型逐个判断并各自形成结算组。14 人世界一次普通玩家轮产生 10–12 个组；run10 s01 在 295 s 被页面时限中止（9 个场外组），违反「超过 5 分钟不可接受」。
- 对照臂：`?offscreenPolicy=skip` 下同题 run11 201 s、run13 268.6 s 交还；run13 含 3 个 automatic 点与 `policy_stop:no_progress`，语义违规 0。场外 actor 仍经任务/个性六阶段覆盖，场景内 actor 仍逐个 judge。
- 用户决定：**维持 judge**，不改为 skip，也不加每轮场外限额。
- 后果：普通回合仍可能 297–330 秒，300 秒单点门槛与之冲突；G3/G8 的时间证据不能宣布通过。要同时保留 judge 又满足 300 秒，只能在实现上降低结算成本（如点级六阶段），或由用户另行改门槛；本版门槛未改。

## D-018 点级六阶段（位置/外貌按组，任务/个性/理智按点）

- 状态：`signed`（2026-11-21，用户选择「实现点级六阶段」）。
- 背景：D-017 维持 judge 后，普通回合 10–12 个结算组，每组都跑一次六阶段 updates；run10/run17 实测 295–330 秒，300 秒门槛必然失败。用户明确选择改实现，不改门槛。
- 决定：位置、外貌仍按组结算并 stage（组内先后的位置可见）；任务、新增小任务、个性、理智按点一次，结果经 `checkpoint_stage_time_scan` 作为点级单元 stage，commit 时与各组的场景 Δ 合并。六阶段顺序仍是「全体位置/外貌 → 任务 → 小任务 → 个性 → 理智」。
- 理由：任务/个性阶段扫全名册是主要成本；按点一次即可满足 R09 的按点覆盖，同时保留 judge 的逐人行动。
- 影响：`schedule.ts`/`controller.ts`/`turn-execution/port.ts`；T01–T08 场景夹具按新顺序重验或更新；G3/G5 重测时间与语义；协议操作不变（仍用 stage_unit 与 stage_time_scan）。

## D-019 验收变更：放弃用户签字与独立输入

- 状态：`signed`（2026-11-21，用户决定）。
- 决定：用户明确「放弃签字，改验收」。G8 改为技术证据验收；取消用户本人在目标设备签字、10 次独立输入与用户读评作为通过条件。20 次输入由脚本夹具与真实运行记录组成；60/300 计时、离线、服务器关闭、两设备分叉等硬性技术项不变。
- 理由：用户表示看不到全部信息、无法判断；真实模型证据由技术读评承担，不再要求用户署名。
- 影响：`goal.md` §4.1/§6/§8、`acceptance.md` §1/§3/§9、`ledger.md` R16/G8；验收报告须如实写明用户放弃签字。

## D-020 G5/G6 的下一步：HPC 微调对照

- 状态：`signed`（2026-11-22，用户选择「HPC 微调对照」）。
- 决定：G5/G6 的根因按小模型输出质量处理，走 G6 4.3：先在 HPC 用当前叙事模型跑 5 条公开中文续写的微调前基线，微调后再用同一组题复跑对照；对照有结论前不改交付模型（D-007 的 sha256/bytes/license/前后实测仍适用）。运行期事实门暂不加：用户表示尚未理解该决定的含义，待解释后另行决定。
- 理由：技术读评显示正文层硬错（识别带/红痕/物品转移、泛句事实、judgment/fact 互撞）是模型输出质量，不是状态机缺陷；换模型或微调必须先有同题对照。
- 影响：`goal-g6-narration` 的 4.3/4.2；`design/goal/ledger.md` G6；HPC runbook（`docs/hpc-runbook.md`，本地）。事实门维持 D-004 的现状。
- 补充（2026-11-22）：集群登录节点可达但 Slurm 控制器不可达，GPU 作业暂不能提交；微调前基线改在产品同款 wllama WebGPU 本地跑（同一 GGUF、同一提示与采样参数），微调仍在 HPC，微调后在同一本地栈复跑，保证前后同栈。
- 补充二（2026-11-22，1.7B LoRA 对照结果）：历史 199 行配方在 1.7B 上不解决产品格式事实保真，反而新增状态矛盾（镜片细痕）与跨人物属性转移（红发）；流水线已跑通，下一次须按当前叙事投影构造数据。默认保持 raw 1.7B。证据 `artifacts/goal/narration/read-17b-lora-vs-base-20261122.md`。
- 补充三（2026-11-22，page-v3 评估臂）：1.5B 页面格式微调（986,048,064 B，sha256 `a03bcfea…5632f`）速度最好（公版续写 1.8–6.1 s/次，产品回合 93.5/180.8 s），但正文有「十五分钟过去」循环复述、把法定失败写成成功（凭空把红色电台交给阿豹）、识别带与红发混用、断句损坏；检查器 s05 报 band 1 / echo 1。不换默认。
- 补充四（2026-11-22，4B 路线关闭）：Qwen3-4B-Instruct-2507 Q4_K_M 切 5 片后，同一页面累计取到第 5 片（约 1.9 GiB）时 `fetch` 失败，任意顺序最后一片都失败——上限是页面内聚合 Blob 容量（约 2 GB），非文件大小、非存储配额。产品同页还要载 0.6B 语义（0.38 GiB），4B 无法装入。现栈内 1.5B/1.7B 是实际上限。证据 `artifacts/goal/narration/model-size-limit-20261122.json`。
- 结论（2026-11-22）：现成模型与 4B 两条路线都已排除；G6 剩余路线只有按当前叙事投影构造数据的定向微调，或接受已记录的未通过判定。
- 补充五（2026-11-22，候选策略扫测）：base 1.7B 同题跑 `trained` 与 `constrained` 两个候选。`trained` 91.9/64.9 s，正文是静态氛围循环（「护目镜挂在胸前」四次、动作与结算脱节、自造渗血红痕）；`constrained` 107.6/94.2 s，整句复述，并把法定失败的「递电台给阿豹」直接写成已发生。两者都劣于 builtin（run27）。检查器仅报 echo 1，其类别不含「把被拒动作写成已发生」。现状：`auto` 因无 productDefault 候选回落到 builtin。
- 补充六（2026-11-22，解码温度扫测）：base 1.7B + builtin，s05/s06 同题。temperature 0.3（run32，97.1/75.9 s）：同一句「路明非低头检查护目镜…」复述 4 次，随后把提示里的状态原文照抄进正文，s06 凭空写成「阿豹接过电台，转身递给裁判」。temperature 0.7（run33，142.1/80.2 s）：循环更重（同一问句重复 3 次），自造时间 15:21，同一段里「递给阿豹，但未」与「阿豹接过电台」自相矛盾。检查器合计只报 echo 2。结论：解码参数不消除事实错误。
- 补充七（2026-11-22，few-shot 示例臂）：base 1.7B + builtin，提示里加一段异场示例（`?narrationFewShot=1`，run34，94.2/100.6 s）。s05 同句复述 4 次并原文照抄状态清单；s06 再次把「递电台给阿豹」写成已发生，还新增「诺诺扯开他的演习背心」。示例人名未泄漏，但事实与复述均未改善，检查器 echo 1。至此现有约束（wllama/GGUF、raw 原样输出、5/5 零硬错）内的已知手段全部测完且未通过。

## D-021 G6 事实门：只做开发期检查

- 状态：`signed`（2026-11-22，用户选择「只做开发期检查」）。
- 决定：运行期保持 D-004 原样输出，不加运行时事实门。新增开发期检查器 `frontend/scripts/product-acceptance/check-prose-facts.mjs`：逐回合把正文与叙事提示里的已结算事实对照，报告识别带、门状态、输入回声、占位句与元注记；只出 JSON 报告，不改产品路径、不进回合时间。
- 首轮结果（26 个真实回合：run22/23/24、run26/27、chunk1 复跑、chunk2、chunk3b、chunk5）：`band_claim` 2（都是 s02 给路明非加识别带）、`input_echo` 5（s05 复述「识别带和胸袋里的弹匣」等），其余类别 0。报告 `artifacts/goal/narration/prose-facts-check.json`。
- 理由：用户不愿承担运行时门的时长与失败率代价；开发期检查能驱动模型/提示迭代，且保持交付路径不变。
- 影响：G6 已归档未通过的状态不变；账本/验收报告记录本决定。

## D-022 G6 剩余路线：松一条约束，或收尾

- 状态：`pending-user`（2026-11-22）。
- 问题：现有约束（浏览器本地 wllama/GGUF、raw 原样输出、5/5 零硬错）内的已知手段已全部实测且未通过：现成模型（run27–29）、4B（容量上限）、候选策略（run30/31）、解码温度（run32/33）、few-shot（run34）、历史配方微调（run28）。用户问「微调不行是否就没有办法通过门槛」；答复：在约束内没有，要通过必须松一条约束（见下）。待用户选择：定向微调（不松约束，半天到一天），或下列退路之一。
- 影响：决定前 G6 与整体交付判定保持未通过；不新增 OpenSpec change。
- 记录（2026-11-22）：已按新人视角向用户完整介绍现行门槛（`acceptance.md` 第 1–9 节：技术门槛、G5 语义 hard 5/5、G6 叙事 4.2/4.3 硬错清单与未冻结的评分阈值）与当前状态：技术门槛全过，质量门槛未过。目的是确认用户在做「松哪条约束」的决定前理解判据。
- 退路（2026-11-22 预记，按成本排序）：
  1. 收尾：G6 维持未通过，产品按现状交付（当前默认已是 raw 1.7B，判定已记录在账本与 `0284c717`）；失败的微调按 `goal-g6-narration` 的方式归档、打 tag、不改默认（D-007）。
  2. 模型自修复第二遍（改设计）：同一 1.7B 先出草稿，再把「事实包 + 自己的草稿」交回模型要求只改矛盾。`prompt.ts` 已有 `draft/mode='repair'` 的修订提示，1–2 小时可做成评估臂；违反 `narration-generation/index.ts` 现行的「无校验、无修复」声明，每点多一次调用（约 +5–10 秒），需用户同意。
  3. 换浏览器运行时（改技术约束）：WebLLM 等自带缓存/分片的运行时不受 wllama 约 1.9 GiB Blob 上限约束，可载 4B/8B；工程 2–3 天，改「wllama/GGUF」这条已冻结约束，需用户同意。
     - 评估（2026-11-22）：换语言（如 Rust/WASM）不改变推理用时——算力在 llama.cpp 的 WASM/WebGPU 内核里，页面语言只是胶水；实测回合 72–82% 时间是串行模型调用，单次语义调用约 2/3 是 prefill（300–470 tok/s），与宿主语言无关。Rust + wgpu 引擎（candle/ratchet 等）与 WebLLM 是同一个杠杆（换运行时与权重加载方式），不是换语言的功劳；wasm32 的 4 GiB 地址空间限制对 Rust 同样成立。速度门槛已全过（20/20 回合 <300 s），当前卡点是质量而非速度。
  4. 再一轮数据/配方微调：仅当第一轮有改进但未达标时值得。
  5. 改硬门槛：把 G6 的 5/5 改成可量化的开发期门槛。属于「改目标/硬门槛」，必须用户拍板，Agent 不自改。

- 根因补充（2026-11-22，`goal-legal-check`）：s06 合法失败的根因在结算层——`results` 模型把未知实体阿豹的交接判成 `achieved`/`completed`（run37/run39），叙事照抄。质量路线必须覆盖 G5 语义；开发期新增场景门 `legal_failure_not_enforced`（run39 命中）。证据 `artifacts/goal/narration/read-legal-check-20261122.md`。
- 频率测量（2026-11-22，`goal-legal-rate`）：s06 复跑 5 次，结算层误判 4/5；剩下 1 次结算判 blocked 但叙事仍把被拒动作写成已发生——5/5 在某一层失败。质量路线必须同时覆盖 G5 结算与 G6 叙事；开发期还缺一条「被拒动作写成已发生」的正文门。证据 `artifacts/goal/narration/legal-failure-rate-20261122.md`。
- 开发期正文门（2026-11-22，`goal-refused-gate`）：检查器新增 `unknown_entity_claim`；run37/run40 的 3 个 s06 全部命中（含结算判 blocked 的 run40-e），s05 无误报。质量路线现在有结算门与正文门两条自动证据。证据 `artifacts/goal/narration/read-refused-gate-20261122.md`。
- 质量基线（2026-11-22，`goal-quality-baseline`）：17 run / 42 回合，26 个回合至少命中一条开发门（echo 11、band 9、unknown_entity 11、meta 2）；s06 的 11 个合法失败回合全部命中 unknown_entity_claim。任何质量路线都用同一套门对照。证据 `artifacts/goal/narration/quality-baseline-20261122.md`。
- 默认路径基线（2026-11-22，同批检查）：G8 的 20 输入里 5/20 个回合命中开发门（echo 3、band 2、unknown_entity 1、meta 1），s06 合法失败命中 unknown_entity_claim。证据 `artifacts/goal/narration/prose-facts-g8-default-20261122.json`。
- 未知实体规则评估臂（2026-11-22，`goal-unknown-rule`）：results 提示显式写明未登记实体必须 not_achieved/blocked，3 次 s05/s06 中 1 次干净、2 次仍判成功（基线 1/5 干净）。单行提示不是修复；D-022 候选不变。证据 `artifacts/goal/narration/read-unknown-rule-20261122.md`。
- 自修复原型（2026-11-22，`goal-repair-sample`）：把 s06 失败草稿连同原提示交回同一 1.7B、要求只改矛盾处；6/6 次输出保留被阻止的动作（2.5–7.9 s/次）。一遍自修复无效，D-022 剩余候选收缩为定向微调、换运行时、改门槛、收尾。证据 `artifacts/goal/narration/read-repair-sample-20261122.md`。
- 新候选（2026-11-22，用户追问「没有其他手段？」）：程序级合法性校验——结算事实里出现未登记实体/物品时判该点失败并带反馈重试，而不是只靠提示或换模型。它直接落实 R01「未知实体不能靠叙事变成事实」，不需要更大模型或微调；代价是给结算加运行期检查与重试（设计变更，待批准）。另可测检索式 few-shot（按行动类型取正确结算样例）。
- 程序级校验首轮（2026-11-22，`goal-strict-entities`，run43）：`strictKnownEntities` 默认开启后 s06 结算门 1/3 命中（基线 4/5）；未命中样本写成不点名的自造完成（「电台被塞进腰间」）。点名未登记实体被压住，但零硬错未达成。证据 `artifacts/goal/narration/read-strict-entities-20261122.md`。
- WebLLM 原型进度（2026-11-22，`goal-webllm-adapter`）：适配器完成、构建通过；4B 冒烟报浏览器缓存配额，1.7B 冒烟页面 900 秒未 ready；隔离探针显示 WebLLM 能初始化并拉取权重，但停在 HF 的 615 MB / 66%，27+ 分钟无进展。阻塞在模型分发（HF CDN 停滞），不是适配器代码；下一步做断点续传的本地下载与本地托管。证据 `artifacts/goal/narration/read-webllm-stall-20261122.md`。
- WebLLM 链路打通（2026-11-22，run57）：1.7B 本地权重 + OPFS 缓存 5 秒加载完成（30/30、924 MB、WebGPU）；单回合 22.0 s（results 3.0 / position 5.0 / appearance 1.9 / narration 2.0–2.3），远快于 wllama 的 65–180 s。缺陷：正文夹空 `<think>` 标记、部分 JSON 解码 fallback（1.7B 能力）。4B 下载中，下一步量质量门。证据 `artifacts/goal/narration/read-webllm-17b-20261122.md`。
- 4B 加载状态（2026-11-22，run59–61）：4B 已本地化；OPFS 后端在 768 MB 报 QuotaExceeded（页面实测配额 10 GB、usage 0，属后端问题）；Cache API 后端的验证被宿主内存回收停止，按规则未自行重启。1.7B 已证明运行时可用（22 s/回合），4B 还差最后一步加载验证。
- 4B 打通（2026-11-22，run63）：独立探针与验收驱动（`--profile ../.local/edge-profile`）都能加载 4B（2.16 GB、WebGPU、缓存后 6 秒）；产品单回合在 results codec 报 `fact text must be non-empty`（28.6 s），属 4B 输出格式问题。s05/s06 数据在 run64。
- 4B 稳定性（2026-11-22，run69–71）：run69 卡死 30 分钟后停止并加了 150 s 生成上限；run70 撞旧 profile 的残留写入租约；run71 被宿主内存回收杀掉（第二次），未自行重启。4B 可加载（run63），但连续产品回合在本机会触发内存保护；完整 s05/s06 数据待内存宽裕窗口。
- 1.7B 修复后复跑（2026-11-22，run72）：固定 prompts 下 s05 仍 `model output is not JSON`，s06 由 `strictKnownEntities` 拦下（unknown entity 阿豹）。1.7B 的速度不足以抵消格式能力；质量路线要 4B，4B 受宿主内存限制。
- 3B 运行时结论（2026-11-23，run74/75）：约束解码 + think 剥离后，s05 45.0 s 干净完成，但正文复述事实（检查器 echo 1 + band 1）；s06 由 strictKnownEntities 拦下。换运行时在 3B 上解决速度与 JSON，未解决质量；4B 是唯一未测的质量希望，受宿主内存限制。
- 3B 候选扫测（2026-11-23，run76/77）：builtin 复述、constrained 原样回声、trained 表面通顺但凭空添加环境与动作细节（撞「无捏造」）。3B + WebLLM 的三种候选都不合格；质量路线剩 4B（内存受限）与定向微调。
- 移动模拟档 WebLLM（2026-11-23，run78）：3B + 核显 + 4× CPU，s05 整轮 264.9 s、s06 125.4 s 后被结算门拦下。对比 wllama 的 268–298 s 无质变，瓶颈仍是 iGPU prefill；移动 60 秒在当前硬件上仍不可达。
- 4B 公平复跑（2026-11-23，run80）：修复后的栈下 s05 33.8 s 但 narration 失败并带出 disposed 错误，s06 2.6 s 失败；4B 在本机产品回合里不稳定。3B 稳定但质量不合格。质量路线只剩「稳定运行时 + 定向微调」或收尾。
- 4B + 结算门修正（2026-11-23，run81/82）：模型对 s06 写了「阿豹不在场，未能转交」，被过严的 guard 误杀；放宽为只拒绝 completed 且未否认的事实后，s05 93.6 s、s06 45.0 s 结算均通过。剩叙事层：s05 复述、s06 把被拒动作写成已发生（检查器 unknown_entity_claim）。质量路线指向叙事数据微调。
- 4B + trained 候选（2026-11-23，run83）：s05 111.8 s 复述、s06 138.8 s 且结算再现 completed（legal_failure_not_enforced）。4B 上现成候选不解决叙事；质量路线只剩叙事数据微调或收尾。
- 4B + trained + prose-facts（2026-11-23，run84）：s05 92.9 s、s06 52.2 s，驱动与检查器均 0 命中；但正文是状态复述，未叙述行动；s06 未再把交接写成已发生。运行时与候选组合穷尽，叙事质量只剩定向微调或收尾。
- 定向微调准备（2026-11-23）：已抽取 111 条真实叙事提示（84 唯一）到 `.local/narr-train/prompts.jsonl`；集群 SSH 当前不可达（WinError 10060），教师生成与 MLC 转换等集群窗口。
- 凭空细节门（2026-11-23，`goal-invented-check`）：检查器新增 `invented_detail`（窄词表 + 提示比对）；run77 的 trained 候选命中 6 条（夕阳/风声/汗/泥土/焦糊/气味），run75 不误报。该门用于定向微调的数据过滤。
- 定向微调（2026-11-23，`goal-narr-finetune`）：集群不可达，改在本机 RTX 4060 训练 Qwen3-1.7B LoRA。数据 84 条真实提示（排除 6/38/72，补 3 条合成 blocked），教师目标手写并过检查器 0/84；三轮（v1 84 行、v2 108 行、v3 148 行过采样）。结果：v3 在 s05/s06 探针（run89，36.7/28.0 s）驱动与检查器 0、4.2 硬错 0；但五回合集（run90）出现未结算事件（「他看懂了规则牌」「伸手去摸规则」「他把规则牌看了一遍」）与重复句，4.3.4 不合格；temperature 0.2（run91）同失败模式。十输入集（run92）：有正文的 9 个回合里 6 个硬错（主角持诺诺的短枪、把「路明非中立」写成「她」、位置仍在服务巷却写到二层平台、把诺诺的规则阅读记到主角等），检查器 0 命中——现有开发门不足以替代人工读评；9/9 回合有重复句。基座同提示（run88）仍复述并写完成，v1–v3 明显优于基座但未达零硬错。默认不变（D-007）；评估臂 `qwen3-1.7b-narr-lora` 指向 v3（sha256 `f4c0e366…`）。证据 `artifacts/goal/narration/read-17b-lora-v2-20261123.md`、run85–90。
- 开发期门扩展（2026-11-23，`goal-prose-attribution`）：`check-prose-facts.mjs` 新增 `place_claim`（主角被写到与已提交状态不符的登记地点）与 `item_owner_claim`（主角使用他人归属物品）；教师数据 84 条与 run89 干净回合 0 误报，run92 命中 t5/t8。张冠李戴与「规则阅读转移」仍无自动门，人工读评必需。
- 投影瘦身评估（2026-11-23，`goal-narr-projection`，run96）：去掉静态外观/物品/他人外貌后，t3/t9 仍把诺诺的规则阅读记到主角，t8 位置与状态相反，t3 出现「没有林亦舟」与「脚踝的伤势还在」的自相矛盾；交还 45.9–91.4 s，4/10 超 60 s（完整投影 30.3–53.4 s）；细节丢失确认。不采用，默认投影不变。非换模型路线只剩「按人物分调用」（调用翻倍，当前延迟下不可行）。
- DPO 对照（2026-11-23，`goal-narr-dpo`，run97）：在 v3 上用 84 对自采样反例做 DPO（beta 0.1、2 epochs）。十输入集 10/10 ≤60 s，但正文滑向否定复读，出现主角持枪（t2）、写诺诺引语又说巷里没有诺诺（t9）、凭空脚步声/计时器（t7/t10）、位置矛盾（t8）；检查器 5 命中。v4 不采用，评估臂恢复 v3（`f4c0e366…`）。同日归因变体工作流接受 9 条，其中 2 条把识别带/相机给了错误的人；要用数据扩充路线，必须用世界登记表硬校验并达到数百条规模。
- 归因数据 v5（2026-11-23，`goal-narr-attribution-data`，run98）：84 条 + 23 条世界校验的归因变体（只换动作/观察类主语，跳过移动与他人归属物品）。十输入：10/10 ≤60 s，正文 78–137 字，重复句消失；硬错从 v3 的 6/9 降到 3/9（t3/t9 把诺诺的规则阅读记到主角、t8 未结算移动写成完成），t5 轻判；检查器 3 命中中 2 条是既有误报。v5 为当前评估臂（`b4b143c7…`）；默认不变。剩余两个形状：规则阅读归因、未结算移动。
- 数据迭代平台（2026-11-23）：v5 的 23 条变体已覆盖 24 个「规则阅读」对照里的 21 个 base；再训 v7 只能重复这些对照，而 v6 已证明重复会倒退（结算中止、超 300 s、重复句回归）。快速数据迭代到 v5 为止（3/9）；要到零只剩「手工整理数百条世界校验样本」或「接受 3/9」。v7 不启动。
- v6 加权复训（2026-11-23，run99）：把问话+诺诺看规则、未结算移动等样本重复到 181 行，结果倒退——t3/t4 结算中止、t5 超 300 s、t1/t2/t7/t9 重复句回归、t8/t10 位置矛盾，规则阅读归因仍在。重复样本不能修形状；评估臂恢复 v5（`b4b143c7…`），v5 仍最好（硬错 3/9、无重复句、10/10 ≤60 s）。
- v5 五回合验收（2026-11-23，run100）：s02 忠实、s03 规则阅读归因、s04 时间数字、s05 凭空「侧身挡住视线」、s06 结算中止；未达 5/5。快速数据迭代平台结论不变。
- v7 手工大样本（2026-11-23，`goal-narr-v7-curated`，run101/102）：199 条世界校验变体 → 工作流 107 接受 → 过滤后 45 条新样本（129 行 SFT）。五回合：s02 规则阅读归因、s04 时间数字、s05 重复、s06 结算中止；十输入：10/10 ≤60 s，但 t3 归因、t5 主角持枪、t8 位置矛盾、t9 视角泄露、t10 位置不符，硬错 ≥4/9。v7 不优于 v5；评估臂恢复 v5。数据路线在 129 行平台；继续需多轮工作流（每轮约 45 条可用、约一小时），且不保证 1.7B 到零。
- 4B 十输入部分（2026-11-23，run93）：WebLLM 4B 同臂跑到 t4 被宿主内存回收；t1/t2/t4 复述状态清单，t3 把未结算的林亦舟与脚踝伤写进正文（硬错），t4 `accepted_over_60s`；检查器 0 命中。4B 基座不改变未通过判定。
- 结算门收紧（2026-11-23，同 change）：`assertKnownEntities` 把缺省 outcome 也视为断言，仅放行显式 blocked 或带否定线索的 fact；`settlement.test.ts` 99 passed；驱动 `legal_failure` 门改读叙事提示的结算段（raw 尝试含被拒/被丢 fact，不再作判据）。后果：0.6B 结算模型无法稳定产出 blocked fact，s06 约 2/5 中止、3/5 宽松轮丢 fact；4B WebLLM 能产出（run82），但本机回合受宿主内存限制。

## D-023 设备范围：笔记本、4B 与移动端的取舍

- 状态：`signed`（2026-11-24 用户裁决：维持 60 秒同口径；移动档实测不通过）。
- 背景：4B 浏览器本地方案（D-022 退路 3）把设备下限抬到约 4–6 GB 可用显存/内存的笔记本；移动端即使在今天也承受不了当前 1.5 GB 权重的 1.7B 栈（手机 WebGPU 覆盖碎片化、标签页内存上限、散热与 prefill 速度都会击穿 60/300 秒门槛）。验收协议（D-010）指定的设备是 RTX 4060 Laptop 8 GB + Edge，移动端从未进入验收范围。
- 取舍：质量门槛（5/5 零硬错）在小模型上过不了；要过就得上更大模型，设备下限随之上抬。今天无法同时满足「零硬错」与「手机可玩」。
- 用户裁决（2026-11-22）：「到不了就想办法，什么叫做题目做不对就把题目改了？」——移动档不改门槛，必须想办法达到 60 秒；不采用「另立移动门槛」的选项。待办变成工程路线：减少每回合调用数/缩短提示/换运行时，并需真机验证。
- 调用成本（2026-11-22，run35/36 分析）：移动档三大成本是 position（59–78 s）、results（31–62 s）、continuation（27–32 s），合计 120–170 s；六阶段里 appearance 另占 14–21 s。合并 position+appearance、程序 handback 跳过 continuation 后，估算地板仍在 70–90 s——60 秒在当前 0.6B + 核显栈里很可能到不了，再往下只能换更快的运行时/硬件。证据 `artifacts/goal/narration/read-mobile-call-costs-20261122.md`。下一步原型 `mobileSchedule`（合并更新+程序交还）待批准。
- Prefill 占比（2026-11-22，同批证据）：移动档语义调用的 prefill 普遍高于解码（1738 tokens：prefill 12.6 s vs 解码 1.9 s）。省时要省输入与调用数；合并 position+appearance 估净省 10–20 s。移动 60 s 与运行时强耦合：wllama + 0.6B + 核显到不了，需更快的运行时或硬件。
- 移动 WebLLM 复测（2026-11-23，run95）：同一 0.6B 移动配置换 WebLLM 运行时，s05 225.1 s、s06 170.1 s，均超 60 s；换运行时没有改变 iGPU 预填瓶颈。两种运行时（wllama 210.5 s / WebLLM 225.1 s）都在 170–225 s，60 秒需更小模型/场景或更快硬件。证据 `artifacts/goal/narration/run95-mobile-webllm-06b.json`。

- 用户裁决（2026-11-24）：移动档维持与笔记本同一口径的 60 秒硬门，不另立门槛。按手机模拟条件（CPU 限速、核显、单模型预算）实测 189–229 秒（run94/103/104）与 WebLLM 170–225 秒（run95），移动档判定**不通过**。
- 交付终态：笔记本档按 v13 默认通过（D-028）；移动档按 60 秒同口径不通过。此为本轮交付的最终裁决。

- 内核/调度探针（2026-11-24，`goal-mobile-kernel-schedule`）：升级 wllama 4.0.0（libllama b12637）对比 3.8.1（b11364），核显 WebGPU prefill 23.10 s vs 18.55 s（0.80×），Intel gen-12lp 无 Flash Attention——内核升级未达 ≥2×；position+appearance 合并（f55b43e1）与程序交还（forceHandback）已是当前产品，移动 20 输入实测 137.1–272.1 s（run133–137，20/20 全部超 60 秒；五回合子集 166.1–232.6 s），70–90 s 估算被证伪。组合路径无法达到 60 秒；移动档判定不变。证据 `artifacts/goal/narration/read-mobile-kernel-probe-20261124.md`、`read-mobile-schedule-probe-20261124.md`。
- 用户裁决（2026-11-23，第二次）：**继续移动工程攻关**；接受当前 210–225 秒，继续压缩提示与调用数。60 秒门槛不变。
- 移动提示压缩（2026-11-23，run103/104）：只压 results 场景清单时 s05 189.1 s（基线 210.5），s06 27.4 s 中止；再压位置/外貌的容器目录会让模型把被裁掉的容器当目的地、触发重试，s05 反升到 229.9 s，已回退。60 秒仍需约 3 倍；当前 0.6B + 核显的工程上限在 190–230 s。用户裁决继续工程攻关；该杠杆已到实际上限。
- 当前代码移动复测（2026-11-23，run94）：0.6B + 核显 + 4× CPU 限速，早交还臂 + skip，s05 交还 210.5 s；两个参与组的 results/position/appearance 合计 112.3 s、叙事 62.1 s；s06 结算 3 次后中止（36.1 s）。位置/外貌合并只在该组有计划外貌变化时生效。60 秒仍差约 3.5 倍。证据 `artifacts/goal/narration/run94-mobile-current.json`。
- 影响：决定前不改验收协议与默认模型。
- 更新（2026-11-22，用户澄清）：移动端要在产品范围内；验收不在真机上做，而是在当前环境模拟移动端性能条件（用户此前口径）。因此移动端不是「缩小版笔记本档」，而是独立配置 + 独立门槛：  1. 移动档配置：单引擎 0.6B（语义与叙事共用一套权重，页面臂 `narrationModel=semantic` 已存在），权重从约 1.5 GiB 降到约 0.4 GiB；配合 `offscreenPolicy=skip` 与更小上下文（12,288 → 8,192）降低 KV cache 与串行调用。
  2. 验收模拟（已加进 `accept-world-local.mjs`）：`--cpu-throttle N` 用 CDP 把渲染进程降速（模拟手机 CPU）；`--gpu-lite` 不强制独显（让 Edge 走核显近似移动 GPU）；内存峰值单独记录。模拟不到的部分：真实散热降频、iOS 标签页回收、手机内存压力。
  3. 门槛分档：移动档与笔记本档不共用 5/5 零硬错 + 60/300；需用户拍板移动档的时间与质量门槛（例如首段 ≤120 s、单点 ≤600 s、质量按移动档单独读评）。
  4. 首组数据（run35/36，2026-11-22）：单 0.6B + Intel gen-12lp 核显，s05/s06 整轮等待加 4× CPU 限速为 296.3/298.5 s，去掉限速为 283.8/267.9 s（只差 5–10%）。瓶颈是核显 + 0.6B 流水线本身，不是 CPU 限速。正文复述输入、把法定失败的「递电台给阿豹」写成已发生、夹内部注记。结论：现行移动档配置不可行；移动端要成立，先做 D-024 的调度改造，再重测。证据 `artifacts/goal/narration/read-mobile-sim-20261122.md`。

## D-024 延迟口径：再次可行动 ≤60 秒，2 分钟不可接受

- 状态：`signed`（2026-11-22，用户批准「早交还」评估臂原型；产品契约是否切换待原型结果）。
- 决定（2026-11-22 批准范围）：先做评估臂原型——玩家点结算并叙事完成即交还、其余点后台结算或延后；只在 URL 评估开关下生效，不改默认调度、不改验收协议。原型量出真实交还时间与状态一致性后，再决定是否进入产品。
- 背景：用户明确「一个回合等两分钟已经不能接受，60 秒都很勉强」。现行验收只测「提交→首段可读 ≤60 s」（实测 16.9–39.7 s），但玩家真正等待的「提交→再次可行动」等于整轮交还，narration 臂实测 64.9–180.8 s——这就是体感的两分钟。
- 差距来源（实测）：整轮要等所有点结算 + 继续判断才交还；每个点包含六阶段串行调用（更新阶段占回合 72–82%），即使 `offscreenPolicy=skip` 仍在 65 s 以上。
- 两个可动杠杆：①交还时机——玩家自己的点结算并叙事完成就交还，其余角色后台结算（提交在后台结算完成前仍拒绝，状态一致性不变）；②每点调用数——例如单点回合的继续判断改为程序规则、合并部分更新阶段。两者都改 D-017/D-018 的调度契约，需原型与实测。
- 用户裁决（2026-11-22）：批准「玩家点交还」评估臂原型；是否把时间门槛改为「再次可行动 ≤60 s」待原型数据后再定。
- 影响：决定前不改调度与验收协议；移动档同样按 60 s 口径，不另设 120 s。
- 测量（2026-11-22，`goal-latency-analysis`）：run27–34 的 16 个回合，第一点叙事完成 18.7–50.8 s（16/16 <60 s），整轮 64.9–180.7 s，尾部 40.9–156.1 s；run35 移动模拟 s05 第一点 150.2 s、s06 39.7 s。结论：笔记本档早交还上界在 60 s 内，值得做原型；移动档单靠早交还不达标，必须同时减少每点调用。证据 `artifacts/goal/narration/latency-analysis-20261122.md`。
- 原型结果（2026-11-22，run37/38，开关 `schedHandback=player`，base 1.7B，skip）：5 个回合的整轮等待 36.9–45.0 s（同题默认调度 137.6/168.7 s）；交还后第二轮、第三轮提交均被接受；收尾状态 `cursor=order.length`、`conclusion={kind:'handback'}`、`advance=null`、`phase='complete'`；前端全量 1252 passed / 17 skipped。代价：自动链（R10）整体跳过；结论由程序强制但持久记录 `closedBy:'model'`；质量不变（s06 仍写被拒动作）。证据 `artifacts/goal/narration/read-handback-arm-20261122.md`；run40 另 10 个回合同为 25.5–46.3 s（合计 15/15 ≤60 s）。
- 待用户决定（产品化）：a) 接受无自动链的调度；b) 有限自动链（限一轮或给自动链设时间预算）；c) 保持默认并接受 65–180 s 的回合。移动档仍需在此之后重测。
- 候选 b 测量（2026-11-22，`goal-handback-auto`）：保留一轮自动链的第一轮完成时间 59.8–100.6 s，1/16 个回合 ≤60 s；玩家回合本身 31.4–57.7 s。结论：60 s 口径在当前栈内只有候选 a（无自动链，36.9–45.0 s）成立；候选 c 为 65–180 s；候选 b 不值得写评估臂。证据 `artifacts/goal/narration/handback-auto-chain-20261122.md`。
- 20 输入套件（2026-11-22，`goal-handback-suite`，早交还臂）：15/20 个回合完成，交还 35.3–53.5 s、0 问题；chunk3b 的 s15/s16 与 chunk5 被宿主内存回收停止，未自行重启，change 保持 active。证据 `artifacts/goal/narration/read-handback-suite-20261122.md`。
- 套件补跑（2026-11-23）：chunk3b 5 回合完成（s15 49.6 s、s16 **70.7 s**）；chunk5 2/4（g8-t1 结算失败、g8-t2 **330 s 超时**），其余被内存回收停止。结论修正：早交还臂不是普遍 ≤60 s，重输入回合会超线或失败。
- 套件补完（2026-11-23，20/20）：firstReadable 20/20、turnCap 20/20、0 时限收尾、0 失败；交还 32.8–70.7 s，中位 44.9 s，18/20 ≤60 s（s16 70.7、g8-t4 62.8 超线）。汇总 `artifacts/goal/acceptance/run41-summary.json`。
- 默认路径真实等待（2026-11-22，G8 summary 统计）：20 个输入里提交→再次可行动最小 163.5 s、中位 295.3 s、最大 297.8 s，0/20 ≤60 s、20/20 >120 s；同一批的首段可读 1.3–39.7 s（20/20 ≤60 s）。验收的 60 秒门只测了首段，真实等待是 2.7–5 分钟。证据 `artifacts/goal/narration/read-default-latency-20261122.md`。
- 用户裁决（2026-11-23）：**保持默认交还**，不切早交还。默认路径的「再次可行动 ≤60 秒」仍不达标（0/20）；早交还臂仅作评估证据保留。
- 早交还臂十输入（2026-11-23，run92）：提交→再次可行动 30.3–53.4 s，10/10 ≤60 s；t6 结算中途刷新 `restored=true`。同一臂的质量仍不过（D-022：6/9 有正文回合硬错）。证据 `artifacts/goal/narration/read-17b-lora-v3-10turn-20261123.md`。

## 已确认（2026-11-20）
本轮 8 个待确认项已全部有答案，记录在 D-004、D-006、D-010–D-013。当前没有 `pending-user` 项。

后续新问题追加编号，不复活已删除的草案参数。

- 手写数据 v8（2026-11-23，`goal-narr-handwritten`，run105/106）：84 + 168 条手写替代正文（252 行，检查器 0/168）。五回合 s02–s05 人工 4.2 硬错 **0**（首次），s06 仍卡结算层（0.6B 无法产出 blocked fact）。十输入 10/10 ≤60 s，但 t1/t3/t9 归因、t8 位置矛盾，硬错 4/9。评估臂换 v8（`01db72c9…`）。下一步：s06 结算层（程序级 blocked fact 需批准，或更强语义模型）。

- 结算示例臂（2026-11-23，run107）：judgment 出现「阿豹不在场，未能…」的 blocked 理由，fact 仍写 completed，三次被 `results_unknown_entity` 拒绝；提示示例无效。s06 的 5/5 阻塞只剩结算层：程序级 blocked fact、手写结算数据微调 0.6B、换更强语义模型，或接受不通过。

- 判词搬移（2026-11-23，`goal-settlement-rewrite`，run108–110）：fact 点名未登记实体且无否定词时，若该成员 judgment 为 blocked/not_achieved 且理由含否定线索，用判词当 fact、outcome 改 blocked；否则仍拒绝。单测 100 passed。三次五回合均 5/5 完成（s06 结算不再中止），但叙事仍有「主角也看规则牌」的填充（s03/s05、s03/s04/s06、s02），0.2 温度下结算出现占位符/坏事实；5/5 质量仍未达成。

- 定向手写数据 v9/v10（2026-11-23，`goal-narr-targeted-v9`，run111）：v9 = 252 行 v8 + 52 条定向样本（四场景×九形状，检查器 0）；五回合 5/5 完成、32.8–54.5 s，s02–s05 硬错 0，s06 仍有「他看了一遍规则牌」填充（1 处），填充从 v8 的多回合缩到 1 回合。v10 再加 6 条「交接失败+NPC 看规则」样本（310 行，检查器 0）；训练到 epoch 4/5 被内存回收，适配器未保存，未自行重启。

- 定向手写数据 v11（2026-11-23，`goal-narr-targeted-v11`）：修正 v9 两处提示缺陷——弧廊 `TarcadeD` 的红带/她改为蓝带/他（状态块如此），钟楼 `TtowerH` 删除空主语的「：看懂了规则牌」结算；新增 18 条手写样本（巷道/器材棚/西回廊「等待 + NPC 看规则」、巷「等待 + NPC 短讯机」、棚「清点 + 秦越解钥匙」、廊「问话 + 林亦舟挪演习枪」、三场景交接失败各再加 2 条），检查器 0/18；`sft-v11` 328 行。检查器否定线索补 `没找到|没见到`（v10 证据复跑仍 0/6）。训练已提交集群：作业 `276262` 5 epoch 完成，构建作业 `276264` 产出 f16 与 q4km；直拉 1.1 GB 实测约 85 KB/s，改用适配器回传，本地合并量化后装入评估臂（sha `f6b01bc1…`）。

- 集群 v11 验证与合法失败门（2026-11-23，`goal-narr-v11-run`）：run113 五回合 5/5、30.7–58.2 s；逐点抓取显示正文是两个 point 叙述拼接，point 1 的结算把观察/清点判成「路明非：看懂了规则牌」，叙事照写被误认为填充；同一 NPC 动作跨两个 point 重复。未知实体门加严：动作点名未登记名字时，丢名字的成功 fact 也拒绝或按 blocked 判词改写（单测 102 passed）；检查器两处误报修正。run114 五回合 5/5、74.8/37.0/75.1/99.0/65.8 s（1/5 ≤60 s），s06 合法失败由门强制；剩余阻塞为 0.6B 结算归因、两 point 重复叙述与 60 秒回归。

- 规则事实门与 run115（2026-11-23，`goal-settle-rules-guard`）：成员 action 不含「规则」时，写规则牌且不带否定词的结算事实丢弃（原因 `unsupported_action`，不重试）；单测 103 passed。run115 五回合 5/5、35.2/47.6/33.2/45.7/31.8 s（5/5 ≤60 s），规则牌填充消失，s06 无事实、叙事写出交接失败；检查器 0。剩余：两 point 重复叙述、0.6B 自造「故障短讯机」、正文偏短。交付判定仍为未通过（D-026），是否重新裁决由用户决定。

- 分点叙事收窄与 run117（2026-11-23，`goal-narr-point-scope`）：去掉 `onPointCommitted` 的跨 point `resultsText` 回退；`planPoints` 记录 actorIds，叙事只在玩家所在 point 带行动原文。测试 110 passed。run117 五回合 5/5、49.8/39.8/38.1/56.8/38.6 s（5/5 ≤60 s）、检查器 0；动作与结算句重复消失，s06 合法失败叙事正确。剩余：两 point 各写一遍 NPC 状态、正文偏短。交付判定仍为未通过（D-026）。

- KV 缓存量化（2026-11-23，`goal-kv-q8`）：wllama 透传 `cache_type_k/v`；语义 0.6B 开 q8_0（12,288 上下文不变，KV 约 1.38→0.69 GB），叙事 1.7B 保持 f16。run119（双 q8_0）5/5、35.0–39.6 s，但 s05 自相矛盾；run120（仅语义）5/5、40.1/34.0/49.1/46.9/34.8 s（5/5 ≤60 s），检查器 0。全量单测 1258 passed。剩余「故障短讯机」结算自造与 NPC 状态重复。D-026 不变。

- 20 输入复测（2026-11-23，`goal-20input-rerun`，run121）：内存修复后 5 个 chunk 跑完，20/20 输入；18 回合无驱动问题、交还 27.4–50.9 s（≤60 s）；s13 结果门误报中止（贪婪名字截取把「让上来」当实体，已修为弱证据丢弃事实、不中止 point，全量 1258 passed）、s14 自动链 330 s、s15 叙事把诺诺放置短讯机写成路明非（检查器 `item_owner_claim` 命中，下一条数据缺口：NPC 放置物品 → 主角不镜像）。另补非名字过滤（抓到的词含 来/去/上/下/出/进/回/起/看/听 等动词补语字符时不视为实体）；全量 1259 passed。D-026 不变。

- 定向手写数据 v12（2026-11-23，`goal-narr-targeted-v12`）：10 条样本覆盖「NPC 放置物品，主角不镜像」（run121 s15 的缺口），五个基、每基两个变体；检查器 0/10；`sft-v12` 338 行（v11 328 + 10）。训练已完成；结果见下条（拒绝）。

- v12 训练与拒绝（2026-11-23，`goal-narr-v12-rejected`）：集群作业 276342 完成（5 epoch、215 步、loss 0.34），run122 五回合 5/5、40.9/48.4/39.9/34.9/33.6 s（5/5 ≤60 s）、检查器 0；但 s02/s03/s05 把在场的诺诺写成「巷里却没有诺诺」「没有遇见诺诺」，缺席模板从阿豹过拟合到在场 NPC。拒绝 v12，评估臂回退 v11（sha `f6b01bc1…`，权重已换回）；数据保留。下一步 v13 正例对照：找/问在场 NPC 时写明她在场与她做了什么，并与阿豹缺席样本分离。

- 定向手写数据 v13（2026-11-23，`goal-narr-targeted-v13`）：10 条正例对照修 v12 的缺席过拟合（诺诺/芬格尔/林亦舟在场并做动作；主角自问或清点）；检查器 0/10；`sft-v13` 348 行（v12 338 + 10）。训练已完成；结果见下条。

- v13 训练与验证（2026-11-24，`goal-narr-v13-run`）：集群作业 276368（5 epoch、loss 0.096），run124 五回合 5/5、24.5–58.8 s（5/5 ≤60 s）、检查器 0，v12 的缺席回归消失；run125+126 20 输入实际 20/20：chunk1/3/4 干净、chunk5 补跑后 g8-t2/g8-t3 干净（g8-t2 81.7 s 超 60），失败 3（s06 强门中止、s07 330 s、g8-t4 结果截断）；人工读仍见 s14/s16 句子问题；三个门修正全量 1261 passed，run126 未误触发；g8-t4 的结果生成截断已抬上限（420→640，1261 passed）；抬上限后单跑 g8-t4：results 成功但 updates 报 `relative reference lane of lu is in a different location`（位置/相对引用类，G4/G5），回合仍失败，重跑状态可能叠加。相对引用修复：关系目标不在新容器同一地点时丢弃关系、保留位置；g8-t4 再跑 COMPLETED、28.8 s、updates 无错、检查器 0。

- 20 输入验证（2026-11-24，run129 + run126/run128 补点）：当前 build 上 20/20 回合无驱动失败、交还全部 ≤60 s（run129 的 18 回合 27.9–51.3 s）；s06 中止与 s07 超时在这轮消失，s13–s16 无问题；检查器仅 chunk4 1 个 input_echo。套件因内存回收拆两段跑；s07 的 330 s 属间歇风险（D-024 仍在）。默认臂与移动档（D-023）不在本证据内；D-026 不变。

## D-027 叙事训练数据手写（2026-11-23，用户裁决）

- 状态：`signed`（2026-11-23）。
- 决定：所有叙事训练数据的目标正文由执行 agent 本人逐条手写；不得用子代理工作流、模板或自动生成的目标作为训练数据。变体提示可由程序按世界登记表生成，但正文必须手写，并过扩展检查器。
- 理由：v7 的工作流目标出现复述、物品归属错误；v8 的 168 条手写替代目标检查器 0 命中。
- 影响：`.local/narr-train/alt-targets-*.txt` 为手写数据；v7 工作流数据不再作为后续训练来源。

## D-026 交付判定（2026-11-23，用户裁决）

- 状态：`signed`（2026-11-23）。
- 决定：维持目标与「再次可行动 ≤60 秒」硬门不变；用户接受交付判定为**未通过**，本轮以未通过收尾。默认交还保持（D-024），早交还臂仅作证据；质量最好为 v9（五回合 4/5 叙事干净、s06 一处填充），未达 5/5；移动档工程上限 189–229 秒，60 秒不可达。
- 理由：质量、默认延迟、移动延迟三项硬门在现有模型与硬件上均未达成；用户选择不改目标、不改门槛、不换硬件。
- 后续：v8/v9/v10 的手写数据与判词搬移是判定后的研发证据，不改变交付结论；v10 训练被宿主内存回收，待用户触发重跑。
- 影响：`goal.md` 状态置为 closed（未通过）；`ledger.md` R16 与质量行按未通过记录；`artifacts/goal/acceptance/final-status-20261123.md` 为最终判定报告。


## D-030 模型替换澄清（2026-11-24，用户澄清）

- 状态：`signed`（2026-11-24）。
- 澄清：用户从未禁止模型替换，且一直鼓励换模型；D-007 的约束仅是「替换需实测决策、不静默换权重」。此前执行 agent 把「模型替换需批准」误述为禁止，作废该表述。
- 范围：移动档可试更小模型或换运行时；笔记本档默认已按 D-028 为 v13。任何替换仍须实测与记录。

- 运行时探针（2026-11-24，transformers.js 4.3.2 + Qwen2.5-0.5B ONNX q4f16，Edge WebGPU）：短提示（178 字符）可跑（load 14.0 s、prefill 1.65 s、30 tokens 5.2 s）；产品形状的长提示（2,400+ tokens）在 ORT WebGPU buffer 下载处失败（MapAsyncStatus 3）。该运行时路线在本机对产品提示不可用；q4 变体未测。证据 `artifacts/goal/narration/read-runtime-probe-20261124.md`。

- micro-NLU 实验（2026-11-24，`goal-micro-nlu-collaboration`）：浏览器 ORT-WASM 单线程、targets 任务阶梯——0.52M 哈希头 p50 0.10 ms（CV 32/41）、10.4M MiniRBT 196.4 ms（CV 30/41）、102M MacBERT 2,439 ms（加载 2.4 s）、0.6B 基线 2.37 s 桌面 / 7.73 s 移动。结论：微秒级推理对微型哈希头成立（300 次约 30 ms），对需要读 512-token prompt 的编码器不成立（196 ms–2.4 s/次）；可换头的是 targets/position/判定归因/act-skip，action/reaction/fact 正文与 narration 仍是生成任务；银标（lu/nono、全 act）太窄，质量对比无法区分规模；混合流水线（头 + 少量文本生成）有条件可能但未验证。真机无设备未测。证据 `artifacts/goal/micro-nlu/conclusion-20261124.md`。

- 微型模型重设计实验（2026-11-24，`goal-micro-models-redesign`）：300 条手标（四任务各 75，含换名/缺席/否定/指代/未见物品/干扰/多行为对抗子集）。阶梯：CNN/GRU（18–31K）反超 0.26–0.52M 哈希 MLP——targets 13/14、position 11/14（CNN）、intent 12/15、judgment 13/14。共享编码（MiniRBT 10M + 四头，31 tokens）浏览器实测：WASM 单线程 9.54 ms、四线程 5.00 ms、WebGPU 14.79 ms；一次编码 + N 个 0.1 ms 头，300 任务约 35–40 ms。可换头顺序 judgment≈targets>intent>position；60 秒门槛有余地，质量受标注量限制（15 测试/任务）；真机无设备未测。证据 `artifacts/goal/micro-redesign/conclusion-20261124.md`。

- 微型模型量化对照（2026-11-24，`goal-micro-quant`）：同一 MiniRBT 共享编码 + 四头，fp32 vs 动态 int8，ORT-WASM（i7-13700H，headless Edge）：32 token 1 线程 10.0/7.2 ms、128 token 38.7/27.0 ms、512 token 206.1/154.5 ms；4 线程 4.5/4.6、13.9/12.3、61.9/48.3 ms。量化收益 1.3–1.45×，线程收益 1.5–3.3×。holdout fp32 与 int8 精确匹配相同（targets 12/14、position 3/14、intent 11/15、judgment 7/14），决策一致 55/57；质量成因未分离（训练轮数/容量/分布/输入信息量），int8/fp32 相同仅表示本轮未见总体下降。复核更正：32 token 下 int8 单/四线程 7.17/4.58 ms、fp32 四线程 4.45 ms 均 ≤10 ms（fp32 单线程 10.03 ms 贴线）；D-030 的「编码器类 196 ms–2.4 s/次」只适用于 fp32、512 token、单线程；短输入 + int8 为 7–10 ms（32 token）、27 ms（128 token、1 线程）。证据 `artifacts/goal/micro-quant/conclusion-20261124.md`。

- 微型模型联合实验（2026-11-24，`goal-micro-joint`）：批次切分（v1–v4 训练、v5 测试，15/任务），40 epoch。T2（打乱）natural 46/60（targets 13、position 10、intent 12、judgment 11）；T1（固定顺序）43/60；T3（打乱 + 32 截断训练）44/60。32 token 下 T2 准确率 45/60（position 截断 9、手写压缩输入 10），int8 延迟 7.83 ms（1 线程）/4.57 ms（4 线程），fp32 5.34 ms（4 线程）；16 token 时 targets 11、position 6、judgment 10；8 token 崩。结论：32–64 token 在本批测试上达到自然输入水平（样本内；fp32 单线程 10.87 ms 未达 10 ms）；训练截断不如自然训练；压缩输入能补回 position 的 1 行；训练打乱 +3 行（单种子）。分类头固定实体/地点词表，跨世界泛化未验证；准确率与延迟的精度/环境未统一。证据 `artifacts/goal/micro-joint/conclusion-20261124.md`。

- 微型模型泛化实验（2026-11-24，`goal-micro-generalize`）：候选打分（MiniRBT 句对，[CLS] 文本 [SEP] 候选 [SEP]）去掉固定词表；训练 329 对（每行 2 个硬负例）。浏览器内同输入同精度：seen position 10/13、targets 8/9；held（未见过的名字）position 7/7、targets 18/22；p50 3.83 ms（4 线程）/6.52 ms（1 线程），pair 输入中位 29 token。结论：未见过的地名/角色可打分；硬负例是必要条件（无硬负例时误报到 5/8 行）。但逐字匹配基线更强或持平：seen 9/9 vs 模型 8/9、held 21/22 vs 18/22、链 8/8 vs 5/8；模型只在非词面匹配（否定/指代/省略）上有潜在价值，现有数据只有 1 个省略例且双方都失败。限制：held position 7 行、seen targets 9 行。证据 `artifacts/goal/micro-generalize/conclusion-20261124.md`。

- 微型模型协同链（2026-11-24，`goal-micro-chain`）：12 回合（8 act / 4 skip），intent → targets → position → judgment 在浏览器里串行。端到端 7/12；intent 10/12、targets 5/8、position 8/8、judgment 7/8；46 次调用，170.1 ms（4 线程）/279.0 ms（1 线程），每回合 p50 17.2 ms；上一版漏计 skip 分支，已修。targets 错时 judgment 3/3、targets 对时 4/5，但骰点文本已含结果词，不能证明无传播；targets 逐字匹配基线 8/8 强于模型 5/8。position 输入是人工结算事实，按行动文本喂掉到 3/8；位置不依赖前面模型的输出。端到端 act 4/8、skip 3/4。限制：12 回合手写、单种子。证据 `artifacts/goal/micro-chain/conclusion-20261124.md`。

- 微型模型事实提取（2026-11-24，`goal-micro-facts`）：24 条手写事实测试集（direct/negation/pronoun/ellipsis/movement）。规则基线（字符串匹配 + 否定/代词/省略/移动/阻断结算）在 29 条（24 + 5 反例）上 targets 27/29、destination 27/29、negated 27/29；模型组合 targets 20/29、destination 16/29，否定字段无。反例子集：规则 targets 3/5、模型 4/5——互补性出现但只有 5 条；规则缺陷是否定词一刀切、问句地名当移动、看/望当移动。判定条件（模型在否定/省略集比基线高 ≥2 行）仍不成立。链改用浏览器内 JS 规则结算 position（动作 + 骰点，不再读手写事实）：端到端 6/12、act 3/8、position 8/8、targets 4/8、judgment 7/8、30 次调用、107.8 ms（4 线程）/178.5 ms（1 线程），结算 ≤0.155 ms。研究目标不设为模型击败规则；协议见 `artifacts/goal/micro-eval/protocol.md`（冻结规则与模型，五方案对比）。

- 微型模型 300 条评测（2026-11-24，`goal-micro-eval`）：300 条自写数据（作者与规则同一人，独立性未满足）。三字段全对：规则 227/300、10M 模型 —（218/207，无否定）、规则+10M 225/300、cue 门控混合 229/300、0.6B 103/300（145/233/278，p50 1998 ms）、规则+10M+0.6B 否定 230/300。混合的回退在 66 个空标签行误加 6 行、在 30 个非空行补对 17 行，净 -2；cue 门控修复。0.6B 单次约 2 s，只把三字段从 225 提到 230（门控版反而 229→222，噪声级）。复现口径：评测改用 int8（fp32 对照 223/208/153）。数据弱点：context 单在场、multi_turn 直呼姓名。复核更正：0.6B 的 103 是单次三字段配置，不代表产品多阶段语义系统；230 为全量 0.6B 否定，否定词门控为 222；10M 与 0.6B 都未解决语义理解，不能据此判定微型路线不如现有路线。300 条冻结为开发集。云端优先级下调。证据 `artifacts/goal/micro-eval/conclusion-20261124.md`。证据 `artifacts/goal/micro-facts/conclusion-20261124.md`、`artifacts/goal/micro-chain/conclusion-20261124.md`。

## D-028 v13 发货默认与交付重判（2026-11-24，用户裁决）

- 状态：`signed`（2026-11-24）。
- 决定：批准把微调版 v13（Q4_K_M `82e513db…`）作为产品默认叙事模型（`DEFAULT_NARRATION_MODEL` 已切换）；按 v13 的 20 输入证据重判交付：run129 的 18 回合 + run126/run128 补点 = 20/20 回合无驱动失败、交还全部 ≤60 s、检查器仅 1 个 `input_echo`；默认路径 run130 五回合 5/5、检查器 0（s02 77.3 s 属方差，其余 ≤60 s）。
- 范围：本裁决覆盖笔记本档与产品默认路径；移动档仍按 D-023 未验收，整体交付在移动档裁决前不作全部通过宣称。
- 影响：`goal.md` 状态改为「用户重判通过（笔记本档），移动档 D-023 未决」；`ledger.md` R16 与终态报告同步；默认切换与证据见本工作包。

## D-031 研究回归产品（2026-11-24，用户裁决）

- 状态：`signed`（2026-11-24）。
- 决定：暂停多跳协同推理研究（`goal-micro-reasoning`），不以「证明微型模型更强/数百次协作更强」为目标；回到 Jity 产品：LLM 继续承担开放语言理解与叙事生成；用规则与微型模型替代高频、可判定的语义任务（targets/position/judgment/act-skip）；以完整回合耗时、结算准确率、叙事质量为验收；手机真机验证。
- 理由：多跳协同是研究提问，不是产品需求；今天的性能数据（10M 4–8 ms、规则+10M 门控混合 229/300 三字段）可作为降低语义调用耗时的候选手段，但不能替代叙事生成。
- 影响：`goal-micro-reasoning` 暂停（脚本与数据保留，不归档）；下一工作包做「同一游戏输入下替换语义调用」的前后对比；60 秒门槛与 D-023 不变。

## D-032 微型工作流是产品技术目标（2026-11-24，用户澄清）

- 状态：`signed`（2026-11-24）。
- 澄清：D-031 把微型模型表述为「降延迟手段」不准确。目标是 Jity 的 AI 工作流由多个微型专用模型协同完成：行动理解与分解、NPC 自主行为决策、目标识别与指代消解、NPC 反应判断、行动结果结算、人物/物品/位置/任务状态更新；开放式文本生成（叙事等）继续用 LLM。微型工作流是产品的技术目标，不是可选的优化，也不是脱离产品的学术实验。
- 影响：下一工作包 `goal-micro-workflow`——在 `game-model` 加可切换的语义后端（默认保持现有 LLM 路径作为对照），用真实 20 输入回合驱动开发与验收；D-031 中「暂停多跳协同推理」仍有效。

## D-033 continuation 微型工作流：结构化事件 + 四头，不以重复句本身判无效（2026-11-25，用户指令）

- 状态：`signed`（2026-11-25）。
- 决定：自动推进不再只由「候选是否可能且与主角相关」两句 LLM 判断控制。浏览器端先生成结构化事件记录（位置/外貌/理智/任务/子任务），用 actor + 规范化文本 + worldDigest 区分「同一世界里的原句重放」与「世界已变后的连续警戒/观察」；只有前者在编码前拒绝，后者允许但受连续重复上限约束。专用微型模型（MiniRBT 共享编码 + novelty/unfinished/necessity/intervene 四头）对程序候选逐条打分，四条判断共同决定是否继续以及哪些角色行动；涉及主角的候选把 intervene 抬到 0.75，交还玩家。候选生成复用现有 `behaviorCandidates`；模型缺失或失败返回 null，回退原 LLM 提案+判断。
- 数据与边界：`continuation-data.jsonl` 432 行/84 场景/14 人物，标签由规则生成（多正例）；留出人物 caesar/lin/qin/tomiyama。四头留出混淆 novelty 102/107、unfinished 107/107、necessity 102/107、intervene 107/107（正例仅 3 条）；决策层与规则臂 24/24 场景同角色。该结果只说明模型复现规则标签，不作为语义泛化或优于 LLM 的证据。
- 证据：真实录音 39 次 continuation 调用固定输入回放，micro 与录制 LLM 接受的 character set 一致 39/39；但录制 LLM 38/39 继续，回放不证明质量。四臂完整回合（同输入、seed 11）：LLM-only 257.7 s / 104 接受调用（本轮未到 continuation，turn_budget；上一轮同输入 261.0 s / 2 个自动点）；micro 无 continuation 150.8 s / 119 / 4 次 36.3 s / 3 个自动点；micro 直接规则 153.6 s / 119 / 4 次 0.0 s / 3 个自动点；micro 四头 99.2 s / 109 / 3 次 0.7 s / 2 个自动点。规则 vs 四头 seed 11 为 153.6→99.2 s（少一个自动点），seed 17 为 95.7→91.5 s（状态相同、只差 4.2 s）；两 seed 合计 −29.3 s 但差异来自 seed 11 的额外自动点，直接规则 vs 四头尚无稳定差异。四头相对 LLM continuation 两 seed 分别省 51.6/62.2 s；直接规则在 seed 17 省 58.0 s，在 seed 11 因 updates/narration 轨迹更慢反而 +2.8 s。每次玩家操作四头臂：task calls 52、共享编码器 137（推理规模以此计）、头输出 488（不是推理次数）、候选评分 137；接受任务来源 program 37 / micro 29 / model 33，10 次 model attempt 单列，未标注 0。
- 影响：`?micro=1&microContinuation=0` 保留上一版微型工作流作对照，`microContinuation=rule` 直接执行规则作四头对照；默认 LLM 路径不变。下一步：独立评价者填 50 行盲评；按分歧修规则/数据；reaction 微型工作流已接入（触发分类 + 意图候选 + judge 三头 + 合理性门，真实威胁回合 source=micro），专用反应头与多威胁回合 A/B 仍待做；扩大输入与 seed。

## D-034 tasks/subtasks 微型工作流先做核验，不先替换任务阶段（2026-11-25，用户指令）

- 状态：`signed`（2026-11-25）。
- 决定：任务进展由"条件分解 + 事实/条件匹配 + 达成/部分/未达成"多步判断；但 pilot 的 satisfaction 留出只有 9/15，不能直接替换 LLM 核验器。`microTaskVerifier` 只在 `?taskVerifier=micro` 下启用，低置信/低相关一律回退；`micro=1` 默认仍是 LLM 核验器。子任务先做重复过滤（父任务/现有任务同文拒绝），开放式生成保留 LLM。
- 证据：`task-match-data.jsonl`（80 对，20 任务）、`task-match-report.json`、`task-match-llm-arm.json`；真实回合 tasks 阶段两次空 `achieved`，核验器没有输入；`settlement.test.ts` 的 `subtask_duplicates_existing` 测试。 
- 影响：不通过降低语义校验换性能；下一个阻塞是任务阶段不提出达成候选，而不是核验器耗时。

## D-035 单动作转移与叙事一致性先于新模型（2026-11-25，用户指令）

- 状态：`signed`（2026-11-25）。
- 决定：先修「行动成功但状态不变」和「正文与已提交状态矛盾」两条独立故障，不换模型统一处理。状态侧用结构化 `去向=` 进入 projection 与 programScene；叙事侧用在场/物品归属守卫，失败时用已结算事实草稿重写一次，仍失败才回落程序草稿。任务核验移除「达到目的→任务完成」的直接映射，改为逐项条件覆盖；覆盖不足时 yes 降为 partial，零覆盖判 no。
- 证据：`evidence-transfer-single9.json`（goggles_lu→nono、source=model、problems=0）、`evidence-multi-turn-micro2.json`、`projection.test.ts`、`results.test.ts`、`committed-narration.test.ts`、`task-progress.test.ts`。
- 影响：不通过放宽校验或提前结束事件换性能；共享 tokenizer 已接入（七端口一次词表加载），共享 runtime/批量推理未做；仍待多回合台账泄漏、空移动与 program 回落。

## D-036 task proposer：整轮 results + 条件台账 + 程序下限（2026-11-26，用户指令）

- 状态：`signed`（2026-11-26）。
- 决定：tasks 批只在最后一个 plan point 跑，但 `staged` 在点提交时清空，玩家点的 results 进不了 tasks 阶段；`ControllerMemory.roundResults` 按回合合并每个 `stage_unit` 的 results，point-rest 批读整轮，`pointPlan`/`round_conclusion_conclude`/`clearRoundWork` 重置。task proposer 继续只提案、核验器提交；每条条件由 4 类模型判断 none/keyword/attempt/satisfied，跨回合台账只在 satisfied 全齐时提案。`satisfied` 增加程序下限：action 必须在事实里出现动作词（或首字），confirmation 必须出现确认词且任务自身 item/target/location 之一出现在事实或跨回合依据里；这是上限约束，不是完成判定。proposer 的条件标签随 support 传给微型核验器，替代词面 `conditionCoverage`；LLM 核验器提示改为打印 `basisText`，跨回合依据不再显示“引用不存在”。personality 阶段把 `<f1>` 这类事实 id 解析为事实所属人物，避免一个 0.6B 格式错误让整点失败、丢掉同点任务达成。
- 模型实验：带 `任务：<goal>\n条件：<label>` 输入的 v2 条件模型留出 73.7%，真实行上把护目镜确认从 satisfied 降为 keyword；不部署 v2，部署模型仍是 condition+fact 的 v1（留出 88.9%）。真实错误由程序下限兜住。
- 证据：`evidence-task-accum-micro4.json`（玩家事实缺失，facts=12 全 NPC）、`evidence-task-accum-micro6.json`（跨回合护目镜 support 3/3，但 `task_lu_kit` 被“拿起护目镜”误判为 `进入`，且 personality `<f1>` 让整点取消）、`evidence-task-accum-micro7.json`（程序下限后 turn1 1/3、turn2 2/3、turn3 3/3 + verifier yes，kit 误判消失；personality 改写 `<人物id>` 仍使整点 turn_failed）。`<f1>`/`<人物id>` 到触发人物的映射已加单测；micro8 真机复跑在首回合前因宿主机内存低被停止；micro9 完成三回合验收（COMPLETED、0 failures）：护目镜 1/3→2/3→3/3、verifier yes、快照 `task_lu_goggles=achieved`、回合后待办列表已移除该任务；personality 写 `<f1>` 且复述事实的行被独立拒绝，未丢任务。回合等待 123.5/107.7/121.4 s。
- 影响：不为了任务进度放宽六阶段原子提交；personality 失败仍记录，但已知事实 id 不再让点失败。仍待：proposer 台账跨刷新持久化、后续子任务提案、移动端与共享 runtime/批推理。

## D-037 task 条件台账进入本地存档（2026-11-26，用户指令）

- 状态：`signed`（2026-11-26）。
- 决定：task proposer 的跨回合台账不放进 `WorldState`（不改变 world digest），作为 `LocalGameSnapshot.taskLedger` 随每次本地存档/进度同步保存；`taskLedgerOf` 在保存时导出，`onRestoreTaskLedger` 在 restore/create 时导入/清空。快照版本 1 保存 `worldId`、已去重事实键、每个任务的条件、status、active、evidence 和失效时间。物品条件视为持续条件：每次 proposer 调用按当前持有链复核，物品离开任务主人则 `active=false` 并记 `invalidatedAt`；重新持有则恢复。时间/地点/对象/动作/确认条件视为历史条件，满足后保持。只有全部条件 satisfied 且 active 才提案。
- 证据：`task-proposer.test.ts`（导出/导入、重复事实去重、物品失效/恢复）、`session-recovery.test.ts`（快照携带并回传台账）、`evidence-task-accum-refresh1.json`（第 2 回合后 reload，`restored=true`、history 2→2；第 3 回合仍以 3/3 完成护目镜任务，快照 `achieved`）。
- 影响：刷新、存档切换、回滚都使用与快照同版本的台账；重复事实不再重复打分。第 3 回合 accepted 139.5 s，60 s 门槛仍未达到，tasks 阶段在最终 support 前有重复调用；下一步用共享 runtime/批推理/重试收敛压这部分成本。

## D-038 共享 ORT 会话与条件批推理（2026-11-26，用户指令）

- 状态：`signed`（2026-11-26）。
- 决定：ORT session 按模型 URL 全页共享，端口持有引用计数；`dispose` 在最后一个引用释放时释放会话。task proposer 把条件/事实行 padding 成一批，一次 `session.run` 取回每行 logits；`packBatch` 单独测试。暂不做自动空闲驱逐：端口在整个会话期持有引用，需要端口级 release 信号后才能安全回收。
- 证据：`evidence-task-accum-batch1.json` COMPLETED、0 failures；proposer 17 行 344 ms（micro9 同量级 18 行 721 ms，−52%），8 行 90 ms vs 72 ms、11 行 66 ms vs 47 ms（小批 padding 反而慢）；回合等待 84.2/90.0/124.9 s，护目镜任务仍 `achieved`；JS heap 149/137/128 MB。单测 `runtime.test.ts`。
- 影响：条件行多时批推理有效，小批应按行数阈值退回单行；内存主项仍是 narration/semantic GGUF，micro session 共享/批推理只解决重复会话与逐行开销。下一步：端口级 release/空闲驱逐，LLM tasks 重试收敛。

## D-039 进入完整工作流性能优化阶段（2026-11-26，用户指令）

- 状态：`signed`（2026-11-26）。
- 决定：task proposer、跨回合条件、存档恢复与任务提交已进入回归维护；研发重心转为一次玩家操作的端到端效率。建立每回合时间轴（加载/提示/生成/等待/重试/依赖），按真实阻塞排序；优先用微型模型替换剩余高耗时语义任务（tasks/subtasks/personality/sanity、后续子任务、专用反应）；独立微型任务并行/批推理，同一状态+事实的重复核验复用已验证结果；优化 GGUF 驻留、上下文长度、调度与空闲释放；建立六类独立场景集；桌面/移动持续测 30/60 s。小批量阈值不再作为重点。
- 证据：micro9/refresh1/batch1 完整回合 84.2–146.9 s；proposer 17 行 344 ms（旧 721 ms）但回合仍由 LLM 主导；batch1 heap 149/137/128 MB，共享会话无重复可省；micro9 任务 `achieved`、refresh1 刷新后仍 `achieved`。
- 影响：不再以单端口训练/阈值为主；性能结论必须来自整回合时间轴与真实页面。30 s/60 s 未达前不宣称性能通过。

## D-040 整回合性能：动作模板回退、verifier memo、GGUF 驻留（2026-11-26，用户指令）

- 状态：`signed`（2026-11-26）。
- 决定：研发重心转向端到端。动作阶段在 LLM 把任务目标当行动时，第一次拒绝后直接使用已校验的模板候选，不再付两次 repair；`templateFallback:false` 保留实验路径。任务核验对同一 engine 上完全相同的温度 0 prompt 做 32 条成功判决 memo，命中不调 LLM、失败不缓存。GGUF 侧把叙事默认上下文 4096→2048（约省 224 MiB f16 KV），页面不再保留已 fetch 的 GGUF Blob（最多省 1.4 GiB Blob 配额；硬停止重载改为重新 fetch）。独立场景集 `scenarios-independent.json` 覆盖物品交互、移动、对话、冲突、任务推进、环境变化，共 8 回合。
- 证据：`evidence-task-accum-action1.json`（动作回退）：等待 69.2/85.3/100.8 s，action1 的 action LLM 调用 8/8/8（batch1 16/16/19）、attempt 6/6/7（batch1 11/10/12）、action ms 28.9/31.5/42.3（batch1 42-65），护目镜仍 `achieved`，COMPLETED/0 failures。`timeline-20261126.md`：9 回合均值 107.6 s，action 24.1 s、position 14.9 s、tasks+subtasks 22.0 s、正文尾 26.5 s；没有相同 prompt 的完全重复调用。verifier memo 与 GGUF 改动的整回合复测进行中（perf1）。
- 影响：动作重试是最大单项可省；verifier memo 只省重复核验（2-5 s/次），不是 100 s 主因；GGUF 改动解决内存/Blob 配额，不把回合拉到 30/60 s。空闲 worker 释放、narration 双跑、position 批处理仍是下一轮。

- 复测（perf1，2026-11-26）：三回合 COMPLETED、0 failures；等待 68.0/88.2/119.2 s，护目镜 1/3→2/3→3/3 并 `achieved`；action 仍是 8 次 LLM/6-7 次 attempt。verifier memo 在这三回合 0 命中（每回合只出现一次相同 support），只对重试点/恢复回合有意义，不能算当前收益。叙事 2048/不保留 Blob 只降内存，不降回合时间。空闲 worker 释放已接入：tab 隐藏且无回合在跑时退出两个 worker，可见时预热重载；真实页面未测该路径。

## D-041 独立场景基准与动作/位置精度（2026-11-26，用户指令）

- 状态：`signed`（2026-11-26）。
- 场景基准：`scenarios-independent.json` 8 回合（对话、冲突、移动×3、物品、环境×2）已跑（`evidence-independent-scenarios-1.json`）。8/8 回合完成，地点全部符合预期（服务巷→庭院→器材棚→检修口→门厅）；但总状态 FAILED：第 5 回合 `program_text_not_model/source_program`，第 7/8 回合 `prose_not_identical_to_record`；全部任务仍 pending。对话回合的结果事实是「只完成一部分」，`task_lu_choice` 0/2；检修通道回合的结果没有让 `task_lu_route` 的地点条件成立。说明通用任务理解仍不足，场景断言需要按真实语义复核。等待 139.6/111.5/144.1/118.1/86.2/79.9/95.9/95.1 s（均值约 108.8 s）。
- 代码：action 回退改为复用三头 judge 的排序，取最高分合法候选；position 先做确定移动（`去向=`）、确定无移动（无移动动词 + 停留/观察/物品动词或无地点名）与不确定（移动动词无目的地）三分，只对不确定问模型。
- 影响：动作回退不再默认第一个合法候选；position 的模型调用应明显下降。两项改动后正用同一 8 场景集回归（`evidence-independent-scenarios-2.json`），未完成前不宣称通用任务理解通过。

- 场景回归（scenarios-2，2026-11-26）：action 回退改用 judge 排序、position 三分类后，同一 8 场景 **COMPLETED、0 failures**（基线为 FAILED）。等待 59.8/75.6/95.0/79.7/62.6/60.2/78.3/81.2 s，均值约 74 s（基线约 109 s）；第 1 回合 59.8 s 首次进入 60 s。地点轨迹全部正确。仍全部任务 pending（对话结果只完成一部分、route 条件未成立）；turn5 的 `program_text_not_model` 消失，turn5/7/8 仍有 `prose_not_identical_to_record`。`prose_not_identical_to_record` 和任务通用性仍是下一优先级。

## D-043 语义理解优先：场景指标、跨人物证据、决策与物品目的地（2026-11-26，用户指令）

- 状态：`signed`（2026-11-26）。
- 指标：`scenario_report.py` 分开统计运行成功率、状态断言、任务断言、叙事一致性和耗时。修正对话检查（询问不等于获得回答，任务应保持 pending）后：基线/回归状态断言 39/48（81.2%）、任务断言 11/14（78.6%）、3 个回合有叙事一致性问题；均值 108.8→74.1 s。COMPLETED 不代表质量通过。
- 根因：results 事实只有「正文 + 成功程度」，路线决策被当成地点到达；对话只有询问，没有回答事实；`spare_mag2` 的嵌套容器目的地没有被 action structure 解析；检修盖/长桌的环境变化没有进入状态。
- 已修：proposer 对每条事实判断所有 pending 任务（别人的回答/行为可支持任务主人）；路线目标分解为 decision 条件并抑制选项地点；`塞进/放进/装进` 解析物品容器与两字槽位（弹匣→背心/胸袋）。对话场景的期望改为 pending，等待真实回答。
- 下一步（暂缓细节性能）：results 增加实际结果、获得信息、环境变化、涉及对象与因果；条件分解支持信息获取、路线选择、决策、承诺、环境状态、物品状态、复合条件；分别训练事件语义提取/任务相关性/条件满足/跨事件组合的微型模型，数据覆盖同义、否定、隐含结果、他人信息、多事件共同满足与同词不同结果的反例；不针对 8 个输入写规则。

- 追加（语义修复）：proposer 对所有 pending 任务判断（他人的回答/赠予可支持任务主人）；路线目标分解为 decision 并抑制选项地点；`塞进/放进/装进` 解析物品容器与两字槽位；results 在最终尝试把「目标回应」事实归给行动者并从句中派生 target（只限回答/回应/拒绝/摇头等回应事实，防止把别人的行动解释当结果）；确认条件遇到「没有回答/未确认/拒绝说明」按否定处理。对应单测：跨人物回答、否定回答、路线 decision、物品目的地、目标回应归因。scenario-4 正在跑。

- 追加（稳定性）：第一人称主角事实「我向诺诺问清…」中「我」即组成员，mentioned 补入主角，避免被严格规则当成只写了诺诺而整点失败；跨人物任务证据只允许在事实点名任务主人或事实人物正是任务 target 时进入，避免宽场景事实把大量无关任务带进 verifier/personality。scenario-4 因这两点分别出现 turn1 results 失败和 290-330s 回合，修复后用 scenario-5 复验。

- 语义回归（scenarios-5，2026-11-26）：COMPLETED、0 failures；状态断言 42/48（87.5%）、任务断言 14/14（100%）、叙事问题 3 回合；均值 76.8 s（max 95.1）。相比 scenarios-2：状态 39→42、任务 11→14；路线 decision 与跨人物回答生效，对话在无回答时保持 pending。剩余失败：spare_mag2 嵌套物品（sc04/5/7）与环境外观（sc06/8 的 anyOf）。之后给 micro results 的 transfer guard 增加物品容器目的地与同房间开放来源；scenarios-6 回归中。

## D-044 微型生成模型与结构化事件（2026-11-26，用户指令）

- 状态：`signed`（2026-11-26）。
- 事实：任务断言 14/14 里只有 1 个唯一任务（路线）真正达成，其余 11 项是 pending 检查、2 项是该达成状态的持续检查；`scenario_report.py` 现分开统计唯一任务达成、false achievement、missed achievement。scenarios-5：状态 42/48、唯一任务 1/1、false 0、missed 0、叙事问题 3、均值 76.8 s。14/14 不等于多类任务理解。
- 决定：下一阶段正式探索微型生成模型，不再主要增加分类头/关键词规则。统一结构化事件表达：意图、实际结果、获得信息、环境变化、人物承诺、决策、因果关系；事件提取与任务条件分解交给短序列生成模型（微型生成），现有分类头做相关性/条件门控，LLM 保留对照与核验。训练/评价数据覆盖不同世界设定、人物、物品、任务类型、同义/否定/隐含结果、他人信息、多事件共同满足、同词不同结果反例；对比纯规则、分类、生成、混合、LLM 五臂；冻结独立测试集与评价标准，分别统计真实达成、错误达成、遗漏达成、跨回合状态正确性。继续修环境变化、嵌套物品容器、叙事一致性；资源允许时复跑 scenarios-6。
- 当前：`scenarios-independent.json` 已冻结 sha256 `8a52c6aeb8abea71ad0d4d25c338c46b9ae038bbb2d96d161ffaf33ce5235805`；`scenario_report.py` 已加唯一任务/false/missed 指标。下一步：结构化事件 schema + 生成端口 + 数据集/五臂评测。

- scenarios-6b（2026-11-26）：嵌套物品 transfer guard 修复后，8 场景 COMPLETED、0 failures；状态断言 46/48（95.8%）、唯一任务 1/1（task_lu_route）、false 0、missed 0、叙事问题 3 回合；均值 76.3 s（max 88.2），turn1 58.0 s。剩余仅检修盖/长桌两个环境外貌 anyOf 与 3 个 prose provenance 标记。该证据不改变 D-044：1 个唯一任务仍不足以证明多类任务理解。

## D-045 微型生成试点：先不接入生成臂（2026-11-26）

- 状态：`signed`（2026-11-26）。
- 试点：`micro_generative_pilot.py` 训练从零开始的 Encoder-Decoder，标称 5M/15M/30M（实际 4.69M/14.63M/33.30M），分别做任务条件分解与事件提取；输出 `key=value` 短序列，实体字段用世界 ID，输入附实体表，解码时把 `target/item/loc/dest` 限制在表内候选。数据 380 行（308 训练/72 测试），按 15 个任务和 3 个事件角色留出；标签来自规则/动作结构，训练字段召回约 1.0，因此测试差距是记忆而非欠拟合。
- 结果：测试字段召回 conditions 0.21–0.36、events 0.35–0.60，整串精确 0–0.22。最好的事件臂是独立 15M（0.60）；5M 为 0.35，30M 为 0.45。多任务 15M 事件 0.35、共享编码器+双解码器 22.59M 事件 0.35，均低于独立 15M；共享编码器没有收益。15M 事件只有 `result` 达到 1.000，`target/item/dest` 为 0；条件臂 `time/act/decision/item` 为 0，`target` 0.333。约束解码把 15M 条件从约 0.27 提到 0.33–0.34，但没有修好事件实体。
- 延迟/体积：15M GPU p50 30–41 ms、p95 50–85 ms；CPU p50 66 ms；int8 6.6/19.8/44.7 MB（5M/15M/30M）。浏览器 WASM/WebGPU 未测，不能把桌面 CPU 当浏览器成本。证据：`design/goal/micro-generative-pilot.md`、`artifacts/goal/micro-workflow/micro-generative/pilot-report.json`。
- 决定：不把生成臂接入 `/world-local`，不替换任务条件分类器或实体链接。下一步：手写/人工标注的同义、否定、隐含结果、他人信息、多事件和同词不同结果测试集；只把 5M–15M 的 `result` 头做混合臂，实体继续由动作结构/链接器给出，`info/env/promise/decision/cause` 继续由 LLM 或核验器处理；条件生成只在任务创建/修改时缓存；最后在冻结的 `scenarios-independent.json` 上做五臂比较，不能拿本轮试点替代真实页面证据。

## D-046 微型生成 v2/v3：候选指针与预训练编码器（2026-11-26）

- 状态：`signed`（2026-11-26）。
- 独立补测（D-045 缺口）：独立 5M/15M/30M 六模型分别导出 ONNX 并测 CPU；int8 6.57/19.84/44.66 MB；CPU p50 54.2–105.9 ms、p95 77.4–149.4 ms；15M 条件字段 0.417、事件 0.50，5M 0.315/0.40，30M 0.287/0.35。结果与同进程多任务臂有训练顺序/run 方差（15M 事件 0.50 vs 0.60）；延迟/体积以独立报告为准。证据 `independent-report.json`。
- v2 数据/输出：训练改为去重后的 95 行（73 条件 + 22 事件，不再用四份前缀变体）；测试为 24 条手写 gold（12 条件/12 事件，20 本世界 + 4 个新世界 `mistport`，新实体 ID 训练时不可见）。2×2：从头/预训练 × 自由 ID/`<pN>` 索引。自由 ID BERT 字段 0.231、实体 0.259；`<pN>` BERT 0.179/0.111；从头自由 0.064/0.037；从头 `<pN>` 0.179/0.111。所有臂在新世界实体字段为 0：索引 token 不等于指针。
- v3 候选指针：解码器在实体字段发 `<e>`，对行内候选做点积选择；BERT 编码器冻结，候选编码器从头训练。BERT 候选指针字段 0.244、实体 0.333、新世界实体 0.200；从头候选字段 0.205、实体 0.296、新世界实体 0.000。候选指针是首个整体超过自由 ID（0.244 vs 0.231）且能选新世界实体的臂；增益小，`mistport` 只有 4 行。
- 有限类：BERT+线性 result 分类器 0.583；BERT 候选指针生成 `result` 0.583、从头 0.500；分类器预测全 `completed`，12 条中 7 条 completed；没有生成优势，保留分类器。`info/env/promise/decision/cause/time` 仍为 0；95 行训练数据是瓶颈。
- 决定：后续混合臂采用“候选评分指针 + 冻结 MiniRBT 编码器”处理实体字段，实体候选由链接器/世界表提供；`result` 用分类器；生成只承担开放式字段与复合条件。下一步先扩手写**训练**数据并按世界/任务类型/事件类型分测试集，再接入 `/world-local` 做五臂、浏览器 ONNX 与产品收益；不扩大参数量。证据 `design/goal/micro-generative-v2.md`、`v2-report.json`、`v3-report.json`。

## D-047 ONNX 形状缺陷与固定长度回退（2026-11-26）

- 状态：`signed`（2026-11-26）。
- 事实：独立模型的 ONNX 声明 `src_len/tgt_len` 为动态，但 legacy exporter 把 dummy 长度写死。`indep_5M_conditions-int8.onnx` 只在 `src=55,tgt=18` 可跑，54/56/96×64 都在 `Reshape` 失败；其余独立图同类。该缺陷来自 D-045 的导出配方；`onnxscript` 未安装，dynamo 导出未跑。已复现并记入 `independent-report.json:shapeCheck`。
- 固定长度回退：96×64 导出可跑并量化，5M int8 7.86 MB，CPU p50 3.3 ms（单次 teacher-forcing forward，不是逐 token 解码，也不是浏览器）。证据 `fixed-onnx-report.json`、`check_fixed_onnx.py`。
- 决定：当前 ONNX 不作为可部署动态模型；浏览器混合臂必须用固定 padding 并分别导出 encoder/decoder-step 图，或先安装 `onnxscript` 走 dynamo；在完成前不宣称浏览器延迟/内存通过。D-045/D-046 的 int8 MB 只作权重体积，不当作运行时形状能力。下一步仍按 D-046：手写训练数据 + 候选指针 + 分类器 result，然后五臂。

## D-048 手写训练种子：数据有响应（2026-11-26）

- 状态：`signed`（2026-11-26）。
- 数据：`hand_train.py` 28 条手写训练（12 条件 + 12 事件 + 4 条第三世界 `frost`），与 24 条 `hand_test.py` 不重叠；v3 训练 123 行（95 规则 + 28 手写），测试仍 24 行（20 dragon + 4 mistport）。种子由执行 agent 手写，不是用户核验标注。
- v3 复跑：BERT 候选指针字段 0.346、实体 0.481、开放 0.275、新世界实体 0.400、整串精确 0.083；对比 95 行时 0.244/0.333/0.196/0.200/0.042。从头候选 0.295/0.333/0.275/0.200，对比 0.205/0.296/0.157/0.000。28 条手写训练带来明显提升，预训练编码器仍在新世界更好。
- 未解决：`info/env/promise/cause/neg` 仍为 0（手写训练里有这些字段，模型没有生成对）；`loc` 0；`result` 在 BERT 0.500、从头 0.750、分类器 0.583 之间不稳定；p50 从约 47 升到约 94 ms（输出更长）。12 条事件测试和 4 条 mistport 不足以做显著性结论。
- 决定：继续扩手写训练（目标数百条，按世界/任务/事件类型分测试），优先开放字段与复合条件；实体用候选指针 + MiniRBT，`result` 用类别加权分类器；不在 28 条种子上接产品，不宣称浏览器通过。证据 `design/goal/micro-generative-v2.md`、`v3-report.json`、`hand_train.py`。

## D-049 数据规模、开放字段与浏览器逐 token（2026-11-26）

- 状态：`signed`（2026-11-26）。
- 固定架构：BERT 候选指针不变；训练 123 行基础（95 规则 + 28 手写）+ 877 行模板生成 = 1000 行；250/500/1000 热启动；测试仍是 24 行手写（20 dragon + 4 mistport）。模板生成行不是人工标注。
- 学习曲线：250/500/1000 字段 0.333/0.333/0.359、实体 0.370/0.333/0.481、mistport 实体 0/0/0、精确 0.083/0.042/0.042。28 条手写种子（D-048）是 0.346/0.481/mistport 0.400；模板扩容没有迁移到新世界，数据来源比数量更关键。不能把模板曲线当泛化。
- 开放字段：1000 行中 info 223、cause 162、promise 146、decision 104、env 92、neg 48；v3 生成 info/env/promise/cause 全 0，decision P0.2/R0.33；同一数据的 BERT 多标签存在性分类器 F1 为 info 0.31、env 0.73、promise 0.67、decision 0.67、cause 0.40、neg 0.50。字段存在性可学，内容生成没有；先存在性分类再专用提取的方向成立。
- 片段 vs 生成：手写开放 gold 的输入子串率 env/cause 0、info 0.17、promise 0.25、decision 0.43、neg 1.0；开放值多是摘要，span 提取无法产生，需短序列生成。字段级损失/训练拟合未埋点，是下一诊断项。
- result：未加权 0.667，类别加权 0.333（加权把 5 条 completed + 1 条 partial 判成 failed）；D-048 的“类别加权”被推翻，保留未加权分类器，等更大平衡集再校准。
- 浏览器逐 token：5M 试点固定 96/64、encoder/decoder-step 分图、int8 ORT-WASM；Edge 下 load 939 ms、encode 33.8 ms、9.61 ms/token、12 token 全链 p50 118.1 / p95 150.2 ms；模型 5.14 MB。v3 候选指针的浏览器导出/耗时仍未测。
- 决定：不再换架构；模板数据不计入学习曲线；下一步用人工/核验语义数据扩规模，做“存在性分类 -> 专用开放字段提取器”，保留未加权 result 分类器，并导出 v3 候选指针的逐 token 浏览器图；语义质量达标后再接产品、五臂。证据 `design/goal/micro-generative-scale.md`、`scale-report.json`、`exists-report.json`、`browser-seq2seq-probe.json`。

## D-050 真实语义数据生产流程（2026-11-26）

- 状态：`signed`（2026-11-26）。
- 数据源：20 条真实产品输入（`run41-turns-20-chunk*.json`）+ 8 条冻结场景（`evidence-independent-scenarios-6b.json`），按 id 去重（s12 重复）；字段含玩家行动、同回合正文、前后状态与快照；8 个场景另带 checks。
- 流程：DeepSeek 强模型提出 `{info:{present,content,support}, env:{...}}`，要求 support 是行动/正文原文子串；脚本做事实核验（子串 + env 状态外观 + 移动/物品转移拒绝 + info 行动摘要拒绝），生成 `real-semantic.jsonl` 与 `real-semantic-spotcheck.md`；spot-check 供用户人工抽查，不自动批准。缓存 `real-semantic-cache.jsonl`，重跑不再调 API。
- 首批标签暴露了强模型的类别错误：把移动（sc03/sc05）和物品转移（sc04）写成 env，把 NPC 行动摘要（sc02/sc04）写成 info；子串核验能通过，但类别规则拒绝。sc01 的“没有答出”判 info=false，符合任务保持 pending；sc05 的检修口观察保留为 info。
- 当前：pro 模型较慢，撰写时缓存 5/28；标签流程、核验和抽查文件已就绪，三任务（存在性 / 专用内容提取 / 事实支持）和 held-out 真实事件的状态补丁尚未训练/验证。用户目标是“多个微型模型协同理解一个未见事件并正确改世界状态”，本轮未完成。
- 决定：停止模板扩容；先把真实语义缓存跑完并抽查；再训练三任务、在 sc06/sc08/sc01/s11/g8-t3 上按存在性、给定类别提取、完整工作流分别统计；状态补丁把 env 映射到 item/location 外观、info 映射到任务条件/事实；随后做 v3 候选指针浏览器导出与固定长度 vs KV Cache，再五臂。证据 `design/goal/real-semantic-pipeline.md`、`real_semantic_data.py`、`real-semantic-cache.jsonl`。

## D-051 语义数据四态与回合差分（2026-11-26）

- 状态：`signed`（2026-11-26）。
- 用户核查指出的三个问题已修：
  1. `state_summary` 改为 `state_diff(before, after)`：只比较回合前/后快照的活动外观记录，输出 `known/added/removed`；每个 chunk/场景首回合无前快照时 `known=false`，不据此产生负例。
  2. 标签不再是“未通过=present false”。四态：`present` / `absent`（需明确“没有答出/没有变化”证据）/ `insufficient`（证据不足）/ `conflict`（已结算行动或叙事与旧状态冲突）。`insufficient` 与 `conflict` 不进训练负例；`conflict` 是修复集，保留内容/支持供人工抽查。
  3. 8 个冻结场景整体 test-only；20 条产品输入按 5 个 chunk 作 train，不跨同一连续过程切分；场景 checks 不进 labeler。
- 新增区分：玩家意图、`actions` 已结算结果、同回合叙事、回合前后快照差分；叙事不能补写状态。
- 首批 7 条缓存结果：sc01 info absent（没有答出）、env insufficient（无前快照）；sc02/sc04 info insufficient（NPC 行动摘要不是信息）、env insufficient（移动/物品转移不是环境）；sc03/sc05/sc07 info present；sc06 env **conflict**（行动提开检修盖，旧状态无新增外观），正是用户预判的修复事件；sc06 info insufficient（模型把路线决策当观察，需抽查修正）；sc08 未缓存，按行动应产生 conflict。
- 后台旧标签器已停止；新核验用 `CACHE_ONLY=1` 在 7 条缓存上跑通。强模型类别错误保留在原始缓存，核验器只降级，不制造负样本。
- 决定：不急于训练；先跑完/抽查真实数据，修正 sc06 info 与 sc08 conflict，再在 `present`/`absent` 上训练三任务；held-out 8 场景测状态补丁且检查无额外变化；随后 v3 浏览器/KV 与五臂。证据 `design/goal/real-semantic-pipeline.md`、`real-semantic.jsonl`、`real-semantic-spotcheck.md`。
