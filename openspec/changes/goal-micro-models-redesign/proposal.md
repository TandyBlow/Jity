# Proposal: goal-micro-models-redesign

## Why

上一轮实验（`goal-micro-nlu-collaboration`）只验证了「不同规模的模型能否替换现有 Jity 任务」，没有验证「重设计任务后微型模型能否协作」。批评成立：

- 300 次任务不等于 300 次编码：共享一次编码 + N 个微型头才是设想形态；上一轮把编码次数与任务次数画了等号。
- 10M/100M 模型被喂了为通用模型设计的整段 prompt，输入设计错误；缺 token 数、消融、长度扫描、精度与分段耗时，196 ms 无法归因。
- 阶梯跳过了 0.1M–5M 的 CNN/MLP/GRU 与 fastText。
- 41 条、两个实体、单一 act、循环银标，撑不起能力结论；需要对抗性切分与手标。
- 「action/reaction/fact 不可替换」混淆了「不能替换现有自由文本契约」与「不能换一种方式完成任务」；结构化语义解析是另一条路。

## What Changes

- 任务重设计：动作/reaction/fact 改为结构化记录（actor/action/target/source/destination/stealth 等），头只输出字段；叙事在结算后统一生成。
- 共享编码协议：输入编码一次，N 个头读同一向量；长度扫 8/16/32/64/128 tokens；编码与头分别计时。
- 阶梯补齐：0.1M/0.5M/2M/5M 的 MLP/CNN/GRU + fastText + MiniRBT；记录精度、量化、张量形状。
- 消融：删任务说明/示例/规则后的准确率；分词/张量构造/推理/后处理分段耗时；多线程/SIMD/WebGPU 上限对照。
- 数据：手标平衡集替代银标；对抗性切分（换名、未见物品、改写/否定/指代/省略、相似干扰、多行为先后）。
- 真机有设备才跑；无设备如实记录。

## Capabilities

（无；实验与数据工作，不改产品默认。）

## Impact

- 新增实验 harness、数据与模型，不动产品默认路径。
- 证据：`artifacts/goal/micro-redesign/`。
- 风险：手标工作量、组合误差、未见世界的泛化。
