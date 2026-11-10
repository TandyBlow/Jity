# 冻结协议：u240 逐事实生成的三臂素材对照（c6）

冻结时间：本文件提交时；冻结时提交号记录在 `frozen/manifest.json` 的 `commitAtFreeze`。
分支：`exp/c-scene-expression`（父分支 `world-components` @ `64405346fe63c2f05cf067f3b328893fa9e0d381`）。

## 0. 路径登记与范围

- v3 方案正文写的目录是 `experiments/world-components/parallel/c-context-ablation/`；任务书与并行分支编号表登记本分支为 `experiments/world-components/parallel/scene_expression/`。所有产物统一放后者，前者不存在。
- 本轮只跑受控对照：不训练、不改共享契约、不改 `backend/`、不改正式世界页面、不接产品路由。
- 对应 R11（叙事生成）／R03（人物与世界变化）。当前档位：**输入已冻结，尚未生成**。

## 1. 问题与结论边界

问题：对同一批已提交事实，补充当前有效、主角视角可见的世界素材，能否让同一模型写得更自然，同时不增加事实遗漏、错误或未授权行动。

结论只覆盖 **u240 逐事实生成（一事实一次调用）＋固定程序拼接** 这条流程中的素材效果。已测过的“整回合一次调用”只作为兼容性诊断（`step1/step1-verify.json`：两事实输入 180 token，输出一句“沈砚从潮渡上来,袖口沾了铜油。”），不作为正式路线，也不能把它的结果外推到本实验。

## 2. 模型身份与运行环境

| 项 | 值 |
|---|---|
| 权重文件 | 主工作树 `.local/models/u240-model.safetensors` |
| 字节数 | `309783976`（实际重算一致） |
| SHA-256 | `ab8a98264ee6b4f83eba17d624d7b92b23522c8eacef07d07a5be960e390184a`（实际重算一致，64 位完整） |
| 同目录副本 | `model.safetensors` 同为上述 SHA-256；加载按显式文件读取，不依赖目录里的文件名选择 |
| 配置 | `T5ForConditionalGeneration`，d_model 512 / d_ff 1024 / 8 层 / 6 头 / vocab 32596 / fp32 |
| 参数量 | 77,440,384 |
| Tokenizer | `spiece.model`（SHA 见 `step1/step1-verify.json`），`legacy=False` |
| 运行 | CPU，torch 2.9.1+cu126，transformers 4.57.3，fp32，14 线程 |
| 加载方式 | safetensors 显式读文件 → `load_state_dict(strict=False)`；只允许缺 `encoder/decoder.embed_tokens` 两个键（它们是 `shared.weight` 的别名，`data_ptr` 已核对相同），不允许有多余键 |

身份来源：该检查点即 `train_routed_arms.py` 记录的 u240（route-split 训练第 240 个全局步的 control 检查点，基座 `assets/randeng-t5-77m`，训练 `truncation=False`，AdamW，seed 20261102）。实验只做推理，不改权重。

## 3. 样本冻结

| 项 | 值 |
|---|---|
| 来源 | `frontend/src/lib/world-engine/runtime/narration-split-samples.ts` |
| 源文件 SHA-256 | `4e8dccebc3b019cbde4de3b4d84643d2a35faa95bf081a5d1f8e9a218ebb2a12` |
| 导出件 | `step1/narration-split-samples.export.json`（哈希进 manifest） |
| 正式十题 | `ns-appear-1`、`ns-loc-appear-1`、`ns-task-1`、`ns-task-time-1`、`ns-pers-1`、`ns-multi-1`、`ns-empty-1`、`ns-cont-1`、`ns-cont-2`、`ns-cont-3` |
| 仅调试 | `ns-pos-1`（不计自然度门槛，只用于流程自检） |

不换题、不降低分母、不改七题门槛。`mayMention` 不进入授权素材、不进任何词表、不补成 `requiredFacts`。

四道题（`ns-task-1`、`ns-task-time-1`、`ns-empty-1`、`ns-cont-3`）的必述内容全部落在旧契约表达不了的种类上，**没有任何模型可生成的槽位**，整篇只有程序句。它们保留在十题里，标为“仅程序输出”，不能用来证明素材改善了模型叙事。

