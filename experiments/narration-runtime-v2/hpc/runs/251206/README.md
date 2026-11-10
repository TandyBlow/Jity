# Job 251206: v2 result-block YuYan LoRA diagnostic

## 作业

| 项目 | 值 |
| --- | --- |
| runId | `yuyan-lora-result-v2-r1` |
| 提交 | 2026-11-10T11:30:58 +08:00 |
| 开始 | 2026-11-10T11:30:58 +08:00 |
| 结束 | 2026-11-10T11:37:28 +08:00 |
| 取回 | 2026-11-10T11:39 左右（本地 `fetch.json`） |
| 耗时 | 00:06:30（训练脚本自报 375.6 s） |
| 状态 | COMPLETED，exit 0:0 |
| 节点/显卡 | hpcgpu10 / NVIDIA GeForce RTX 4090 D，24,564 MiB |
| 环境 | Python 3.11.17，torch 2.5.1+cu124，transformers 4.51.3 |
| 配置 | `configs/yuyan-lora-v2.json`，canonical SHA-256 `9fc7f4a271c208069bb8b5393f8e0ad94cded3a72cb20ca971ad0e25e85349c1` |
| 基座 | `hpc:~/narr_rows/checkpoint_best.pt`，SHA-256 `674b897a…` |
| tokenizer | `hpc:~/narr_rows/dict.txt`，SHA-256 `20287a9d…` |
| 数据 | `hpc:~/narr_v2/data/rows-yuyan-v2.jsonl`，SHA-256 `cb6764bf…` |
| split | `c6686b4b…`，train 139 / dev 40 / test 20 |
| 训练 | LoRA rank 16 / alpha 32，lr 1e-4，6 epochs，batch 1，maxLen 2560，seed 20261109 |
| 显存峰值 | 11,089 MiB |
| 最终 adapter | `hpc:~/narr_v2/runs/yuyan-result-v2-r1/adapter-best.pt`，SHA-256 `789ab22c…`（未提交权重） |
| resume | `hpc:~/narr_v2/runs/yuyan-result-v2-r1/resume.pt`，SHA-256 `15ccfd0d…`（未提交权重） |

## 结果

| 项目 | v2（本作业） | 旧臂 `report-250409.json` | 差 |
| --- | --- | --- | --- |
| best dev | 1.4106 @ epoch 3 | 1.4096 @ epoch 3 | +0.0010 |
| test loss | 1.4241 | 1.423 | +0.0011 |
| train loss | 1.0582 | — | — |
| 秒 | 375.6 | 545.5 | — |

两臂共享基座、199 行、split、seed、LoRA rank/alpha、lr、epochs。唯一有意的格式差异是
v2 的 `【本回合状态】` 结果块和物品 `位置`。另有一个已登记差异：旧臂 `maxLen=2048` 会静默截断
`row-0002`，v2 用 2560 装下 2382 token；因此这不是完全同条件比较。

## 样本观察（不能当质量通过）

- v2 greedy 字数：row-0006 621 / row-0007 593 / row-0017 308 / row-0018 445 / row-0037 460；
  旧臂对应 418 / 321 / 213 / 419 / 415。输出普遍变长。
- 但 v2 全部样本仍以 `stopReason=length` 结束（600 token 上限），没有自然 EOS。
- 重复 4-gram 仍然很高：greedy maxRepeat4 6–14，sampled 5–16。
- `row-0006` 的 sampled 输出出现 `程雪峰`，该人物不在该行输入人物表中；这是具体的事实捏造。
- dev/test loss 基本不变，且 loss 不是正文质量指标；因此本作业不声称“模型质量改善”，也不把
  数据修复当成语义通过。

逐样本长度/重复/旧臂对照见 `comparison.json`；完整报告见 `report.json`，原始样本见
`samples.txt`。

## 复现

```bash
cd experiments/narration-runtime-v2
python -X utf8 train/hpc_client.py deploy
python -X utf8 train/hpc_client.py submit
python -X utf8 train/hpc_client.py poll <jobId>
python -X utf8 train/hpc_client.py fetch <jobId>
```

远端实际执行的是 `~/narr_v2/run_yuyan.sh`，即 `train/submit_yuyan.sbatch`；它先跑
`preflight_v2.py --hash-base`，再跑 `train_yuyan_v2.py --resume auto`。

## 文件

- `report.json`：训练报告，已把 `/home/student/<user>/` 替换为 `hpc:~/`；
- `samples.txt`：5 行 × greedy/sampled 原始正文；
- `comparison.json`：与旧臂的数字和样本统计对照、结论；
- `job.out` / `job.err`：Slurm 日志（`job.err` 为空）。

权重、checkpoint 和 204 MiB resume 文件留在集群，不进入 Git。
