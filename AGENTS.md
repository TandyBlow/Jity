# Source-only training handoff (2026-11-10)

This branch starts from remote `world-components-logic@d80a031`, not from either aborted model-backup commit. The user authorizes publishing training code and necessary reproducibility material only. Never publish weights, adapters, learned heads, checkpoints, optimizer states, model backup archives, or large raw logs. Keep all author-machine training/diagnostic work untouched.

The teammate entry is `experiments/world-components-logic/reproduce/README.md`. Its portable fresh-training recipe creates new candidates from pinned public bases and frozen synthetic data. Historical scripts and outcome records do not establish cross-device reproducibility. CUDA and full CPU Qwen training remain unvalidated. No existing checkpoint is required by the new entry.

Do not start the historical final-training claim as part of packaging. It belongs to another ongoing task. The prior 5 remote LFS objects (~1.96 MB) are a separate unfinished support-cleanup matter; do not resume their upload. Use explicit staging paths.

---

# D 工作树：非叙事组件专项工作说明

本工作树统一代号为 **D**，对应 `world-components-logic`，从 C / `world-components` 的 `30069354cc061be94fc31c897dada0f641ed3f90` 创建。本专项负责非叙事组件架构、程序与模型分工、模型选型及专项验证，由项目协调人统筹跨分支协作。D 即此前的 logic 专项，分支名和目录名不变；原设计 C1–C7 是职责编号，不是工作树代号。

开始工作前，完整阅读 [任务与交接说明](design/world-engine-reports/components-logic/README.md)，并按其中的阅读顺序核对原设计和继承方案。该说明定义本专项的职责与执行范围；继承文档中“C 首批只做叙事”等旧排期，不限制本分支开展非叙事研究。

- 先分析非叙事部分需要多少组件、每个组件是否需要模型、模型如何选择和共享，再以行动、目标／反应、共同结果为首批深入验证对象。现有 C1–C7 是职责编号，不是已确定的组件数量或模型数量。
- 性能按用户2026-11-04最新要求执行：每个小组件仍尽量快，**50毫秒仅作局部参考，不再是硬门槛**；完整一次非叙事计算含模型协同和程序交接仍须在 **500毫秒以内**。当前优先补齐行动描述生成并验证真实协作链，依据整链热点继续细拆任务/换更小模型。几十至几百M、允许更小模型协同；质量、完整覆盖与程序权威保留，未实测不签完整性能通过。旧报告按当时50ms工程门保留，不追溯改成质量/完整500ms通过。
- 本分支独占 `design/world-engine-reports/components-logic/`、`experiments/world-components-logic/`、`artifacts/world-components-logic/` 及本文件；新增实验的大文件、权重、缓存与本地依赖不入库。`experiments/` 被继承的 `.gitignore` 忽略，交付源码时按明确文件路径跟踪，不改全局忽略规则。
- A 保留服务、协议、存储和状态计算；B 保留页面、调度／控制／运行层与整链；C 保留叙事专项及原 `world-components` 目录。可读取固定提交的成果，不直接修改其他线负责的文件。
- 程序继续掌握 ID、骰点、准入、冻结、顺序、状态应用、保存与恢复。语义判断不能靠固定规则或缩减原功能冒充完成。
- 不借用 B/C 的训练、校准、开发、评测或封存样本及其改写作为本专项数据。新样本须登记来源、分组与哈希，先定判据，再比较候选。
- 不重启或写入 B/C 正在使用的服务、数据库、模型缓存和运行产物。训练／推理使用独立资源目录，共享 GPU 或重负载 CPU 时由项目协调人统筹运行窗口。
- 不因切出新工作树而重新打开原 H2 验收。离线验证、浏览器验证、生产接线分别报告；变更公共接口以提案交接，不能并行创造另一套权威协议。
- 只按本次任务路径提交；不使用全仓 `git add .`。分支同步与跨线接入按交接说明执行，不自动合并或发布其他分支。
