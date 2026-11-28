# Proposal: goal-semantic-micro

## Why

D-145 把产品终态扩展为「运行期不依赖任何数亿参数通用语言模型」。语义工作流目前仍调用 Qwen3-0.6B：二十输入 20 回合共 344 次语义 LLM 任务调用（E53），其中任务达成 20 次、新增小任务 29 次、行动 159 次、目标识别 63 次，结算侧单次 prompt 中位 2.9k–4.0k 字。这些调用要的是判断、分类、抽取与受限生成，不是长文理解；现有规则与微型头已接管 results 289/292、continuation 33/33、reaction 4/4。需要一个独立的工作包把剩余职责逐项替换，并在浏览器里证明 0.6B 不再被下载、初始化或调用。

## What Changes

- 建立语义调用职责清单：每项职责的输入、输出、触发条件、回退与重试路径、调用次数、耗时、现有替代组件与未解决能力；区分程序可计算、语言理解、信息抽取与开放生成。
- 新增独立 micro-only 实验配置：程序 + 微型模型，显式禁止语义 LLM；不是现有 `semanticArm=rules|classifier` 那种把引擎代理成抛错的降级臂。该配置对不确定结果做候选重选与保守结算，不以拒绝行动、跳过状态更新或减少 NPC 行为提高成功率。
- 按优先级替换：任务达成判断 → 新增小任务 → 人格 → 理智 → 外貌 → 位置 → 行动结果 → NPC 自主行动。每项先建基线（程序规则 / 现有微模型 / 原 0.6B / 新候选），再训练与接入。
- 从冻结验收证据导出逐任务数据集：`semanticCalls` 的 `(输入, 输出, 校验结果, 耗时)`，按场景 / 事实集 / 回合分组切分；冻结八场景与二十输入不进入训练或阈值调整。
- 新增结构化事件兼容层：行动者、目标、动作、对象、结果、程度、原因、位置、信息、环境变化、事件关系与事实来源；保留 present / absent / insufficient / conflict 四态。适配层不改 `WorldState` schema，叙事侧先用适配层读取。
- 浏览器验收：micro-only 配置跑八场景、二十输入、刷新恢复、离线、共同结算、任务变化、NPC 自主行动与自由交互；用请求记录、运行时初始化记录与推理计数证明 0.6B 未加载。
- 每一研究工作包在 `design/research/` 记录假设、实验条件、结果、失败原因与下一步决策。

## Capabilities

### New Capabilities

- `semantic-micro-workflow`: 运行期语义职责在无通用 LLM 时的行为契约：逐任务程序/微型实现、弃权与保守结算、micro-only 配置、0.6B 未加载的验收证明、逐任务基线与证据口径。

### Modified Capabilities

- 无。叙事模型与产品页交互契约不变；本变更不修改 `product-page` 与 `browser-world-kernel` 的既有要求。

## Impact

- 代码：`frontend/src/lib/world-engine/local/semantics/**`（actions、settlement 各阶段）、`local/micro/**`（任务提案、验证、更新、行为）、`frontend/src/app/world-local/page.tsx`（语义臂开关与模型加载）、`frontend/scripts/`（验收驱动与数据导出）。
- 资产：新增或替换 ONNX 权重与 vocab；移除产品对 `/models/Qwen3-0.6B-Q4_K_M.gguf` 的依赖（叙事 1.7B 不变）。
- 数据：新增导出与标注脚本；大数据集留在 `experiments/semantic-micro/`（gitignored），仓库只存清单、哈希与报告。
- 测试：Vitest 单元/集成测试 + 冻结验收夹具；Python 仅作开发期分析脚本，不进入运行期。
- 风险：弃权策略若设计不当会以「拒绝行动 / 跳过更新」虚增成功率；任务达成与新增小任务是开放式判断，微型模型可能只在固定场景过拟合。验收必须同时报告错误类型与被跳过的合法变化。
