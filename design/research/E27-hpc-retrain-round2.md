# E27 第二轮数据上的三任务重训（HPC 282032）

**Question.** 用第二轮采集后的数据集重训 existence/support/extraction 三个
微型任务，哪些能上新、哪些还不行？

**Setup.** HPC 作业 282032（RTX 4090D，torch 2.5.1+cu124，transformers
4.51.3）：`_hpc_micro_submit.py` 上传快照与三份当前数据集（existence 383
样本：info 57/106、env 55/165；support 273 行；extraction 55 对）后顺序训练
existence env/info、support env/info、extraction 和 5-seed 联合消融。本地
CPU 试训（同脚本、无 holdout）作健全性对照。

**Results（holdout 为脚本内置前缀划分，与现役 manifest 同协议）.**
- existence env：fit loss 0.0001 @30 epochs；holdout `sm6-` **8/9**（现役
  8/9，训练行 53/153 → 55/165）。
- existence info：fit 0.0009；holdout `sm10-` **9/10**（现役 9/10，训练行
  57/92 → 57/106）。
- extraction：fit 0.0031；holdout top1 **12/14**（现役 9/14；bigram 基线
  12/14）。
- support env：fit 0.015；holdout 16 行 **14/16**（正例 8/10、负例 6/6）。
- support info：fit 0.526；holdout 10 行 **5/10**（5 个负例全判成正例）——
  新数据上退化，不上新（support 头本就未进 public/micro）。
- 本地 CPU 试训：fit 0.591 → 0.0004（30 轮），训练集 383/383 全对；纯 fit，
  仅证明脚本对新数据可跑。
- 部署 parity：`check_head_parity.py` exit 0，五个头 torch vs int8 决策一致
  （最大概率差 0.1005，无翻转）。
- 5-seed 联合消融在记录时仍在跑（ablation-v2.log 已出 shared-text 两个 seed），
  完成后补记。

**Ship decision（D-137）.** existence env/info（holdout 持平、训练行更新）与
extraction（9/14 → 12/14）的 int8 ONNX 替换进 `frontend/public/micro/`，manifest
更新为 job 282032 的哈希/行数/holdout；support 两个头只留在本地，等负例数据补强。

**Conditions.** 单世界 dragon-raja-free-day；holdout 前缀沿用脚本内置划分，
不是冻结八场景（冻结集不作模型选择）；AI 标注数据见 E26/D-135。

**Artifacts.** `real-semantic*.jsonl`、`semantic-{existence,support,extraction}.jsonl`、
`existence-manifest.json`、`.local/hpc-micro/`（日志与 .pt，gitignored）、D-137。