## 4. 必述内容的责任分配（冻结）

每条 `requiredFact` 只有一个承担者；模型句与程序句不重复表达同一内容。

| 样本 | 模型调用数 | 槽位（按拼接顺序） |
|---|---|---|
| `ns-appear-1` | 1 | 程序:timePassage；模型:appearanceText |
| `ns-loc-appear-1` | 1 | 程序:timePassage；模型:appearanceText |
| `ns-task-1` | 0 | 程序:timePassage；程序:taskGoal |
| `ns-task-time-1` | 0 | 程序:timeReached；程序:taskGoal；程序:timePassage |
| `ns-pers-1` | 2 | 程序:timePassage；程序:taskGoal；模型:personalityText；模型:sanity_changed（方向）；程序:sanityValue（数值） |
| `ns-multi-1` | 2 | 程序:timePassage；模型:position；模型:appearanceText；程序:taskGoal |
| `ns-empty-1` | 0 | 程序:timePassage |
| `ns-cont-1` | 1 | 程序:timePassage；模型:position |
| `ns-cont-2` | 1 | 程序:timePassage；模型:appearanceText |
| `ns-cont-3` | 0 | 程序:timePassage |

规则：

- 模型能表达的种类只有旧契约四种：`moved`、`appearance_changed`、`personality_changed`、`sanity_changed`（只给方向词“放松/发紧”）。
- `timePassage`、`timeReached`、`taskGoal`、`sanityValue` 一律程序句，三臂同文同位置。
- `taskGoal` 的程序句只申明“任务达成”这个已提交事实，并引用目标文本作标识，不写任何完成动作细节；C 臂素材里的待办任务只作背景，不带完成含义。
- 理智一次变化出两句：模型写方向，程序写数值（固定先后顺序）。两句内容不同，不构成同一事实的重复表达。

## 5. 素材池与来源表

生成物：`frozen/materials.json`（每题三臂场景头＋素材明细）。素材只从样本已提交状态读取，字段可追到 `entityId` 与 `fieldPath`。

| 类别 | 来源字段 | 可见性 | 生效点 |
|---|---|---|---|
| 地点初始外貌 | `initial.locations.<id>.initialAppearance` | 主角所在地点，可见 | 初始状态 |
| 地点外貌变化 | `after.locations.<id>.appearanceChanges[].text`（`active` 为真） | 同上 | 本点 after 时间 |
| 物品初始外貌 | `initial.items.<id>.initialAppearance` | 物品位于主角所在地点 | 初始状态 |
| 物品外貌变化 | `after.items.<id>.appearanceChanges[].text`（`active` 为真） | 同上 | 本点 after 时间 |
| 人物个性 | `initial.characters.<id>.initialPersonality` 与 `after...personalityChanges[].text` | 人物位于主角所在地点 | 初始／本点 |
| 待办任务目标 | `after.characters.<id>.tasks.<taskId>.goal`（`status != achieved`） | 同上 | 本点 |
| 上一段叙事 | 无 | — | — |

- 拼接素材时去掉每段末尾的 `。；，`，避免“。；”；素材原文不变。
- 数据集没有“上一段叙事”字段：**C 臂不含前文**，该类别登记为缺失，不补造、不用 `note` 或 `mayMention` 顶替。
- `text` 字段原样使用，不裁剪、不改写。

## 6. 三臂定义（冻结的场景头）

三臂共用同一事实行、同一要求行、同一 tokenizer、同一次数、同一拼接规则；差别只在场景头。

- **A**：历史模板的基础头（地点、地点可见的名字、时段、视角）。
- **B**：A 加上当前有效的地点外貌、可见物品外貌。
- **C**：B 加上主角所在地点可见人物的个性与待办任务目标。

示例（`ns-loc-appear-1`，唯一一条模型调用）：

```
A:
地点=走廊
地点可见=钥匙
场景=中午
视角=主角；第三人称
事实=走廊｜外貌变化｜两侧的储物柜都被关上了
要求：…（下同，逐字冻结）
短句：

B: A 的基础上加
地点外貌=两侧是储物柜；两侧的储物柜都被关上了
钥匙外貌=一把黄铜钥匙

C: B 的基础上加
学生A｜性格=谨慎
学生B｜性格=外向｜任务=帮主角熟悉校园
主角｜性格=好奇｜任务=取回柜子里的东西
```

