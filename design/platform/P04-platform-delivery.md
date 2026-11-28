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

6. **匿名对照样本.** 从 87 对留出集取前 20 例，三臂（记录正文 / E55 / E57）共 60 份
   输出，按 case 打乱为 A/B/C；`review.md` 可直接打分，`key.json` 单独保存解盲。
   这是工具与流程证据，不是质量结论；`current` 仍是历史记录正文，不能当默认模型。

7. **新输入真机留出集：1 回合链路打通，驱动提前退出。** 22:06 用单模型
   `semanticCtx=4096` 跑 `turns-holdout-v1.json`，第一回合 278 字、`source=model`、
   wait 78.4 s；随后驱动在只有 1/4 回合时退出（日志无 `[done]`，evidence 停在
   `IN_PROGRESS`）。`verify_run --expect-turns 4` 判失败并留下 `1/4` 记录——完整性门
   生效，没有把部分运行当通过。该回合冻结为 `narration-holdout-v2-newrun.jsonl`
   （事实块不在语料/bundle，2 条结果标签）。三臂：current 覆盖 0.875、结果标签
   **0/2**；E55 覆盖 0.875、**2/2**；E57 覆盖 1.0、**2/2**；编造 0。样本=1，只作链路
   与方向证据，不作排名。驱动提前退出的原因未定，按工具缺陷记录。

8. **语义独立探针：shipped 存在性头在未见实体上 0/8。** 先用真实标注校验探针金标：
   71 条含"走进"的训练回合里 env=present 只出现在伴随环境变化的动作中，单独走进
   (`sm-e-move-1`) 是 info absent/env absent——原探针的"进入地点→env present"已改成
   双 absent。随后用页面实际加载的 `existence-{info,env}-int8.onnx`（MiniRBT 分词、
   256 截断）在 13 条 test 探针上离线打分（`head_predict.py` + `--status-only`）：
   - 总体状态准确率 **0.50**（16 字段）；item_inspect **0/6**、person_observe **0/2**
     全部把 info-present 判成 absent（present 概率 ~1e-4）；place_enter 6/6、
     negation 1/1、unknown 1/1 正确。
   - 这是 out-of-route 探针，文本比真实回合短，不能等同于线上准确率；但它说明
     在 seen 路由上 9/10 的存在性头没有迁移到未登记实体/新动词短语。产品默认还有
     程序规则通道；本结果只否定"头可单独泛化"。

**Conditions.** 语义探针的文本是合成的短事实块，比真实回合短，头打分只作
out-of-route 证据；叙事新跑只完成 1/4 回合，独立结果标签验证只有 1 点（方向一致，
不能作排名）；历史 LoRA 输出模式与当前默认不同，不能横向比较；性能数字来自旧
`timing-baseline.json` 与失败/部分的新跑，不是今天完整构建的验收。

**Status（实现 / 实验 / 局部验证 / 产品验收）.**

| 交付 | 实现 | 已运行 | 独立验证 | 产品验收 |
|---|---|---|---|---|
| 数据索引 + 完整性校验 | 是 | 3,744 文件 / 4.7 GB | 发现 4 处坏 JSON、998 MB 跟踪大文件、64/161 行证据未跟踪 | 不适用 |
| 分割登记与重叠检查 | 是 | 6 对关系 | 50/58 holdout 出现在语料（已标回归） | 不适用 |
| 叙事独立留出集 87 对 | 是 | 三臂评分 | 事实级独立验证通过；结果标签缺口 1/87 | 未做 |
| 语义独立探针 29 条 | 是 | 冻结 + 契约校验 + shipped 头打分 | status 0.50；info-present 0/8；place/unknown 正确 | 未做 |
| 统一运行入口 | 是 | 成功/失败/恢复冒烟 | 失败证据保留、完成不重跑 | 未做 |
| 资源监控 | 是 | 子进程 RSS/漂移 | 峰值与漂移可复现 | 未做 |
| 运行核验 | 是 | 18 份证据 | 权重失败 0；LLM 提示 11–305/证据 | 未做 |
| 性能归一化 | 是 | 旧计时 + 内存 CSV | 列出未测项，不冒充通过 | 未做 |
| 调度器可靠性修复 | 是 | 临时队列冒烟 | 合并写、锁回收、stop 落账、attempt 日志 | 未做 |
| 新输入真机留出集 | 是 | 4 条输入 | 3 次尝试失败；第 4 次 1/4 回合，冻结 1 点并评分 | 未做 |

**Next.** 用语义 Agent 的程序/混合臂在同一探针上预测并按内容子句打分；等驱动修复后
补完 4 回合新留出集；把 `perf_report.py` 的未测项补进驱动；把
`verify_run.py --max-llm-semantic 0` 作为"语义无 LLM"阶段的准入门；盲评用
`anonymize.py` 出 A/B/C 表。

**Artifacts.** `tools/experiment_platform/`（14 个模块 + 14 个测试 + `splits.json`）、
`artifacts/goal/platform/eval/`（87 条叙事留出集、29 条语义探针 + 头预测/分数、1 条
新输入、失败运行与重试脚本、20 例盲评样本）、`artifacts/goal/platform/{verify-12-q8kv.json,
verify-turns20-pi.json,verify-all-evidence.json,verify-holdout-v1d.json,perf-report.json}`。P04。

**Note.** 四个只读审计 Agent 没有交付报告（已停止）；P01/P02 的数据与工具结论均由平台
工具扫描加人工复核直接得出，证据都在上列 artifact 里。
