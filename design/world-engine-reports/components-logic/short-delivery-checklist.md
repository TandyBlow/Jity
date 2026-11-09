# Qwen 与 focus 后续交付核对清单

本文件是 2026-11-09 的只读交付审计，不覆盖旧报告或旧 inventory。后续浏览器结果仍需完成并按原冻结计划记账；此清单不授予语义或生产接入通过。工程脚本只读取文件、流式计算哈希和检查 Git 状态，不加载模型。

## 待更新的已有报告

| 文件 | 仍有效的历史证据 | 新版必须补充的内容 |
|---|---|---|
| `short-results.md` | r1/r3/r5 的全部历史训练与失败、D01—D08 工程及生产接入边界 | 将“62 个编码头、14 个生成任务已训练”明确绑定原模型；活动自然语言后端为 Qwen，旧燃灯不能回退。新增 focus r6 两个整臂、Qwen 训练/合并/导出与浏览器的各自完成状态。不要把旧模型错误率直接当新模型错误率。 |
| `short-comparison.md` | 原方案、r1/r3 的成本及不同工作负载不可直接比较 | 加 r5、r6 和 Qwen 的独立行；MPS 原厂/适配后比较与 ONNX 浏览器部署分开。首发资源、日志、CPU placement、设备验证失败均保留，未启动不作低延迟成功。 |
| `data-model-inventory.json` | 当时的来源版本、原始权重/适配层身份与继承证据 | 原件保持只读。另写 v2 指向原件 SHA，并区分历史燃灯、r5 编码器、r6 四头整臂、Qwen 原厂/微调/合并/量化权重以及运行时包。旧 `currentRuntime` 不能解释为现在的活动配置。 |

Qwen r2 的失败摘要明确记录 **44 条生成原文未在资源检查前保存**。保留原日志不等于已经保存这些缺失输出；新版必须保留这个缺口，不能用重跑结果、后续模型或固定文本补齐。r3 的 `invalid_journal` 也不能改写为完整验证成功。

## D01—D08 交付边界

| 组件 | 已具备的工程边界 | 本轮仍不能宣布通过的部分 |
|---|---|---|
| D01 | 六步完整上下文、草稿身份、引用/覆盖、固定 A 初始候选校验 | 真实生成的完整初始化语义及正式创建世界接线 |
| D02 | act/skip/语义 incomplete、短片段逐条提出、角色/依赖/覆盖审核、一次机会冻结 | 自主规划、多步和条件完整性；r6 四头只是开放草稿诊断，整臂仍未达到全部阈值 |
| D03 | 全人物目标、已行动及场外人物保留、完整实际判定接口 | 真实上游驱动后的目标语义和生产骰点/版本来源接线 |
| D04 | 全威胁/判定输入、已确认行动复用、强制反应和再次牵连 | 空约束时过早结束仍有 r6 实证；新文本模型的真实反应链 |
| D05 | 全闭组共同判断、四类达成标签、原子事实、事实成员覆盖、不可覆盖冻结输入 | r6 未修 D05.2；原子结果因果与遗漏副作用必须用实际新链检查，不能只看合法引用 |
| D06 | U1—U6 顺序、真实固定 A 纯逻辑预览、联合位置图、多项描述操作及纯解除、全部任务、pending 子任务、全人物个性扫描、严格理智、结果映射与恢复 | 逐事实语义映射和真实上游六阶段；纯时间独立真实模型链；不是生产 A 提交。当前 A 已支持 partial U5 preview，不再列为旧接口缺口。 |
| D07 | 同轮及关联段完成/ready 来源门、可能性与关联性分判 | 正式 A/B/C 整轮结束和自动后续链，不能用局部结算单元完成替代整点提交 |
| D08 | 初始/剩余后缀计划、已访问含 skip 排除、冻结顺序、时间锁与恢复 | 模型时间/事件边界的语义及正式调度接线；提议不构成实际访问 |
| C/D | 同一点 before/原始变化/after 来源绑定、正式提交后叙事、失败同事实重试及旧 ready 隔离 | 真实 C 模型、正式提交/ready 服务与浏览器完整请求；C 质量未测 |

