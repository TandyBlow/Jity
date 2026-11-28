# P04 平台交付与独立验证：评价集、指标、统一入口、资源与运行核验

**Question.** 平台能不能给两个研究方向提供同一套可复现入口，并独立回答三个问题：
评价数据是否与训练隔离、模型工作流丢不丢事实、产品运行实际加载和调用了什么？

**Setup（工具，均在 `tools/experiment_platform/`）.**

| 模块 | 作用 | 产物 |
|---|---|---|
| `data_index.py` | 枚举数据、sha256、git 来源、格式摘要 | `artifacts/goal/platform/data-index.json` |
| `validate_data.py` | 损坏/重复/大文件/边车哈希/manifest/证据引用/绝对路径 | `data-validation.json` |
| `split_sets.py` | 声明 train/dev/test 与独立性，检查重叠 | `split-check.json` |
| `eval_set.py` | 评价集契约、规范化哈希冻结与复核 | `*.manifest.json` |
| `build_narration_holdout.py` | 从历史 run 建叙事故事留出集（事实块与语料/开发集不重叠） | `eval/narration-holdout-v1.jsonl` |
| `narration_metrics.py` | E58/E61 口径：事实覆盖、结果标签、否定丢失、编造、重复、句形 | `eval/narration-holdout-v1-eval.json` |
| `build_semantic_probes.py` | 从静态世界外观作者化语义探针（物品/地点/人物/否定/复合/未知） | `eval/semantic-probes-v1.{dev,test}.jsonl` |
| `semantic_score.py` | 语义预测打分（状态 + 内容子句，按族） | 打分包 |
| `run_experiment.py` | 清单 + 原始日志 + 结果记录 + attempt 级恢复 | `platform/runs/…` |
| `resource_monitor.py` | 进程树 RSS/CPU 采样、峰值与漂移 | `*.csv` / `*.summary.json` |
| `verify_run.py` | 权重请求、引擎、模型 id、语义 LLM 调用数、micro 开关 | `verify-*.json` |
| `perf_report.py` | 计时/内存归一化，列出未测项 | `perf-report.json` |
| `anonymize.py` | 按 case 打乱 A/B/C、隐藏模型名，输出盲评表与解盲 key | `blind.jsonl` / `key.json` |

**Data（独立集与构造证据）.**

- **叙事留出集 87 对**，来自 34 个 `artifacts/goal/narration/run*.json`。抽 257 个
  `product.narration` 对，按事实块哈希排除：语料 6、开发 bundle 48、重复 116，
  余 87。事实块哈希未出现在 225 个语料事实块与 97 个 bundle 事实块中——这是隔离的
  机器可查证据，不是"换了个文件名"。
- **语义探针 29 条**（dev 16 / test 13）：物品检查 12、进入地点 8、观察人物 6、
  否定 1、复合 1、未登记实体 1。期望内容取自世界文件 `initialAppearance`；名字已在
  语义训练文本中出现的 56 个实体被排除。覆盖缺口明确列出：任务变化、多人结算、
  NPC 自主、部分成功。

**Results.**

1. **独立叙事集上的三臂（87 对，无字符 F1）**

| 臂 | 事实覆盖 | 每点字数 | 句数 | 编造人名/数字 |
|---|---|---|---|---|
| 记录正文（全部，混合模型） | 0.069 | 68.0 | 3.0 | 0 / 0 |
| 记录正文 @ 基座 1.7B（6 对） | 0.426 | 175.0 | 5.7 | 0 / 0 |
| 记录正文 @ 1.7B LoRA（78 对） | 0.007 | 52.6 | 2.6 | 0 / 0 |
| 规则 E55 | 0.660 | 197.6 | 7.6 | 0 / 0 |
| 事件聚簇 E57 | **1.000** | 273.2 | 8.1 | 0 / 0 |

   结论受两个条件约束：历史 LoRA run 的输出模式是短段落（52 字），不能当作当前默认
   模型的基线；留出集里只有 1/87 条带结果标签，因此**结果标签覆盖率无法在独立集上
   判定**，只能确认规则/聚簇臂按构造保真。基座 1.7B 的 0.426 与 E58 的 0.569 同向，
   但样本只有 6 对。该表证明的是评价管线可用，不是新的模型排名。

