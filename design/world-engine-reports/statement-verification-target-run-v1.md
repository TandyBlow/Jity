# 目标表达核对：300-update 训练结果（2026-11-05）

**结论：新 confirm 未通过。** 无依据检出 20/24 达到最低线，但合法误拒 **3/24**，超过“至多 1/24”；合法待复核 0/24。整体不通过，不能宣布职责成立。

旧 `selected.pt` 在同一新 confirm 上更差：检出 7/24、合法误拒 8/24、合法待复核 4/24。新模型有改善，但还不够。

---

## 1. 复看与冻结

- 复看 64 对 / 128 条：36 个模板族各至少一整对；`when / see / through / notcleared` 全部对；confirm 全部 24 对 / 48 条。
- 复核者仍是同一助手，记录为“复看”，不是独立人工金标。
- **判定范围**：标签只判 `candidateText` 在上下文中的含义；`fullText` 只帮助恢复主体/语境，不是授权来源；不判整段正文是否干净。`when` 的时间、`see` 的感知、`through` 的遮挡、`notcleared` 的“还没散”都在候选之外。
- body 9 个族代表正例都是状态/变化描写（勒得发白、湿透、起了青包、划出血痕等），不是只有静态外貌。
- 复看中只做了两处同对内的候选替换（`窗纸补好`→`窗纸揭过`、`窗纸糊好`→`窗纸换过`），避免动作结果与状态重叠；标签仍 unsupported，`labelChanges=[]`。
- 冻结：`split-freeze-target-v1.json`、`training-protocol-target-v1.json`、`review-target-v1-summary.json`。

## 2. 训练

| 项 | 值 |
| --- | --- |
| 初始化 | 同一 MiniRBT-H256 基座；**不加载**旧 general 检查点 |
| 模型/头/损失/优化器 | 不变：mean-pool + linear(2)，CrossEntropy，AdamW，lr 3e-5 |
| 数据 | target train 160；target dev 40；target confirm 48；general 298；regression 36 |
| 更新预算 | **300 updates**；每 **25 步**评 target dev，共 12 次 |
| epochs | target train 160 / batch 32 = 5 steps/epoch；**60 epochs** |
| 实际耗时 | 39.8 秒（RTX 4060 Laptop） |
| 长度 | p50 116、p90 151、max 183；256 上限检查，无截断 |
| 选中 | **step 150 / t_conf=0.50**；dev 1.0 / 0.0 / 0.0 |
| 旧对照 | `ckpt-verify-binary/selected.pt` + 旧 t_conf=0.53；在新 confirm 上只评一次 |

target dev 在 step 150 已达到 1.0 recall / 0 legal rejection / 0 legal pending；step 175–300 也保持 1.0，按“最早 step”选 150。没有早停，训练实际跑满 300 步。

## 3. 新 confirm

| 指标 | 值 | 整数门槛 | 结果 |
| --- | --- | --- | --- |
| 无依据检出 | **20 / 24** | 至少 20/24 | 过 |
| 合法误拒 | **3 / 24** | 至多 1/24 | **失败** |
| 合法待复核 | **0 / 24** | 至多 3/24 | 过 |
| unsupported precision | 0.8696 | 辅助 | — |
| uncertain | 0 / 48 | — | — |

**总体：不通过。**

### 分类别

| 类别 | 无依据检出 | 合法误拒 | 合法待复核 |
| --- | --- | --- | --- |
| body | 5/6 = 0.833 | 0/6 = 0.0 | 0/6 |
| background | 6/6 = 1.0 | **2/6 = 0.333** | 0/6 |
| visible-state | 6/6 = 1.0 | **1/6 = 0.167** | 0/6 |
| extra-action | **3/6 = 0.500** | 0/6 = 0.0 | 0/6 |

整体检出只到 20/24，extra-action 只检出 3/6；合法误拒集中在 background（2）和 visible-state（1）。这正是“总体过线/接近线但目标类别集中失败”的情况。

### 7 个错误（逐例）

**合法被误拒（3）：**

