# c5 多事实组表达（group_wording）

支持 R11（多事实组表达）。当前档位：**有实验结果（19 组：fixed 6 + regression 13）**。
不训练、不改服务；所有新文件都在本目录。

## 要回答的问题

B-large-77M 和 B-large-784M 都在 19 个多事实组里留下 `2/19` 的安全错误（漏项/添写）。
本轮比较两种写法，用同一个检查点：

- **J（整组联合）**：一个组一次调用，模型直接写整组；
- **S（逐事实再组织）**：每个事实单独调用，再由程序按计划合并。

问题是：S 能否减少漏项/添写，同时不把可读性写坏。

## 输入

- 材料：`artifacts/world-components/organize-wording/sentence-scale-v1.jsonl`，sha256 `2f537830…`（LF 规范化后；本工作树是 CRLF 检出，原始字节哈希记在冻结里）。
- 样本：19 组，固定编号 `GW-01`–`GW-19`。
  - 第一批（`GW-01`–`GW-10`）：fixed 6 组 + `t24`/`v20`/`v07` 4 组；
  - 第二批（`GW-11`–`GW-19`）：`fixture-r5`、`train-r4`、`t03`、`v14`、`v18`、`t08` 两组、`t22` 两组。
- 溯源：fixed 行的事实带 `entityId` + `source.field`；旧回归行只有姓名和文本，没有 `pointId`。这批语料早于 pointId 契约，本轮不补造。
- 为什么不用 77M：它的训练脚本没有保存最终权重；本地 `.local/models` 的 77M 用真实 prompt 复放后输出与 A/B 记录都不一致（`probe-identity-v1.json`），不是同一检查点。

## 方法

1. `build_freeze_v1.py` / `build_freeze_b2.py` 分别生成两批冻结：样本、逐字 prompt（第一批 35 条、第二批 42 条）、检查点/材料/组织器哈希，以及与 784M 归档对照的整行文本。
2. `run_group_wording_v1.py` 在 HPC `gpu` 分区跑 784M `ckpt-final`，两批用同一脚本：
   - J 臂装配后必须与归档逐字节相同（确定性检查）；
   - S 臂把逐事实句子交给 `organizer_v1.py` 组织（同实体去重姓名、组间「。」、edge 目标加「随后，」）。
3. `audit_v1.py` / `audit_b2.py` 逐事实筛查；人工逐条核对全部 19 个样本，写 `review-table-v1.md`、`review-table-b2-v1.md`。

## 结果

| 指标 | J | S |
| --- | --- | --- |
| 漏项 | 1（`v20` f1 理智） | 0 |
| 添写 | 1（`t24` 多“衣角”） | 0 |
| 人物/字段错配 | 0 | 0 |
| 可读性“自然” | 17/19 | 18/19（GW-07 多“的”） |
| 可读性“不自然” | 0 | 0 |

按分组：

- fixed 6 组：J 0 错、S 0 错；两臂 6/6 自然。
- regression 13 组：J 2 错（GW-07 添写、GW-09 漏项），S 0 错；J 11/13 自然（GW-07、GW-18），S 12/13 自然（GW-07）。

运行：

| 批次 | HPC job | 调用 | 生成耗时 | 墙钟 |
| --- | --- | --- | --- | --- |
| 第一批 | `247043` | 35（J 12 / S 23） | 28.4 s | 5 分 29 秒 |
| 第二批 | `247046` | 42（J 15 / S 27） | 6.6 s | 2 分 13 秒 |

- 两批 J 臂共 16 行整行装配文本与 784M 归档逐字节相同，说明比较对着真实的 2/19，不是新跑偏。
- J 的 2 条错误就是 784M 归档的两个错误项；S 没有新错误，并在 GW-07/GW-09 上把事实写全。
- 完整逐组表见 [summary-19-v1.md](summary-19-v1.md)。

