# 真实题库三组问答试测：离线准备与执行合同

> 历史记录：以下状态与本机路径对应原独立项目交付时点。迁移后的入口及数据目录见 [仓库集成说明](repository-integration.md)。

本次准备目录：`runs/qa-pilot-20261106-v1.2-preflight`。题库为 `full-games-20261106-v1.2` / `1.2.0-review`。这是独立问答实验，不运行游戏，不使用录制回答冒充新回答，不使用付费评分模型。

## 当前状态与两道启动门槛

截至2026-11-06，题库12/12题仍为 `pending_human_review`，未发现明确人工批准记录。离线核验通过不等于人工验收。本次已准备12题×3组×1次的36份请求，但**已批准题数0、真实新回答0、付费请求0**，没有模型成绩。

启动必须同时具备：

1. 逐题人工审查批准、确认历史证据足够。外部批准记录绑定本次run清单、题目、标准答案、逐点审计和证据指纹；不改变原题库审核状态。
2. 用户明确确认**本次独立总预算**及请求/token上限。原游戏采集的预算无效。本次建议US$1、最多36次HTTP尝试、每样本最多1次、自动重试0。

`approval-templates/review.json`、`approval-templates/budget.json`均为待确认模板，不能直接启动。用户可批准全部12题或给出明确ID子集；子集按已冻结顺序运行，不补题凑数、不额外增加重复。首次执行后批准范围和预算绑定SQLite，恢复时不能扩大。

四局已读取原始终态及既有严格重放：提交55/52/52/51次、推进均50次，重放分别113/113、115/115、120/120、120/120。均以预算结束的“未竟的追寻”收束，不能称主线通关；本次没有重跑游戏。未结束smoke、PCB提取失败、嵌入404和重试等原始限制保留在冻结来源审计中。

## 三组与正常游戏路径的差异

复用题库的 `question_bank.make_input` / `channels` 合同以及真实提交快照；每份请求由既有 `public/inputs/<ID>/<mode>.json` 中的question、instruction和context构造，其他题目ID、组别标签、类型和私有审计不会进入消息正文。

| 组别 | 模型实际可见内容 |
|---|---|
| full | 最近6次提交的玩家行动与完整output；当前真实NSB三级摘要/turn_buffer、PCB sketches、recap_compressed、recent_events；结构化状态及物品账本 |
| recent | 仅上述固定最近6次提交的行动与完整output |
| state | 相同最近6次提交＋结构化状态及物品账本，无历史摘要、PCB、章节回顾或recent_events旁路 |

结构化字段沿用 `STRUCTURED_KEYS`：current_location、sanity、health、turn、player_status、items、npcs、quests、world_facts；另加score_tracker物品账本。近期output自然包含选项、检定条件和memory_updates，不删去其中合法出现的答案事实。state中的world_facts、人物信息和物品账本也可以合法提供答案。

原游戏PromptBuilder/旧replay.context会把问题当成下一步玩家行动，套GM剧情和StoryOutput格式，并可能裁剪近期消息、结构化列表、NSB，加入检索、战役锚点与结局内容。因此本次保留已审计冻结输入，用独立、三组相同的问答包装；**不声称与正常游戏最终提示词完全相同**。不导入或调用Jity游戏运行时、数据库、向量检索、缓存、摘要生成、记忆强化、章节推进或骰子。

共同说明原样保留：

> 仅依据本次提供的记录回答；无法确定时明确说明，不补造事实。行动题只判断和解释，不执行行动。

统一要求输出JSON字符串字段 `answer` 和 `explanation`，历史对话及选项仅作资料。每题每组单独一份两消息请求：system共同指令＋user问题与允许的records。没有前题回答、聊天会话ID、工具或自动修复调用。

## 模型、顺序、长度与费用

显式使用 `deepseek-flash`、`POST https://api.deepseek.com/chat/completions`、非思考模式、temperature=0、stream=false、max_tokens=1024、JSON输出。当前本地.env旧模型名不继承，只在启动门槛通过且确实需要发送时读取DEEPSEEK_API_KEY。凭据不保存到运行产物。底层使用httpx及已有CaptureTransport，不使用SDK自动重试，不跟随重定向，不读取代理环境。

2026-11-06官方文档把deepseek-flash映射为DeepSeek-V4.1-Flash-1017；这是可更新别名，不能保证供应商内部权重不可变。保存每次实际返回的model、时间和原始响应。

