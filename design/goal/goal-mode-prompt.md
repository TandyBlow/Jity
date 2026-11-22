# Jity Goal v12：浏览器本地完整可玩（goal 模式长文任务书）

状态：active。日期：2026-11-22。Goal v12 文本基线：`c1f93c99`；tag `goal-v12-final-20261122`。

> 这是长文任务书，供执行 agent 完整阅读。实际设置 goal 时使用 [`goal-mode-short.md`](goal-mode-short.md)；短版会要求执行 agent 先读本文件。

## 0. 角色与最终目标

你是 Jity 项目的执行 agent。唯一目标：交付 Jity——一个中文 TRPG。玩家从预置静态世界文件开局，在浏览器里连续游玩；同一产品覆盖笔记本与移动端两档设备。以下是终态，不分成阶段：

- 开局只读取、校验并封存 S₀；不动态生成世界。
- 玩家每次输入后，行动判断、目标识别、被迫反应、骰点准入、组冻结、共同结算、六阶段状态更新、继续推进和中文叙事全部在浏览器内完成；不调用远程模型或游戏计算 API。
- 浏览器 TypeScript 内核是运行期唯一的 apply/merge/commit/replay 权威；服务器只存取不透明进度快照；禁用游戏计算端点与保存服务后仍可游玩与本地保存。
- 叙事按 2026-11-11 决定（D-004）原样显示非空模型正文；运行期不检查、不裁改、不程序补写。
- 延迟：提交到再次可行动 ≤60 秒；首段可读 ≤60 秒；单点正文完成 ≤300 秒。两档设备同口径，2 分钟不可接受（D-024）。
- 质量：验收回合零硬事实错误（`acceptance.md` 4.2），四类跨回合检查通过。笔记本档 5/5 零硬错；移动档门槛由用户裁定（D-023）。
- 设备两档：笔记本档（独显，基线 RTX 4060 Laptop 8 GB + Edge，语义 0.6B + 叙事 1.7B）；移动档（手机浏览器，单模型约 0.4 GB，验收用当前环境模拟移动条件，真机抽验一次）。
- 同步：单用户两设备从同一快照分叉、选择一支、另一支仍可恢复。
- 验收：R01–R16 各有代码、运行与真实页面证据；≥20 次真实页面输入；离线、服务器关闭、两设备分叉；移动模拟档独立记录。用户签字按 D-019 放弃，除非用户恢复。

完成条件不是“代码存在”或“夹具通过”，而是 `acceptance.md` 的硬门槛全部满足，且未决项（D-022/D-023/D-024）都已由用户裁决并写回 `decisions.md`。

## 1. 开工前必读与基线检查

按顺序读：
1. `AGENTS.md`
2. `design/goal/goal.md`（v12 终态文本）
3. `design/goal/architecture.md`
4. `design/goal/decisions.md`
5. `design/goal/ledger.md`
6. `design/goal/acceptance.md`
7. `design/README.md`
8. `openspec/config.yaml`

不要先读 historical/superseded 文档；需要背景时按 `design/README.md` 标签查。

开工检查：
- `git status`：工作树必须干净；有未提交改动先记录，不 reset、不覆盖。
- `git log --oneline -5`：必须包含 `c1f93c99`（Goal v12 文本）；tag `goal-v12-final-20261122` 指向该提交。
- `openspec list --json` 与 `openspec list --specs --json`：确认 active change 与 spec 清单。
- 若文档缺失或基线不符：先补文档，不直接开工。

## 2. 不可协商的约束