勘误（2026-11-08）：GW-07 的 S 原始文本是“纸灯笼被风扯破一角，排水沟的里面积了泥。”，原记录误写成“排水沟里面积了泥”；据此把该条可读性从“自然”改为“可用但生硬”，S 自然条数改为 18/19。事实层计数不变（S 仍无漏项/添写）。

## 失败与限制

- 原安全门是“B 对 A-large-77 的 B-only = 0”，比较两个不同检查点；本表比较同一检查点的两种调用方式。S 0/19 **不能**写成“安全门现在通过了”。
- 单检查点（784M）。77M 权重已丢失；结论不外推到 77M 或其他基座，也不外推到新场景。
- S 对 784M 是训练分布外输入：它按整组训练，只有单事实组见过逐条形式。本批没出错不代表换检查点也稳。
- 组织器只做同实体姓名去重和标点连接；句内语法、指代、语序它不改。GW-07 的“的”就是这样留下的。
- 自动审计对理智句会误报弱匹配（理智事实没有 `text` 字段），本批靠人工确认方向。
- GW-18 的 J 语法退步（“木桩的缠着”）来自模型，S 在这一条恰好没有；这是单次输出的差异，不当作组织器的能力。

## 下一步

1. 用未参与本轮的更新夹具跑一次，检验 S 的 0/19 是否只在旧回归组成立。
2. 审计规则改成按理智 `from→to` 判方向，去掉误报。
3. 补测组织器边界：第二句不以姓名开头、跨组同实体、句内有“的”时的合并。
4. 之后再谈接入服务和浏览器延迟；本轮只测离线生成。

## 文件

| 文件 | 作用 |
| --- | --- |
| `evidence-2-of-19-v1.md` | 77M / 784M 的 2/19 逐条整理与错误分类 |
| `protocol-v1.md` | 冻结的对照协议、判定与停止条件 |
| `freeze-v1.json` / `freeze-b2-v1.json` | 两批输入清单、prompt、哈希、归档对照文本 |
| `organizer_v1.py` | 逐事实句子的确定性组织规则 |
| `run_group_wording_v1.py` | 两批共用的 HPC 推理脚本 |
| `hpc_group_wording_v1.sh` / `hpc_group_wording_b2.sh` | 两批 sbatch |
| `run-v1/` / `run-b2-v1/` | 两批原始输出与作业日志 |
| `audit-v1.json` / `audit-b2-v1.json` | 自动逐事实筛查 |
| `review-table-v1.md` / `review-table-b2-v1.md` | 19 个样本的人工逐条核验 |
| `result-v1.md` / `result-b2-v1.md` | 分批结果、机制、限制 |
| `summary-19-v1.md` | fixed 6 + regression 13 的完整汇总 |
| `build_freeze_v1.py` / `build_freeze_b2.py` | 两批冻结构建 |
| `precheck_v1.py` / `precheck_b2.py` | 两批运行前检查 |
| `probe_identity.py` / `probe-identity-v1.json` | 本地 77M 检查点身份排查 |
| `manifest-v1.json` | 第一批文件哈希快照 |
| `manifest-v2.json` | 当前全部 31 个交付文件的哈希清单（第二批交付主清单） |

## 复跑

```bash
# 本地：重建冻结与运行前检查
python experiments/world-components/parallel/group_wording/build_freeze_v1.py
python experiments/world-components/parallel/group_wording/build_freeze_b2.py
python experiments/world-components/parallel/group_wording/precheck_v1.py
python experiments/world-components/parallel/group_wording/precheck_b2.py

# HPC（登录用户 t330034047）
cd experiments/world-components/parallel/group_wording
scp freeze-v1.json freeze-b2-v1.json organizer_v1.py run_group_wording_v1.py \
    hpc_group_wording_v1.sh hpc_group_wording_b2.sh \
    t330034047@hpc.bnbu.edu.cn:~/group_wording_v1/
ssh t330034047@hpc.bnbu.edu.cn 'cd ~/group_wording_v1 && sbatch hpc_group_wording_b2.sh'
# 结果在 ~/group_wording_v1/run-b2-v1/results.json
```
