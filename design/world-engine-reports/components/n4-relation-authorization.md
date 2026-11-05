# 上游关系授权追溯（2026-11-04，未训练）

问题：表达层要用“同时/先后/因此”组织跨主体内容，上游到底拿得出什么证据。

先说结论：**现有真实数据只能支持 `before`，而且证据是“时间推进大于零”，不是“数组顺序”；现有跨主体源一条也拿不到证据。**

## 1. 真实事件记录长什么样

`world.db` 里有 10 个时间线点、3 个 advance、6 个 round。点（point）的字段：

`id / sequence / kind / previous_point_id / round_id / advance_id / linked_from_point_id / time_json / delta_json`

| 字段 | 能证明什么 | 不能证明什么 |
| --- | --- | --- |
| `sequence` + `previous_point_id` | **已提交的顺序**（真实落库的链，不是数组下标） | 不等于叙事里的事件先后，只说明提交先后 |
| `time_json.boundary="elapsed"` + `duration.amount>0` | **确实过了这么久** → 两点之间有真实时间间隔 → 可支持 `before` | 不支持“因此”，也不支持“同时” |
| `time_json.boundary="instant"` + `duration=0` | 只说明引擎没推进时间 | **不等于同时**（同批次≠同时） |
| `advance_id` 相同 | 属于同一次输入引起的批次 | 批次≠同时，也与先后无关 |
| `round.order_json` / `cursor` / `acted` | 引擎遍历演员的处理顺序 | 处理顺序≠叙事顺序 |
| `trigger=player/automatic` | 谁触发 | 与时间无关 |
| `entity_deltas` | 才是真正的“事件内容” | **本地库里 5 个已提交点的 delta_json 全是空的** |

## 2. 三个“有证据”和两个“无法授权”的实例

**能授权 before 的（真实数据）**

1. `world_13`：`point_20`(seq 1) → `point_23`(seq 2)，`previous_point_id` 相连，两点各推进 **1 秒** → 可以写“先……后……”。
2. `world_35`：`point_42` → `point_45`，同样 1 秒 → 同上。
3. 一般规则：同一 world 的同一 chain 上，两点之间**时间推进之和 > 0** 才成立。`world_1` 只有一个点，没有点对，因此该世界目前无法产生任何 before。

**明确不能授权的**

4. `world_13` 的 `round_19`：`order=[person_a, person_c]`、`cursor=2`。这只说明引擎先问谁后问谁，不能写成“林川先动手，周宁随后”。
5. `point_20` 与 `point_23` 同一个 `advance_17`：同批次只说明它们由同一次输入引发，**不能**写成“同时发生”。

## 3. 我们的 5 个跨主体源：一条证据也没有

| 源 | 事实 | 事件 ID | 结论 |
| --- | --- | --- | --- |
| `v01` | f0–f3 | 无 | 无法授权 |
| `t07` | f0–f3 | 无 | 无法授权 |
| `t09` | f0–f3 | 无 | 无法授权 |
| `t19` | f0–f3 | 无 | 无法授权 |
| `t21` | f0–f3 | 无 | 无法授权 |

原因是这些材料由 `final24.py` / `cf24_materials.py` **手写**，事实里没有 pointId/eventId 字段，`world.db` 里也没有对应记录。硬塞一条 `before` 会被校验拒绝（`缺少 evidenceEventIds`）。

**这就是当前的能力缺口，按你的要求保留，不靠填字段补。**

## 4. 最小关系契约

放在 N3 计划的独立 `relations` 字段，**不改 `fact_contract` 的事实序列化**：

```json
{
  "type": "before",
  "fromFactId": "f2",
  "toFactId": "f10",
  "evidenceEventIds": ["point_20", "point_23"]
}
```

第一版只允许 `before`；`causes`、`same_time`、`reorderable` 一律拒绝（没有字段能证明）。

校验规则（`relation_contract.validate`，7 条测试全过）：

| 规则 | 判定 |
| --- | --- |
| 两端 factId 必须在计划内 | 否则拒绝 |
| 不能自指 | `f2→f2` 拒绝 |
| `evidenceEventIds` 非空 | 空即拒绝 |
| 证据必须能追溯到两端事实 | 事件不在两端事实的事件集里 → 拒绝 |
| 两点必须在同一 chain 上 | 否则拒绝 |
| **两点之间时间推进 > 0** | 为 0（instant/elapsed 0）→ 拒绝 |
| 不成环 | 有环 → 拒绝 |

另外一条不给证的规则：**事实列表顺序、factId 字典序、advanceId、round 处理顺序都不作为证据来源**，校验器根本不读它们。

## 5. 要你决定的两件事

1. **1 秒够不够写“随后”**：真实数据里的间隔都是 1 秒。表达层若把它写成“过了一会儿”就是夸大；只能写“接着/随即”这类不指定时长的词。要不要给 `before` 加一个 `minElapsed` 门槛（比如 < 5 秒只能用“随即”）？
2. **要不要让上游把 delta 写全**：本地库 5 个已提交点的 `delta_json` 都是空的，所以连“哪个事实来自哪个点”都追溯不了。若后续要真的在浏览器里跑这条链，至少要让每个事实带上产生它的 pointId。

## 6. 交付物

`relation_contract.py`（校验器）、`test_relation_contract.py`（7 条，全过）、`n4-relation-authorization.json`（可授权/不可授权实例与 5 个跨主体源的追溯结果）。