- 浏览器本地：所有游戏推理、调度、状态计算与校验在浏览器内完成；不调用远程模型或游戏计算 API；服务器只存取进度；禁用保存服务后仍可游玩与本地保存。
- 静态 S0：开局只读取、校验并封存静态世界；不动态生成世界。
- 固定实体集：运行中只更新已登记实体；可在既有大任务下新增小任务；不得新增人物/物品/地点。
- 时间线：S₀ + 逐点 Δ；同点同实体合并为一次变化；S_t = apply(S_{t-1}, Δ_t)；可从 S₀ 回放；缓存可重建。
- 排序与共同结算：非关联点按理智升序冻结；关联点保持冻结顺序；先识别目标、准入骰点、冻结整组再统一结算；已行动角色不二次行动，但其骰点仍影响结果。
- 六阶段固定顺序：位置→外貌→任务达成→新小任务→个性→理智；后续阶段读取更新后的工作状态；任务与触发的个性检查覆盖所有角色。
- 理智链：只有任务达成→个性变化→理智重算可改变理智；无事件直加直减；无每回合自动恢复。
- 自动推进：只对主角相关高概率后续行动；一次输入可产生多个点；输入只消费一次；不得用调用次数、异常或暂停伪装正常 handback。
- 叙事边界：只读已提交的 S_{t-1}/Δ/S_t；可省略或暗示未公开变化，但不得写状态、不得发明未结算事实；运行期原样显示非空模型正文，不检查、不裁改、不程序补写。
- 模型输出是候选：模型不设置持久 ID、骰点或阈值；程序负责确定性校验、应用、合并、持久化与回放；拒绝、重试、回退如实记录。
- 方法与资产自由：单/多模型、共享骨干、微调、提示、程序规则、约束解码、检索与编辑均可；禁止固定答案、检索考卷正文、只支持少数命令的流程；记录模型/程序/检索/模板/编辑/重试各自贡献。
- 时间门槛：再次可行动 ≤60 秒；首段可读 ≤60 秒；单点完成 ≤300 秒；超过 5 分钟不可接受；记录分阶段时间。
- 验收规模：R01–R16 逐项有代码、运行与页面证据；至少 20 次真实页面输入，覆盖自动链、共同结算、暂停恢复、历史、删除叙事重生、离线、服务器关闭、两设备分叉。
- 单一 schema：只使用 `WorldState`/`WorldInitialState`；浏览器按规范编码重算 `stateDigest`，不一致拒绝开局。
- 治理：单一 `agent` 工作树；按工作包提交与打 tag；不 force push；不自动合并；代码/数据/模型哈希固定。
- 设备与资产：笔记本档 RTX 4060 Laptop 8 GB + Edge；移动档单模型约 0.4 GB，验收用 `--cpu-throttle` 与 `--gpu-lite` 模拟，真机抽验一次；GGUF 走外部下载脚本，仓库只存 sha256/bytes/license 清单与脚本。
- 世界供给：本版只做 `dragon-raja-free-day`；跨世界泛化另开一批。
- 同步部署：单用户 Bearer + 本地/内网服务；服务器只存不透明快照；不做多用户、GC、分页或公网部署。
- 草案参数：35/90%/10/9/32-of-35/3 长输入/18 世界族/1 GB/6 GiB/120 s/40 s 已删除，不复活。

## 3. 权威与冲突

- `design/goal/decisions.md`：冲突裁决的唯一权威。新决定先写这里，再同步其他文档。
- `design/goal/goal.md`：终态目标、门槛、约束与未决项的唯一入口；不写阶段路线。
- `design/goal/ledger.md`：R01–R16 状态的唯一来源。机制存在不等于能力完成；没有证据不写通过。
- `design/goal/architecture.md`：运行期与部署事实。
- `design/goal/acceptance.md`：验收协议。
- `design/README.md`：active/reference/historical/superseded 索引。
- 带 `superseded`/`historical` 横幅的旧文档只作参考，不作为当前任务书。
- OpenSpec change 的 `proposal/design/tasks/specs` 是本次工作包的执行计划，不是新的持久权威；与 `decisions.md` 冲突时，改 change，不改 decisions。
- 不新建第六份权威文档；新设计先放 change 的 `design.md`，稳定后由用户决定是否升级到 `design/goal/`。
- v11 的 G1–G8 已废弃为执行编号；归档 change 与 tag 仍是证据，能力看 `ledger.md`。

## 4. 用 OpenSpec 管理文档并驱动工作包（强制）

### 4.1 每个工作包一个 change

命名：`goal-<slug>`（例如 `goal-sched-handback`、`goal-mobile-tier`、`goal-narr-finetune`）。不再使用 `goal-g<N>-<slug>`。

每个 change 的流程：

1. 建 change：`openspec new change "goal-<slug>"`；纯文档/工具变更在 `.openspec.yaml` 设 `skip_specs: true`。
2. 读状态：`openspec status --change "goal-<slug>" --json`。
3. 按依赖顺序读指令并写 artifact：
   - `openspec instructions "proposal" --change "goal-<slug>" --json`
   - `openspec instructions "design" --change "goal-<slug>" --json`
   - `openspec instructions "tasks" --change "goal-<slug>" --json`
   - 需要能力契约时再处理 `specs`。
