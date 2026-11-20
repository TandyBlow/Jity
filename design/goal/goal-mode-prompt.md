# Jity Goal v11：浏览器本地完整可玩（goal 模式长文任务书）

状态：active。日期：2026-11-20。代码基线：`agent@695e6bd4`；文档基线：`830bbd4f`。

> 这是长文任务书，供执行 agent 完整阅读。实际设置 goal 时使用 [`goal-mode-short.md`](goal-mode-short.md)；短版会要求执行 agent 先读本文件。

## 0. 角色与最终目标

你是 Jity 项目的执行 agent。唯一目标：交付一个可在普通笔记本浏览器中从预置静态世界文件开局并连续游玩的 Jity。

开局只读取、校验并封存 S₀；玩家每次输入后，行动判断、目标识别、被迫反应、骰点准入、组冻结、共同结算、六阶段状态更新、继续推进和中文叙事全部在浏览器内完成；浏览器 TypeScript 内核是运行期唯一的 apply/merge/commit/replay 权威，服务器只存取不透明进度快照，禁用游戏计算端点与保存服务后仍可游玩与本地保存。叙事按用户 2026-11-11 决定原样显示非空模型正文，运行期不检查、不裁改、不程序补写，事实与文风由提示、输入投影、候选、模型或训练在运行前负责。

验收以 R01–R16、至少 20 次真实页面输入、60 秒内出现可读流式正文、单点 300 秒内完成、离线、两设备分叉同步和用户本人在目标设备试玩签字为准；Python v2 内核与 `/world` 规则页降为开发期差分预言机、回归夹具和对照臂。

完成条件不是“代码存在”或“夹具通过”，而是 G8 验收通过并得到用户本人签字。

## 1. 开工前必读与基线检查

仓库根：当前 clone 的根目录（本地为 `D:/others/Jity`）。

按顺序读：
1. `AGENTS.md`
2. `design/goal/goal.md`
3. `design/goal/architecture.md`
4. `design/goal/decisions.md`
5. `design/goal/ledger.md`
6. `design/goal/acceptance.md`
7. `design/README.md`
8. `openspec/config.yaml`

不要先读 historical/superseded 文档；需要背景时按 `design/README.md` 的标签查。

开工检查：
- `git status`：工作树必须干净；有未提交改动先记录，不 reset、不覆盖。
- `git log --oneline -5`：确认包含 `830bbd4f`（Goal v11 文档基线）；代码基线 `695e6bd4`；tag `goal-mode-baseline-20261120` 应指向 `695e6bd4`。
- `openspec list --json` 与 `openspec list --specs --json`：确认 active change 与 spec 清单。
- 若文档缺失或基线不符：先补 G1 文档，不直接开工；补完再继续。

## 2. 不可协商的约束

- 浏览器本地：所有游戏推理、调度、状态计算与校验在浏览器内完成；不调用远程模型或游戏计算 API；服务器只存取进度；禁用保存服务后仍可游玩与本地保存。
- 静态 S0：开局只读取、校验并封存静态世界；不动态生成世界。
- 固定实体集：运行中只更新已登记实体；可在既有大任务下新增小任务；不得新增人物/物品/地点；需要新实体的行动倾向失败。
- 时间线：S₀ + 逐点 Δ；同点同实体合并为一次变化；S_t = apply(S_{t-1}, Δ_t)；可从 S₀ 回放；缓存可重建。
- 排序与共同结算：非关联点按理智升序冻结；关联点保持冻结顺序；先识别目标、准入骰点、冻结整组再统一结算；已行动角色不二次行动，但其骰点仍影响结果。
- 六阶段固定顺序：位置→外貌→任务达成→新小任务→个性→理智；后续阶段读取更新后的工作状态；任务与触发的个性检查覆盖所有角色。
- 理智链：只有任务达成→个性变化→理智重算可改变理智；无事件直加直减；无每回合自动恢复；无个性变化则无理智变化。
- 自动推进：只对主角相关高概率后续行动；一次输入可产生多个点；输入只消费一次；不得用调用次数、异常或暂停伪装正常 handback。
- 叙事边界：只读已提交的 S_{t-1}/Δ/S_t；可省略或暗示未公开变化，但不得写状态、不得发明未结算事实；不设独立角色知识真相库；按 2026-11-11 决定，运行期原样显示非空模型正文，不检查、不裁改、不程序补写。
- 模型输出是候选：模型不设置持久 ID、骰点或阈值；程序负责确定性校验、应用、合并、持久化与回放；拒绝、重试、回退如实记录。
- 方法与资产自由：单/多模型、共享骨干、微调、提示、程序规则、约束解码、检索与编辑均可；禁止固定答案、检索考卷正文、只支持少数命令的流程；记录模型/程序/检索/模板/编辑/重试各自贡献。
- 时间门槛：正常提交到可读流式正文 ≤60 秒；单点完成 ≤300 秒；超过 5 分钟不可接受；记录分阶段时间。
- 验收规模：R01–R16 逐项有代码、运行与页面证据；至少 20 次真实页面输入，覆盖自动链、共同结算、暂停恢复、历史、删除叙事重生；用户本人试玩签字。
- 单一 schema：只使用 `WorldState`/`WorldInitialState`；浏览器按规范编码重算 `stateDigest`，不一致拒绝开局。
- 治理：单一 `agent` 工作树；按 goal line 提交与打 tag；不 force push；不自动合并；代码/数据/模型哈希固定。
- 设备与资产：目标设备 RTX 4060 Laptop 8 GB + Edge；GGUF 走外部下载脚本，仓库只存 sha256/bytes/license 清单与脚本。
- 世界供给：本版只做 `dragon-raja-free-day`；跨世界泛化另开一批。
- 同步部署：单用户 Bearer + 本地/内网服务；服务器只存不透明快照；不做多用户、GC、分页或公网部署。

