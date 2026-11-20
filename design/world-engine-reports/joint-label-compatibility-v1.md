# 联合训练前标签兼容检查（2026-11-05）

**2026-11-05 更正：原“检查不通过”判断过严，已撤回。发现的是句法形式差异，不是判定范围冲突；联合训练允许启动，不改候选、不重标材料。**

> 判断指定候选跨度在当前上下文中表达的内容，是否得到权威授权支持。候选可以是句子、分句或短语。正文只用于恢复主体、指代及影响候选含义的否定、条件等语境；正文中其他独立陈述不纳入本次判定，也不构成授权来源。

下面保留原检查记录。

两池的标签都挂在 `candidateText` 上，正文不作为授权来源；但监督单元不一致：

- 原 general 训练池的 unsupported 候选是完整句；
- target 训练池的 body / background / visible-state 候选是片段；
- 只有 target extra-action 是完整句。

这正是“不能一池判整句、另一池只判片段”的条件。没有扩材料、没有建模型、没有跑联合训练。

## 1. 范围和计数

只检查训练池：

| 池 | 训练样本 | unsupported | 来源 |
| --- | --- | --- | --- |
| 原 general | 754 | 377 | `pairs-v1.jsonl` 的 general/train |
| target | 160 | 80 | `pairs-target-v1.jsonl` 的 train |

原 general dev、confirm、target dev、confirm 都没有进入训练池。

## 2. 单元统计

| 池/标签 | n | 候选是完整句 | 比例 |
| --- | --- | --- | --- |
| general supported | 377 | 377 | **1.000** |
| general unsupported | 377 | 377 | **1.000** |
| target supported | 80 | 20 | **0.250** |
| target unsupported | 80 | 20 | **0.250** |

target unsupported 按类：

| 类别 | n | 完整句 | 例子 |
| --- | --- | --- | --- |
| body | 20 | 0 | `指节被麻绳勒得发白` |
| background | 20 | 0 | `河雾里` |
| visible-state | 20 | 0 | `纸灯已点亮` |
| extra-action | 20 | 20 | `阿棠把鱼筐推开。` |

general 的 unsupported 例子：

```text
候选：顾北汀从咸水澳来到了鱼行。
正文：顾北汀从咸水澳来到了鱼行。阿禾完成了任务「清点鲞货」。二十分钟过去了，陈九从咸水澳来到了鱼行。
facts：阿禾完成了任务「清点鲞货」；陈九从咸水澳来到了鱼行；前后大约20分钟
label：unsupported
```

这里标签确实是候选句，而不是整段正文；general 的 `candidateText` 不等于 `fullText`（377/377 不是同一段），但候选是完整句。

target 的 body/background/visible-state 候选则是短语/片段；只有 extra-action 与 general 同为完整句。

## 3. 标签范围是候选级，但单元不一致

两边都满足：

- 标签在 `candidateText` 上；
- `fullText` 只提供上下文，不是授权来源；
- 正文中候选之外的越界内容不应改变候选标签。

但两边不满足：

- general 的候选是完整句；
- target 的 body/background/visible-state 候选是片段；
- target background `河雾里` 甚至不是主谓句，而是地点/背景片段。

因此不能把两池直接当成同一监督任务。若直接训练，模型会同时收到“判完整句”和“判片段”的两种单位；这会把标签兼容性问题混进联合训练结果，无法区分是配比/训练问题还是任务表示问题。

## 4. 归因修正

上一轮 target-only 训练是从 MiniRBT 基座独立初始化的，没有加载旧核对模型。因此：

- **不能说“目标训练破坏了原有 general 能力”**；
- 更准确的说法是：两个独立检查点跨分布表现失衡；general 298 是 **general 迁移评测**，不是能力保持证明；
- 也没有证据说发生了灾难性遗忘。

## 4.1 更正后的解释

原先把“general 完整句、target 片段”直接当成阻断条件，限制过严。真正需要排除的是：一池把整段正文当标签单位，另一池只判候选。检查结果支持后者：两池都只在 `candidateText` 上，`fullText` 只是上下文，未发现整段正文标签。

“指节被麻绳勒得发白”“纸灯已点亮”本身已表达完整状态，不能用有没有句号来判监督单位；“河雾里”作为背景框架，按上下文解释后也可纳入同一支持判断。

区别仍然保留：不检查候选外的独立陈述，不等于忽略影响候选含义的上下文（否定、条件、指代等仍要看）。`unsupported` 是“当前授权不足”，不是“与世界事实矛盾”。

## 5. 原记录：没有做什么

- 没有启动 16+16 联合训练；
- 没有建新模型/新检查点；
- 没有扩材料；
- 没有做配比搜索；
- 没有接 source head、服务或自动删句。

## 6. 更正后的决定

采用第 2 条“候选跨度支持”：候选可以是句子、分句或短语，`candidateText` 是唯一判定单位；正文只帮助恢复主体、指代及影响候选含义的上下文，候选外的独立陈述不纳入。

不改候选、不重标材料、不另设兼容审计；按固定的 general 16 + target 16、300 updates、25-step eval 方案执行。

## 7. 文件

- 检查记录：`artifacts/statement-verification/label-compatibility-v1.json`
  - sha256：`6a1a48c54cdb342f894d0df6b41d4083ceac64bef93a90d5edd67b258e943eec`
- 原 general 训练池：`artifacts/statement-verification/pairs-v1.jsonl`（general/train）
- target 训练池：`artifacts/statement-verification/pairs-target-v1.jsonl`（train）

没有新的训练/确认结果。
