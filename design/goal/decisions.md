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

## D-021 G6 事实门：只做开发期检查

- 状态：`signed`（2026-11-22，用户选择「只做开发期检查」）。
- 决定：运行期保持 D-004 原样输出，不加运行时事实门。新增开发期检查器 `frontend/scripts/product-acceptance/check-prose-facts.mjs`：逐回合把正文与叙事提示里的已结算事实对照，报告识别带、门状态、输入回声、占位句与元注记；只出 JSON 报告，不改产品路径、不进回合时间。
- 首轮结果（26 个真实回合：run22/23/24、run26/27、chunk1 复跑、chunk2、chunk3b、chunk5）：`band_claim` 2（都是 s02 给路明非加识别带）、`input_echo` 5（s05 复述「识别带和胸袋里的弹匣」等），其余类别 0。报告 `artifacts/goal/narration/prose-facts-check.json`。
- 理由：用户不愿承担运行时门的时长与失败率代价；开发期检查能驱动模型/提示迭代，且保持交付路径不变。
- 影响：G6 已归档未通过的状态不变；账本/验收报告记录本决定。

## 已确认（2026-11-20）
本轮 8 个待确认项已全部有答案，记录在 D-004、D-006、D-010–D-013。当前没有 `pending-user` 项。

后续新问题追加编号，不复活已删除的草案参数。
