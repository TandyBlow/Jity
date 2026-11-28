# P03 研究结果复核：E58 / E60 / E61 与 rules 产品接线

**Question.** 叙事方向最新三页报告的结论能否从原始文件重算？新接入的零参数 rules 臂
会不会改变产品默认叙事路径或绕过 D-004 的边界？

**Method.** 只读复核：读 `design/research/E58..E61`、`artifacts/goal/narration-standalone/`
下的 `pairs.jsonl`、`pairs-eval.json`、`evaluate-arms.json`、`compose-candidate-summary.json`、
`check-failures.json`、`check_failures.py`；用 Python 重算比率；grep `narrationCandidate`
的默认值与引擎分支。没有运行模型。

**Findings.**

1. **E58 可重算。** `pairs.jsonl` 51 行；`pairs-eval.json`：现役覆盖 0.569、结果标签 0.000；
   `evaluate-arms.json`：292/424、6/141。与报告一致。该 51 对来自与 E55–E60 同一批开发
   输入，按 P01 第 5 条只是 dev，不是独立评价。

2. **E60 可重算，但两个已知风险都已落地。**
   - `compose-candidate-summary.json`：161 点、16,634 字、103.3 字/point、0.069 ms；
     `evaluate-arms.json`：424/424 事实、141/141 结果标签。与报告一致。
   - 开场句是玩家**意图**而非已结算动作。E61 的 `openingWithOutcome=13/54` 证实：54 个
     开场里只有 13 个在头两句带结果线索，其余 41 个是"脚步放轻"这类尝试。报告已写明，
     但这是产品化前必须人工逐条核对的风险，不是纯文体问题。
   - 3 条"未表达"来自 q4kv 失败运行留下的结算残片（`唐骁kind_shagan` 等），候选照抄；
     E61 已指出是输入污染。评价集应过滤 engine 错误行，否则会把数据缺陷算成模型错误。

3. **E61 表内数字与 `check-failures.json` 一致，但 JSON 有两个误导字段。**
   - 一致：97/435 被写到的明确主语事实；错归属 0 vs 8（1.8%）；失败表达 141/141 vs
     2/141；成功表达 133/136 vs 12/136；句数 699 vs 3,068。
   - `check-failures.json` 的 `chars=98,037`、`sentences=3,068` 是**按 point 重复累计
     turn 正文**（每个 point 都记整回合正文）；报告里的 176.2 字、5.3 句来自
     `evaluate-arms.json`（E58 已更正的口径）。同一页的数字跨两个文件，JSON 字段名
     没有提示重复计数；建议改名为 `repeatedTurnChars`，或补 `charsPerPoint`。
   - "错归属 0" 只在 97 条被写到的明确主语事实上成立；缺主语片段（E54 的 36%）不在
     检查范围。报告的 Caveats 已承认，评论文本引用时不要省略。

4. **rules 接线是评估臂，默认未变。** `?narrationCandidate=rules` 在
   `game-model.ts:615` 直接走 `rulesNarration`，不触碰引擎；页面默认仍是
   `candidate ?? 'builtin'`（`page.tsx:1137`）。因此不违反"运行期原样显示非空模型正文"的
   默认路径，但**任何正式验收证据必须写明是否带了该 flag**；rules 臂按 D-004 只能作对照臂，
   不能算模型能力。`rules-narration.test.ts` 已存在。
   后续 `f03c6d53` 给驱动加了 `--allow-program`：默认关闭，只在显式程序臂时把
   `source_program`/`program_text_not_model` 从阻断项里排除，并把
   `programNarrationAccepted` 写进证据。产品验收仍应加
   `verify_run.py --forbid-program`，防止程序臂被当成模型正文。
   2026-11-28 22:51 的 `artifacts/goal/narration-rules/scenarios8-rules.json` 实测：
   `arm.narrationFile=null`、`narrationBytes=0`、`narrationModel=rules`，已记录回合
   `source=program`、`textSource=program`；因为带 `--allow-program`，`problems` 为空。
   这条证据只能记“程序臂运行”，不能记模型叙事通过。

5. **E61 检查器的名字表缺 5 个世界人物，多了 3 个非本世界名字。**
   `role_parse.py:10` 的 `NAMES` 有 12 个；世界文件 14 人，缺
   `苏茜 / 周映 / 沈澄 / 富山雅史 / 曼施坦因`，同时含 `阿豹 / 夏弥 / 绘梨衣`
   （不在本世界）。后果：这 5 人的事实不计入"被写到/错归属"，以他们开头的句子不计入
   同头重复，涉及他们的编造也测不到；"0 错归属"与"1.8% 错归属"的适用范围比报告窄。
   这是一个可复现的自动评价器漏报（false negative）样本：世界文件 vs 检查器常量。
   平台侧 `narration_metrics.py` 已改为从世界文件读名字，重建并重新冻结了留出集；
   E61 的检查器归叙事 Agent 修，未直接改。

**Verdicts.** E58：数字成立，评价集降级为 dev。E60：数字成立，意图开场与输入污染是
两个未闭合风险。E61：数字成立，产物字段有重复计数陷阱，名字表漏报 5/14 人物。
rules 接线：可接受，仅限显式 `narrationCandidate=rules`。

**Standing rule.** 报告里的每个数字都应能从单一 artifact 重算；跨文件的派生指标要在
报告里注明来源（E61 的 176.2 就没注）。复核记录继续写在本文件，按 E 编号追加。

**Artifacts.** 本页；被复核文件见上。P03。
