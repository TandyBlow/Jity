# P08 叙事内容选择与句间组织评价集

**Question.** 叙事臂除了“事实覆盖/结果标签”，能不能分别测“该选哪些事实”和“句子怎么组织”？
把内容选择与组织拆开，避免用字符 F1 或单一覆盖率代替质量。

**Setup.** 从平台独立留出集 `narration-holdout-v1`（162 点，事实块不在语料/开发 bundle）生成
`narration-selection-org-v1.{dev,test}.jsonl`：40 dev / 122 test。每条记录：

- `expected.mustSelect`：事实块中必须被选中的从句（过滤玩家动作行、长度 ≤4）。
- `expected.outcomes`：结算里的结果标签（本留出集只有 1 条带标签，结果指标只作方向）。
- `expected.order`：相邻 mustSelect 从句的先后约束；同一句内合并不算违序。
- `constraints`：相邻同主语句 0、编造人名 0、8-gram 重复 ≤0.02、失败/部分完成必须有线索词。
- `input.prompt/factsText/resultLines`：与留出集相同的冻结输入。

**Metrics（`narration_org_eval.py`）.**

- 选择率：mustSelect 从句被候选覆盖（二元组 ≥0.5）的比例。
- 结果标签率：失败/部分完成角色句是否带线索词。
- 编造：事实/结算之外的人名、数字。
- 同头：相邻句以同一人物名开头。
- 重复：8-gram 重复率。
- 违序：两个都被选中的从句，候选中的首次出现顺序与事实顺序相反（同句合并豁免）。

**Baseline.** 用记录正文（历史 LoRA/基座混合）在 5 条 dev 上做冒烟：选择率 0、结果率 0，
原因是这些历史输出只有 50–70 字、没覆盖事实块；这不是模型排名，只验证打分链路。正式
评价需要叙事 Agent 提供 `{id,text}` 预测文件。

**Usage.**

```bash
python -m tools.experiment_platform.narration_org_eval \
  --set artifacts/goal/platform/eval/narration-selection-org-v1.test.jsonl \
  --predictions arm-outputs.jsonl
```

**Caveats.** 选择/顺序金标由事实块与结算构造，不是人工逐句标注；`mustSelect` 含全部长事实，
因此规则/聚簇臂选择率天然高，微模型的价值在组织与长度；结果标签在独立留出集只有 1 条，
结果率只能作方向；test 分片不要在调参时反复使用。

**Artifacts.** `artifacts/goal/platform/eval/narration-selection-org-v1.{dev,test}.jsonl`、
`.manifest.json`、`.summary.json`；`tools/experiment_platform/{build_narration_org_set,
narration_org_eval}.py`。P08。
