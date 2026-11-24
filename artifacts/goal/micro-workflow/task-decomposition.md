# Jity 语义任务拆分（2026-11-24，基于真实回合记录）

## 数据

- `?record=1` 在页面里包住语义引擎，记录每次 `complete(prompt) → raw`；一轮真实回合得到 79 对，`records.jsonl`。
- 分布：results 21、updates 18、action 24、targets 11、reaction 1、continuation 4。
- 该回合（默认 LLM 路径）耗时 251.5 s。

## 任务拆分

### results（21 对，97.8 s/回合）

- 现输出：`judgments[]{memberId,label,reason}` + `facts[]{text,memberIds}`。
- 可拆：每位成员一条 5 类判定（achieved/partial/not_achieved/blocked/no_change）+ 归因；facts 是开放式短句。
- 微型模型：共享编码器 + 5 类头（输入 = 组上下文 + 该成员行动 + 骰点/准入）；训练标签直接取捕获的 judgments（银标）。
- 保留程序：骰点、准入、组冻结；facts 文本先留 LLM 或模板。

### updates（18 对，55.1 s/回合）

- 现输出：`positions[]{entityId,containerId,slotId,relativeTo}` + `appearances[]`（按阶段调用）。
- 可拆：实体是否移动（二分类）→ 目标容器/槽位（闭集打分）→ 外貌文本（开放）。
- 微型模型：移动判定头 + 候选容器打分（共享编码器）；外貌文本留 LLM。
- 保留程序：位置图、槽位合法性、环检测。

### action（24 对，81.4 s/回合）

- 现输出：`{kind:'act'|'skip', text}`。
- 可拆：act/skip（二分类，t2 intent 头已存在）→ 行动句（开放）→ 条件/可行性（分类）。
- 微型模型：act/skip 头 + 可行性头；行动句留 LLM。
- 保留程序：主角冻结命令、场景范围、去重。

### targets（11 对，6 ms/回合）

- 规则提议 + 打分器校验 + LLM 弃权（已实现）；不再优先投入。

### reaction（1 对）

- 被牵连角色的即时反应：文本开放（LLM）+ 反应判定（微型）。

### continuation（4 对）

- 候选行动生成（LLM）+ 每候选 likely 判定（微型二分类）。

## 训练计划

1. 从 `records.jsonl` 抽取 per-task 样本：results 的每成员判定、updates 的移动/位置、action 的 act/skip、continuation 的候选 likely。
2. 共享 MiniRBT 编码器 + 任务头（沿用 t2 四头结构），先训 results-label 与 act/skip；按回合切分训练/测试。
3. 判定：同任务头上，微型头与 LLM 标签的一致率；不一致样本人工看。
4. 集成：`?micro=1` 下按任务路由（程序 → 微型头 → LLM），统计比例与耗时；A/B 对照完整回合状态与叙事。

## 限制

- 79 对来自一轮、银标（LLM 已接受输出）；需要更多回合与人工复核。
- results 的 facts 与 reaction 文本是生成任务，不由分类头承担。