- [官方模型和价格](https://api-docs.deepseek.com/quick_start/pricing/)
- [Chat Completions接口](https://api-docs.deepseek.com/api/create-chat-completion/)
- [token说明](https://api-docs.deepseek.com/quick_start/token_usage/)

按峰时、无缓存折扣：输入US$0.30/百万tokens，输出US$1.20/百万tokens。本次36份最终请求，本地估计输入720,668 tokens，保守输入预留1,920,850，输出上限36,864；若全部用满输出，分别估价US$0.2604372和US$0.6204918。它们都是估算，不是账单。预算拟设US$1，另设总输入2,200,000、总输出36,864、HTTP尝试36的硬门槛；错误请求和不确定用量仍占预算。没有重试或额外评分模型费用。

逐通道计量等价复用Jity的纯本地regex fallback规则，明确命名为估计器，不冒称DeepSeek tokenizer或cl100k精确计量。预算沿用BudgetLedger的完整请求UTF-8字节数＋256预留；这也是保守估量而非供应商保证。响应usage才是服务端实测总量；不能据总量精确反推各通道token。缺usage保留整笔预留并标未知，不能记免费；已知usage按公布费率估算费用，也不能当实际账单。

统一上下文预算131,072，包含预留输入与1,024输出。最大请求输入预留84,603，所有36份均可完整容纳，裁剪记录均为空。若任何一组超限，则整题三组标context_blocked、不发送、不裁剪、不填充；改变策略必须另建版本。

随机种子20261106用于打乱题目顺序；三组的6种排列各使用两次，使12题的组别位置平衡。它不作为模型采样seed，也不保证temperature=0输出绝对可复现。若只批准子集，保持原顺序并报告实际分布，不按结果重排。

## 请求持久化、恢复及中断边界

复用 `capture.CallJournal`、`BudgetLedger`、`CaptureTransport`、`capture_network_guard` 和storage原子写/进程锁。每样本独立journal，共享本run专属预算账本，避免跳过完成样本导致调用顺序错位。网络守卫阻止未捕获网络/子进程，不宣称提供整个文件系统隔离。

- 发送前重新核对该份请求字节指纹；固定代码、运行时版本、配置、模板和计划也须通过验证。
- 请求先预留预算并写入journal，原始HTTP响应在解析前持久化。保存请求正文、原始字节、原始响应、参数、usage、返回model、时间、失败及事件；授权头不存盘。
- 已完成、API失败、解析失败或不确定样本不再请求；答错样本也不会重试筛选。
- 完整响应已落盘但结果尚未写入，可纯本地恢复，不需要密钥，不重新付费。即使预算已永久停止，仍可读取已保存的响应。
- 超时、流中断、pending journal不能证明服务端未执行，标uncertain，不自动重发。有预留而无journal的孤立预留单列，停下核对，不重新预留发送。
- `model_calls`在报告中称“登记请求尝试”：pending记录可能还未到服务端；另列完整HTTP响应、未知结果和孤立预留。没有服务商账单接口，不能宣称exactly-once计费保证。

## 评分与解释

完整回复首先本地解析。HTTP失败、非法JSON、空答、意外工具调用、finish_reason=length分别记录为异常，不直接计作知识错误，也不通过付费模型修复。解析成功的开放答案一律 `pending_human_review`，分数为null，未使用关键词判分。

人工评分按冻结题库33个要点和统一语义规则进行，记录每点correct/partial/incorrect/omitted/unsupported/contradictory、分数、说明及证据ID。必须接受同义和清楚蕴含；同一语义不重复得分；没有犯错本身不是独立加分；结论与理由矛盾按既有政策处理。不得看过某组回答后改评分标准。

同时记录六个诊断维度，适用性在回答前冻结：历史事实、当前状态、过时信息误用、无依据断言、信息不足时承认未知、行动可行性。每维以已人工复核的correct/incorrect作为分母，不适用和未审核另列。这些是诊断标签，不额外加要点分；无依据断言维度correct代表该维通过。不能仅因当前输入漏掉历史答案就自动把所有相关事实判为编造，仍须区分历史真伪、实际可见证据和因果归因。

导入评分要求人工复核者、时间、本run指纹、原回答hash、冻结rubric hash、完整要点和证据；导出时再核对评分与回答未改变。不调用付费评分模型。模板命令只列已有有效回答，当前为0。

报告提供逐题三组输入/原始回答/评分/证据，按组、题型、游戏、间隔与用途汇总；满分正确率的分母是已人工评分的有效回答，部分分另列得分率。API/解析/不确定/未完成/未评分均不记错。另列完整计划配对、三组有效回答配对和三组已评分配对，不能把部分完成暗示为完整配对结果。

G02-Q03、G04-Q03保留历史答案但存在实际输入遗漏；G03-Q03、G04-Q02分别为近期未知和0间隔状态控制。三道行动题均是否定结论。12题来自4局，不能当12个独立游戏样本；单次探索性对照不能证明长期记忆能力或稳定表现。

## 命令

从 `/Users/davidz/Documents/GitHub/jity-eval` 运行，推荐已记录的Python 3.11环境。下面verify/report不付费：

```sh
PYTHONDONTWRITEBYTECODE=1 /opt/anaconda3/envs/jity-backend/bin/python -m jity_eval.qa_pilot verify runs/qa-pilot-20261106-v1.2-preflight
PYTHONDONTWRITEBYTECODE=1 /opt/anaconda3/envs/jity-backend/bin/python -m jity_eval.qa_pilot report runs/qa-pilot-20261106-v1.2-preflight
PYTHONDONTWRITEBYTECODE=1 /opt/anaconda3/envs/jity-backend/bin/python -m unittest discover -s tests -v
```

仅在用户明确确认题目及独立预算后，依据确认内容将两份审批记录写入新 `approvals/` 文件；当前未创建这些已批准文件：

```sh
PYTHONDONTWRITEBYTECODE=1 /opt/anaconda3/envs/jity-backend/bin/python -m jity_eval.qa_pilot run runs/qa-pilot-20261106-v1.2-preflight --review runs/qa-pilot-20261106-v1.2-preflight/approvals/review.json --authorization runs/qa-pilot-20261106-v1.2-preflight/approvals/budget.json --env-file /Users/davidz/Documents/GitHub/Jity/backend/.env
```

恢复使用相同命令，把`run`换成`resume`；已完成样本不重复执行。不确定请求不会自动重发。可用`--max-samples N`暂停流程，不改变总预算或批准范围。若当前代码变动，可在同一已记录依赖环境中用冻结代码恢复：

```sh
PYTHONPATH=/Users/davidz/Documents/GitHub/jity-eval/runs/qa-pilot-20261106-v1.2-preflight/code PYTHONDONTWRITEBYTECODE=1 /opt/anaconda3/envs/jity-backend/bin/python -m jity_eval.qa_pilot verify /Users/davidz/Documents/GitHub/jity-eval/runs/qa-pilot-20261106-v1.2-preflight
```

生成和导入人工评分（不调用模型）：

```sh
PYTHONDONTWRITEBYTECODE=1 /opt/anaconda3/envs/jity-backend/bin/python -m jity_eval.qa_pilot grade-template runs/qa-pilot-20261106-v1.2-preflight
PYTHONDONTWRITEBYTECODE=1 /opt/anaconda3/envs/jity-backend/bin/python -m jity_eval.qa_pilot import-grades runs/qa-pilot-20261106-v1.2-preflight --file /absolute/path/to/human-reviewed-grades.json
```

如需重新准备，使用`prepare --bank ... --config ... --output <不存在的新目录> --jity-root ...`。现有运行、v1.2、v1.1和原录制都不覆盖。预算不同、评分合同或输入改变均需新版本，不能在已开始的运行中扩张。

## 文件索引

`manifest.json`与`.sha256`固定本run；`plan.json`固定顺序；`requests/`是待发送消息与token审计；`private/bank/`是完整冻结私有题库及原始证据；`code/`保留源码和相关Jity边界源码；`approval-templates/`是未批准模板；`qa.sqlite3`管理状态；获准执行后`calls/`、`responses/`、`budget.sqlite3`记录新请求；`results.json`、`events.json`、`report.html`是派生审阅结果。`validation/`保存离线回归、浏览器、审批门槛和原文件保护核验。它们都不是模型输入。

本批结束后不自动扩大题目、重复次数或付费实验，不提交、推送或合并Git改动。