完整三臂 prompt 见 `frozen/inputs.json` 每个模型槽位的 `prompts.A/B/C`。

已知混杂（保留并披露，不修改）：

- 三题的外貌事实（`ns-appear-1`、`ns-loc-appear-1`、`ns-multi-1`、`ns-cont-2`）里，B 的场景头已含该事实原文；`ns-pers-1` 的个性变化原文也在 C 里。这是“当前有效素材”定义带来的，分析时不得把 B/C 在这些题上的收益全部算作素材效果。
- C 一次引入个性与任务两类背景，本轮不能区分哪一类单独有效。

## 7. 调用与拼接（“一题一臂一份初稿”的解释）

- **一题一臂一份初稿 = 该臂全部模型调用输出 ＋ 该题全部程序句，按第 4 节顺序拼成的唯一文本。** 不是一次模型调用产出一份。
- 每条模型槽位只生成一个候选：贪心解码，不采样、不重试、不择优、不追加提示。
- 事实行写法与 `fact_contract.serialize_fact` 逐字一致（`名字｜标签｜取值`）；要求行与 `fact_contract.build_unit_input` 逐字一致。包装器只跳过其中的姓名正则检查（样本名字是“学生A/学生B/主角”，含拉丁字母会被 `[一-鿿]{1,6}` 拒收）；共享契约不改，这一拒收不计为模型失败。
- 拼接规则：
  1. 按第 4 节槽位顺序；
  2. 模型句去首尾空白；若末尾已是 `。！？` 保留一个，否则去掉末尾的 `，、；,.;：` 后补 `。`；
  3. 空输出或只有标点：该槽位记为空，不替代、不重试，直接造成必述遗漏；
  4. 程序句按第 9 节模板原样使用；
  5. 直接相连，不加分隔符、不改顺序、不合并句子。

## 8. 解码参数

| 项 | 值 |
|---|---|
| 解码 | 贪心（每步取 argmax） |
| 随机性 | 无采样，因此无 seed；同一输入重跑必须逐字相同（已在第 1 步验证） |
| 输出上限 | 不设 token 上限，按墙上时间 30 秒中止（沿用 `sequence_policy.generate_greedy`） |
| 输入截断 | 不截断；每次编码后断言实际长度等于输入长度，发现静默截断即中止该次运行并报告 |
| 精度／设备 | fp32 / CPU |

输入长度（`frozen/prompt-tokens.json`，单位 token）：

| 臂 | 条数 | 最小 | 中位 | 最大 |
|---|---|---|---|---|
| A | 8 | 114 | 118.5 | 125 |
| B | 8 | 136 | 147 | 160 |
| C | 8 | 168 | 172 | 197 |

（十题共 8 条模型调用 × 3 臂 = 24 次调用，生成 30 份初稿；另有一题 `ns-pos-1` 只用于流程调试，不计入上表。）

u240 训练输入长度分布为 145–181（三个单元池，341 条）。A 全部短于训练最短值，C 有两条（`ns-appear-1` 197、`ns-loc-appear-1` 193）超过训练最长值。181 只是已观察到的训练最大长度，不是模型容量上限，因此**不截断 C**；每次记录实际长度，解释结果时保留这个限制。

## 9. 程序句（冻结）

沿用历史 `composeSentences` 模板，`timeReached` 无历史模板，新定固定句：

| 种类 | 模板 | 例子 |
|---|---|---|
| `timePassage` | `约{数量}{单位}过去了。` | `约两分钟过去了。` |
| `timeReached` | `时间已到中午。`（hour=12）／`时间已到{hour}点。` | `时间已到中午。` |
| `taskGoal` | `{名字}完成了任务「{目标}」。` | `学生A完成了任务「坚持到中午」。` |
| `sanityValue` | `{名字}的理智值{升为|降为}{数值}。` | `学生B的理智值升为12。` |

