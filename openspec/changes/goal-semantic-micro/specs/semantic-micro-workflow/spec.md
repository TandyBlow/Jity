# Spec Delta: semantic-micro-workflow

## Purpose

浏览器本地 TRPG 的语义工作流在运行期不依赖任何通用语言模型：行动理解、目标识别、被迫反应、共同结算、状态更新、任务变化与继续推进由确定性程序与专用微型模型完成，并对不确定结果给出可验证的弃权与保守结算路径。

## ADDED Requirements

### Requirement: Runtime semantic work calls no general LLM

运行期语义职责 MUST 由程序与微型模型完成，MUST NOT 调用通用语言模型；产品语义臂 MUST NOT 下载、初始化或调用 `/models/Qwen3-0.6B-Q4_K_M.gguf`。叙事生成按 D-145 继续使用现役 1.7B 模型，不属于本要求。验收 SHALL 同时提供模型请求记录、运行时初始化记录与推理调用计数三类证据。

#### Scenario: Micro-only turn completes with zero semantic LLM calls

- **GIVEN** micro-only 配置且 0.6B 模型文件被阻断
- **WHEN** 玩家提交一次会触发行动、结算、状态更新与叙事的输入
- **THEN** 回合完成并提交状态
- **THEN** 请求记录、初始化记录与调用计数中语义 LLM 调用数为 0，且叙事继续由 1.7B 生成

### Requirement: Abstention resolves conservatively without shrinking the game

当微型模型或规则不确定时，配置 MUST 通过候选重选、证据补充、局部判断或合法保守结算继续回合。它 MUST NOT 以拒绝玩家行动、默认结算失败、跳过状态更新、减少 NPC 行为或提前结束回合来提高成功率；这些回退 SHALL 被记录并计入验收报告。

#### Scenario: Low-confidence decision still settles

- **GIVEN** 一次玩家行动的目标识别或结算判断低于微型模型置信门
- **WHEN** 回合继续
- **THEN** 程序按保守规则给出可提交的合法结果（例如无状态变化或保留原值），并记录弃权原因
- **THEN** 被跳过的合法变化、被拒绝的行动与减少的 NPC 行为在验收报告中计数，而不是计为成功

### Requirement: Micro-only is an explicit experiment configuration

系统 SHALL 提供独立可选的 micro-only 配置：每个语义端口接入程序与微型模型，语义 LLM 被显式禁止。该配置 MUST 区别于现有 `semanticArm=rules|classifier` 的引擎代理抛错臂，覆盖正常调用、异常输入与微型模型弃权后的处理路径，并可在真实页面复现。

#### Scenario: Normal and invalid inputs across every port

- **GIVEN** micro-only 配置
- **WHEN** 依次执行正常输入、异常输入（未登记实体、否定、复合动作）与触发弃权的输入
- **THEN** 每个语义端口都走程序/微模型路径或记录弃权后的保守处理
- **THEN** 页面证据标明该臂身份，且不产生语义 LLM 请求

### Requirement: Structured events carry source and evidence state

语义工作流 SHALL 输出结构化事件，覆盖行动者、目标、动作、对象、结果、程度、原因、位置、信息、环境变化与事件之间的关系，并保留事实来源。事件 MUST 保留 present、absent、insufficient、conflict 四种证据状态；insufficient 与 conflict MUST NOT 被当作负例。事件表示 SHALL 通过兼容适配层提供，不修改 `WorldState` schema。

#### Scenario: Insufficient and conflict are preserved

- **GIVEN** 一条事实引用了未核验或与既有状态冲突的证据
- **WHEN** 生成结构化事件
- **THEN** 事件带有 insufficient 或 conflict 状态与事实来源
- **THEN** 该事件不进入训练的负例集合

### Requirement: Each replaced task reports baselines and measured costs

每个被替换的语义职责 SHALL 报告四类基线（程序规则、现有微型模型、原 0.6B、新候选）与指标：任务正确性、覆盖率、错误类型、拒绝率、误判率、参数量、权重体积、推理耗时与运行内存。新增模型 SHALL 优先在 1e5–1e7 参数范围内；更大模型必须给出能力收益与资源成本证据。模型 MUST 通过 PyTorch、ONNX 与浏览器运行结果的一致性验证。

#### Scenario: Task replacement evidence

- **GIVEN** 一项语义职责的新候选
- **WHEN** 该候选完成离线与浏览器评测
- **THEN** 报告包含四类基线与上述指标、冻结测试集与真实回合结果
- **THEN** 质量或成本不达标时保留失败记录，不接入产品默认

### Requirement: Frozen acceptance data never trains or tunes the replacement

冻结八场景与二十输入验收数据 MUST NOT 进入训练、验证或阈值调整。训练与测试划分 SHALL 按场景、事实集与回合分组，防止同一事实及其改写同时出现在两侧；开发期用更强模型辅助标注时 MUST 有独立证据核验，原 0.6B 输出 MUST NOT 未经核查直接作为正确答案。

#### Scenario: Grouped split rejects leakage

- **GIVEN** 从真实回合导出的逐任务数据集
- **WHEN** 构造训练与测试划分
- **THEN** 同一场景、同一事实集或同一回合的样本只落在其中一侧
- **THEN** 冻结八场景与二十输入不在训练、验证或阈值扫描中出现

### Requirement: Browser acceptance covers the frozen contract

micro-only 配置 SHALL 在真实页面完成冻结八场景、二十输入、刷新恢复、离线、共同结算、任务变化、NPC 自主行动与额外自由交互验收，并维持现有混合方案的状态 48/48、任务 14/14、成就 3/3 表现；同时 MUST 检查额外错误状态与被跳过的合法变化。新增场景 SHALL 有独立事实与状态验证。

#### Scenario: Frozen contract comparison

- **GIVEN** micro-only 配置与现役混合方案
- **WHEN** 两者跑同一冻结八场景夹具
- **THEN** micro-only 至少维持 48/48 状态、14/14 任务、3/3 成就
- **THEN** 报告列出额外错误状态、被跳过的合法变化、桌面与移动端耗时及峰值内存
