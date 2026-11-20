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

## 已确认（2026-11-20）
本轮 8 个待确认项已全部有答案，记录在 D-004、D-006、D-010–D-013。当前没有 `pending-user` 项。

后续新问题追加编号，不复活已删除的草案参数。
