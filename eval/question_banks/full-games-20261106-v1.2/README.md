# Jity 长期一致性题库 v1.2 人工审阅版

版本 `1.2.0-review`，12个稳定ID、4局、原检查点及最近6次提交行动窗口不变。全部 `pending_human_review`；用户意见是修订依据，自动核验不等于人工验收。本次无模型回答、付费API、游戏行动或Git提交。

## 交付文件与隐私边界

- `public/questions.json`：题目、稳定ID、游戏、数据版本、检查点指纹；只有通用recall/action类型。
- `public/inputs/<ID>/{full,recent,state}.json`：36份冻结输入，每题未来独立作答，每次只提供相应一份。没有未知、诊断、控制或评分提示。
- `private/answers.json`：标准答案、可接受表述、33个语义评分要点、分值、部分分、典型错误。
- `private/scoring-policy.json`：统一的正确、遗漏、错误、额外无依据断言、矛盾及来源归属规则。
- `private/authoring.json`、`private/revision-spec.json`：作者稿和本次机器可读修订规格。
- `audit/evidence.json`：200条原始/冻结输入引用，路径、JSON Pointer、最小摘录、行动、节点及指纹。清单缺失证据用名称投影，不把整个无关物品文本作为答案。
- `audit/points.json`：逐要点首次、最近明确披露、更新、两种间隔、实际三组支持程度及对应字段证据。`historical_evidence_exists`表示答案或不足判断有历史支持；`target_value_explicitly_disclosed`另行区分具体值是否曾披露。
- `audit/items.json`：保留整题最近公开相关话题间隔，附逐要点审计链接、原冲突及待复核项。
- `audit/disclosure-scan.json`：完整output（含选项、检定条件、提交更新）及实际行动的检索候选。命中是候选，不自动等于明确重述；语义裁决见points。未选择的未来行动/失败条件不当已发生事件。
- `audit/unknown-scope-search.json`：沿用并核验的未知题完整历史前缀排查；分别限定initial0–A42及initial0–A38。
- `audit/dataset.json`、`private/candidates.json`：原来源资格、异常和候选区原样保留。
- `audit/changes.json`、`CHANGES.md`：逐题修改、原因和评分含义变化。
- `reports/review.html`：浏览器私有审阅报告，可按历史事实、诊断或控制用途筛选，展开逐要点原文和组内证据。
- `manifest.json` / `manifest.sha256`：题目、输入、答案、审计的核心版本指纹；`delivery.sha256.json` / `.sha256`：包括报告、说明、测试和浏览器核验的完整交付文件指纹。

除public单题输入外，上述材料都不能交给待测模型。原始近期记录自然携带的答案事实是合法内容，不用答案关键词过滤来删改输入。验证器逐项比对v1.1并从原始冻结记录重建，输入中只有问题和统一说明发生改变，context完全相等。题库版本独立于未变的数据封存版本。

统一模型说明：**仅依据本次提供的记录回答；无法确定时明确说明，不补造事实。行动题只判断和解释，不执行行动。**

## 评分与间隔

按准确表达或清楚蕴含的语义事实评分，不要求内部字段、逐字匹配或重复免责声明。同一语义不重复给分；“没犯错”本身不给分。遗漏为0，部分表达按各点规则；额外无依据断言单列标记，如改变所问结论或依据使相关点为0。结论与理由互相矛盾时，相关判断/依据点不能靠堆词得分。各题总分不同，尚未定义跨题汇总或模型成绩。

G02-Q02只答不知道可得未知结论1/3分，人物描述与芬格尔搬箱角色必须正面正确才得其分。G03-Q03只答不知道为1/2分，准确指出记录未给出值等依据再得1分。二者均接受“本次提供的信息不足”，不要求近期组替未见的全局历史作断言。

保留整题话题间隔。逐点明确披露间隔分别为检查点行动序号差、`progress.turns_total`战役推进差。时间线节点仅作标识，链路由已验证录制核对，不用节点ID直接相减。持久world_facts、摘要与物品账本在检查点持续可见，单列通道曝光，不计作新剧情披露。

