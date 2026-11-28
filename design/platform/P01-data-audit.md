# P01 数据与工具审计：索引、完整性与独立集现状

**Question.** 现有实验数据能不能被枚举、校验和重放？哪些"独立评价集"其实已经参与开发？
哪些完整性声明是机器可查的，哪些只是报告里的一句话？

**Setup.** 新平台工具 `tools/experiment_platform/`（stdlib，只读）：

- `data_index.py`：扫描 `artifacts/goal`、`experiments`、`data/worlds`，记录路径、family、role、
  bytes、sha256、git blob/最后提交、dirty/untracked、JSON/JSONL/CSV 结构摘要。上限：
  解析 ≤8 MB，哈希 ≤64 MB；超限只记大小。
- `validate_data.py`：malformed JSON/JSONL、空数据集、JSONL 字段漂移、同内容重复、
  被 git 跟踪的大文件、报告引用不存在的路径、`.sha256` 边车、语义 manifest 摘要。
- `split_sets.py` + `splits.json`：每个数据集声明 usage / independent，成对检查
  disjoint/subset/report。

命令：`python -m tools.experiment_platform.data_index`，`...validate_data`，`...split_sets`。
产物 `artifacts/goal/platform/{data-index,data-validation,split-check}.json`。

**Data（索引快照，headCommit 见 data-index.json）.** 3,744 个文件 / 4,736 MB；3,426 个被 git
跟踪；4 个 JSON 解析失败；215 组同内容重复；84 个被跟踪文件 >5 MB，合计 **998 MB**。

按 family：`micro-workflow` 529 文件 / 3,428 MB（202 个 run-record，多为 40–87 MB 的
全量回合 JSON）；`narration` 199 / 578 MB；`semantics` 108 / 264 MB；`acceptance` 26 /
157 MB；`results` 22 / 132 MB；`world-components` 1,750 / 37 MB。

**Findings.**

1. **仓库里囤了 998 MB 的跟踪大文件。** 最大的是 `results/product/evidence/09-turns20-pi.json`
   （54.8 MB）、`evidence-independent-scenarios-7/8.json`（各 40.0 MB）和 6 个 27.1 MB 的
   `run9x-17b-lora-v3-10turn.json`。这违反 "大文件、权重、原始日志不入 git" 的约定，
   直接抬高 clone/push/索引成本。平台侧对策：每次运行只提交摘要与增量证据，原始
   请求/响应留在本地 `.local/`，需要时按 manifest 回取。

2. **4 个"模型配置"其实是错误文本。** `experiments/narration-model-search/sources/hf/`
   下 `gemma3-1b-it-qat/base-config.json`（128 B）等 4 个文件内容是
   "Access to model google/gemma-3-1b-it is restricted…" 或 "Entry not found"，
   不是 JSON。也就是说这两个候选模型的身份记录不完整；任何引用这些配置的模型清单都不成立。
   已标为 warn（vendored），不计入数据漂移的 fail。

3. **完整性声明已经机器可查，但有两种哈希口径。**
   - `scenarios-independent.sha256` 与文件哈希一致：`8a52c6ae…5805`。
   - `real-semantic-manifest.json`：raw 用**文件字节**哈希（`43ad55f7…`），train/test 用
     **解析后 `json.dumps(ensure_ascii=False)` 的规范化哈希**（`f9379e4b…` / `34a72912…`），
     行数 280/245/8。`train_micro_semantic.py:28-36` 按同一口径校验。
   - 口径本身没写进 manifest，也没有校验器文档；任何按文件字节校验的外部工具都会
     误报（本平台第一版就误报过）。建议 manifest 增加 `hashMode` 字段。

4. **语义验收门对缓存与覆盖的声明强于实现。**
   - `validate_real_semantic.py:60` 的 `validate(raw, train, test, cache, …)` 收了 `cache`，
     函数体从未使用；docstring 第 2/5 条声称"每个标签都有匹配 input hash/model/evidence
     的 v2 缓存记录"，实际只检查行内 `labelMeta` 字段（`:70-78`）。缓存 305 行，门没有比对。
   - `ROOT = Path('D:/others/Jity')`（`:21`）写死，换机器/换目录即断，平台不可复现。
   - 意图回显只做精确相等（`:80-81`）。我用 difflib ≥0.6 或互相包含扫了 280 行，
     **未发现改写后的回显**；但这条检查本身挡不住改写。
   - 训练覆盖率：`expectedTrain=272`、`trainRows=245`，门只要求 raw 覆盖（`:63-64`），
     不报告 27 条预期训练输入没有产出可训练标签。覆盖损失应成为显式指标。

