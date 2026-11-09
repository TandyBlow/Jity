# 四个早停判断头：r6 完整语境与请求关注对照

2026-11-09。批次 `short-encoder-focus-20261109-r6` 已真实完成 CPU 单线程训练及 140 条首次开发/测试分类，零重试、零未启动。四个头均未达到预先冻结的草稿一致性门槛，不能标为能力验收通过。没有加载或调用 Randeng，没有调用任何生成模型。旧 r3/r5 仅以只读编码头身份参与诊断。

## 退化的证据与本批改动

r3 的 62 个编码任务共享 320 次样本曝光；D02.1、D02.2.next、D04.1.next、D05.3.next 各只有 5 次。D02.2.next 中 end/fragment 为 3/2，D05.3.next 中 end/fact 为 3/2。r5 另给 D02.1 32 次三标签曝光，但 24 个开发/测试输出仍全是 act。r3 的 D02.2.next 26 个输出全 end，D04.1.next 8 个全 constraint，D05.3.next 12 个全 end；这不是程序合法结束规则，而是实际训练头的退化输出。

原表示保留全部输入事实，按完整事实分窗，以每窗 token 均值再按 payload token 数加权平均。相同世界下，请求与当前片段只占很少的输入。本批真实测得，异标签而世界相同的 D02.1、D02.2.next、D04.1.next、D05.3.next 全局表示平均余弦分别为 0.999959、0.999828、0.999975、0.999956。这支持“差异被强烈稀释”的诊断，但不证明它是唯一原因。

新模块 [short_encoder_repair.py](../../../experiments/world-components-logic/short_encoder_repair.py) 仅为四个头建立独立 registry。MiniRBT 保留原固定 revision 和 `[0,1]` 派生层，冻结骨干。两臂均使用训练集拟合的逐维均值/标准差和同容量 MLP：`Linear(512,64) → GELU → Linear(64,classes)`。

- `full_mean_control`：完整原输入全事实编码，拼接同一全局向量两次。
- `global_plus_focus`：完整原输入全事实编码，再附加一份实际请求字段的独立编码。focus 程序复制非 world 字段、当前请求、片段、当前约束、全组判定及结果候选；按实际 actorId 或 D04 memberId 绑定当前人物记录，不作语义抽取或答案选择。完整 world、initial、任务、记录、时间始终仍在 global 分支。

两个分支都没有动作目录、固定生成答案、强制 fragment 或覆盖 end。D04 的执行人使用 memberId，而不是原威胁的 context.actorId；D02 反应意图使用编排已设置的反应人物和全部反应约束。D05 不按人物独立判断，其完整组和全部候选事实保留。

## 冻结范围

沿用 r5 的不可变数据快照，不改原数据包；仅选上述四个 label 任务。共 211 行，141 训练、70 开发/测试，来源组仍为 8/2/2。所有样本均是助手草稿，人审 0、来源未核；开发/测试此前已被查看，因此本次不能称新泛化成绩。每个标签在三种 split 都有实际样本。

每臂冻结 512 步、batch 8，四头各 1,024 次曝光。每条训练行均被真实使用，最低曝光次数分别为 D02.1 14、D02.2.next 12、D04.1.next 64、D05.3.next 21。两臂使用相同任务/标签/来源均衡 schedule、随机种子、MLP 容量与归一化规则。全部已生成标签均有正目标数据梯度；新权重真实保存、重载并校验。原骨干 tensor hash 不变，其他 58 个头的表示和权重没有迁移。

训练内只复用同一冻结输入、编码器、分词和精度下的特征。开发/测试每臂逐例重新编码完整实际输入。最长原 payload 7,623 token、16 个全局窗；focus 最多 6 窗，没有截断。全部标签和草稿目标只用于训练或事后评分，不进入实际推理输入。

监督限制为 1,200 秒、3,072 MiB、单进程单线程、零重试；使用既有 `experiment.py` 公共监督器和 AppendJournal，而不是另造运行器。原始事件完整落盘，内存只保有界 checkpoint 引用。

## 全部首次结果

下表是草稿标签匹配，不是人工语义评分。历史列为本批在同一完整输入上用原 r5 编码头只读计算的输出；它不参与初始化、选择或覆盖新输出。

| 组件 | 历史编码头 | 新完整平均控制 | 新全局＋focus |
| --- | ---: | ---: | ---: |
| D02.1 | 12/24 | 16/24 | 20/24 |
| D02.2.next | 12/26 | 22/26 | 22/26 |
| D04.1.next | 4/8 | 4/8 | 5/8 |
| D05.3.next | 4/12 | 8/12 | 8/12 |