2. **运行核验（真实证据）.** `verify_run.py` 在
   `12-q8kv-s03-clean.json` 上通过：权重请求 2/2、引擎 semantic ctx8192 生成 13 次、
   narration ctx2048 生成 5 次、语义 LLM 提示 13 条、micro 开启。批量扫
   `results/product/evidence/*.json`（`verify-all-evidence.json`）：18 份有效证据的
   权重请求失败均为 0；有回合的 14 份全部加载 semantic + narration 两个引擎；语义 LLM
   提示量 11–305 条/证据（20 回合的 `09-turns20-pi` 为 **305 条**，约 15/回合）。
   在 `09-turns20-pi.json` 上按 1.7B 默认模型验收会被工具直接拒绝（该 run 的
   narration 是 `semantic` 单模型臂）——这正是"防隐藏回退"要的行为。我们失败的
   holdout 尝试则是 0 引擎、0 提示，工具如实区分"没跑到推理"与"跑错模型"。

3. **性能归一化（旧计时记录）.** 冷启动 18.9/19.3/24.7 s；12 个计分点首段最差
   43.5 s、单点正文最差 13.8 s，但 7/12 回合中途停止（`FAIL_OR_INCOMPLETE`）。
   阶段总耗时：updates 921.1 s / 69 次、results 397.2 s / 70 次。内存 CSV 558 采样：
   Edge 峰值 4,849 MB、结束 3,390 MB、漂移 +395 MB、最低空闲 3,027 MB、30 进程。
   报告同时列出未测项：控制权交还时钟、页面/进程峰值 RSS、GPU、长期漂移、分模型冷启动。

4. **统一入口与恢复.** `run_experiment.py` 冒烟：manifest 记录命令、种子、模型、
   输入 sha256 与 HEAD；成功/失败/超时都落 `result.json`；`--resume` 对已完成任务
   直接跳过，对失败任务先归档 `result.attemptN.json` 再重跑，日志按 attempt 保留。
   `resource_monitor.py` 在子进程上采到 RSS 峰值与漂移（测试通过）。

5. **新输入真机留出集（2026-11-28 21:52–22:00）：平台按设计失败并保留证据。**
   4 条新输入已冻结为 `eval/turns-holdout-v1.json`（新产品页、非训练输入）。三次尝试：
   - 21:52 单模型 + ctx8192：内存地板触发（free 163 MB，peak 2,014 MB），进程被杀，
     `results/product/evidence/holdout-v1-20261128.json` 为 `FAILED`、1 回合、0 正文。
   - 21:55 单模型 + ctx4096：被 lane `09-ui` 的验收租约拒绝，日志
     `artifacts/goal/lab/job-20261128-215545-534.attempt1.log`；证明 `lease.mjs` 的互斥
     有效，也说明机器当前 ~5 GB 空闲不足以与另一条验收并行。
   - 21:58 第三轮在别的验收间隙启动，拿到 `IN_PROGRESS`/0 回合的部分证据后再次被租约
     占住；`retry-holdout.ps1` 已按"等租约 + 等内存"重试，但 10 分钟窗口内没有完整
     回合，保留失败产物，不伪造结果。
   结论：新输入留出集与结果标签评价要等机器空闲窗口；平台的 lease/memory 门按预期
   阻止了并发重跑。

**Conditions.** 语义探针尚未对任何工作流打分（没有 predictions）；叙事留出集的结果
标签缺口要靠新跑带结果标注的回合补，而新跑目前被并发验收的租约/内存挡住；历史 LoRA
输出模式与当前默认不同，不能横向比较；性能数字来自旧 `timing-baseline.json` 与一次
失败的新跑，不是今天完整构建的验收。

**Next.** 等租约与内存同时空闲，用 `turns-holdout-v1.json` 跑完 4 回合，产出带结果
标签的新留出集；用 `semantic_score.py` 接语义 Agent 的预测；把 `perf_report.py` 的
未测项补进驱动；把 `verify_run.py --max-llm-semantic 0` 作为"语义无 LLM"阶段的准入
门；盲评用 `anonymize.py` 出 A/B/C 表。

**Artifacts.** `tools/experiment_platform/`（13 个模块 + 13 个测试 + `splits.json`）、
`artifacts/goal/platform/eval/`（87 条叙事留出集、29 条语义探针、4 条新输入、失败运行
与重试脚本）、`artifacts/goal/platform/{verify-12-q8kv.json,verify-turns20-pi.json,
perf-report.json}`。P04。
