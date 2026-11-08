# c5 收尾说明（供父分支汇总）

## 1. 任务与阶段

| 项 | 值 |
| --- | --- |
| 编号 | c5（`exp/c-group-wording`） |
| 对应设计 | R11 多事实组表达 |
| 阶段 | **有实验结果**（不训练；未接线、未做浏览器验收） |
| 实验最终提交 | `8e00b41`（两批结果、19 组汇总、清单）；本收尾说明是其后的一份文档提交 |
| 汇总文件 | `summary-19-v1.md` |

## 2. 结论（三类，按冻结协议）

**已证明（限定：该 784M 检查点、这 19 组夹具）**

- S（逐事实生成 + 程序组织）事实错误 **0/19**，可读性自然 **18/19**。
- J（整组联合）事实错误 **2/19**，可读性自然 **17/19**。
- 两批 J 臂共 16 行整行装配文本与 784M 归档逐字节一致，比较对象是真实的归档输出。

**已失败**

- J 复现了两条归档事实错误：GW-07 `t24` 添写“衣角”；GW-09 `v20` 漏理智 f1。
- S 仍保留 GW-07 的表达瑕疵：逐事实句子写成“排水沟的里面积了泥”，多一个“的”；组织器不改写句内语法，该条可读性记“可用但生硬”。

**无法判断**

- 新场景泛化（本轮 19 组全部来自旧材料，fixed 6 组也只是训练留出，不是新分布）。
- 其他检查点效果（77M 权重在训练时未保存，本地无同源检查点；单 784M）。
- 原安全门是否通过（原门是“B 对 A-large-77 的 B-only = 0”，比较两个不同检查点；本表是同一检查点的两种调用方式，S 是“模型 + 程序组织”的组合，不是训练出的接收者）。

## 3. 勘误一致性

第一批核验表曾把 GW-07 的 S 文本误写成“排水沟里面积了泥”，正确原文是“排水沟的里面积了泥”。
三份文档已统一更正并加勘误段：`review-table-v1.md`、`result-v1.md`、`README.md`。
统一后的计数：S 自然 18/19（第一批 9/10 + 第二批 9/9）；事实层计数不变（S 0 漏项、0 添写）。
自动检查见 `verify-delivery-v1.json` 的 “wrong GW-07 quote only in errata” 与 “S natural 18/19 in README”。

## 4. 哈希清单的用途

| 文件 | 用途 |
| --- | --- |
| `freeze-v1.json` / `freeze-b2-v1.json` | 两批输入冻结（prompt、样本、检查点/材料/组织器哈希）。只读，不再改。 |
| `freeze-v1.sha256` / `freeze-b2-v1.sha256` | 冻结文件自身的哈希。 |
| `manifest-v1.json` | 第一批交付时的文件哈希快照（历史，不是当前状态）。 |
| `manifest-v2.json` | 当前交付文件的哈希清单（收尾后以此为准；不含 manifest 自身和下方生成报告）。 |
| `verify-delivery-v1.json` | 本次收尾核验的逐项结果：清单、冻结、原始输出、GW 覆盖、勘误一致性。它是每次运行生成的报告，不列进 manifest-v2，避免清单引用自身。 |

## 5. 交付核验结果

`verify_delivery_v1.py` 共 32 项检查：

- `manifest-v2.json` 列出的文件全部存在且哈希一致，没有未列文件；
- `freeze-v1`（`0d8db13f…`）、`freeze-b2-v1`（`34d7be71…`）、`run-v1/results.json`（`77d71287…`）、`run-b2-v1/results.json`（`4464b03c…`）哈希与登记一致；
- 检查点 `6abd0cdd…`、组织器 `867dd6dd…`、运行脚本 `051f483b…`、材料 `2f537830…` 在冻结和当前文件两侧一致；
- `GW-01`–`GW-19` 连续、无重复；fixed 6 组与 regression 13 组分别与材料里的多事实组集合**完全相等**（无缺、无多）；
- 两份审计的样本集合与各批冻结一致，确定性标志为真；
- 汇总表列全 19 个编号；勘误检查通过。

## 6. 复跑入口

```bash
# 冻结与运行前检查
python experiments/world-components/parallel/group_wording/build_freeze_v1.py
python experiments/world-components/parallel/group_wording/build_freeze_b2.py
python experiments/world-components/parallel/group_wording/precheck_v1.py
python experiments/world-components/parallel/group_wording/precheck_b2.py

# HPC（用户 t330034047；两批共用同一 runner/organizer）
cd experiments/world-components/parallel/group_wording
scp freeze-v1.json freeze-b2-v1.json organizer_v1.py run_group_wording_v1.py \
    hpc_group_wording_v1.sh hpc_group_wording_b2.sh \
    t330034047@hpc.bnbu.edu.cn:~/group_wording_v1/
ssh t330034047@hpc.bnbu.edu.cn 'cd ~/group_wording_v1 && sbatch hpc_group_wording_b2.sh'

# 核验与审计
python experiments/world-components/parallel/group_wording/audit_v1.py
python experiments/world-components/parallel/group_wording/audit_b2.py
python experiments/world-components/parallel/group_wording/verify_delivery_v1.py
```

## 7. 边界与后续

- 本轮不训练、不改服务、不做浏览器验收；这些另立任务。
- 后续优先做独立的新场景验证：用未参与本轮的材料建新夹具，检验 S 的 0/19 是否只在旧回归组成立。
- 旧材料与旧权重不动；冻结文件和原始输出不重写。
