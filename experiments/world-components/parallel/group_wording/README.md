# c5 多事实组表达（group_wording）

支持 R11（多事实组表达）。当前档位：**有实验结果（第一批 10 个样本）**。
不训练、不改服务；所有新文件都在本目录。

## 要回答的问题

B-large-77M 和 B-large-784M 都在 19 个多事实组里留下 `2/19` 的安全错误（漏项/添写）。
本轮比较两种写法，用同一个检查点：

- **J（整组联合）**：一个组一次调用，模型直接写整组；
- **S（逐事实再组织）**：每个事实单独调用，再由程序按计划合并。

问题是：S 能否减少漏项/添写，同时不把可读性写坏。

## 输入

- 材料：`artifacts/world-components/organize-wording/sentence-scale-v1.jsonl`，sha256 `2f537830…`（LF 规范化后；本工作树是 CRLF 检出，原始字节哈希记在冻结里）。
- 样本：9 行 / 10 组，固定编号 `GW-01`–`GW-10`；fixed 6 组为主样本，`t24`/`v20`/`v07` 4 组只作回归。
- 溯源：fixed 行的事实带 `entityId` + `source.field`；旧回归行只有姓名和文本，没有 `pointId`。这批语料早于 pointId 契约，本轮不补造。
- 为什么不用 77M：它的训练脚本没有保存最终权重；本地 `.local/models` 的 77M 用真实 prompt 复放后输出与 A/B 记录都不一致（`probe-identity-v1.json`），不是同一检查点。

## 方法

1. `build_freeze_v1.py` 生成 `freeze-v1.json`：样本、35 条逐字 prompt、检查点/材料/组织器哈希、以及与 784M 归档对照的 9 行文本。
2. `run_group_wording_v1.py` 在 HPC `gpu` 分区跑 784M `ckpt-final`：
   - J 12 次调用，装配后必须与归档逐字节相同（确定性检查）；
   - S 23 次调用，逐事实句子交给 `organizer_v1.py` 组织（同实体去重姓名、组间「。」、edge 目标加「随后，」）。
3. `audit_v1.py` 逐事实筛查；人工逐条核对 10 个样本，写 `review-table-v1.md`。

## 结果（HPC job `247043`）

| 指标 | J | S |
| --- | --- | --- |
| 漏项 | 1（`v20` f1 理智） | 0 |
| 添写 | 1（`t24` 多“衣角”） | 0 |
| 人物/字段错配 | 0 | 0 |
| 可读性“自然” | 9/10 | 9/10 |

- J 的 2 条错误与 784M 归档完全一致（9 行装配文本逐字节相同），说明比较是对着真实的 2/19，不是新跑偏。
- S 把 `t24` 的“衣角”和 `v20` 漏掉的理智都补回来了，其余 8 个样本两臂事实都完整。
- 35 次生成合计 28.4 秒；作业墙钟 5 分 29 秒，其余时间在 3 GB 权重的哈希与加载。

详细逐样本文本和理由见 [result-v1.md](result-v1.md) 与 [review-table-v1.md](review-table-v1.md)。

勘误（2026-11-08）：GW-07 的 S 原始文本是“纸灯笼被风扯破一角，排水沟的里面积了泥。”，原记录误写成“排水沟里面积了泥”；据此把该条可读性从“自然”改为“可用但生硬”，S 自然条数改为 9/10。事实层计数不变（S 仍无漏项/添写）。

## 失败与限制

- 只测了 19 个多事实组中的 10 个样本，**不能**说 2/19 已清零，也**不能**说安全门通过。
- 单检查点（784M）。77M 权重已丢失；结论不外推到 77M 或其他基座。
- S 对 784M 是训练分布外输入：它按整组训练，只有单事实组见过逐条形式。S 在本批没出错，不代表换成别的检查点也稳。
- 组织器只做同实体姓名去重和标点连接；逐事实句子本身写错时它不修。第二句不以姓名开头的情况本批没出现，未验证。
- 自动审计对理智句会误报弱匹配（理智事实没有 `text` 字段），本批靠人工确认方向。

## 下一步

1. 第二批 ≤10 个样本：剩余 9 个 regression 多事实组，把 19 组补全；同一冻结、同一检查点、不调 prompt。
2. 审计规则改成按理智 `from→to` 判方向。
3. 补测组织器的边界情况（第二句不以姓名开头、跨组同实体）。
4. 之后再谈接入服务和浏览器延迟。

## 文件

| 文件 | 作用 |
| --- | --- |
| `evidence-2-of-19-v1.md` | 77M / 784M 的 2/19 逐条整理与错误分类 |
| `protocol-v1.md` | 冻结的对照协议、判定与停止条件 |
| `freeze-v1.json` / `freeze-v1.sha256` | 输入清单、prompt、哈希、归档对照文本 |
| `organizer_v1.py` | 逐事实句子的确定性组织规则 |
| `run_group_wording_v1.py` / `hpc_group_wording_v1.sh` | HPC 推理脚本与 sbatch |
| `run-v1/results.json` / `run-v1/run.log` | 原始输出与作业日志 |
| `audit-v1.json` | 自动逐事实筛查 |
| `review-table-v1.md` | 10 个样本的人工逐条核验 |
| `result-v1.md` | 结果、机制、限制、下一步 |
| `build_freeze_v1.py` / `precheck_v1.py` | 冻结构建与运行前检查 |
| `probe_identity.py` / `probe-identity-v1.json` | 本地 77M 检查点身份排查 |

## 复跑

```bash
# 本地：重建冻结（会覆盖 freeze-v1.json，先确认没有被引用）
python experiments/world-components/parallel/group_wording/build_freeze_v1.py
python experiments/world-components/parallel/group_wording/precheck_v1.py

# HPC（登录用户 t330034047）
scp freeze-v1.json organizer_v1.py run_group_wording_v1.py hpc_group_wording_v1.sh \
    t330034047@hpc.bnbu.edu.cn:~/group_wording_v1/
ssh t330034047@hpc.bnbu.edu.cn 'cd ~/group_wording_v1 && sbatch hpc_group_wording_v1.sh'
# 结果在 ~/group_wording_v1/run-v1/results.json
```