- `tgt:background:confirm:confirm-01:p03:sup`：`海雾从茶盏那边漫过来…`，候选 `海雾`；p(unsup)=0.879。
- `tgt:background:confirm:confirm-02:p01:sup`：`贺川把门闩落下时，夜色正浓。`，候选 `夜色`；p(unsup)=0.973。
- `tgt:visible-state:confirm:confirm-01:p03:sup`：`等水缸满，叶澄把水桶放下。`，候选 `水缸满`；p(unsup)=0.784。

**无依据漏检（4）：**

- `tgt:body:confirm:confirm-01:p02:unsup`：候选 `指甲沾了墨`，事实是 `手背沾了灰`；p(unsup)=0.013。
- `tgt:extra-action:confirm:confirm-01:p01:unsup`：候选 `贺川从灶房搬出鱼筐`，事实是 `从柴房搬出鱼筐`；p(unsup)=0.052。
- `tgt:extra-action:confirm:confirm-01:p02:unsup`：候选 `许砚从墙边取下灯罩`，事实是从窗边；p(unsup)=0.006。
- `tgt:extra-action:confirm:confirm-01:p03:unsup`：候选 `叶澄从岸边拖回缆绳`，事实是从船头；p(unsup)=0.002。

## 4. 旧 selected.pt 对照

| 指标 | 旧检查点 | 新检查点 |
| --- | --- | --- |
| 无依据检出 | 7/24 | **20/24** |
| 合法误拒 | 8/24 | **3/24** |
| 合法待复核 | 4/24 | **0/24** |
| 总体 | 失败 | 失败（合法误拒 3>1） |
| uncertain | 7/48 | 0/48 |

新模型相对旧模型在检出和合法误拒上都有改善，但新模型仍未过合法误拒门槛；不能把“比旧模型好”当成通过。

旧检查点分类别：

| 类别 | 无依据检出 | 合法误拒 | 合法待复核 |
| --- | --- | --- | --- |
| body | 4/6 | 6/6 | 0/6 |
| background | 0/6 | 0/6 | 1/6 |
| visible-state | 0/6 | 0/6 | 0/6 |
| extra-action | 3/6 | 2/6 | 3/6 |

## 5. general 迁移评测（不是能力保持证明）

新模型在 298 条 general 迁移评测（原 general dev + confirm）上：

| 指标 | 值 |
| --- | --- |
| unsupported recall | 148/149 = 0.993 |
| legal rejection | **145/149 = 0.973** |
| legal pending | 0/149 |
| unsupported precision | 0.505 |

也就是说，general 上几乎把所有合法表达都判成了 unsupported。注意：新模型从 MiniRBT 基座独立训练，没有加载旧核对模型；这里是两个独立检查点的跨分布比较，不是同一模型训练前后的灾难性遗忘。可以说 target-only 检查点在 general 迁移集上合法接受差，不能叫“破坏了原有 general 能力”。

## 6. 20 源回归（单列）

新模型在 36 条旧回归上：

| 指标 | 值 |
| --- | --- |
| 20 源/A1 unsupported 检出 | **9/10**（7 条 A1 中 6 条 + 2 条目标 visible 全部） |
| 20 源/A1 supported 合法误拒 | **17/24** |
| unsupported precision | 0.346 |
| 旧回归总体 | 检出提高了，但合法误拒严重 |

分类：

- `regression-supported` 20 条：5 正确、**15 条被误拒**；
- `regression-unsupported` 7 条：6 检出、1 漏；
- `visible-state` 2 条 unsupported：2 检出；
- `background` 4 条：1 unsupported 检出，2 条 supported 被误拒；
- `body` 1 条 supported：正确。

旧 selected 的 20 源回归仍是上一轮的 0/10；新模型把检出提高到 9/10，但代价是 15/20 条合法 A1 表达被误拒。**检出提高不等于解决实际表达核对。**

## 7. 这轮说明什么

