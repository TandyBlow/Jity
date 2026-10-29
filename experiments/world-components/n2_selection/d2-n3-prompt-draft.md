# D2 N3 模型臂 prompt 预登记草案（未冻结）

日期：2026-10-29。状态：**草案**——按 D2 预登记（n2-content-selection.md §6 判据行「一次预登记 prompt，总重试 1 次」），本文件经 C 审查者与项目负责人签认后冻结哈希，随后才允许运行 N3 模型臂。冻结前不得运行任何模型推理。

## 预登记口径

- **唯一 prompt**：模型臂只使用下述模板（含 R1–R6 规则原文），不针对结果调参、改写或加提示。跑输即归档失败。
- **总重试 1 次**：每次调用若输出不可解析为合法 JSON（或违反 H1/H2 结构检查），允许带固定的重试后缀重试一次；两次都失败计该条目失败。
- **盲 A/B 只作佐证**：如需佐证，仅允许记录输入顺序翻转等呈现变体的行为差异，不进判据、不改变主判定。
- 模型臂对象按 [model-training-runtime.md](model-training-runtime.md) §3.1：instruct 生成臂（现役 0.6B）先行；编码器 pairwise 头不消费本 prompt，另行登记。

## Prompt 模板（正文逐字冻结对象）

```text
你是叙事组织器。输入是一个视角和一组已选定的事实条目（JSON）。你的唯一任务是把它们组织成句组计划，不写正文。

规则（必须全部遵守）：
R1 同一 entityId 的全部事实进入同一个句组。
R2 不同实体的 task_achieved 事实若 goal 逐字相同，这些实体所在的句组合并为一个句组。
R3 kind 为 time 的事实并入其输入序中紧邻前驱事实所在的句组；若 time 位于输入首位，则并入输入序第一个事实所在的句组。
R4 不满足 R2 的不同实体事实各自成句组，不合并。
R5 句组之间按各组内最小输入序号升序排列；句组内部 factIds 按输入序号升序。
R6 每个句组输出 coreference：句组内每条含 entityId 的事实各产一条 {"mention": 该实体登记名, "refersTo": 该 entityId}，顺序与该句组 factIds 一致。

只输出一个 JSON 对象，不要输出任何其他文字：
{"itemId": "<条目ID>", "sentences": [{"index": 0, "factIds": ["f1"], "coreference": [{"mention": "名字", "refersTo": "entityId"}]}]}

视角：{viewpoint_json}
事实条目（输入序）：{facts_json}
```

- `{viewpoint_json}` / `{facts_json}`：逐字节取自 `d2_capability_items.jsonl` 对应条目的 `viewpoint` / `facts` 字段（`json.dumps(..., ensure_ascii=False)`），不增删改字段。
- 重试后缀（固定逐字）：`上次输出无法解析为合法计划。重新只输出 JSON 对象。`

## 解析与判定

- 解析只取首个顶层 JSON 对象；交由 `d2_metrics.py`（哈希见冻结记录）按预登记指标评分，不另设软性判分。
- H1/H2 违规视同该次尝试失败，进入重试；两次失败计失败。
- 全部原始输入/输出、尝试次数、耗时与设备随运行归档；16 项 v2 集与 8 项能力集分开报告，不合并分母。

## 冻结方式

签认后：本文件正文（模板+后缀+本节以上的口径文字）的 sha256 记入 D2 冻结记录（artifacts/world-components/），随后方可运行模型臂。任何改动即需重新签认。
