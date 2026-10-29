# D1：AI 独立标注、v3 冻结与分支判定

日期：2026-10-29。分支：`world-components`。范围：D1 标注流程与既有输出重评分；未运行训练、N2/N3 新模型实验或浏览器接线。独立审查签字已记录：C 审查者对 `dd2a513` 签字关闭，见 [`signoff-dd2a513.md`](../../../artifacts/world-components/signoff-dd2a513.md)。

## 1. 结论

- 两个不继承原会话的 AI 标注任务分别完成 16 项、92 条事实的三分类标注；各自 must 32、may 40、omit 20。
- 原始两份标签 92/92 一致，Cohen's κ＝1.0；分歧 0，因此无待裁决项。已冻结 `labels-v3.jsonl` 与 `n2-labels-v3.json`。
- v3 与 v2 的 must 集合差异为 **0/16 项**，未超过 >2/16 的门，沿用既有 N3 16 项输入。
- P1-rule 的 must-R 为 **1.0**，must-P 为 **0.433333（macro）／0.421053（micro，32/76）**；16 项中满足降级条件的项数为 0，不能据此降级 N2 或转移资源。逐项和 macro 两种解释均不触发分支。
- 六个既有实验臂在 v3 的逐项 D1 判据下均为 **0/16**；不宣布任何 N2 模型通过。Qwen 的 must-R 为 0.875、must-P macro 为 0.459375。

冻结标签只解决本批判据的来源与一致性；κ 不是语义正确性、模型质量或产品完成度的证明。

## 2. 标注身份与协议变化

本轮经项目负责人明确安排，由 AI 执行独立标注。原 rubric 写有人工／实现者与审查者分工，本轮的参与者变更记录在 `annotation/d1-ai-protocol.json`，不回写已登记 rubric，也不改变标签定义、κ≥0.7 或 D1/D2 分支门槛。

两位 AI 标注者分别在无继承会话的新任务中，只读取同一套已哈希的 rubric、盲表和空模板，不读取 v2 标签、逐项模型输出、实现者标签或彼此标签。两份原始标签保留逐条理由及身份声明。模型家族没有作异构承诺，共同偏差仍可能存在；这是 **AI 独立标注，不是人工评测或真人双盲实验**。

原 `labels-c-impl.jsonl` 及其暴露记录保留为历史，本轮 κ 不使用它。协调人和 C 审查者均已有旧信息暴露，不被计为盲标者；协调人汇总流程，C 审查者审查冻结证据。两个 AI 的原标签在汇总后未按一致度或模型得分修改。

AI-A 在原标签提交并封存后，另参与只读的计算与工具核验；其后续材料暴露不计入标注阶段的盲性声明，原标签与身份文件的字节哈希保持不变。这不代替 C 审查者的最终独立复审。

## 3. 文件与复跑

下列路径均相对于 `experiments/world-components/n2_selection/`：

| 材料 | 文件 |
| --- | --- |
| 不变的原始输入登记 | `annotation/manifest.json`；rubric SHA-256 为 `69f3f4f1…` |
| 本轮执行协议 | `annotation/d1-ai-protocol.json` |
| 两份原始标签 | `annotation/labels-ai-a.jsonl`、`annotation/labels-ai-b.jsonl` |
| 身份与暴露声明 | `annotation/identity-ai-a.json`、`annotation/identity-ai-b.json` |
| 冻结标签 | `annotation/labels-v3.jsonl` |
| κ／冻结工具 | `annotation_kappa.py` |
| v3 专用重评分工具 | `recompute_must_v3.py`；旧 `recompute_must.py` 仍保留为 v2 历史工具 |

在 C 仓库根目录执行：

```bash
python -X utf8 experiments/world-components/n2_selection/annotation_kappa.py --selftest
python -X utf8 experiments/world-components/n2_selection/recompute_must_v3.py --selftest
python -X utf8 experiments/world-components/n2_selection/annotation_kappa.py --labels-a labels-ai-a.jsonl --labels-b labels-ai-b.jsonl --adjudicated labels-ai-adjudicated.jsonl --protocol d1-ai-protocol.json
python -X utf8 experiments/world-components/n2_selection/recompute_must_v3.py
```

无分歧时不需要创建裁决文件；若出现分歧，原始 κ 达标后仍需对全部分歧逐条裁决，再执行冻结。原始 κ 不达标则回到 rubric 讨论，不以裁决后的相同标签重新计算并冒充原始一致度。

产物位于 `artifacts/world-components/`：

- `n2-annotation-status-pre-ai.json`：保存本轮前的待标注状态。
- `n2-annotation-status.json`：本轮当前状态。
- `n2-labels-v3.json`：标签、κ 混淆矩阵、must 差异门、参与者身份、输入与工具哈希。
- `n2-must-v3.json`：六臂逐项与 macro/micro 指标、完整精度判门、D1 分支结果和来源哈希。

v3 重评分明确替换 must/may/omit 三类，包含可见但按 rubric 不应描述的他人事实；旧 v2 `target` 只作诊断。选中 may 仍计入 must 精度分母。报告中 P1-rule 有 4 次 omit 命中，不能继续以旧“视角合法”成绩视为 v3 通过。

## 4. 可复核性与工具检查

工具自检覆盖三分类一致度、裁决覆盖、v3 标签替换、空选择、未知／重复编号、非法输出、精度边界、未冻结、坏哈希及过期冻结状态。分支门使用完整精度，不用四舍五入后的展示数字判定。

本轮增加 AI 身份与输入暴露检查、冻结与当前状态绑定；当后续重跑低 κ 或缺裁决时，旧冻结文件虽作为历史保留，重评分不能将其当作当前有效结果。裁决合法标签允许使用三分类中的第三类，不受旧工具的二选一限制。

局部 `.gitattributes` 固定原登记材料的 CRLF／LF 形式，并按原字节保存新标签与证据，避免跨平台检出后哈希变化。原 v2 标签、选择输出及既有模型归档的语义内容不变；原 rubric、盲表和空模板的登记哈希不变。没有新增模型预测。

## 5. 后续交接

1. **已完成（2026-10-29）：** C 审查者复核本轮 AI 协议、原始标签、κ、冻结哈希和 D1 分支判定，对 `dd2a513` 签字关闭；记录见 [`signoff-dd2a513.md`](../../../artifacts/world-components/signoff-dd2a513.md)。
2. D1 未触发降级，N2 模型路线仍保留；本轮没有启动训练或自动消耗正式留出集。
3. D2 继续准备 8 项能力样本（4 项含时间、4 项双人同事件）、grouping/coref gold、隔离记录、指标和 prompt 冻结，然后才运行 N3 模型臂；16 项与 8 项分开报告。
4. D2 原协议中的人工 gold 要求没有因本轮 D1 的 AI 执行安排而自动变更。若后续仍用 AI 生成或复核，须另行明确标识和审查方法。
5. N4 留出集保持封存，浏览器端到端、指代消费和生产接线仍是原待办。
