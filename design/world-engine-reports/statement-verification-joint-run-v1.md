# 联合训练结果：general 16 + target 16（2026-11-05）

**结论：两组 dev 都过，general 固定回归恢复，target 固定的合法误拒也降到 0；但 20 源回归仍 0/10，target confirm 的无依据检出降到 18/24。** 这是明显顾此失彼：合法接受恢复了，实际表达的检出收益没有保留。按预定条件，停止当前“单个二分类头覆盖两类材料”的方案，不再逐个错误补样本。

## 1. 方案

| 项 | 值 |
| --- | --- |
| 初始化 | 同一 MiniRBT-H256 基座；不加载旧检查点 |
| 每批 | **general 16 + target 16**，共 32 |
| 更新 | **300 updates**；每 25 步评两组 dev，共 12 次 |
| 数据 | general train 754；target train 160；两组 dev 分别 190 / 40；两组 confirm 固定回归 108 / 48；20 源回归 36 |
| 采样 | 每池无放回循环，耗尽后重洗；general 4800 次抽取 ≈6.37 遍，target 4800 次 =30 遍 |
| 模型/头/损失/优化器 | 不变：mean-pool + linear(2)，CrossEntropy，AdamW，lr 3e-5 |
| 选中 | **step 175 / t_conf=0.50** |
| 耗时 | 52.9 秒（RTX 4060 Laptop） |
| 长度 | p50 132、p90 152、max 183；无截断 |

选中 step 175；两组 dev 分别满足三项门槛：

| dev | 检出 | 合法误拒 | 合法待复核 | 结果 |
| --- | --- | --- | --- | --- |
| general 190 | 95/95 = 1.0 | 0/95 = 0.0 | 0/95 = 0.0 | 过 |
| target 40 | 20/20 = 1.0 | 0/20 = 0.0 | 0/20 = 0.0 | 过 |

两组 dev 的宏平均检出为 1.0；没有用 confirm 调阈值。

## 2. 固定回归：general confirm

已使用的 general confirm 108 条，只评一次：

| 指标 | 值 |
| --- | --- |
| unsupported 检出 | **52/54 = 0.963** |
| 合法误拒 | **1/54 = 0.0185** |
| 合法待复核 | 0/54 |
| unsupported precision | 0.981 |

general 的合法接受基本恢复；这是本臂最明确的改善。

## 3. 固定回归：target confirm

已使用的 target confirm 48 条，只评一次：

| 指标 | 值 |
| --- | --- |
| unsupported 检出 | **18/24 = 0.75** |
| 合法误拒 | **0/24** |
| 合法待复核 | 0/24 |
| unsupported precision | 1.0 |

分类别：

| 类别 | 检出 | 合法误拒 |
| --- | --- | --- |
| body | 6/6 | 0/6 |
| background | 6/6 | 0/6 |
| visible-state | **4/6** | 0/6 |
| extra-action | **2/6** | 0/6 |

合法误拒从 target-only 的 3/24 降到 0；但检出从 20/24 降到 18/24，visible/extra 的漏检更集中。

## 4. 20 源回归（单列）

| 指标 | 值 |
| --- | --- |
| unsupported 检出 | **0/10** |
| supported 合法误拒 | **4/24 = 0.167** |
| unsupported precision | 0.0 |

分类：

- `regression-unsupported` 7 条：**0 检出，7 条全被判 supported**；
- target visible-state unsupported 2 条：**0 检出**；
- target background unsupported 1 条：**0 检出**；
- `regression-supported` 20 条：16 正确、**4 条被误拒**；
- body 1 条 supported：正确。

也就是说：

- 20 源的合法误拒从 target-only 的 17/24 降到 4/24，**下降了**；
- 但 20 源的无依据检出从 9/10 降到 **0/10**，**没有保留检出收益**；
- 这正是“靠接受恢复合法接受”的失败形态，不能算解决实际表达核对。

## 5. 和 target-only 臂的对照

