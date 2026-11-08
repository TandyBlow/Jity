# 真实录制长期一致性题库

首批交付为 `question_banks/full-games-20261106-v1.1/`，版本 `1.0.1-review`。12题来自4局，每局3题，全部标记为 **待人工审阅**。没有调用付费API、执行游戏行动或生成三组回答，也没有模型记忆成绩。

## 来源资格与限制

本次独立核验原始封存清单934个文件，均匹配。四局的真实终态与已封存严格重放结果均通过：提交行动分别55、52、52、51；有效战役推进均50；包含初始节点的时间线节点数分别56、53、53、52。重放调用消费分别113/113、115/115、120/120、120/120，均无网络尝试且状态、结局、重载匹配。本次读取并核验既有重放证据，**没有重新执行重放**。

四局都以 `budget-incomplete / 未竟的追寻` 收束，不代表主线通关或四种不同结局。未结束的 `smoke` 只是验收片段，单列候选来源，未入正式题。四局没有明确的 `consumed` 物品账本状态；移除、遗失、移交和毁坏不能冒称消耗。PCB人物记忆提取在调用前失败、嵌入404及本地回退、第三局解析重试和第四局结局长度重试均保留在来源审计中。

## 文件边界

| 文件 | 用途 | 可交给待测模型 |
|---|---|---|
| `public/questions.json` | 稳定ID、问题、检查点与数据版本；只有recall/action类型 | 可选；实际作答只给单题 |
| `public/inputs/<题目ID>/{full,recent,state}.json` | 36份冻结通道输入，每题各3份 | 每次只给对应一份 |
| `private/answers.json` | 标准答案、可接受表达、要点、部分分与典型错误 | 否 |
| `private/authoring.json` | 冻结的完整作者稿 | 否 |
| `private/candidates.json` | 10道备选或冲突候选，不参与首批计划 | 否 |
| `audit/items.json` | 题型目标、事实沿革、间隔、通道、有效期、未知审查和人工复核事项 | 否 |
| `audit/evidence.json` | 原路径、冻结路径、JSON Pointer、行动/节点、最小摘录、字段/文件指纹 | 否 |
| `audit/dataset.json` | 逐局结束、重放、异常、实际覆盖及来源资格 | 否 |
| `frozen/source/` | 只读用途的逐字源文件副本、选题历史前缀、终态与验收证据 | 否 |
| `manifest.json`、`manifest.sha256` | 版本、来源封存标识、文件清单与SHA-256 | 仅编排器使用 |
| `validation.json`、`validation/` | 离线验证、回归与浏览器检查 | 否 |
| `reports/review.html` | 可直接打开的自包含私有审阅报告 | 否 |

未知类标签只存在于私有作者稿和审计分类，不进入公开题型或模型输入。题目不附标准答案或证据摘录。原始近期输出自然包含的事实是合法输入，不通过“禁止出现答案字串”错误删除它们。验证器从冻结源重新构建每份输入并逐项比较，防止标准答案或其他私有内容被额外加入。

## 三组的固定合同

近期窗口预先固定为最近 **6次已提交行动**，包括检查点本次行动。每次提交的玩家行动和完整提交后output原样保留，包括选项、检定条件及memory_updates；不按题目删减。三组问题、检查点、指纹、窗口完全一致。

- `full`：近期上下文 + 当前记录中的NSB三级摘要和turn_buffer、PCB sketches、recap_compressed、recent_events + 结构化状态。
- `recent`：仅上述固定近期上下文。
- `state`：上述固定近期上下文 + 结构化状态。

结构化通道复用现有 `replay.context.STRUCTURED_KEYS`：地点、数值资源、turn、player_status、items、npcs、quests、world_facts；另加入权威 `score_tracker` 物品账本。结构化字段中自然含有人物和叙事信息，不把state组解释为“没有叙事知识”。full保存录制时实际存在的摘要，包括遗漏和冲突，不按标准答案补写理想记忆。

这些是 `capture_snapshot_v1` 冻结通道材料，不是生产PromptBuilder已经裁剪后的最终提示词。为保持本次只读离线范围，不运行生产上下文检索、token裁剪或游戏生成链。后续接入模型时应固定适配器、预算、模型和最终序列化方式，保留最终提示词哈希；不能给近期组自动注入其他状态。若改变窗口、通道、问题、检查点或裁剪规则，必须另建版本。

