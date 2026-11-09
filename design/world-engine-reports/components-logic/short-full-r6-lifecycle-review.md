# Full r6：初始化与纯时间的实际首次输出复核

本报告只审查 `evaluation-qwen-webgpu-base-full-20261109-r6` 已完成的 4 个 `live_initialization` 和 4 个 `live_pure_time` 槽位。436 槽总批次在复核时仍运行；此处不是全批结论。生成器是 0 步社区 Qwen3-0.6B WebGPU 基座，配合既有已训练编码头，不是未获导出资格的训练后 Qwen。四个来源组为 gate、waiting（开发）及 jointlift、newentity（此前已检查的测试）；不构成新的独立泛化证据。以下为助手复核，人工审阅 0，来源核验 pending。

**8 例均未完成。实际 A 初始校验和阶段预览均为 0 次，正式提交和 C 调用均为 0。** 81 次语义原语调用、963 个编码器窗口前向、15 次完整 `model.generate` 均有首次输出记录；15 次生成都到达 EOS。技术生成完成不表示语义通过。

## 初始化：4/4 在 D01.1 后停止

| 来源 | 真实实体提议 | 结构与语义问题 |
|---|---|---|
| gate | 4 个 `characters`，名称均为 `D01.1.name` | 重复组件名代替自然人名；未提出 brief 中的地点 |
| waiting | 2 个 `characters`，名称均为 `D01.1.name` | 同上 |
| jointlift | 2 个 `characters`，名称均为 `D01.1.name` | 同上 |
| newentity | 3 个 `characters`，名称均为“天文校时台” | 地点名称被生成为人物；地点清单为空 |

四例 `kind` 头在上述人物后给出 `end`，所有 `slot_next` 为 `end`，`protagonist` 为 0。主角索引对返回的人物列表合法；实际触发 `invalid_initial_protagonist_or_places` 的是地点缺失，不能笼统误诊为主角选择错误。D01.1 聚合可返回 `result`，但完整初始化在下一层结构检查失败。D01.2 拓扑、D01.3 外貌、D01.4 任务、D01.5 个性、D01.6 理智及 A 校验/封存全部未开始。

评分只依据实际 brief（两个地点和当前工作），没有要求模型复原未提供的参考世界人物姓名或数量。已有错误足以证明本次初始化未通过，无须借用隐藏参考答案。

## 纯时间：D08 有结果，六阶段未完成

| 来源 | 实际 D08 输出 | U1 首个对象的容器选择 | 停止位置 |
|---|---|---|---|
| gate | `elapsed / 0 minute` | 闸门手柄 → b（易安） | U1.2 选择槽位，但 b 没有槽位 |
| waiting | `elapsed / 50 minute` | 记录仪 → b（顾芒） | 同上 |
| jointlift | `elapsed / 0 minute` | 标本托盘 → a（柯遥） | U1.2 选择槽位，但 a 没有槽位 |
| newentity | `elapsed / 0 minute` | 校时钟 → b（奚白） | U1.2 选择槽位，但 b 没有槽位 |

每例 D08 读取完整世界、空冻结行动及 `time_scan=true`，实际先给出 `elapsed`、`minute`，再由生成器输出表内数值。其余三例的零时长通过现有 D 时间形状检查，但没有证明正向时间推进；此处不虚构唯一应取的正数。waiting 世界明确写有“观察期刚开始，显示还需稳定等待五分钟”，人物任务也指向该五分钟边界；50 分钟越过该明确事件边界，属于语义错误。

随后 U1.1 对每例全部 2 件物品、3 名人物分别调用，20/20 输出 `change`。完整输入没有 D05 结果、没有新冻结行动；单凭纯时间不支持这组无区别的移动判断。对 gate，b 原本“握着手柄”的描述也不能证明全部五个实体都发生了新的位置变化。U1.2 在首个 object 上选择表内人物为容器，再输出 `slot_mode=select`；该人物的注册 `slots=[]`，程序明确返回 `incomplete`，未补槽位或默认保持原位。

结构上，U1.1 实体覆盖为 20/20；U1.2 仅开始 4/20 个对象选择，完整新位置为 0。U1 联合图核对和 A 预览未开始，U2—U6 均未开始。四例当前共有 13 个任务，**U3 实际扫描为 0/13**；waiting 的五分钟任务、场外人物任务、个性联动和理智更新因此均未实测通过。没有调用 D05，也没有为了纯时间编造结果事实。

## 计时与证据边界

| 案例 | 局部 case wall（ms） | 包含结果落盘/遥测（ms） |
|---|---:|---:|
| initialization / gate | 6048.699 | 6112.068 |
| initialization / waiting | 2363.045 | 2431.396 |
| initialization / jointlift | 2762.947 | 2825.548 |
| initialization / newentity | 3021.578 | 3088.789 |
| pure-time / gate | 13374.416 | 13443.506 |
| pure-time / waiting | 9988.383 | 10055.401 |
| pure-time / jointlift | 14247.605 | 14320.255 |
| pure-time / newentity | 9003.190 | 9075.771 |

这些是失败局部请求，模型已预载；不包含生产 A/B 服务、正式 C 和 ready 门槛，不能用作完整 500 ms 验收。编码器统计是窗口前向次数，生成器统计是完整 generate 次数；不是逐 token 前向数。GPU 证明摘要从原响应保留，本审阅未重扫庞大 kernel 原始内容，也不将 profiling 累计 GPU 时间当作无追踪开销的纯算力。

[逐例审阅 JSON](../../../artifacts/world-components-logic/short-semantics/evaluation-qwen-webgpu-base-full-20261109-r6.lifecycle-assistant-review.json) 保存全部 81 次原语首次值、15 次生成原文/token/EOS、完整输入文件及哈希、实际阶段、未扫描任务，以及对应原始 journal 的 byte offset、length、raw-line SHA 和 event SHA。该 JSON SHA-256：`8041f06ecf0f01a1447006c12c5c9eebd8844b41a6f25ce9f38bab23072fd61b`。每个保留的语义事件已按 offset 重新读取原文件核对；原日志未修改。

冻结计划 SHA：`44e445df431419238b764330914f0fd24958a6030924a87ea7695ccec79b921e`；完整前 56 槽提取前缀止于 sequence 35654，前缀 SHA：`2da988d7b08f57d417bc4e3845fd3a9f47ebe184a0994c80ff400b7a8ac83b37`。本报告仅使用其中序号 48—55，未选择成功样本，未重试、改答案或接入运行代码。

后续改进应分别针对 D01 人物/地点类别与结束条件、生成器误复述组件名、D08 显式事件边界，以及 U1 对纯时间条件的判断与槽位依赖。先保留这些真实错误做训练和来源分组验证，不能通过程序生成地点、移动或任务达成来绕开当前失败。