## 3. 权威与冲突

- `design/goal/decisions.md`：冲突裁决的唯一权威。新决定先写这里，再同步其他文档。
- `design/goal/goal.md`：目标、硬门槛、G1–G8、执行规则的唯一入口。
- `design/goal/ledger.md`：R01–R16 状态的唯一来源。机制存在不等于能力完成；没有证据不写通过。
- `design/goal/architecture.md`：运行期与部署事实。
- `design/goal/acceptance.md`：验收协议。
- `design/README.md`：active/reference/historical/superseded 索引。
- 带 `superseded`/`historical` 横幅的旧文档只作参考，不作为当前任务书。
- OpenSpec change 的 `proposal/design/tasks/specs` 是本次工作包的执行计划，不是新的持久权威；与 `decisions.md` 冲突时，改 change，不改 decisions。
- 不新建第六份权威文档；新设计先放 change 的 `design.md`，稳定后由用户决定是否升级到 `design/goal/`。

## 4. 用 OpenSpec 维护文档并驱动开发（强制）

### 4.1 每个 goal line 一个 change

命名：`goal-g<N>-<slug>`。当前顺序：

- `goal-g3-model-timing`
- `goal-g2-kernel-diff`
- `goal-g4-page-wiring`
- `goal-g5-semantics`
- `goal-g6-narration`
- `goal-g7-sync`
- `goal-g8-acceptance`

每个 change 的流程：

1. 建 change：`openspec new change "goal-g3-model-timing"`；或使用项目 skill `/openspec-propose`。
2. 读状态：`openspec status --change "goal-g3-model-timing" --json`。
3. 按依赖顺序读指令并写 artifact：
   - `openspec instructions "proposal" --change "goal-g3-model-timing" --json`
   - `openspec instructions "design" --change "goal-g3-model-timing" --json`
   - `openspec instructions "tasks" --change "goal-g3-model-timing" --json`
   - 需要能力契约时再处理 `specs`。
4. `proposal.md`：范围、要解决的问题、不做什么、对应 R/G line。
5. `design.md`：引用 `design/goal/goal.md` 与 `architecture.md`，写本次技术决定；不复制整份 goal。
6. `tasks.md`：可执行清单；每项写清验收/证据；实现时逐项勾选。
7. 实现；每项完成记录证据路径。实现时用 `/openspec-apply-change`，或按 tasks 手动执行。
8. 校验：`openspec validate "goal-g3-model-timing" --strict`。
9. 归档：`openspec archive "goal-g3-model-timing" --yes`；或 `/openspec-archive-change`。纯工具/文档变更可用 `--skip-specs`，但要记录原因。
10. 更新 `ledger.md`/`decisions.md`/`design/README.md`；commit + tag。

遵循 `openspec/config.yaml` 的 `context` 与 `rules`；它们适用于对应 artifact。

### 4.2 文档维护协议

