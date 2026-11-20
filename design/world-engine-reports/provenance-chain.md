# 真实来源链打通：事件记录、事实来源与 `before` 授权（2026-11-04）

目标：让表达层以后能用“随后”，前提是有**真实可追溯**的事件证据，而不是靠数组顺序或提交顺序。本轮不改旧样本、不训练、不把新字段塞给 u240。

## 1. 权威提交时记录真实事件

新增**证据台账**（`world_evidence_v1.sql` + `world_evidence_store.py`），写在同一事务里：

- 写入点：`world_repository._save_point`，紧跟 `world_points` 写入之后，用的就是提交点的那条 `BEGIN IMMEDIATE` 事务，所以**状态、时间点、证据三项要么一起提交，要么一起回滚**；
- 证据由 `point.entityDeltas` 推导，不另造数据：位置变化、外貌变化项、性格变化项、理智、达成任务、新增子任务，每项一条，事件 ID 形如 `point_160/person_a/appearance/change_162`；
- **空 delta 是合法情况**：提交时没有变化就写 `delta_status='none'`，不是“没记录”；
- **缺行才表示“未记录”**：没有台账行的点（旧点、或没走新写入路径的点）读出 `None`，**不回填**。

```sql
world_point_evidence(world_id, point_id, sequence, previous_point_id,
                     delta_status CHECK(delta_status IN ('recorded','none')),
                     contract)
world_evidence(evidence_id, world_id, point_id, sequence, entity_id,
               kind, item_key, payload_json)
```

台账单独建表、单独版本号（`world_evidence_schema`），**不动冻结的 `world_storage_v2.sql`**，所以 150 条既有 world 测试全绿。

## 2. 事实来源

`backend/app/services/world/provenance.py`：

```python
bind_fact(factId, worldId, pointIds, evidenceIds)
```

- 只要点、没有事件 → 直接拒绝（“只有点是追溯不到事件的”）；
- 一个事实绑定多个点 → 标记 `sustained=True`（持续状态在不同点被看到，**没有单一发生时刻，永远不能排序**）；
- 来源结构与 `fact_contract` 完全分开：**N4 的文本序列化一个字节都没改**。

## 3. 证据分类型，`before` 校验

关系只允许一条 `before`，证据带类型：

```json
{"type": "before", "fromFactId": "f0", "toFactId": "f1",
 "evidence": [{"type": "event", "evidenceId": "point_221/person_a/appearance/change_223"},
              {"type": "event", "evidenceId": "point_225/person_a/appearance/change_227"}]}
```

校验（`validate_relations`）：

| 规则 | 结果 |
| --- | --- |
| 只有 `point` 证据 | 拒绝：“点顺序不构成事件先后” |
| 事件不属于该事实 | 拒绝 |
| 事件追溯不到 | 拒绝 |
| 两端在同一时间点 | 拒绝 |
| 两端不在同一 chain | 拒绝 |
| **两点之间时间推进为 0** | 拒绝 |
| 事实是持续状态 | 拒绝 |
| 成环 / 自指 | 拒绝 |

## 4. 浏览器真跑通一条链

在真实的无头 Edge（`HeadlessChrome/… Edg/156`）页面里，用页面自己的 `fetch` 走完整流程：

`create_world` → 根点旁白 → `start_advance` → `begin_point`（2 秒）→ 组协商 → `stage_unit`（外貌变化“袖口沾了雨”）→ 跳过其余演员 → `seal_point` → `commit_point` **点 A** → 旁白 → `round_conclusion_conclude(continue)` → 自动轮 → `begin_point`（3 秒）→ 同上 → **点 B**（外貌变化“袖口干了”，supersedes 点 A 的项）。

结果（`artifacts/world-provenance/provenance-browser.json`）：

```
pointA = point_221, previousPointId = root, elapsed 2 秒, delta by person_a
pointB = point_225, previousPointId = point_221, elapsed 3 秒, delta by person_a
evidenceRefs = [point_221/person_a/appearance/change_223,
                point_225/person_a/appearance/change_227]
beforeAuthorized = true
```

关键点：证据 ID 是浏览器**用 `get_state` 返回的 `entityDeltas` 自己拼出来的**（`pointId/实体/类型/变化项ID`），不是服务端私有的东西，所以表达层能引用，也能核对。

## 5. 三项负面控制（同一批真实 ID）

`artifacts/world-provenance/provenance-browser-verify.json`，用 Python 权威校验器跑同一份真实数据：

| 控制 | 结果 |
| --- | --- |
| 正例 | `[]`（通过） |
| 只有点证据 | `f0 只有点证据，点顺序不构成事件先后`；端点同报 |
| 时间推进改成 0 秒 | `两端之间时间推进为 0，不构成先后证据` |
| 事实没有来源事件 | `拒绝：f9: 没有来源事件，只有点是追溯不到事件的` |

`VERIFY PASS`。

## 6. 明确没做的

- **旧点不回填**：`world.db` 里 5 个历史点 `delta_json` 是空的，`read_point` 对它们返回 `None`（未记录），与“无变化（recorded, none）”区分开；
- **五个手写跨主体样本不伪造来源**：`v01/t07/t09/t19/t21` 仍然一条证据都没有，`before` 照旧拒绝；
- **1 秒能不能写“随后”**：按你的决定不设门槛，`before` 只表示先后，不承诺间隔；本轮没有生成任何“随后”文本，表达层接入是下一步。

## 7. 交付物

代码（world-server 分支）：
`backend/app/database/world_evidence_v1.sql`、`world_evidence_store.py`、`world_repository.py`（写入挂点）、`backend/app/services/world/provenance.py`、`backend/tests/test_world_provenance_chain.py`（6 条）。

证据：
`artifacts/world-provenance/provenance-browser.json`（浏览器链结果）、`provenance-browser-verify.json`（正例＋三项负面）、`provenance-chain.cjs` / `provenance-browser-run.cjs` / `verify-browser-chain.py`（可重跑脚本）。

测试：`test_world_provenance_chain.py` 6/6；world 相关 150 条既有测试全绿；`backend/tests` 里 `test_campaign_wiring.py` 的 2 个失败是本分支既有问题（改动前后一致）。
