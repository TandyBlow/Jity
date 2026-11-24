# Design: goal-micro-workflow

## 结构

- 动作语义层（targets）新增 `microTargets` 端口：输入为声明的 call input（state/sourceId/actionText/maxTargets），输出目标 id；返回 null 表示弃权。
- 证据区分四种来源：`program`（纯规则）、`micro`（规则+微型模型）、`model`（LLM 接受）、`fallback`（LLM 失败后的程序兜底）。弃权/拒绝/异常分别记 `micro_abstained` / `micro_rejected` / `micro_failed`。
- 结算任务（results/updates/continuation）在 turn-execution 端口按同一模式接入；微型值必须通过现有校验器，失败即回退并记录原因。

## 统计

- 每任务记录：backend（rules/micro/llm）、调用次数、耗时、回退原因。
- 首载：微型模型（ONNX/GGUF）加载耗时单独计；回合耗时只含加载后的推理。

## 验收

- 同一 20 输入，微型开关关/开各跑一遍；回合耗时、结算错误、检查器、叙事质量对比。
- 不读取人工预设结算；回合由真实游戏输入驱动。
