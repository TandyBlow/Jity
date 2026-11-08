# 第 3–4 步运行报告：u240 三臂素材对照（生成 · 评分 · 评审材料）

日期：2026-11-08（本地时区 +08:00）。分支 `exp/c-scene-expression`，代码基线 `d8e03eb`（= 冻结提交）。
本报告不给人审结论：事实合法性与自然度都等人工评审；自然度门槛按冻结协议仍为 `not_evaluable`。

## 1. 已有运行的核对（没有重复调用）

| 检查 | 结果 |
|---|---|
| 进程 | 无 `run_frozen.py` 进程残留（`tasklist` + `Get-CimInstance Win32_Process` 命令行过滤；在跑的是别的分支的 uvicorn/预检） |
| `step3/run.json` | 存在，`startedAt` 06:55:25Z、`finishedAt` 06:58:04Z，`calls=24`、`drafts=30`、`retries=0`、`failedCalls=[]` |
| 产物哈希 | `run.json` 记录的 `preflight.json`／`calls.jsonl`／`drafts.jsonl` 三个 SHA-256 与实际文件逐一相符 |
| `preflight.json` | 冻结清单、样本导出、构建脚本、权重文件、判分器与 `sequence_policy` 的 blob 全部 `match: true`；断言依赖文件未被改动 |
| 结论 | 该次运行已完整结束，**未重跑**；原件保留 |

`run_frozen.py` 的写法与冻结协议一致：启动前断言 `HEAD=d8e03eb`、逐文件校验哈希；每槽位只调用一次（`x` 模式写日志、存在即中止）；编码 `truncation=False` 且断言实际 token 数等于冻结值、词表上限；三臂事实行与要求行必须逐字相同；失败不重试、不替换。

## 2. 生成结果

| 项 | 值 |
|---|---|
| 模型调用 | **24 条**（十题 8 条模型槽位 × 3 臂），全部 `stopReason=eos`、`status=complete`、`error=null`、无空输出 |
| 初稿 | **30 份**（十题 × 三臂），全部由该臂调用输出＋程序句拼成，`integrity.problems = 0` |
| 重试／回退 | 0／0 |
| 单条耗时 | 0.87 / 2.05 / 5.07 秒（最小／中位／最大），24 条合计 55.0 秒（CPU，14 线程） |
| 新生成 token | 11–21 |
| 输入长度 | 与冻结值逐条相同（114–125 / 136–160 / 168–197）；**无静默截断**（编码后 ID 重新编码比对、断言长度） |
| 超长输入 | C 臂两条超过训练观察上限 181：`ns-appear-1` 197、`ns-loc-appear-1` 193；`ns-multi-1` 的 C=181 正好等于上限。A 臂全部短于训练最短 145 |

4 题 `ns-task-1`、`ns-task-time-1`、`ns-empty-1`、`ns-cont-3` 无模型槽位，三臂初稿逐字相同，均为程序句（报告内标 `programOnly`）。

证据：`step3/calls.jsonl`（完整提示、输入 ID、原文、停止原因、耗时、时间戳）、`step3/drafts.jsonl`（部位与拼接文本）、`step3/run.json`、`step3/preflight.json`。

## 3. 程序评分

- 判分器：`evaluateNarration`，源码 `frontend/src/lib/world-engine/runtime/narration-split-eval.ts`；按项目 `tsconfig` 的严格设置编译（`--strict --target ES2020 --lib dom,dom.iterable,esnext --esModuleInterop --skipLibCheck`），仅把 `module` 改为 `commonjs` 以便 node 直接运行。
- **自检 8/8 全过**（错误时长、否定结果、主体交换、方向反转、新增物品、规则基线全过、重叠词宿主句零标记、中午未被断言记遗漏）后才开始评分。
- 共享授权词表：按冻结协议第 10 节，用该样本全部有效素材（不区分该臂是否呈现）＋历史词表构造，三臂同一张表；残差句记为 `unsupported_detail`，只作待核验项。
- 编译产物哈希与自检明细见 `step4/scores.json` 的 `scorer` 字段。

