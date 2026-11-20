# 叙事正文判分器 v1（材料 + 判分器 + 误报漏报报告）

对象：N4 叙事正文（「场景上下文 + 结构化事实 → 一段正文」）。
范围：只做离线判分，不训练、不导 ONNX、不改页面。判分器自己的误报/漏报先测，未过人工复核前不用于放行模型。

## 交付物

| 文件 | 作用 |
| --- | --- |
| `materials.py` | 从已审语料与真实模型输出构建四组材料 + 单点改动负例 + 合法变体 |
| `checker.py` | 判分规则：全局禁述、视角、逐事实（移动/结果/外貌/个性/理智/无变化）、未知专名、重复 |
| `run_eval.py` | 跑四组材料，统计误报/漏报，写 `eval-report.json` / `eval-report.md` |
| `test_checker.py` | 17 条最小单元测试（每条规则 + 合法省略/同义/视角内心理） |
| `../../artifacts/world-components/n4-narrative-eval-v1/` | 材料、人工标注稿、评测报告 |

## 材料怎么来的

| 组 | 数量 | 来源 | 用途 |
| --- | --- | --- | --- |
| `cases.jsonl` | 132 | 已审语料 v0(12)/v1(20)/v2(88) + 新世界 holdout(12)；每条含 facts/sceneState/perspective/目标正文 | 判分输入 |
| `positives.jsonl` | 132 | 上述目标正文（用户已审） | 正例：判 fail = 误报 |
| `mutations.jsonl` | 734 | 对目标正文做**单点改动**：换主语、反转方向、加他人内心、泄任务目标、加数值面板、写明确时长、加未授权人名、删必述事实句 | 负例：没按预期规则判出 = 漏报 |
| `legit_probes.jsonl` | 528 | 合法变体：删模糊时间词、同义改写、加视角人物内心、加场景细节 | 合法变体：判 fail = 误报 |
| `model_outputs.jsonl` | 24 | 12 条 zero-shot 整段输出（`n4-holdout-r1`）+ 12 条槽位臂整段（`n4-compose-full-r2`） | 真实输出对照 |
| `annotations.jsonl` | 24 | 逐条逐事实的人工标注稿（`annotator=assistant-draft`，`reviewStatus=pending-human`） | 与判分器对照 |

标注字段：`perFact[{factId, status(covered/violated/omitted/uncertain), note}]`、`overall(pass/fail/uncertain)`、`reasons[]`。

## 判分器怎么判

输出 `verdict ∈ {pass, fail, uncertain}`，每条检查带 `rule`、`factId`、`span`（出错原文）、`evidence`（依据）。

**`pass` 的边界**：结果里固定带 `verdictScope=automatic-rules-only`、`passMeans`、`notAutomated`。pass 只表示"现有自动规则没有发现问题"；自然度、隐含事实、代词与身体感受都没有检查。下游不得把 pass 当验收通过，人工结论要另存字段。

| 规则 | 判据 | 结果 |
| --- | --- | --- |
| `forbidden.goal` | 出现任务标语或 taskId（**目标原文与结果动作同形时不算泄漏**，这是修过的一处误报） | fail |
| `forbidden.numeric` / `.digit` | 数值面板、阿拉伯数字 | fail |
| `forbidden.duration` | 明确时长（契约要求模糊/省略） | fail |
| `forbidden.fieldName` | 位置/事实/输入/输出/字段/面板等 | fail |
| `pov.innerOther` | 他人姓名 + 内心词；代词主语只归 uncertain | fail / uncertain |
| `fact.moved.direction` | 从已知地点出发的方向短语与事实比较；小地名只作不确定 | fail / uncertain |
| `fact.moved.subject` | 移动短语前 8 字内最近的人名 | fail / uncertain |
| `fact.outcome.*` | 结果动作内容词命中；本人有动作句时看归属；整段无此人 → fail | pass/fail/uncertain |
| `fact.attribution` | 结果动作所在分句的主语是别人、且本人没有带同一锚点的分句 | fail |
| `fact.{appearance,personality}` | 细节内容词命中，否则 uncertain | pass / uncertain |
| `fact.sanity.direction` | 只判方向（上升/下降）是否与事实一致 | fail / uncertain |
| `fact.noChange` | 无变化点上出现变化措辞 → uncertain | uncertain |
| `fabrication.name/place/item` | 与输入、场景、世界设定的词表比对 | 一律 uncertain |
| `style.repetition` | 分句原样重复 | uncertain |

不自动判的：**自然度、隐含事实、代词指向是否越界**——这些固定返回 `uncertain`，交人工。`checker.py` 末尾的 `not_automated` 字段也写明。

## 当前结果（`eval-report.json`）

| 组 | 结果 |
| --- | --- |
| 正例 132 | **没有被误判 fail**（45 条 uncertain） |
| 合法变体 528 | **没有被误判 fail**（182 条 uncertain） |
| 单点负例 734 | 按预期规则判出 **532**，uncertain 24~132 视类型，漏 0~18 |
| 真实输出 24（对照修订后标注） | 一致 3，**误报 0**，严格漏报 1，人工存疑但机器放行 8，abstain 12；矩阵见 `eval-report.json` |

单点负例分类型：目标泄漏 55/55、数值面板 132/132、明确时长 132/132、他人内心 132/132、方向反转 28/29、删事实句 42/84、换主语 11/38（其余为 uncertain/漏）、未授权人名 132/132 归 uncertain（按设计不判 fail）。

## 已知缺口（不粉饰）

- `drop-fact`：删句后别处仍提到同一地点/动作时抓不到；42/84 判出，18 条完全漏。
- `swap-actor`：只对"结果动作"判归属；移动被省略时给 uncertain，23/38 属此类。
- 事件捏造（如「点亮铁链」「冰箱」）、语义搭配错、空间矛盾、自然度：**判分器不判**，只能 abstain 或交人工。
- 标注稿是机器初标，已按第二轮审查修订 7 条，仍未签字；在复核前，本报告只能说明判分器的规则状态，不能当作模型验收结论。
- 24 条真实输出的混淆矩阵：人工 pass 5（机器 pass 2 / uncertain 3）、人工 uncertain 10（机器 pass 8 / uncertain 2）、人工 fail 9（机器 pass 1 / uncertain 7 / fail 1）。零误报主要是靠"少判"换来的。

## 复跑

```bash
cd experiments/world-components/n4_narrative_eval
python -X utf8 materials.py     # 重建材料（读 ../n4_narrative_dev 与 c9 归档）
python -X utf8 test_checker.py  # 17 条单元测试
python -X utf8 run_eval.py      # 四组评测，写 eval-report.{json,md}
```