G02-Q03烟蒂数量在历史里可核实，但在检查点实际full记忆和state里已经遗漏；G04-Q03的兜帽人解释也只在原历史里，当前full仅保留部分答案。二者明确标记为记忆保留缺口，不能把所有缺分归因于回答模型。G04-Q02是0间隔近期状态控制题。每题真实可见性和相关但不足的实体提示均在审计中列出，不按哪组应该获胜挑选输入。

## 时间、证据与评分

主间隔为 `检查点提交行动序号 − 最近公开相关重提序号`。另列距首次出现的行动差、有效战役推进差和祖先边数。时间线节点ID只是标识，不能通用地用ID相减作距离。本数据的祖先链已逐步核对；本地审查拒绝可能形成提交节点但不推进战役，未提交的解析重试不产生新提交行动。

最近重提扫描包含完整output的所有字符串及真实玩家行动，包括未选择选项和检定条件；作者补充的语义重提也必须有原文引用。扫描采用明确的别名/话题词，完整命中列表和局限可审阅。通道内持续保留的状态或摘要与剧情重新披露分开记录，不能据公开间隔声称所有通道都未重复。未知题的间隔只是话题间隔，不是一个已知答案被遗忘。

叙事题以已提交历史正文为“发生了什么/某人说了什么”的证据；原模型推测、人物说法和摘要中的断言不会自动升级成世界真相。物品题同时对照提交后的items与物品账本；本地规则报错、拟议变更和未提交输出不能替代权威状态。当前不可可靠判断的徽记、通行卡恢复、封条移交等冲突进入候选区。

评分为私有语义要点评分合同，允许同义表达，逐要点部分得分；**尚未实施模型评分**。正确叙事解释无需说出 `items`、`SCORE` 或 `lost` 等内部名词。行动题只问判断和解释，不能执行取回、开门等动作。未知题必须区分“历史未披露”和“角色自己不知道”，不能填一个看似合理的名字或数字。

## 离线命令

在 `/Users/davidz/Documents/GitHub/jity-eval` 运行，推荐现有Python 3.11环境：

```sh
/opt/anaconda3/envs/jity-backend/bin/python -m jity_eval.question_bank validate question_banks/full-games-20261106-v1.1 --check-original
/opt/anaconda3/envs/jity-backend/bin/python -m jity_eval.question_bank report question_banks/full-games-20261106-v1.1
/opt/anaconda3/envs/jity-backend/bin/python -m unittest discover -s tests -p 'test_question_bank.py' -v
```

不带 `--check-original` 时仅依赖冻结副本；带此参数会额外重核原始封存文件，仍只读。报告命令只重新生成审阅HTML，不运行模型。

重建时必须指定不存在的新目录，禁止覆盖已有版本或写入录制目录：

```sh
/opt/anaconda3/envs/jity-backend/bin/python -m jity_eval.question_bank build \
  --source runs/full-games-20261106 \
  --spec question_banks/full-games-20261106-authoring/spec.json \
  --dataset-audit question_banks/full-games-20261106-authoring/dataset-audit.json \
  --output question_banks/my-new-review-version
```

扩展采用独立 `jity.capture-question-bank.v1` 格式，复用已有JSON/指纹工具和结构化字段白名单。旧 `schema_version=1` 模拟器只能精确匹配人工facts注释，不能表达真实证据、部分评分、0间隔与未知审查；因此不要把本题库交给旧 `jity_eval run` 假装产生三组结果。没有修改原有命令或录制工具。

## 人工审阅与未来实验

打开报告逐题检查：问题是否暗示答案，证据是否足以支持每个要点，角色声称与观察是否分开，是否遗漏同义重提，未知题是否可由其他线索推导，当前状态是否存在冲突。候选题须先解决冲突才可入库。人工审阅完成前保留 `pending_human_review`，不声称语义验收已完成。

以后每个“题目×组别×重复”都应启动独立只读作答；不把前题回答写入后题上下文，不把回答写回录制。12题是4局内部的相关观察，36份输入不是36份回答，也不是36局独立游戏；未来统计需按游戏聚类并报告同一战役和同类结局的限制。
