# P08 叙事内容选择与句间组织评价集：事件必选、静态可选、run 分组切分

**Question.** 叙事臂除了“事实覆盖/结果标签”，能不能分别测“该选哪些事实”和“句子怎么组织”？
把内容选择与组织拆开，避免用字符 F1、单一覆盖率或“复述全部静态描述”代替质量。

**Setup.** 从平台独立留出集 `narration-holdout-v1`（162 点，事实块不在语料/开发 bundle）生成
`narration-selection-org-v1.{dev,test}.jsonl`。旧版 40/122 按 id 哈希切分、把全部静态事实设为
`mustSelect`，已撤回——那会奖励复述世界描述，且 99.2% 的 test 从句在 dev 出现过。现版：

- **切分单位是 run，不是样本 id**：53 个来源 run 按 sha1 排序取前若干，直到 dev ≥20% 样本；
  结果 **32 dev（9 runs）/ 130 test**，同一 run 的点不跨分片。
- **`mustSelect` = 本回合结算事件**（`expected.resultLines` 解析出的 actor/action/outcome），
  平均 1.03 条；**31 条没有结算事件**的样本 `selectionApplicable=false`，不计入选择率分母。
- **`optional` = 静态世界/物品/人物描述**，平均 10.4 条，不要求出现；单独报 `optionalRate`，
  不再混进 mustSelect。
- **`avoidRepeat` = 同一 run 更早正文已说过的静态事实**（按位置索引读取源 run 的 point/narration
  正文，bigram ≥0.5 判定），平均 1.15 条，62 个样本非空；重复率另报，越低越好。
- **负例**（由本样本事实构造，用于校准打分器）：人物错归属（换 actor）23 条、否定丢失
  （如 `没有→有`）148 条、事件顺序反转 24 条。test 分片 20/116/21 条。
- `constraints`：相邻同主语句 0、编造人名 0、8-gram 重复 ≤0.02、失败/部分完成须有线索词、
  人物错归属 0、否定丢失 0。
- `input.prompt/factsText/resultLines`：与留出集相同的冻结输入。

**Metrics（`narration_org_eval.py`）.**

- `selectionRate`：mustSelect 事件动作被候选覆盖（bigram ≥0.5）的比例。
- `optionalRate` / `avoidRepeatRate`：静态事实被覆盖 / 已说过的事实又被重复的比例。
- `attributionMismatches`：事件动作匹配到句子，但该句不含正确 actor、含其他已知人名。
- `negationLost`：带否定词的 optional 事实匹配到句子，但该句没有否定词。
- `orderViolations`：两个都选中且可区分的事件，候选中的首次出现顺序与事实顺序相反
  （同句合并豁免）。
- `outcomeRate`、编造人名/数字、相邻同头句、8-gram 重复。
- `negativeDetection`：每条负例必须被对应指标抓到；`negativeMisses` 列出漏检。

**Calibration（test 130 条，自动跑）.** 人物错归属 20/20、否定丢失 116/116、顺序反转
21/21 全部检出，`negativeMisses=[]`。这说明三个指标不是“写了但抓不到”。

**Split 泄漏检查（test vs dev）.** test 事件 137 条：36 条（26.3%）在 dev 出现过，71 条
（51.8%）与 dev 事件 bigram ≥0.5；这是同一世界/同一任务模板的重复，不是同一条事实块。
静态 optional 事实仍几乎 100% 重叠——这正是把它们降为 optional 的原因。选择率应主要看
事件，且报告 `devEvents=30` 的规模限制。

**Baseline（仅验链路，不作排名）.** 用记录正文（历史 LoRA/基座混合）在 test 130 条上：
selectionRate **0.187**、optionalRate 0.09、avoidRepeatRate 0.535、attributionMismatches 3、
negationLost 0、orderViolations 2、invented 0、sameHead 5、repetition8 0.004、平均 73.5 字。
历史正文只覆盖约 19% 的结算事件，且重复了 53.5% 的已说事实；这不是模型排名，正式评价
需要叙事 Agent 提供 `{id,text}` 预测文件。

**Usage.**

```bash
python -m tools.experiment_platform.narration_org_eval \
  --set artifacts/goal/platform/eval/narration-selection-org-v1.test.jsonl \
  --predictions arm-outputs.jsonl \
  --out arm-eval.json
```

**Caveats.** 选择/顺序金标由结算记录与事实块构造，不是人工逐句标注；事件动作在不同 run 间
有模板重复，run 分组只能消除同 run 泄漏，不能消除同世界重复；`avoidRepeat` 依赖源 run 的
更早正文，源文件缺失时为空；结果标签在独立留出集只有 1 条，结果率只作方向；31 条无结算
事件样本只能测组织/编造，不能测选择；test 分片不要在调参时反复使用。

**Artifacts.** `artifacts/goal/platform/eval/narration-selection-org-v1.{dev,test}.jsonl`、
`.manifest.json`、`.summary.json`、`narration-selection-org-v1.recorded-eval.json`；
`tools/experiment_platform/{build_narration_org_set,narration_org_eval}.py`。P08。
