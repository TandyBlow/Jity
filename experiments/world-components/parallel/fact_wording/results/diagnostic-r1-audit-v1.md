# r1 审计补注（不覆盖原记录）

封存对象：`results/diagnostic-r1-report.md`（sha256 `a416ed2870bde40d…`，11,237 字节）保持不改。本文件是唯一权威的更正说明；凡与本文件冲突的，以本文件为准。

| 对象 | sha256（前 16） | 说明 |
|---|---|---|
| `results/diagnostic-r1-report.md` | `a416ed2870bde40d` | 原报告，封存不改 |
| `artifacts/fact-wording/diagnostic-r1/20261108T150002-a0ed91d4/raw.jsonl` | `616da43f6f9906af` | 170 行原始生成记录 |
| `…/order.jsonl` | `3c413784f69bbbcf` | 实际执行顺序 |
| `…/failures.jsonl` | `e3b0c44298fc1c14` | 空文件（0 次重试） |
| `…/analysis.json` | `a12337dcb2b827f2` | 汇总（判定后生成） |
| `…/run.json` | `695088b391420901` | 运行元数据（进程在结束时写出） |
| `…/env.json` | `44bd4629c909eaf1` | **事后重建**，见 A5 |
| `…/blind/map.json` | `f024ffc249d34d85` | 编码映射 |
| `freeze/comparison-inputs-v3.json` | `a0ed91d4865eda51` | 清单 |
| `comparison-protocol-v3.md` | `b1644af511ee42aa` | 协议 |

---

## A1. “保留 2 条 53 次、3 条 32 次”是字段口径写错

原报告 §2 的“束宽保留完成数：2 条 53 次；3 条 32 次”把 `finishedCount` 当成了保留数。核对结果：

- `beam2.py` 对完成列表执行 `del finished[width:]`（width=2），**保留数恒为 2**；
- 85 条 beam 记录里 `len(retainedFinished)` 全部等于 2（85/85），没有一条超过 2；
- 每条的输出分数等于保留列表里的最高分（85/85）；
- 53 / 32 的分布来自 `finishedCount`，即**累计发出 EOS 的次数**（2 次或 3 次），不是保留数。

**更正**：原字段应写“累计完成次数（finishedCount）：2 次 53 条、3 次 32 条；保留列表恒为 2 条”。这是报告字段命名错误，**不是协议偏离**，判定与计数均不受影响。

## A2. “已穷尽”统一改为“满足束搜索停止条件”

原报告多处写“已穷尽 / 穷尽”。按协议 v3 §1.3，`searchExhausted=true` 只表示**在本宽度 2、最多保留 2 条完成的搜索空间里**满足停止条件（85/85 `stop=rule`），不代表全空间穷举或全局最优。

**更正措辞**：把“已穷尽”读作“满足束搜索停止条件”。原始 `searchExhausted` 字段不动，它是实现层标志。

## A3. 执行版本源码快照

执行版本哈希 `9b4b3946fbb679bf…`（`run.json.runnerSha256`）。本轮通过反向应用“断点续跑”补丁重建了该版本，**逐字节校验通过**：

- 快照：`scripts/snapshots/run_diagnostic-9b4b3946.py`
- 快照 sha256：`9b4b3946fbb679bf6a2f5570bf8cd0be617e45b54d9e16e6fd15b017320be813`（与执行版本一致）
- 当前工作脚本：`scripts/run_diagnostic.py`，sha256 `007999ebf9c00585…`，多出未使用的续跑分支。

因此“只有哈希、没有源码”的情况**没有发生**：源码可复得且已固化。

## A4. 运行目录事故

- 运行开始约 30 秒后，我误用 `rm -rf` 清理“空目录”，删除了该运行目录下的 `env.json` 与 `run.json`；
- `raw.jsonl`、`order.jsonl`、`failures.jsonl` 因被进程占用未被删除；
- 运行未中断；`run.json` 由进程在结束时按内存中的 `run_meta` 重新写出（内容含启动时读到的时间与哈希，`startedAt` 未变）；
- `env.json` 无法由进程重写，**由 `run.json.env` 事后重建**，字节与原始“进程启动时写出的 env”不保证相同（原始文件未留存）。

## A5. 环境记录标记为事后重建

`…/env.json`（206 字节，`44bd4629c909eaf1…`）是事后重建文件，内容取自 `run.json` 的 `env` 块：python 3.12.3、torch 2.7.0+cu126、transformers 4.57.3、sentencepiece 0.2.0、CPU、4 线程。原始 env.json 已被误删，**无法证明它当时与现在字节一致**。

## A6. `方向=平` 写“上来”仍记措辞风险／U

冻结规则不变：这类输出**不改称确定冲突**，判 `undetermined`，附 `direction_wording_risk`。r1 中：

- `t14:f0`、`t18:f0`：两臂同文本、同判 U，类别表里计入 direction；
- `t07:f0` 的束宽输出另记方向风险，但该条**因位置与新增被判失败**——两者并存，不互相替代。

## A7. 判定口径的两处修正已记录

盲判过程中修正过 4 条判定（`t12:f2`、`t24:f3` 两臂）：事实文本本身写“门槛边”，门槛由**事实**授权，输出忠实，不算新增；改判通过并附 `fact_visible_conflict`。修正发生在查看映射之前，两臂同等受影响。详见 `results/t12f2-t24f3-verification-v1.md`。

## A8. 本轮没有新增推理

本审计轮没有启动任何生成；`raw.jsonl` 仍是 r1 那一份（170 行，sha256 `616da43f6f9906af…`）。

## A9. 本轮可支持的结论（范围声明）

在 cf24 这批诊断样本上，束宽 2 相对贪心增加 4 条通过、退化 0 条，耗时约为 2.7 倍。

沿用已登记的训练重叠结果（`cf24-overlap.json`，签名级）：4 条改善里

- `t07:f1`、`t17:f0`、`t23:f2` 为 **seen-fact**（签名在训练池里出现过）；
- 只有 `t15:f0` 为 **independent**（签名独立）。

因此这条收益**不足以支持把束宽设为默认**：改善主要落在见过的签名上，且位置、新增、复述与语病仍在；模型分数提高不能替代事实判定。

状态口径：**诊断完成，独立验收尚未开展**。