| 项目 | target-only | 联合 16+16 |
| --- | --- | --- |
| target confirm 检出 | 20/24 | **18/24** |
| target confirm 合法误拒 | 3/24 | **0/24** |
| general 迁移评测 298 检出 | 148/149 | — |
| general 迁移评测 298 合法误拒 | 145/149 | — |
| general 固定 confirm 108 检出 | — | **52/54** |
| general 固定 confirm 108 合法误拒 | — | **1/54** |
| 20 源 unsupported 检出 | 9/10 | **0/10** |
| 20 源合法误拒 | 17/24 | **4/24** |

注：general 的 298 迁移评测和 108 固定 confirm 不是同一评估集，不能直接相减；这里只说明联合臂在固定 general confirm 上合法接受恢复，但 20 源检出归零。

## 6. 这轮说明什么

1. **两组 dev 可以同时过**：一个头能拟合两种候选表达分布，句法形式差异本身不是阻断条件。
2. **general 合法接受恢复**：固定 general confirm 53/54 supported 被接受，合法误拒 1/54。
3. **target 合法误拒也降到 0**，但代价是检出 18/24；visible/extra 漏检集中。
4. **20 源实际表达仍 0/10**：所有 20 源 unsupported 都被接受；合法误拒虽降到 4/24，但没有无依据检出收益。
5. 这不是“general 被破坏”的问题；是联合目标下**合法接受与无依据检出没有同时成立**。
6. 因此不能宣布“一个核对模型已兼容两种表达分布”；只能宣布：dev 兼容，固定 confirm 部分兼容，20 源实际表达不成立。

## 7. 决定

按预定条件，联合训练已经显示明显顾此失彼：

- **停止当前单个二分类头覆盖两类材料的方案**；
- 不继续逐个错误补样本；
- 不跑第二轮配比、不改 16+16、不在 confirm 上调阈值；
- 不接 source head、不接服务、不自动删除；
- 新盲确认不准备。

如果继续，下一步应重新检查任务表示和标签边界，而不是继续训练同一个头。两个 dev 同时过只证明“可拟合”，不证明“实际表达可核对”。

## 8. 文件

| 文件 | 内容 |
| --- | --- |
| `artifacts/statement-verification/joint-train-report.json` | 训练/选点/固定回归/20 源回归总报告 |
| `joint-dev.json` | 12 个 step × 50 t_conf 的两组 dev 表 |
| `joint-general-confirm.jsonl` / `-summary.json` | general confirm 固定回归逐例/汇总 |
| `joint-target-confirm.jsonl` / `-summary.json` | target confirm 固定回归逐例/汇总 |
| `joint-regression.jsonl` / `-summary.json` | 20 源回归逐例/汇总 |
| `joint-training-protocol-v1.json` | 固定 16+16 / 300 updates / 25-step eval 协议 |
| `joint-freeze-v1.json` | 协议/数据冻结 |
| `label-compatibility-v1.json` | 候选跨度检查；更正为句法差异、无范围冲突 |
| `ckpt-joint-v1/` | 12 个 step checkpoint + selected（step 175 / t=0.50） |
| `train_verify_joint.py` | 联合训练/选点/评测脚本 |

关键哈希：

```text
joint-training-protocol-v1  20ec731168e95a292579550102ce79f3f90b9efbe1a356c5cc6988ff54c64266
joint-freeze-v1             e264e7a04f451aaf62eb267bb12c5e4ad7b524ea3ee7a9948cbd0f842dbbdc35
label-compatibility-v1      29f1cd55719e050e66bf5efaf7b0f292691b7160a7b6e6d3e9e82fb04f9ed311
new selected.pt             7b8017e46729d473ab8579ea0a1f806a4fff1227acc1845a42f84763944d9f9b
joint-general-confirm       eeae8c2ec99447884398e7a6278f388c8c72f0dd8dfb7bc6d5739740dfa169bf
joint-target-confirm        f4ed5df916ff698262df5ac0aa56667078ac91d20744f971afb0336fef677247
joint-regression            58190a481b807199fb0f7cb7df6c0030be925c1096dbdb8d077a76eba68a8027
```