| 臂 | 初稿 | 有模型句的初稿 | 必述遗漏（条／涉及初稿） | 历史残差句 | 共享词表残差句 |
|---|---|---|---|---|---|
| A | 10 | 6 | 3 / 3 | 8 | 8 |
| B | 10 | 6 | 4 / 3 | 7 | 7 |
| C | 10 | 6 | 4 / 3 | 8 | 8 |

遗漏明细（判分器字符串口径，人工可改判）：

- `ns-appear-1`：A、B 漏“钥匙表面蒙上了灰尘”——模型写的是“钥匙**的**表面蒙上了一层灰尘”，多一个“的”、少“黄铜”，字符串口径不匹配。
- `ns-loc-appear-1`：A、C 漏“两侧的储物柜都被关上了”——写成“走廊的储物柜都被关上了”，丢了“两侧”。
- `ns-multi-1`：A 漏钥匙外貌；B、C 另漏“学生A 位于大厅”（两句都只说“从走廊过来”，没写到达大厅）。
- `ns-cont-1`：B、C 漏“学生A 从走廊到了大厅”（同上）。

残差集中在三类：把字段名写进句子（`钥匙外貌的变化`、`学生B的性格变化`）、给移动补了未提交的物件动作（`把钥匙从门外挪到两侧`、`把钥匙放在柜子里`）、以及程序句“时间已到中午”（词表缺口，三臂同句）。逐句见 `step4/clauses.jsonl`。

## 4. 人工评审材料

| 文件 | 内容 |
|---|---|
| `step4/ballot/order.json` | 固定种子 20261108 的遮蔽映射：每题三份文本的 甲/乙/丙 顺序对应的臂 |
| `step4/ballot/ballot.json` | 十题选票：只显示 甲/乙/丙 与文本，`choice`/`reason` 留空；四道 `programOnly` 题已标注（三份文本逐字相同，其选票不计入门槛） |
| `step4/clauses.jsonl` | 72 条分句核验记录：`label` 全部 `undetermined`，`sourceId` 为自动匹配的来源候选（10 条无候选，已注明需人工判断），`human` 各项留空 |

未预填任何“人工通过”。

## 5. 门槛状态

- 有效配对 6 题（4 题仅程序输出），< 10；按冻结协议，自然度门槛 **`not_evaluable`**，不降分母、不改阈值。
- 事实合法性（含遗漏、未支持细节、视角、新动作）与自然度结论：**待人工评审**，本轮不下结论。

## 6. 文件清单

| 路径 | 说明 |
|---|---|
| `step3/preflight.json` | 运行前哈希核对记录 |
| `step3/calls.jsonl` | 24 条调用记录 |
| `step3/drafts.jsonl` | 30 份初稿 |
| `step3/run.json` | 运行元数据与环境 |
| `step3/scorer-build/` | 运行方先前试编译的判分器产物（未用于本轮评分，保留不删） |
| `step4/scores.json` | 自检、完整性核对、逐题逐臂评分 |
| `step4/ballot/order.json`、`step4/ballot/ballot.json` | 遮蔽映射与空选票 |
| `step4/clauses.jsonl` | 分句核验表 |
| `step4/scorer-build/` | 本轮 `--strict` 编译产物（哈希记入 `scores.json`） |
| `run_frozen.py`、`score_drafts.mjs`、`build_review_materials.mjs` | 运行、评分、评审材料脚本 |

## 7. 限制（不因本轮结果改变）

1. 本轮只覆盖 u240 逐事实生成流程；整回合单次调用仍是诊断，不是路线。
2. 时间、任务、理智数值由程序句承担；模型侧效果只在 6 题上可评价。
3. C 臂“上一段叙事”缺失，C 只测个性与任务背景。
4. B 臂素材含本轮外貌事实原文，C 臂含个性变化原文；“答案在提示里”的混杂保留。
5. 判分器字符串口径会漏判合法改写（上面“的”字例即是一例），因此必须并列人工核对，不能拿自动通过率当结论。
