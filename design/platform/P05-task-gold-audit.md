# P05 任务达成金标独立核查：标签是对的，基准撑不起 14.8% 的语义结论

**Question.** 语义分支说“原有任务达成标签可能不正确”；它的 `bench-v1` 严格标签是否可信？
如果可信，E57 的 14.8% 能不能当作“模型语义正确率”？新的“正确答案”应该长什么样？

**Setup.** 只读复核语义分支 `semantic-micro-only`（HEAD `6e6e02d9`，报告提交 `a9dd03e5`）：

- 原样快照 `artifacts/goal/semantic-micro/bench-v1.jsonl` →
  `artifacts/goal/platform/task-gold/bench-v1.semantic-branch.jsonl`。
- 读 S01 标准、E54/E55/E56/E57、`build_bench_v1.py`、`eval_bench_v1.py`、
  `goal-verifier-v1-report.json`；不改语义分支、不跑其模型。
- 第二遍读评：对 114 条可判样本逐条按 S01 重判；yes/partial 全部人工核对，no 按任务分组
  逐组核对；结论写入 `task-gold-v1.cases.jsonl`，任务级规格写入
  `task-gold-v1.tasks.json`。

**Data.** `bench-v1` 120 行：`no 105 / partial 6 / yes 3 / skip 6`。可判 114 条只对应
**78 个唯一 (task, goal, fact)**；同任务内重复 **36 条（31.6%）**。覆盖 17 个有目标的
任务；`task_42`、`task_164` 的 6 条样本目标为空。全部 120 条都是旧 LLM 判 yes 的样本。

**Findings.**

1. **标签本身经得起第二遍读评：114/114 一致。** 我确认 yes 3 条（护目镜戴好且确认无裂纹、
   芬格尔换电池并拍到场面、路明非选定地下检修通道并说明掩护）、partial 6 条（护目镜只完成
   佩戴或确认、只拿到护目镜没有装备、只查明小桥通行没有避让证据）、no 105 条。
   所以“旧标签错”不是标注错误，而是**判定标准与样本构造**的问题。

2. **14.8% 不是语义正确率，是负例上的误提交率。** 114 条全部是旧 LLM 判 yes 的样本，
   其中 107 条已被旧系统提交为 achieved；这 107 条里严格只有 3 条 yes，
   **104 条（97.2%）不是 yes**（100 no + 4 partial）。这个数字证明“行为克隆会继承宽松
   提交”，但不能当平衡准确率：yes 只有 3 条，precision/recall 的置信区间极宽。

3. **单事实基准无法表达多子句目标。** 17 个有目标任务里 14 个含多子句、否定或前置条件
   （`task_lu_kit` 的“进入交火区前拿到护目镜与装备”、`task_chu_flag` 的“进入前安排持守与
   信号”、`task_nono_squad` 的双否定、`task_fingel_help` 的条件句）。bench 每条只给
   一个 fact，按构造就不可能完成多个子句，105/114 no 是预期结果，不是模型发现的语义。
   要测“达成”，样本必须是**同一回合的多条事实**；单事实只能测“这一条是否足以达成”。

4. **E57 报告的分母与冻结数据不一致。** 报告写 `bench n=108`（confusion 合计 108），
   同一提交里的 `bench-v1.jsonl` 有 **114 条可判**。`eval_bench_v1.py` 读的是本地
   `experiments/semantic-micro/bench-v1.jsonl`，不是跟踪的 `artifacts/...` 副本；
   报告没有从冻结文件重算。结论方向不变，但 108/114 的差必须在重跑时消除。

5. **36 条同任务重复会放大错误。** `task_lu_kit` 27 行只有 17 个唯一事实，
   `task_lu_route` 25→17，`task_fingel_help` 21→14，`task_nono_squad` 19→12。
   同一事实重复计权，会让“误提交率”与任何微调损失被少数样本主导。

6. **S01 标准基本成立，但条件句缺一个状态。** 对 `task_fingel_help`（若路明非求助）与
   `task_tang_fallback`（被两处射界夹住时），触发条件未出现时应是 `not_triggered`，
   不是 `no`；否则负例里混入“任务本来就没激活”的样本。S01 的“否定只字未提不算遵守”
   与“intent/attempt/partial 不算达成”两条是正确的，应保留。

**Delivered gold（平台侧，供语义 Agent 使用）.**

- `task-gold-v1.tasks.json`：17 个有目标任务的任务级规格——required 子句 id、前置条件、
  否定约束、partial 规则、旧系统的 forbidden shortcuts（走进房间、读地图、提到负责人、
  准备动作等）。`task_42/task_164` 标为缺目标。
- `task-gold-v1.cases.jsonl`：78 条去重后的第二遍读评样本（`verdict` 与 bench 一致，
  附 reason / requiredIds / 是否有否定与前置条件），已用规范化哈希冻结。
- `task-gold-v1.bundles.jsonl`：11 条**多事实**开发夹具（5 yes / 2 partial / 3 no /
  1 not_triggered），按任务规格手工构造，覆盖单事实基准测不到的组合；它们是夹具，
  不是真实运行结果，正式评价仍需真实回合采集。
- `task-gold-v1.report.json`：本页全部计数与差异。
- `tools/experiment_platform/task_gold_eval.py`：对任意 `{id, verdict}` 预测打分
  （exact accuracy、yes 提交的 P/R、误提交列表、按任务汇总）；`not_triggered` 已进
  任务规格的判定表。

**Numbering（按用户提议，避免合并后引用混乱）.**

| 方向 | 前缀 | 现有编号 | 处理 |
|---|---|---|---|
| 实验平台 | **P** | P01–P05 | 不变 |
| 语义微模型 | **S** | S01；历史 E54–E57 | 新报告用 S##；历史 E 号保留但引用加 `semantic/` |
| 叙事微模型 | **N**（新） | E54–E61；已见 N10 | 叙事侧已开始用 N 前缀；历史 E54–E61 保留，合并时重定向 |

冲突映射（必须带分支前缀引用）：E54 = 语义调用审计 / 叙事角色解析；E55 = 语义任务数据集
/ 叙事规则基线；E56 = 语义任务条件分解 / 叙事规则组织；E57 = 语义目标裁决器 / 叙事事件
聚簇。平台此前在 P03/P04 里写 `E57` 均指**叙事**；从本页起引用一律写 `narration/E57` 或
`semantic/E57`。

**Next（需要用户或语义 Agent 动作）.**

1. 语义 Agent 从冻结的 114 条重跑 E57 报告，消除 108/114 差异；解释 6 条空目标样本。
2. 条件任务加 `not_triggered` 状态（平台规格已加；语义 Agent 的训练负例需同步排除未触发样本）。
3. 以 `task-gold-v1.tasks.json` 的 required 子句重写候选生成与裁决；bench 单事实只作
   负例，不作为“达成”正例来源。
4. 平台下一步从真实回合抽多事实证据，按任务规格生成独立 test 集；在此之前 bundles 只
   作开发夹具。
5. 用户裁决：严格标准是否替换旧 14/14 口径；在裁决前产品默认不变，旧口径只作行为对照。

**Artifacts.** `tools/experiment_platform/{build_task_gold,task_gold_eval}.py`；
`artifacts/goal/platform/task-gold/{bench-v1.semantic-branch.jsonl,task-gold-v1.tasks.json,
task-gold-v1.cases.jsonl,task-gold-v1.cases.jsonl.manifest.json,
task-gold-v1.bundles.jsonl,task-gold-v1.report.json}`。P05。