已知判分器残差：`时间已到中午。` 里的“中午”不在冻结词表中，`evaluateNarration` 会把它标进 `fabricationFlags`。这是词表缺口，不是模型捏造；三臂同句同位置，不影响臂间比较。原始标记保留，人工核验时按 `supported` 处理并写明理由。

## 10. 程序评分

- 固定入口：`evaluateNarration(sample, text)`（`narration-split-eval.ts`，未改动）。评分前先跑 `scorerSelfTest()`，任一项不过则该轮评分作废。
- 输出：`factChecks`、`omissions`、`fabricationFlags`、序列样本重复度。
- 残差口径：按任务书第 5 节，另建独立包装器，用**该样本全部有效授权素材**（不区分该臂是否呈现）构造共享词表，三臂用同一张表；删除后仍有残余的句子记为 `unsupported_detail` 等人工核验，不自动判成语义捏造。旧 `fabricationFlags` 原文保留，不改旧归档。
- `narration-alignment.ts` 只做交叉诊断，不进门槛。

## 11. 分句人工核验

- 每条分句一行 JSONL，字段：`sampleId`、`arm`、`clause`、`label`（`supported`/`unsupported`/`undetermined`）、`sourceId`（数组，写实际依赖的来源 ID 或 `fieldPath`，不得凭空写不存在字段）、`note`。
- 另记：语法流畅、视角是否成立、是否新增动作、是否造成必述遗漏。
- 三臂同等审查；不因 A 信息少而放宽。
- 程序句同样逐句登记，来源写程序模板名与对应 `requiredFact`。

## 12. 自然度评审（遮蔽顺序）

- 每题三份输出（A/B/C）随机排列，不显示臂名；排序由固定 seed 生成，记录在 `ballot/order.json`，与选票分开保存。
- 问题固定：在事实表达不越权的前提下，哪份文字作为游戏当前时间点的叙事更连贯、读起来更像完整段落？不得因为更长就判优。
- 每题可选一份或“看不出差别”；可写一句理由。
- 评审者知道这是素材补充实验，不声称完全盲评。

## 13. 探索性门槛（预先登记）

- 通过条件：十题中 B 或 C 被选中 ≥ 7 次，且 A 一次都没被选中；胜出文本没有人工确认的新增事实错误或必述遗漏；`undetermined` 不算通过。
- 有效配对数：4 题只有程序句，整篇与素材无关，计为不可评价 → 有效配对 6 题 < 10。按任务书，本轮门槛标为 `not_evaluable`；仍交付十题全部结果、6 题配对统计与逐题选票，不降低分母、不改阈值。
- 每题原始选票分别记录 B 胜／C 胜／A 胜／平票。

## 14. 已知限制与未做

1. 旧契约无时间、任务、数值事实行；这些必述由程序句承担。模型侧的素材效果只能在这些题以外评价。
2. 4 题无模型槽位，只作“仅程序输出”，不参与素材效果结论。
3. C 臂“前一段叙事”缺失（数据集无此字段），本轮 C 只测个性与任务背景。
4. A 的输入长度短于训练最小值，C 有两条超出训练最大值；不截断、如实记录。
5. B 臂素材含本轮外貌事实原文，C 臂含个性变化原文；相应样本上存在“答案在提示里”的混杂。
6. 未做：浏览器内推理、与正式世界流程的接线、N4.0 生产输入装配、N5 逐句核验、训练与模型选型。
7. 本轮不证明“素材能提升叙事”是普遍结论；只按第 13 节门槛判定有效或无效，`not_evaluable` 就是 `not_evaluable`。

## 15. 冻结清单与校验

`frozen/manifest.json` 记录：冻结时提交、样本导出及其源 SHA-256、`materials.json`、`inputs.json`、构建脚本的 SHA-256。

```bash
cd <仓库根>
sha256sum experiments/world-components/parallel/scene_expression/frozen/{materials,inputs}.json
python - <<'PY'
import json, pathlib
m = json.loads(pathlib.Path('experiments/world-components/parallel/scene_expression/frozen/manifest.json').read_text(encoding='utf-8'))
print(m['commitAtFreeze'], m['materials']['sha256'], m['inputs']['sha256'])
PY
```
