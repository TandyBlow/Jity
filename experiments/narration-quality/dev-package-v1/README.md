# 公开开发包 v1（11/12 共用）

`narration-dev-package-v1`：一份**冻结的已结算输入 + 参考正文 + 必述事实**，给 11（模型搜索）和 12（best-of-N）在同一输入、同一哈希、同一 rubric 下比较候选。不是终验，不是产品交付。

- `cases.jsonl`：15 例，每行一个 case（字段见下）。
- `manifest.json`：包版本、每个 case 的输入/参考哈希、来源文件哈希、已知参考缺陷。
- `RUBRIC.md`：质量判据、每例输出格式、晋级门。
- `build_package.py`：重建脚本（只读源文件，不改写任何原文）。

## Case 字段

| 字段 | 含义 |
|---|---|
| `caseId` | 全局唯一 id，引用时用它，不改名 |
| `category` | `no_change` / `move_direction` / `item_transfer_fixture` / `task_time` / `task_sanity` / `sanity` / `multi_person_reference` / `gender_pronoun` / `appearance_item` / `dialogue` / `long_text` / `continuity` / `time_only_derived` |
| `input` | 模型唯一输入：`视角`、`上回合状态`、`本回合变化`、`本回合状态` |
| `requiredFacts` | 必述事实。`kind`+结构化字段+`expression` 说明如何算表达。**不得进入模型提示词** |
| `licensedEntities` | 输入里存在的人物/地点/物品名；包外名字要按"无据人物/物品"判 |
| `priorTexts` | 连续片段的前文（模型自己前几回合写的），用于复读/连续性检查 |
| `reference` | 参考正文及作者、状态（`development_reference`）。带 `knownIssues` 的不要当正例 |
| `notes` / `knownIssues` | 该例考什么、已知缺陷 |

## 覆盖

无变化、移动方向、物品转交、任务+时间、任务+精神值、精神值、多人物指代、性别代词、外貌/物品状态、对白、长文本、三回合连续（含前文）、仅时间变化。

## 用法

1. 读 `manifest.json`，把 `files.cases.jsonl` 的哈希写进你的 `preregistration.json`；声明模型/量化/模板/种子/采样/输出上限/子集（如有）。
2. 每例只把 `input` 交模型，收集完整原文和耗时。
3. 按 `RUBRIC.md` §5 产出每例 JSON，按 §4 判定。
4. 参考实现（可选）：`frontend/src/lib/world-engine/local/narration-quality/`，
   `reviewNarration({id,input,text,options})` 返回逐句 findings 与 mandatory 覆盖；
   批跑：
   ```
   cd frontend
   NARRATION_QUALITY_ROWS=<jsonl: {"id","input","text"}> \
   NARRATION_QUALITY_REPORT=<report.json> \
   npx vitest run src/lib/world-engine/local/narration-quality/batch.test.ts --maxWorkers=1
   ```
   它只是检查器之一：`review`/`pending` 项必须人工/独立复核，不能当通过。

## 已知参考缺陷（不要当正例照抄）

- `frozen-row-0012`：参考正文不写时间推进（旧 199 行的系统性缺口），并加了无依据脚步声。
- `tide-continuity-tide-duty-t1`（05 所写）：参考正文有"一串脚步声"但该回合无人移动；已报 05。

## 独立性

10 例 01 自写、3 例 05 所写、1 例冻结训练行、1 例 01 夹具。01/05 都不能把这些当独立终验；针对性调参后的模型也不能。独立终验另立冻结批次。