1. 给目标表达监督后，模型确实学到了新 confirm 的一部分：检出从旧模型 7/24 提高到 20/24，合法误拒从 8/24 降到 3/24。
2. 但合法误拒 3/24 仍超过 1/24 的硬门槛；**整体不通过**。
3. 检出 20/24 是被 background/visible/body 撑起来的；extra-action 只有 3/6，目标类别集中失败。
4. general 迁移评测的 legal rejection 97.3%，说明 target-only 检查点跨分布失衡；因为是从基座独立训练，不能叫灾难性遗忘或“能力被破坏”。
5. 20 源回归检出 9/10，但合法误拒 17/24；不能用“检出提高”掩盖合法误拒。
6. 没有在 confirm 上调阈值；选中 t_conf=0.50 来自 target dev；confirm 只跑一次。没有第二次预算、没有第二轮训练。

## 8. 决定

- **不接 source head、不接服务、不自动删句、不换 u240。**
- **不跑第二轮训练，不在新 confirm 上调阈值，不补提示词。**
- 这个 target 臂到此结束；如果继续，应先解决“target-only 检查点跨分布失衡、general 迁移合法接受差、目标类别集中失败”的数据和训练表示问题，而不是继续调同一个头。
- 下一轮若要继续，必须重新定义并冻结新的材料和预算；本轮记录不追改。

## 9. 文件

| 文件 | 内容 |
| --- | --- |
| `artifacts/statement-verification/target-train-report.json` | 训练/选择/新老 confirm/general/回归总报告 |
| `target-dev.json` | 12 个 step × 50 t_conf 的 target dev 表 |
| `target-confirm-new.jsonl` | 新 confirm 逐例（48） |
| `target-confirm-new-summary.json` | 新 confirm 指标/整数门槛/分类 |
| `target-confirm-old.jsonl` | 旧 selected.pt 在新 confirm 的逐例 |
| `target-confirm-old-summary.json` | 旧对照指标/整数门槛/分类 |
| `target-general-new.jsonl` | general 298 逐例 |
| `target-general-summary.json` | general 汇总 |
| `target-regression-new.jsonl` | 20 源回归逐例 |
| `target-regression-summary.json` | 回归汇总 |
| `review-target-v1.{jsonl,md}` | 训练前复看 |
| `review-target-v1-summary.json` | 复看范围/判定范围/材料修正 |
| `split-freeze-target-v1.json` | 材料/复看/协议冻结 |
| `training-protocol-target-v1.json` | 300 updates / 25-step eval 协议 |
| `experiments/world-components/n4_corpus_v2/ckpt-target-v1/` | 12 个 step checkpoint + selected |
| `experiments/world-components/n4_corpus_v2/train_verify_target.py` | 训练/选择/评测脚本 |

关键哈希：

```text
pairs-target-v1.jsonl        746c0f0754bbae536d34a513280e714f6c33eb3c92804cb37aec46efac79a603
general-capability-v1.jsonl  259ecbd03f82a33b53a7d57b19b15766eb9f873fad63ee6489e2382be212d5fb
audit-target-v1.json         50f5e9cc1a82ad6aa7a1b4b0c4589836433e9be4265464c7637c93ccf41797c2
review-target-v1-summary    3045018d8df3190e1e537ad53ec9342d877ad67d5ff9ca6e16657b22ab124717
split-freeze-target-v1.json  0c0d3a99ce14a8aec9d6b08c241bbfee26cf857b5a3e2f89de7a31f739f2439c
training-protocol-target-v1  8f38a05196cd5c042a7c98a1a593ee7ebcbebdab2a4eaa571773e09ffb5bf353
new selected.pt              379912a5302d4d1f6372467d29ce805b714d59810f5d3981db136d66706eb7b8
old selected.pt              28b304167f1dd387d11d18634115072183479f5b6d3de186befde8548dffd784
target-confirm-new.jsonl     c907e8825efd993bd212fa68ad1d0342fb29ff4d2f805bec4c7eb491e9257ddb
target-confirm-old.jsonl     845f66196b589457bb4a49855f245b4d8c57e0b82321b3eb0fe023170c9696ce
```