冻结的探索门槛为每头总匹配率至少 90%、每标签召回至少 80%，且正式提升仍需语义人审。两个臂的四个头均未全部满足本地草稿门槛。

focus 臂具体错误：

- D02.1：act 8/12、skip 8/8、语义 incomplete 4/4。漏掉三条消费后 NPC 自主行动，以及一条玩家已给完整尝试原文的控制例；该控制即使正确也不证明自主规划。
- D02.2.next：fragment 14/14、end 8/12。gate 与 waiting 两个来源的普通/消费后变体在已有完整行动片段后仍继续，不能把这类过度生成称作修复完成。
- D04.1.next：constraint 1/4、end 4/4。waiting、jointlift、newentity 在尚无约束时过早 end，依然阻断合法反应。
- D05.3.next：fact 4/8、end 4/4。遗漏 gate 的后续结果、waiting 的首条及后续事实、jointlift 的后续事实。

D02.2.next 两个新臂结果相同，说明本批改善不能单独归功于 focus；相对历史还同时增加了训练曝光、MLP 与归一化。focus 与控制之间可比较的是固定这些条件后的附加输入表示。focus 的四头同世界异标签平均余弦为 0.999696、0.998618、0.999861、0.999683；差异扩大仍没有消除语义错误。

## 成本与交接

整个双臂训练＋验证监督墙钟 99.526 秒，250ms 采样峰值 RSS 427.58 MiB。实际 6,077 次 encoder window forward，累计 84.264 秒。这里包含训练特征提取和两臂验证，不能当成请求推理耗时。生成调用、A 正式服务、C 生成和 ready 等待均为 0；完整 500ms 仍未测。其他并行实验进程不在本进程 RSS 范围内，不能把此墙钟解释成独占整机基准。

`FocusSemanticProvider(manifest, checkpoint=...)` 返回 Completion；其 `.identity` 明确列出仅四个组件和精确模型/表示身份，`.checkpoint` 可由上层逐请求替换。D02.1 的原始 incomplete 标签先入日志，再转换成 `Completion.incomplete('semantic_incomplete:D02.1')`。未训练头、缺正类梯度、权重/表示漂移、错误均返回 incomplete；未知组件拒绝路由，不退回旧头。两臂 provider 均保存，后续实验应先冻结选定的整臂，不按每个头的成绩挑选。

本批没有修复 D05.2 的 partial/incomplete 判断，没有验证文本生成、真实上游候选分布、自动连锁或 C 交接。下一步应把已冻结的完整 focus 实验臂接入新 Qwen/WebGPU 文本后端，保留过早结束和过度继续错误，新增来自这些实际错误的同源监督时仍维持原来源组。对于 D04/D05，需进一步训练对“当前已有候选是否覆盖完整语义需求”的表示，不能直接按候选数量写 end 规则。

## 证据

- [冻结计划](../../../artifacts/world-components-logic/short-semantics/short-encoder-focus-20261109-r6.plan.json)：SHA `bcec0cfc8699f19aef789aaea9ffdc223a174f534ceffc08a2f11768b3674798`。
- [完整小型汇总](../../../artifacts/world-components-logic/short-semantics/short-encoder-focus-20261109-r6.summary.json)：包括 140 槽、逐标签混淆与全部失败；SHA `dae5625e5c55fa34c5968ad06c6f3edae3c5154818b9ea63e44edbfd22ea3101`。
- [原始记录索引](../../../artifacts/world-components-logic/short-semantics/short-encoder-focus-20261109-r6.raw-archive.json)：完整 record 和 journal 原件保留，gzip mtime=0，压缩及解压 SHA 均核验。原件/大 gzip/模型不入 Git。
- 模型：`.local/world-components-logic/focus-encoder-models/short-encoder-focus-20261109-r6/{full_mean_control,global_plus_focus}/provider.json`。focus manifest SHA `870cf849f9097311b575aa393aa0427d7ceacb5f0f5a430607af16d46941bf15`，控制 SHA `10cf7caf6f1f372a580696c38fc2dcbb062803423905b6962d905819eec1af04`。
- [工程反例](../../../experiments/world-components-logic/tests/test_short_encoder_repair.py)：16 项通过，覆盖完整全局输入、反应执行人、全组候选、未知头、未训练正类、身份漂移、合法 end、语义 incomplete 和预调用超时。工程替身不算模型能力。