B 现有 `rollRefs` 已含实际 `result/eligible/admitted` 等字段，不能再次报告为“完全没有实际骰点”。需要交接的是完整来源和覆盖证明。完整请求 500 ms 始终包括 C、服务、ready、关联段与自动后续；未连接部分标未测，不填 0。

## 原件路径与小索引

只读工具：[short_delivery_index.py](../../../experiments/world-components-logic/short_delivery_index.py)。默认只输出预检摘要；指定新输出路径才落盘，而且拒绝覆盖任何已有文件。`--final` 会拒绝仍在运行、只有计划未执行或保留/身份检查有问题的批次。默认不读取权重字节，明确标为 size-only；需要最终逐字节核验时显式使用 `--verify-model-bytes`，不导入神经库。

- Qwen 计划、失败摘要、原始日志和冻结源：`artifacts/world-components-logic/qwen-short/`。
- 浏览器各批计划及完整 `.record.json`、`.record.journal.jsonl`、`.record.webgpu.jsonl`：`artifacts/world-components-logic/short-semantics/evaluation-qwen-webgpu-base-20261109-r*`。
- focus r6 计划、摘要及原件/无损 gzip 索引：同一 `short-semantics/` 目录下 `short-encoder-focus-20261109-r6.*`。
- focus 两个整臂身份：`.local/world-components-logic/focus-encoder-models/short-encoder-focus-20261109-r6/{full_mean_control,global_plus_focus}/provider.json`。不得按单头分数拼装两臂。
- 非云缓存：`~/.cache/jity-d-short-semantics-20261109/{webgpu,encoder}/`。复制清单保留源和目标的实际 SHA；改变部署路径不改变权重身份。

任务目录内新增三份局部 `.gitignore`，只排除原始 record/journal/webgpu/process/stderr、探针原始记录及权重。小计划、摘要、索引与冻结源仍可显式纳入 Git。索引逐路径登记 `tracked/ignored/outsideRepository`，已跟踪原件或仓库内未忽略的原件都会报告问题。没有运行 `git add`，没有删除原件，也未改全局忽略规则。

截至本次预检，218 个选定文件/资产登记未发现 Git 保留或已读取字节身份问题；模型字节未在本次预检重读。Qwen WebGPU r5 仍在执行，因此 `readyForFinalIndex=false`。这是瞬时观察，最终 v2 必须重新读取全部已结束证据。


本轮索引工具已扩展到 `qwen-short`、`short-semantics`、`short-semantics-20261109` 的全部本次批次和快照，并登记 `time-choice-v2` 数据迁移、source-recheck、隔离与资格更正。普通 `.plan.json/.record.json` 和 `.export-plan.json/.export-record.json` 分别配对，保留的 `.gz` 也视为记录，不因只有压缩副本就写成未执行。原始记录状态与更正后的 `effectiveDisposition` 分开；有计划身份、理由及明确零模型调用证据的 `superseded_before_execution` 可结案，但 `executionCompleted=false`。

默认 raw 及权重只索引路径、大小、时间和此前登记的哈希，不重新读取大原始记录或取回云端占位；`evidenceNotRehashed` 逐项列出这种限制，缺已有哈希不会冒称完整校验。显式 `--verify-raw-bytes` / `--verify-model-bytes` 才对可读取的相应文件重新流式散列。云占位不会自动触发下载，运行元数据仍不明时保留未解决状态。新正式浏览器批次的 raw 应在仍为本地实体时完成散列、无损压缩及存档索引，再纳入最终清单。

`quarantine-export-r1/relocation-index-v2.json` 记录旧顶层路径到保留隔离路径及原字节 SHA，并绑定原 index；原 index 和 manifests 未改写。r1 的严格失败关联使用另存的 `qualification-correction-v2.json`，旧 `diagnostic_completed` 不再被解释为导出合格。索引不运行模型、不写 Git，不修改旧 inventory；最终 inventory v2 仍应等待最新浏览器批次封存后独立生成。
