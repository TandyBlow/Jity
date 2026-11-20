# 授权关系 → 表达闭环（2026-11-04，未训练）

第一个**有事实依据的跨主体承接**。它不等于整体叙事流畅，但表达层开始用真实关系，而不是猜关系。

## 1. 链条：两个不同的人，中间确实过了时间

真实无头 Edge 页面里，用页面自己的 `fetch`：

| 步骤 | 内容 |
| --- | --- |
| 点 A | `point_95`，林川（person_a）外貌变化「袖口沾了雨」，时间推进 **2 秒** |
| 点 B | `point_101`，周宁（person_b）外貌变化「斗篷下摆湿了一片」，时间推进 **3 秒** |
| 链 | `point_95.previous_point_id = root_91`，`point_101.previous_point_id = point_95` |

数据库里可查（`world_evidence` / `world_point_evidence`）：

```
point_95/person_a/appearance/change_97   appearance  {"text": "袖口沾了雨"}
point_101/person_b/appearance/change_103 appearance  {"text": "斗篷下摆湿了一片"}
point_95  seq=1  prev=root_91      delta_status=recorded
point_101 seq=2  prev=point_95     delta_status=recorded
```

## 2. 授权：只看校验器结论

服务端 `authorize()` 产出 N3 可用的片段：

```json
{"verdict": "pass", "validatorVersion": "world-relation-validator/1",
 "relations": [{"type": "before", "fromFactId": "f0", "toFactId": "f1",
                "evidence": [{"type":"event","evidenceId":"point_95/person_a/appearance/change_97"},
                             {"type":"event","evidenceId":"point_101/person_b/appearance/change_103"}],
                "authorization": {"verdict": "pass",
                                  "validatorVersion": "world-relation-validator/1"}}],
 "problems": []}
```

**浏览器能自己拼出证据 ID，不等于拿到授权**——编辑层只认这个 `verdict` 和版本号，不认客户端自己的推断。

## 3. 表达：只加一个操作

`relation-edit/1`，五个条件全满足才动手：

| 条件 | 不满足时的回退原因 |
| --- | --- |
| 两个单元在事实顺序里相邻 | `not-adjacent` |
| 关系方向与顺序一致 | `relation-reversed` |
| 授权 `verdict == pass` | `no-authorized-relation` |
| 校验器版本匹配 | `validator-version-mismatch` |
| 后一句以自己的姓名开头 | `subject-not-at-start` |

满足时只在**后一句前面**插“随后，”，**保留姓名、保留完整句界，不省主语、不合句、不重排**。

## 4. 真实产出

u240 照旧只生成单事实短句（HPC 作业 `239302`，2 单位，1.36 s / 0.10 s，均 `complete`）：

```
林川的袖口沾了雨。周宁的斗篷下摆湿了一片。
```

加上已授权关系后：

```
林川的袖口沾了雨。随后，周宁的斗篷下摆湿了一片。
```

操作记录（`chain-edit-result.json`）里带着两端 factId、证据引用与校验器版本，可逐条追到具体关系。

## 5. 四项验收

| 验收 | 结果 |
| --- | --- |
| 事件来源真实 | 两条证据 ID 在 `world_evidence` 可查，两点 `recorded`、链指向前一点 |
| 先后授权有效 | `verdict=pass`，两点间时间推进 2 s / 3 s（均 > 0） |
| 两条事实保持 | 两条事实文本都在、两个姓名都在、**句号数量不变**（句界未变） |
| 连接操作可回退 | 四种负例正文**一字未改**：无关系→`no-authorized-relation`；校验拒绝→同；方向相反→`relation-reversed`；不相邻→`not-adjacent` |

`ACCEPT PASS`。

## 6. 边界

- 关系缺失／失效／顺序相反／不相邻时**原样输出**，不猜、不加词；
- 不把 `relations` 塞给 u240——它仍然只看单事实输入；
- 只在同一条 chain 上、且两端都有事件证据时才成立；持续状态（一个事实绑多个点）永远不加连接词；
- 本轮不加“随即”“过了一会儿”，也不做合句、省主语、重排——这些都不在这一个操作的范围内。

## 7. 冻结

这一项能力冻结为 `relation-edit/1` + `world-relation-validator/1`。改动任一条规则都需要重新跑这条真实链并重出四项验收。

## 8. 交付物

服务端：`backend/app/services/world/provenance.py`（`authorize` + `VALIDATOR_VERSION`）、`backend/scripts/authorize_relations.py`、`backend/tests/test_world_provenance_chain.py`（7 条）。
表达层：`experiments/world-components/n4_narrative_dev/relation_edit.py`、`test_relation_edit.py`（7 条）、`build_chain_units.py`、`run_chain_units.py`、`run_chain_edit.py`。
证据：`artifacts/world-provenance/`（`provenance-browser.json`、`n3-authorized-relation.json`、`chain-units.jsonl`、`chain-out.json`、`chain-edit-result.json`）。