5. **"独立集"现状。** 机器可查的分割登记在 `tools/experiment_platform/splits.json`：
   - 语义：train 245 ∩ test 8 = 0；test 的 8 个 id 恰好就是 8 个冻结场景。8 场景从
     D-061 起被反复用来定位和修复（scenarios-1…12、run103/104 等），**已不是泛化测试集**，
     登记为 `regression-only`。
   - 叙事：161 点 bundle 是 E55–E60 设计规则的同一批输入，登记为 `dev-regression`；
     58 条 holdout 是 E38 的 32 组哈希留出，58/58 ⊆ 410 行 planning-v14，**但 50/58 的 id
     又出现在 424 行语料里**（同一提示的备选/版本目标）。语料若直接进训练，必须按
     prompt 去重并剔除 holdout；E46 的 290 行是手工剔除的，无门禁。
   - 语料本身：424 行 = **241 个唯一 prompt + 183 条备选/版本目标**，`TarcadeD#1/#2`
     各重复一次；26 行 id 是 int、398 行是 str，按严格相等连接会漏配（我第一版
     重叠统计就因此少了 8 条）。任何"362/424 条语料"的结论都应按唯一 prompt 重新表述。

6. **报告数字可追溯抽查（E58/E60）。** `pairs.jsonl` 51 行、`inputs.jsonl` 161 行；
   `pairs-eval.json` 的 0.569 覆盖 / 0.000 结果标签、`evaluate-arms.json` 的 292/424 与
   6/141、`compose-candidate-summary.json` 的 16,634 字 / 103.3 字每 point 均与报告一致。
   这两页的结论有原始文件支撑；它们的评价集独立性按第 5 条降级。

7. **bundle 的四成输入来自未跟踪的本地证据。** `inputs.jsonl` 引用 11 个
   `results/product/evidence/*.json`，其中 5 个未被 git 跟踪：`10-scenarios-pi.json`、
   `10-scenarios-pi-2026-11-28T1041-fbe4.json`（各 24 行）、`10-offline-pi.json`（8 行）、
   `11-smoke-default-ctx8192.json`（4 行）、`09-turns20-ctx8192.json`（1 行），合计
   **64/161 行（40%）**；`pairs.jsonl` 也有 **20/51 对**来自这些文件。克隆仓库后无法重建
   这两个 bundle，E58/E60 的上游证据只在当前机器上。检查已自动化（`evidence_ref`）。

8. **研究脚本不可移植。** 168 个 `.py` 写死 `D:/others/Jity`（`validate_real_semantic.py:21`
   只是其中一个），148 个引用 `.local/`；叙事训练源 `sft-v13.jsonl` 只存在于
   `.local/narr-train/`（该目录 47 GB，gitignored），`assemble_corpus.py`、
   `frame_pairs.py`、`selection_model.py` 等都直接读它。换机器或新 clone 后这些脚本
   全部失效。已加 `absolute_path` 检查；修复需要各脚本改用仓库相对路径，并把可再生的
   小型文本源（如 sft-v13.jsonl）纳入跟踪或由 manifest 指明的重建命令生成。

**Conditions.** 索引只覆盖三个数据根；`.local/`、`lab/pi-gate-profile` 等本地/浏览器目录
不在内。哈希上限 64 MB，因此 >64 MB 文件只记大小、无 digest。重复检测按整文件 sha256，
不做行级近似重复；key drift 只查 train/test/dev/labels/cache/input/fixture 角色。

**Next.**

1. 给 `splits.json` 增加 prompt 级 key（规范化 prompt 哈希），把语料/留出集的重叠从
   id 口径升级到 prompt 口径。
2. 把语义门的缺陷（缓存未用、ROOT 写死、覆盖率不报、意图回显只查精确相等）连同复现
   命令交给语义 Agent；平台只提供检查，不改其工作流。
3. 建新的独立评价集：语义用未参与训练的新回合输入，叙事用未进入 161 点 bundle 的
   场景运行输出；先出 dev 集，正式 test 集冻结后只读。
4. 统一运行入口与资源账本待 runner 审计返回后落地；计时口径待 perf 审计返回后统一。

**Artifacts.** `tools/experiment_platform/`、`artifacts/goal/platform/data-index.json`、
`data-validation.json`、`split-check.json`。P01。