4. `proposal.md`：范围、要解决的问题、不做什么、对应的 ledger 行与未决项编号。
5. `design.md`：引用 `goal.md` 与 `architecture.md`，写本次技术决定；不复制整份 goal。
6. `tasks.md`：可执行清单；每项写清验收/证据；实现时逐项勾选。
7. 实现；每项完成记录证据路径。用 `/openspec-apply-change`，或按 tasks 手动执行。
8. 校验：`openspec validate "goal-<slug>" --strict`。
9. 归档：`openspec archive "goal-<slug>" --yes`。
10. 更新 `ledger.md`/`decisions.md`/`design/README.md`；commit + tag。

遵循 `openspec/config.yaml` 的 `context` 与 `rules`。

### 4.2 文档维护协议

- change 开始前：读 `goal.md` + `ledger.md` + `decisions.md`；确认对应能力行与未决项；把要关闭的行写进 proposal。
- change 结束：更新 `ledger.md` 的状态、代码路径@commit、测试/页面证据、缺口；没有证据不写通过。
- 新决定：追加 `decisions.md`（日期、状态、理由、取代对象、影响文件），再同步 `goal.md`/`architecture.md`/`acceptance.md`。
- 改目标、范围、硬门槛：先问用户；用户确认后写 `decisions.md`，不自行改。
- 证据：放 `artifacts/goal/`；change 的 `tasks.md` 与 `ledger.md` 都要链接；失败也保留。
- 旧文档不删；新增/调整用顶部状态横幅；`design/README.md` 只在新文档或归档时更新。
- 冲突：`decisions.md` 优先；新冲突记 `pending-user`，不猜、不按日期新旧判断。
- 提交：按明确文件路径 `git add`；每个 change/任务提交；每个工作包打 tag；不 force push；不自动合并。
- 每次回复结束前：更新文档并提交；未提交的文档变更视为未完成。

### 4.3 OpenSpec 命令清单

```bash
openspec list --json
openspec list --specs --json
openspec new change "goal-<slug>"
openspec status --change "goal-<slug>" --json
openspec instructions "proposal" --change "goal-<slug>" --json
openspec instructions "design" --change "goal-<slug>" --json
openspec instructions "tasks" --change "goal-<slug>" --json
openspec validate "goal-<slug>" --strict
openspec archive "goal-<slug>" --yes
```

若 CLI 不可用：使用项目提供的 OpenSpec skill；两者都不可用时，按同样的 `proposal/design/tasks` 结构手工维护，并在 `decisions.md` 记录原因和替代路径。不能因为工具不可用就跳过文档维护。

## 5. 当前状态与未决项

- 能力状态看 `ledger.md`：技术线（20 输入、计时、离线、服务器关闭、两设备分叉）已有证据；语义与叙事质量线未通过。归档的 change 与 tag 是证据，不是待办。
- 未决项（未经用户批准不得动手）：
  - D-022 叙事质量路线：定向微调 / 模型自修复第二遍 / 换浏览器运行时 / 再一轮微调 / 改门槛 / 收尾。
  - D-023 移动档门槛：移动档的时间与质量参数。
  - D-024 延迟口径与调度改造：「再次可行动 ≤60 秒」的交还时机与每点调用数改造。
- 未获裁决前，允许做的是与这些决定直接相关的测量、原型与证据记录；不得静默改产品契约、默认模型或门槛。

## 6. 验收与停止

- 硬门槛以 `acceptance.md` 为准；本文不复制流程。
- 用户签字已按 D-019 放弃；除非用户恢复。
- 失败保留、如实登记；不删场景、不缩输入、不降门槛来制造通过。
- 需要用户决定：改目标/范围/硬门槛；D-022/23/24；模型替换；新增世界族；多用户/公网部署。

## 7. 每轮结束必须输出

- 本次做到哪一步；对应的 ledger 行与未决项。
- 证据路径（`artifacts/goal/...`）。
- `ledger.md` 更新了哪些行；`decisions.md` 新增了哪些决定。
- 当前 OpenSpec change 状态（active/archived）。
- 下一步；是否需要用户决定。
- commit/tag。
