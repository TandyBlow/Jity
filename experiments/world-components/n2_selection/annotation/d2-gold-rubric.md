# D2 gold 标注约定（N3 组织计划）

日期：2026-10-29。任务：对 8 个 N3 能力样本（`d2_capability_items.jsonl`）逐条产出组织计划 gold。本约定是**本实验的 gold 定义**，不是唯一合法的叙事分段方式；两位标注者都必须且只需按本约定执行。

## 输出形状

每个条目产出一个 JSON 对象（JSONL 一行），形状与 N3 窄形状一致：

```json
{"itemId": "n3cap-01",
 "sentences": [
   {"index": 0, "factIds": ["f1", "f2"],
    "coreference": [{"mention": "洛九针", "refersTo": "char_600"}]}
 ]}
```

- `sentences` 的 `index` 从 0 起连续递增。
- `factIds` 只能取该条目 facts 里已有的编号；每个编号恰好出现一次，不得丢失、重复或捏造。
- `coreference`：句组内每条**含 entityId 的事实**各产一条 `{mention, refersTo}`，顺序与该句组 `factIds` 顺序一致；`mention` 填该 entityId 在 facts 中登记的 `name`，`refersTo` 填 entityId。无 entityId 的事实（time）不产 coreference 条目。

## 分组与排序规则（全部机械化，按序应用）

- **R1 实体内聚**：同一 `entityId` 的全部事实进入同一个句组。
- **R2 协作事件合并**：不同实体的 `task_achieved` 事实若 `goal` 逐字相同，则这些实体各自的句组合并为一个句组。
- **R3 时间归属**：`time` 事实并入其**输入序中紧邻前驱事实**所在的句组；若 time 位于输入首位，则并入输入序第一个事实所在的句组。
- **R4 其余独立成组**：不满足 R2 的不同实体事实各自成句组（地点外貌、独立任务、他人的变化都各自成组，不合并）。
- **R5 顺序**：句组之间按各组内最小输入序号升序排列；句组内部 `factIds` 按输入序号升序。
- **R6 coreference**：按上文输出形状的规定逐条产出。

应用顺序：先按 R1 形成每实体句组，再按 R2 合并，再按 R3 归属 time（归入合并后的句组），最后按 R4/R5 排序并按 R6 产出 coreference。

## 校验

交卷前自查：编号恰好覆盖全部事实、index 连续、coreference 与 factIds 同长（无 entityId 的 time 除外）、mention 与登记 name 一致、refersTo 的实体在本句组内有事实。任何违反都视为无效标签。

## 边界说明

- 本约定刻意机械化，使两位标注者可独立复现同一结果；一致度门与裁决规则见 `d2-gold-protocol.json`。
- 不评估叙事优劣；不引入 facts 之外的世界知识；不因"读起来更顺"偏离上述规则。
- 这是 AI 标注约定，产出为 AI gold；其局限见协议文件的 limitations。
