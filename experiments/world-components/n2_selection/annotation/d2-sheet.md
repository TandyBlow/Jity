# D2 gold 标注任务说明（每位标注者必读）

你是本实验的独立标注者之一。任务：阅读 `d2-gold-rubric.md` 与 `d2_capability_items.jsonl`，按约定对全部 8 个条目产出组织计划标签，写入 `d2-labels-template.jsonl` 规定的输出格式。

规则：

1. 只读四个输入文件：`d2-gold-rubric.md`、`d2_capability_items.jsonl`、本文件、`d2-labels-template.jsonl`。不要读取仓库内其他文件、旧标签、模型输出或另一位标注者的结果。
2. 标签完全由你按 rubric 独立判定；不做与其他标注者一致性的猜测或沟通。
3. 输出 JSONL：每条目一行，字段见 rubric；条目顺序与盲表一致。
4. 交卷前按 rubric 的校验清单自查一遍。
5. 完成后填写身份声明 `d2-identity-<你的ID>.json`（标注者ID、上下文声明、方法描述、局限声明）。

本任务是 AI 独立标注，产出 AI gold；不是人工标注或人工评测。
