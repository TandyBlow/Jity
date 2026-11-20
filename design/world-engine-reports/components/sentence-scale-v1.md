# 成句模块数据规模三臂实验（2026-11-06，协议冻结，训练前）

状态：材料与协议冻结；三臂各 120 次优化更新，固定终点，不选点。A-small 不纳入；历史检查点不追找；u240、服务和编辑层不动。

## 1. 三臂

| 臂 | 训练材料 | 训练调用 | 回答 |
| --- | --- | --- | --- |
| A-large | 80 源，逐事实 | 231 | 扩大材料后的安全参照 |
| B-large | 同一 80 源，逐计划组 | 134 | 组级表达是否安全、是否改善表达 |
| B-small | clean-group 原 20 个训练源，逐组 | 42 | 固定预算下扩大 B 数据池有没有收益 |

三臂同基座 Randeng-T5-77M、同 seed 13、同 AdamW/lr 5e-4/warmup 12、同 480 步×累积 4＝**120 次更新**、同 greedy 解码、同 max input 512/max new 128；各自从同一基座初始化，不共享训练后权重。B-small 是**本轮重新训练**，不声称复现旧权重。

## 2. 80 源怎么组成

| 组成 | 源数 | 来源/历史 |
| --- | --- | --- |
| B-small 原训练源 | 20 | clean-group-v1 train 20；19 个 pairs-v2 train，`train-r5` 为 pairs-v2 holdout |
| clean-group 原 dev | 6 | clean-group-v1 dev 6（pairs-v2 dev） |
| pairs-v2 额外源 | 4 | `v03`/`v11`/`v22` pairs-v2 train，`v19` pairs-v2 dev |
| n4 多事实旧训练源 | 50 | n4-group-plan formal-train 中多事实源，取排序前 50/54 |
| **合计** | **80** | |

- **B-small 的 20 个源全部在 80 源内**；B-small 仍是独立训练的 20 源臂。
- 原有干净目标（clean-group 的 20 train、6 dev、10 holdout）**逐字保留**；没有静默重写。新增 54 个 train 源、15 个 fixed、15 个 dev 目标按同一口径新写。
- `t24` 的原 A 目标保留了“纸灯笼的风扯破一角”这个已知语法问题；它只在 regression，不参与训练，也不静默改写。本轮 corrections 为空。
- 新写目标只从现有事实生成，不新增世界、不新增事实；B 组目标不写“随后”，由程序装配。

### 必需的冲突处理：`train-r5`

`train-r5` 属于 clean-group 的 20 个训练源，因此必须进 B-small；但原计划的 15 源 fixed 也包含它。**同一源不能既训练又 fixed**。处理：

- `train-r5` 留在 80 train（B-small 训练）；
- fixed 15 去掉 `train-r5`，补入 `v24`；
- fixed 仍有 6 个多事实源，不是 7 个；其余 9 个是全单组。
- 15 fixed 和 10 regression 都不进入任何一臂的训练或 dev。

## 3. 划分与交集

| 划分 | 源 | 事实 | 组 | 多事实组 | 用途 |
| --- | --- | --- | --- | --- | --- |
| train | 80 | 231 | 134 | 83 | A-large/B-large |
| dev | 15 | 21 | 21 | 0 | 只作交集检查；不训练、不选点、不报质量 |
| fixed | 15 | 31 | 25 | 6 | 固定留出；与 regression 分开报 |
| regression | 10 | 37 | 20 | 13 | 旧回归，单列 |

交集：`train∩dev=0`、`train∩fixed=0`、`train∩regression=0`、`dev∩fixed=0`、`dev∩regression=0`、`fixed∩regression=0`；`B-small ∩ train = 20`，`B-small ∩ dev/fixed/regression = 0`。

dev 是 15 个 n4 旧训练中的全单组源，只用于检查不相交；**没有用于选点或质量结论**。

## 4. 固定预算与采样

- 每臂 480 次训练调用、每 4 次调用一次更新，共 120 次更新；固定最后一个更新点，没有早停。
- 采样：每轮把该臂全部训练调用洗牌（seed+epoch），拼接后截断 480 次。A-large 唯一调用 231（480 次约 2.08 遍）、B-large 134（约 3.58 遍）、B-small 42（约 11.43 遍）。
- 这三组数只是计划池大小；**实际是否覆盖全部单元，以训练脚本逐次写出的 `sampled_calls.jsonl` 和 `sampling_summary` 为准**，不从“480 大于单元数”直接推出。训练后报告未抽到的 unit、事实曝光和目标 token；不临时加步数。
- “扩大”口径是 **B-small 的 20 源 → B-large 的 80 源**；36 是上一轮全部划分的来源数，不是本轮训练源数。

## 5. 评价顺序

1. **B-large 对 A-large**（fixed 15、regression 10 分开）：
   - 多事实组 **B-only 安全损失 = 0**；
   - 表达胜出不少于失利；
   - 单事实组无退步（fixed 19 个单组、regression 7 个单组）。
2. **B-large 对 B-small**（同一 fixed/regression 评价集）：
   - 逐例比较遗漏、归属、重复、新增和表达；
   - 判断固定 120 次更新下扩大 B 数据池的效果；
   - **不称等事实曝光对照**：B-large 每次组调用承载的事实更多，训练曝光不同。

fixed 15 只有 6 个多事实源，联合表达结论只据此限定；其余 9 个 fixed 单组只作保持性检查。regression 的 10 源单独报，不与 fixed 合并成泛化成绩。没有收益就照实结束，不追加配比或步数实验。

## 6. 成本

目标编写/复核 + 复看仍按 8 人日上限控制；三臂训练按 1 GPU 日上限。没有新建世界、服务或审计系统。

## 7. 冻结物

- 材料：`artifacts/world-components/organize-wording/sentence-scale-v1.jsonl`
  - sha256 `2f537830797986b7678566d0f90ff605749a7ad8f0aadef34cf7c6cd27f43816`
- 冻结：`artifacts/world-components/organize-wording/sentence-scale-freeze-v1.json`
- 构建脚本：`experiments/world-components/organize_wording/build_sentence_scale.py`
- 训练入口：`experiments/world-components/organize_wording/train_sentence_scale.py`