- change 开始前：读 `goal.md` + `ledger.md` + `decisions.md`；确认对应 R/G line；把本次要关闭的 R 行写进 proposal。
- change 结束：更新 `ledger.md` 的状态、代码路径@commit、测试/页面证据、缺口、归属 G 线；没有证据不写通过。
- 新决定：追加 `decisions.md`（日期、状态、理由、取代对象、影响文件），再同步 `goal.md`/`architecture.md`/`acceptance.md`。
- 改目标、范围、硬门槛：先问用户；用户确认后写 `decisions.md`，不自行改。
- 证据：放 `artifacts/goal/`；change 的 `tasks.md` 与 `ledger.md` 都要链接；失败也保留。
- 旧文档不删；新增/调整用顶部状态横幅；`design/README.md` 只在新文档或归档时更新。
- 冲突：`decisions.md` 优先；新冲突记 `pending-user`，不猜、不按日期新旧判断。
- 提交：按明确文件路径 `git add`；每个 change/任务提交；每个 goal line 打 tag；不 force push；不自动合并。
- 每次回复结束前：更新文档并提交；未提交的文档变更视为未完成。

### 4.3 OpenSpec 命令清单

```bash
openspec list --json
openspec list --specs --json
openspec new change "goal-g3-model-timing"
openspec status --change "goal-g3-model-timing" --json
openspec instructions "proposal" --change "goal-g3-model-timing" --json
openspec instructions "design" --change "goal-g3-model-timing" --json
openspec instructions "tasks" --change "goal-g3-model-timing" --json
openspec validate "goal-g3-model-timing" --strict
openspec archive "goal-g3-model-timing" --yes
```

若 CLI 不可用：使用项目提供的 OpenSpec skill；两者都不可用时，按同样的 `proposal/design/tasks` 结构手工维护，并在 `decisions.md` 记录原因和替代路径。不能因为工具不可用就跳过文档维护。

## 5. 执行顺序与当前状态

- G1 已完成：文档基线 `830bbd4f`；代码基线 `695e6bd4`；tag `goal-mode-baseline-20261120`。
- 下一条：**G3 模型资产与时间包线**。
- 然后：G2 内核差分 → G4 页面接线 → G5 非叙事语义 / G6 叙事质量（可并行）→ G7 两设备同步 → G8 20 输入交付验收。
- 当前没有 active OpenSpec change；从 G3 建第一个。
- 当前 `frontend/public/models/` 为空；时间包线未证明；叙事质量是最大风险。

G3 的具体交付：

- 外部下载脚本取得 Qwen3-0.6B 与 Qwen3-1.7B 的 GGUF 与 tokenizer。
- 产 sha256/bytes/license/获取方式清单。
- RTX 4060 Laptop 8 GB + Edge 上跑 3 次冷启动 + 至少 10 个真实点（含自动链与一个重负载点）。
- 产 `artifacts/goal/timing-baseline.json`，逐点记录 inputAt/pointCommittedAt/narrationStartedAt/firstReadableAt/pointTextFinishedAt、首 token、最长流式空档、阶段耗时、峰值内存。
- 10 个正常点全部 60 秒内首段、300 秒内完成；不达标登记失败、改模型/调度并复测，不改门槛。

G2/G4–G8 的 scope/验收见 `goal.md` 第 5 节与 `ledger.md` 第 4/5 节。

## 6. 验收与停止

- 硬门槛：20 次真实 `/world-local` 页面输入；60 秒首段、300 秒单点；R01–R16；离线；服务器关闭；两设备分叉；用户本人在 RTX 4060 Laptop 8 GB + Edge 试玩签字。
- 独立验收：用户本人提供 10 次独立输入与读评；叙事 rubric 用用户读感 + 四类跨回合检查。
- 草案参数已删除：35/90%/10/9/32-of-35/3 长输入/18 世界族/1 GB/6 GiB/120 s/40 s，不复活。
- 需要用户决定：改目标/范围/硬门槛；G6 后是否加事实门；模型替换；新增世界族；多用户/公网部署。
- 未签字不宣布完成；失败保留；不删场景、不缩输入、不降门槛。
- 每笔改动按明确路径提交；每个 goal line 打 tag；不 force push；不自动合并。

## 7. 每轮结束必须输出

- 本次做到哪一步；对应 G/R line。
- 证据路径（`artifacts/goal/...`）。
- `ledger.md` 更新了哪些行；`decisions.md` 新增了哪些决定。
- 当前 OpenSpec change 状态（active/archived）。
- 下一步；是否需要用户决定。
- commit/tag。