未知姓名/数值本身没有首次明确披露；对应位置及间隔为null并说明原因。支持“不足”结论的正面线索有各自证据位置；完整前缀审查不注入模型输入。其输入支持“完整”表示有界不足判断可成立，不表示目标姓名或数值已经提供。

G03-Q01首次结构化持有为initial0，首次叙事A1，移交A24。检查点A35距首次持有35次提交/34次推进；原最近相关话题A27及8次提交/7次推进不变。

## 用途、覆盖和解释限制

四局已有真实结束及严格重放通过证据；提交行动分别55、52、52、51，有效推进均50。均以预算结束的“未竟的追寻”收束，不代表主线通关。本轮只读核对既有重放结果及原始封存934文件，没有重新重放。未结束smoke和冲突事件仍在候选区。PCB提取失败、嵌入404/回退、解析及结局重试等原始限制继续保留。

历史事实/状态判断题考察任务、人物证言、物品遗失/移交、后证据更新及可行性。没有明确consumed账本事件，不将遗失、移交或毁坏冒称消耗。没有补造正向行动事件；目前三道行动题的核心结论均为否定，存在标签分布偏向。

- G02-Q03是记忆保留诊断题：历史有“七枚、三枚较新”，当前full/recent/state均不含这两个数量。
- G04-Q03兼有历史事实与保留诊断用途：实际full/state保留试锁失败及反应，兜帽人的解释和来源已经遗漏；recent仅有相关实体。历史标准答案及解释评分要求仍保留。
- G03-Q03是近期未知控制，不代表长间隔遗忘。
- G04-Q02是0间隔近期状态控制，不作为长期记忆优势证据。
- G04-Q01身份、档案记载、亲手封存数字分别审计；帮助理由只透露部分。亲手细节full需跨真实摘要与状态合并，指代仍待人工复核。

多题答案合法存在world_facts、人物信息及物品账本，state可以答对。full为录制时实际摘要，不等于全历史或完美记忆。未保留证据的题可诊断系统，但不能单独证明回答模型在已得到全部证据条件下的能力。历史支持是否存在、输入是否保留、未来回答是否正确分开存储，最后一项全部not_run。

12题来自4局内部相关观察，不能视为12个独立游戏样本；36份输入也不是36个回答。未来实验应独立启动每个题目×组别，禁止前题答案进入后题记忆；应按游戏处理相关性，不在本次计算成绩。

## 离线使用

在jity-eval目录，用已有Python 3.11环境执行（不联网）：

```sh
PYTHONDONTWRITEBYTECODE=1 /opt/anaconda3/envs/jity-backend/bin/python -m jity_eval.question_bank_revision validate question_banks/full-games-20261106-v1.2 --check-original
PYTHONDONTWRITEBYTECODE=1 /opt/anaconda3/envs/jity-backend/bin/python -m unittest discover -s tests -p 'test_question_bank_revision.py' -v
```

直接在浏览器打开`reports/review.html`审阅。旧版本验证器仍用于v1.1；新版输入公共说明不同，请使用上述revision验证器。不要把本库交给旧模拟器当作真实模型实验。

需要重建时必须选择不存在的新输出目录，禁止覆盖版本：

```sh
PYTHONDONTWRITEBYTECODE=1 /opt/anaconda3/envs/jity-backend/bin/python -m jity_eval.question_bank_revision build --previous question_banks/full-games-20261106-v1.1 --spec question_banks/full-games-20261106-v1.2-authoring/spec.json --output question_banks/my-new-review-copy
```

该命令只构建核心JSON和冻结源，HTML由revision report命令生成。报告和说明是私有派生交付；任何后续修订须建立新版本，并重做核心/交付指纹与离线检查。验证通过仅表示格式、引用、隔离及源数据一致性通过，语义评分仍需人工审阅。
