# D2 程序对照臂（规则臂）方案

日期：2026-10-29。提交人：C 实现者。状态：**方案，待 C 审查者复审**——复审通过前不实现、不运行。
基线：`world-components@f9c1190`（= origin，已核实）。
工作区状态：仅一份审查者未提交文件 `artifacts/world-components/signoff-f9c1190.md`，按指令原样保留；全部冻结产物在位，未改动。
范围：本轮只交付本方案；0.6B 真实推理、解码配置报批、模型 runner 钉定继续暂停；不改 prompt、gold、判据、冻结样本或已有签认。

## 1. 程序对照（生成器规格）

**输入**：与现有条目同形的 JSONL 行（`itemId`、`viewpoint`、`facts`、可选 `target`）。已选子集：gate8 = 条目 `facts` 全集；diagnostic16 = `target ∩ facts`（按 facts 输入序，与 runner 现行口径一致）。

**输出**：N3 窄形状 `{"itemId", "sentences": [{"index", "factIds", "coreference": [{"mention", "refersTo"}]}]}`，字段与 [component-contracts.md §5.2](component-contracts.md) 完全一致，无新增字段。

**R1–R6 生成算法**（按 [d2-gold-rubric.md](../../../experiments/world-components/n2_selection/annotation/d2-gold-rubric.md) 的冻结约定独立实现）：

| 约定 | 算法 |
| --- | --- |
| R1 实体内聚 | 按 `entityId` 分桶（每实体一组，桶内保输入序）；无 entityId 事实（time）暂挂待 R3 |
| R2 同事件合并 | 对 `task_achieved` 按 `goal` 逐字相等建实体并查集，合并具传递性（A~B、B~C ⇒ A~C） |
| R3 时间归属 | time 并入输入序紧邻前驱所在组；首位 time 并入首个含 entityId 事实的组（与冻结标注解释一致） |
| R4 其余独立 | 未被 R2 合并的实体各自成组 |
| R5 排序 | 组间按各组最小输入序号升序；组内按输入序号升序 |
| R6 指代 | 组内每条含 entityId 事实按 factIds 顺序产 `{mention: 登记名, refersTo: entityId}`；time 不产条目 |

**独立性声明**：生成器**不复用** `d2_metrics.build_gold_row`（该函数是 gold 约定的程序化实现，复用它生成会使门同义反复）。规则臂从 rubric 文本独立实现；`build_gold_row` 仅作**事后差分核对**——两者在全部已登记输入上的输出必须逐条一致，差分结果入归档。已签认指标工具字节不动（`a3a349b9…`），规则臂导入其评分与形状函数（`evaluate` / `sentence_shape_problems` / `check_gold_sha`）但生成路径零依赖。

**禁读声明**：生成路径不读取 gold、AI 标签、`build_gold_row` 或任何按条目 ID 的分支；来源仅为本条目的 facts 子集与 rubric 常量。

**异常与不支持范围**（显式标记，不静默补造）：

| 输入 | 行为 |
| --- | --- |
| 未知 kind / 缺 factId / 重复 factId / task_achieved 缺 goal 或非字符串 | `ill-formed`，拒绝生成该条目，归档单列 |
| 首位 time 且全表无含 entityId 事实 | `edge: time-orphan`，time 单独成组，报告单列 |
| 连续多个 time 事实 | 每个 time 按 R3 归属（后一个 time 的前驱是前一个 time，同组），另标 `edge: consecutive-time` |
| 全表无含 entityId 事实且无 time | 空计划，`edge: no-entity` |
| 同名不同 entityId | 按 entityId 分组；coreference 同名不同 refersTo 如实输出（歧义渲染列入 N4-coref 未验证，见 §4） |

## 2. 评价口径

- **gate8**：冻结 gold（`cb86aa46…`，钉值取自冻结记录）＋现行 H1/H2/G1–G4 pooled 口径与通过线（H1/H2 全过＋G1≥0.80＋G2≥0.80 且代词位点产出≥0.50＋G3≥0.75；G4 只报告）。**diagnostic16**：仅 H1/H2，`gate=false`，独立归档。两者分母不合并。
- **B1/B2 对照单列**：复用 `run_n3_baselines.plan_b1/plan_b2` 既有实现，在同一指标下报告（历史参考值 B1 G1F1=0.5333/prod=0.25/G3=0.0、B2 0.0/0.0/0.25，均不过线）；对照数字只报告，不计门、不计入规则臂结论。
- **绑定门复用**：直接导入 `run_n3_arm.py` 的 `check_items_binding`、`check_metric_tool`、冻结记录 gold 钉值校验——同一实现，不复制逻辑。门失败（输入漂移、gold 错钉、指标工具漂移）即拒绝执行，退出码沿用 runner 约定。
- **归档**：逐项原始计划全文、逐项 outcome、failureClasses、B1/B2 对照块、差分核对（规则臂 vs `build_gold_row`）结果、计时（§6）。
- **含义限定**：规则臂在 8 项过线仅证明程序符合冻结机械约定（gold 即按同一约定标注）；不宣称 N3 模型能力、自然叙事质量、N4 质量或生产可用。

## 3. 独立探针（全部合成条目，不依赖 8 项固定答案）

| 探针 | 构造 | 断言 |
| --- | --- | --- |
| T-P1 传递合并 | A-B 共 goal₁，B-C 共 goal₂（A-C 无共同 goal） | 三实体同一句组 |
| T-P2 time 居首位 | time 位于输入序 0 | 并入首个实体事实所在组 |
| T-P3 输入序变化 | 同一事实集合两种输入序 | 组集合不变；组内序随输入序可预期变化 |
| T-P4 重名不同实体 | char_a/char_b 登记名相同 | 两组独立；coreference 同名不同 refersTo |
| T-P5 非法输入 | 未知 kind / 重复 factId / 缺 goal | `ill-formed` 拒绝，不产出计划 |
| T-P6 未登记边界 | 连续 time；全表无实体；首位 time 且无实体 | 分别报 `consecutive-time` / `no-entity` / `time-orphan`，不静默补造 |

探针条目使用新来源合成命名，断言内嵌 `--selftest`，不读取 8 项答案或 gold。

## 4. N4 接线边界

- **事实**：`n3cap-07` 冻结 gold 合并组为 **5 事实**句组，超出 N4 已验收的单句组 1–4 事实范围。
- **处理（拟，复审可改）**：规则臂归档对 `len(factIds) > 4` 的组标记 `n4_out_of_range: true` 并单列清单；**不修改 gold 适配 N4**。提供可选程序回退（超限组按输入序切成 ≤4 事实的连续段），回退输出带 `fallback: true` 标记并单列，**不记作任何通过**；切分计划喂 N4 的实际渲染效果列入未验证。
- **coreference**：N4 当前 `render_input` 不消费指代条目；规则臂产出的指代建议（含重名歧义）对 N4 渲染无效果，跨句/组内指代表达列为**未验证**（归属既有 N4-coref 待办）。

## 5. 隔离与可选模型臂

- **隔离声明**：冻结 8 项（含其改名派生）、16 项开发集、N4 封存留出集、B 全部已校准样本及其派生，均不得用于未来任何训练或调参。规则臂为确定性程序，不涉及训练。
- **模型臂前置问题**（本方案不预设训练；提出时须先回答）：针对规则臂哪些**未覆盖的真实需求**（例：非逐字 goal 的事件归并、指代位点的语义选择）；报告必须三分列——模型原始输出、程序后处理、规则对照——不得合并归因。

## 6. 成本与交付

- **计时口径**：离线 CPU，每条目生成 wall time（`perf_counter`）与整批总时长入归档；与模型推理耗时不可比，不混报。浏览器整链（wllama + N4 浏览器端到端）属未来独立批次，当前**未测**。
- **拟新增文件**：
  - `experiments/world-components/n2_selection/n3_rule_arm.py`（生成器＋绑定门复用＋探针＋CLI）
  - `artifacts/world-components/n3-rulearm-gate8.json`、`n3-rulearm-diag16.json`、`n3-rulearm-probes.json`（运行归档）
  - 本方案文档（已随本笔提交）
- **登记内容**：规则臂输出归档哈希登记于预登记修订记录（新增 `ruleArm` 段）；冻结记录不动。
- **验证命令**：`n3_rule_arm.py --selftest`（含 §3 全部探针）；`n3_rule_arm.py --scope gate8 --out ...`；`--scope diagnostic16 --out ...`；输出与 `build_gold_row` 差分核对结果在归档中可查。
- **风险与未完成项**：① 规则臂与 gold 同构，过线是构造性的——价值在对照基线、探针健壮性与 N4 边界标定，不在"成绩"；② N4 >4 事实切分接线未验证；③ 指代表达未验证（N4-coref）；④ 模型臂未排期，前置问题未回答；⑤ 规则臂重名指代歧义在 N4 渲染层未验证。
