# 事实—陈述核对：第一版二分类材料、复看与训练结果（2026-11-05）

**第一版二分类已经跑完：confirm 整体三项门槛通过，但由 general 分布撑住；定向类别和 20 源回归没有过。职责未成立，不接 source head/服务。** 二分类 supported/unsupported；uncertain 由 dev 选出的拒判阈值产生；source head 暂不实现。 任务仍限定为“未经支持的附加陈述”；暂不兼做重复检测、文笔评价和纠错。模型不找字符串位置、不删标点、不改写正文、不组织段落；初期只产生质量判定，不自动删句。

---

## 1. 先清点 N5：哪些能复用，哪些不能

### 1.1 已有 N5

| 项 | 现状 |
| --- | --- |
| 任务 | `(fact, sentence)` → `support / contradiction / unknown` |
| 数据 | 6764 对：5919 train + 845 dev；冻结测试 758（support 256 / contradiction 246 / unknown 256） |
| 来源 | 三个故事族 A/B/C；514 + 66 行；492 + 66 个 `sourceGroupId`；测试只含 C 族 |
| 扰动 | role-swap、direction-flip、number-error、unit-error、goal-misattribution、time-error、relation-flip、text-swap；unknown 用同族别行句子 |
| 模型 | MiniRBT-H256 + masked-mean-pool + linear(3)；8 epochs / 1480 steps / 31.3 s（RTX 4090D） |
| 评测 | 阈值在 dev 固定为 0.4/0.4；冻结测试 support 0.9805、contradiction 0.9959、wrongPass 0、**wrongReject 5/256**；G1/G3/G4 过，**G2 失败，pass:false** |
| 工程 | test-freeze、ONNX 导出、浏览器 24/24 一致；单次 25–134 ms |

关键文件：`corpus_v2/n5/{train,test}.jsonl`、`test-freeze.json`、`build_n5_pairs.py`、`train_n5_head.py`、`eval_n5_head.py`、`artifacts/world-components/n5-relation-eval.json`。

### 1.2 复用矩阵

| 对象 | 结论 | 说明 |
| --- | --- | --- |
| `fact_desc()` | **直接复用** | 事实的规范描述；新材料的 `factText` 用它生成 |
| `group_sentence_spans()` | **直接复用** | 把 N5 行的 fact 映射到句子；新材料的“一事实一句”候选从这里选 |
| N5 行文本 / facts / `sourceGroupId` | **复用为底料** | 生成 general 类的 supported/unsupported 对；按 source group 隔离 |
| MiniRBT-H256 基座、`RelationHead` 的 encoder/mean-pool | **复用架构** | 新任务做二分类 label head；source head 本轮不实现；默认从基座初始化，不用 N5 头权重 |
| test-freeze、dev 固定阈值、confirm 只跑一次 | **复用纪律** | 但验收指标换成三项门槛（见 §4.4） |
| ONNX/浏览器探针 | **后续复用** | 本轮不导出、不接线 |
| N5 的 `support / contradiction / unknown` 标签 | **不复用** | `contradiction` 是“事实被改写”，不是“附加陈述”；`unknown` 是“换行无证据”，不是 `unsupported`；`support` 可作 supported 底料，但不能把 N5 标签当新任务答案 |
| N5 的 fact-sentence 输入格式 | **不复用** | 新任务要完整正文＋候选片段＋事实/场景/可见授权＋来源编号 |
| N5 的 96 token 上限 | **不复用** | 新输入 p50 134、max 183 token；必须用 256 |

N5 的 G2 失败（5/256 合法句被判 contradiction）本身就是一个提醒：**“关系头能分类”不等于“合法陈述不会被误拒”**。新任务把合法误拒单独列为硬指标，不再用总正确率掩盖。

---

## 2. 新任务契约

### 2.1 输入

每条样本包含：

- `fullText`：完整单元正文；保留省略的主语和上下文；
- `candidateId`：已编号的待核对片段（本轮固定 `C1`，不做字符串定位）；
- `candidateText`：候选片段原文；
- `facts`：权威事实，带 `sourceId`（`F1..`）、`kind`、`factText`；
- `scene`：场景授权，带 `sourceId`（`S1..`）；
- `visible`：可见物授权，带 `sourceId`（`V1..`）。

序列化（`verify_input.py`）：

```
正文：...
片段 C1：...
事实：
F1｜...
场景：
S1｜...
可见：
V1｜...
判定：
```

`sourceSpans` 记录每个来源在序列化文本中的字符区间；第一版不使用 source head，保留给后续。全量 1163 条材料序列化后 p50 134 token、p90 153、max 183；**max 256 足够，N5 的 96 会截断大多数样本**。

**正文只提供完整上下文和主语恢复，不是授权来源。** 候选片段出现在正文里，不等于它被授权；授权只看 `facts/scene/visible`。这条是 N5 派生 unsupported 对的关键：正文仍含该句，但事实列表里已经没有支持它的事实。

### 2.2 输出（第一版）

```json
{"label": "supported|unsupported|uncertain", "sourceStatus": "not_implemented"}
```

- 只判定，不编辑；不输出删除位置、改写文本或段落。
- 分类头只学 `supported / unsupported` 两类；`uncertain` 是推理时由 dev 选出的拒判阈值产生的**弃权**，不是训练类。
- **source head 本轮不实现**。输出必须明确写 `sourceStatus=not_implemented`，不能返回空 `sourceIds` 冒充“已核对来源”。材料里的 F/S/V gold 编号只用于人工复核和以后做 source head，不作为本轮模型输出。
- `unsupported` 的语义是**在当前授权中得不到支持**，不等于“与世界事实矛盾”；模型只根据 `facts/scene/visible` 判断，不拿世界知识补。
- 3 条 `uncertain` 边界案例保留；它们不参与二分类损失和主指标，也不能用来声称模型具备“不确定性识别能力”。

### 2.3 不承担

- 不找字符串位置；候选已经编号。
- 不删标点、不改写、不组织、不补遗漏、不修错对象。
- 不做重复检测（N5 的 dedup 语料不并入本任务）。
- 不自动删句；初期只产生质量判定。
- 不做来源定位；source head 是后续独立问题。

---

## 3. 材料：1163 条，按源隔离

### 3.1 总量

| split | supported | unsupported | uncertain | 合计 |
| --- | --- | --- | --- | --- |
| train | 393 | 393 | 1 | 787 |
| dev | 107 | 107 | 1 | 215 |
| confirm | 62 | 62 | 1 | 125 |
| **train/dev/confirm** | **562** | **562** | **3** | **1127** |
| regression（20 源 + A1 + 5 目标稿） | 24 | 10 | 2 | 36 |

分类别（train / dev / confirm）：

| 类别 | train | dev | confirm |
| --- | --- | --- | --- |
| general（N5 派生） | 754 | 190 | 108 |
| body（合法身体描写） | 8 | 6 | 4 |
| background（合法背景引用） | 8 | 6 | 4 |
| visible-state（可见物存在但状态未授权） | 8 | 6 | 4 |
| extra-action（额外动作） | 8 | 6 | 4 |
| uncertain（`棚下散着光` 类复核） | 1 | 1 | 1 |

来源：

| split | N5 派生 | 合成定向 | 合计 |
| --- | --- | --- | --- |
| train | 754 | 33 | 787 |
| dev | 190 | 25 | 215 |
| confirm | 108 | 17 | 125 |
| regression | 0 | 36（20 源/A1/5 目标稿） | 36 |

### 3.2 成对材料：只改一个关键点

每个 `pairId` 有 supported/unsupported 两条；两条要么**正文与候选项完全一样，只改授权**，要么**授权完全一样，只改陈述**。

四个必含类别（auth 对）：

| 类别 | supported | unsupported | 只改哪里 |
| --- | --- | --- | --- |
| body | F1=`指节发白` | F1=`肩头落着灰` | 事实 F1；正文/候选不变 |
| background | 场景 S2=`浓雾` | 场景只有 `夜`（无 S2） | 场景授权；正文/候选不变 |
| visible-state | 场景 S2=`铜灯已点亮` | 场景只有 `夜`；可见 V1=`铜灯` | 场景状态授权；正文/候选不变 |
| extra-action | F1=`把灯罩系紧` | F1=`把灯罩扶正` | 事实 F1；正文/候选不变 |

另外每个类别有 3 条 statement 对（train/dev/confirm 各一）：授权完全一样，候选/正文只改一个关键点，例如：

- body：`指节发白` → `掌心出汗`；
- background：`浓雾里` → `细雨里`；
- visible-state：`铜灯亮着` → `铜灯熄了`；
- extra-action：`把鱼筐推开` → `把鱼筐收紧`。

**长度控制**：auth 对的正文/候选完全相同；statement 对尽量同长度。审计结果是每个 split 内 supported 与 unsupported 的候选长度分布**逐项相同**：

| split | supported 均值/最小/最大 | unsupported 均值/最小/最大 |
| --- | --- | --- |
| train | 12.93 / 3 / 27 | 12.93 / 3 / 27 |
| dev | 12.29 / 2 / 17 | 12.29 / 2 / 17 |
| confirm | 12.19 / 3 / 27 | 12.19 / 3 / 27 |

所以模型不能靠“长句就是加料”区分标签；长句 supported 和短句 unsupported 都在材料里。

### 3.3 按源隔离

- **N5 派生**：492 个 A/B `sourceGroupId` 按哈希约 80/20 分到 train/dev；C 族 66 个 source group 只进 confirm。一个 source group 的所有例子在同一个 split。
- **合成定向**：每个类别 6 个 auth source（3 train/2 dev/1 confirm）＋3 个 statement source（train/dev/confirm 各一）＋1 个 uncertain source；source ID 唯一，不跨 split。
- **20 源 + A1 + 5 目标稿**：单独 `regression-v1.jsonl`，不进入 train/dev/confirm；不拿来教答案。
- 审计：source group 跨 split 0；完整正文+候选跨 split 0；候选不在正文 0；gold source ID 不存在 0；成对缺失 0；auth 对只差一个授权字段 0 例外；statement 对只差候选 0 例外。

### 3.4 审计与冻结哈希

```text
pairs-v1.jsonl       ff67a4cda56c02f49d653cba21bb512e4564fd2289f8e9d7ba25738b675c630e
regression-v1.jsonl  6e060bb7ab6c666e9cf9f317ef1e18f5009e9722559d76be5920174482d27a58
a1.jsonl             e3c470b171e1d02430c33b86765796239d90f847c453023ddd7ec782e144c546
metric-freeze.json   6014c7d2feca07c4615c354c089f704317040d2a2db8e977834ad60845f6552e
```

- 审计问题 **0**；去重丢弃 2 对（4 条）完全重复的 general 文本；3 个 N5 source group 因“同一事实还有另一条等价事实”跳过（否则 unsupported 标签不成立）；27 个 N5 source group 因没有“一事实一句”候选被跳过。

来源编号核查：所有 gold `sourceId` 都能在输入列表中找到；跳过 3 个“同一事实还有另一条等价事实”的 N5 source group，否则 unsupported 会被剩余事实支持；跳过后没有“同一主体+同一事实”的残留重复。剩余 4 条高字面重叠的 general unsupported 分别是不同主体或不同任务目标（如顾北汀/陈九同路线、不同任务名），不构成支持。以上是助手核查；复看见 §3.5，独立人工金标仍未完成。

- `uncertain` 每 split 只有 1 条，不参与二分类损失和三项主门槛；只作为边界案例报告。
- 这些标签由助手构造，§3.5 的复看也是同一助手完成；**不是独立人工金标**。N5 的 support 对也不是人工金标。写新确认集前必须把材料复核状态写清。

---

## 3.5 训练前复看（assistant 复看，不是独立人工金标）

训练前按约定做了一轮有限语义复看，实际复核者仍是同一助手，记录为 **“复看”**，不写成独立人工金标：

- **confirm 全部 125 条**；
- **train/dev 四类定向材料全部 56 条**；
- **train/dev 各抽 20 对 general**（共 40 对 / 80 条），核对正负标签如何产生；
- 合计 261 条；`review-v1.jsonl` / `review-v1.md` 保留逐条内容。

结果：结构问题 0；1 条可疑 residual overlap（顾北汀/陈九同路线、不同主体）判定为不构成支持；没有发现需要再改的标签。此前已修正并重新冻结 3 个“同一事实还有另一条等价事实”的 N5 source group；复看后没有新的标签修订。复看范围、发现和“非独立”声明见 `review-v1-summary.json`。

## 4. 第一版训练设计（二分类）

### 4.1 模型

- **MiniRBT-H256 基座** + masked mean-pool + **linear(2)**；只输出 `supported / unsupported`。
- 不加 source head；不加载 N5 关系头权重；默认从 `assets/minirbt-h256-snapshot` 的基座初始化。
- `uncertain` 只在推理时由拒判规则产生，不进入损失。

### 4.2 输入/长度

- 使用 §2.1 的序列化；max length **256**。
- **动态补齐，不静默截断**：`truncation=False`；任何样本超过 256 token 直接报错并停止，不截断、不丢弃、不补模板。
- 当前全量 max 183 token；256 只是长度检查值。

### 4.3 训练与选择顺序（写死）

- 固定 **12 epochs**；每个 epoch 结束评 dev；每个 epoch 保存 checkpoint；不早停、不按“视情况”改轮数。
- 分类：`p_unsupported = softmax(logits)[unsupported]`；基础标签 `p_unsupported >= 0.5` → unsupported，否则 supported。
- 拒判：`max(p_supported, p_unsupported) < t_conf` → `uncertain`；`t_conf` 只在 dev 上从 `0.50..0.99`（步长 0.01）选。
- 候选（epoch, t_conf）必须先在 dev 满足三项主门槛：
  - `unsupportedRecall >= 0.80`
  - `legalRejection <= 0.05`
  - `legalPending <= 0.15`
- 合格候选中按以下顺序唯一选择：
  1. `unsupportedRecall` 最大；
  2. `legalRejection` 最小；
  3. `legalPending` 最小；
  4. epoch 最早；
  5. `t_conf` 最低（在指标相同时少弃权）。
- 若 12 个 epoch 与全部 t_conf 都没有合格组合：**停止，不跑 confirm**，报告 dev 表；不为过关改门槛或换材料。
- 选中 checkpoint 和 t_conf 后冻结；confirm 只跑一次。

### 4.4 评测

**三项主门槛，不用总正确率：**

| 主门槛 | 定义 | 门槛 |
| --- | --- | --- |
| `unsupportedRecall` | unsupported→unsupported / 全部 unsupported | ≥ 0.80 |
| `legalRejection` | supported→unsupported / 全部 supported | ≤ 0.05 |
| `legalPending` | supported→uncertain / 全部 supported | ≤ 0.15 |

`legalPending` 是防止“靠大量拒判降低合法误拒”的约束；`unsupportedRecall` 同时防止把 unsupported 大量弃权。

辅助报告：`unsupportedPrecision`（≥0.85 为目标）、整体 uncertain 率、general/body/background/visible-state/extra-action 分层指标、逐例结果。`uncertain` 边界案例单独列出，不并入主指标。**sourceStatus 只做 schema 检查；本轮没有来源定位指标。**

### 4.5 通过后怎么用

只有 confirm 三项主门槛都过，才讨论“把判定用于改善输出”。初期只把 `unsupported` 作为质量标记/人工复核入口，不自动删句；source head、来源正确性/完整性、与生成器协同都是后续独立工作。

---

## 5. 20 源回归：只回归，不训练

`regression-v1.jsonl` 36 条：20 条 A1 保留的合法外貌/身体事实、7 条 A1 的 `drop-unsourced`、9 条 5 目标稿（3 条 supported 背景、1 条 supported 身体、2 条 unsupported 可见物状态、1 条 unsupported 背景、2 条 uncertain）。

用选中的二分类 checkpoint 和 t_conf 单独跑一次；**不参与训练、不参与 confirm 选择、不参与门槛调参**。来源编号仍是材料标注，不是模型输出。A1 的独立人工复核仍未完成。

---

## 6. 交付物与状态

| 文件 | 内容 |
| --- | --- |
| `artifacts/statement-verification/pairs-v1.jsonl` | 1127 条 train/dev/confirm 材料 |
| `artifacts/statement-verification/regression-v1.jsonl` | 36 条 20 源/A1/5 目标稿回归 |
| `artifacts/statement-verification/audit.json` | 结构/来源/成对/长度审计 |
| `artifacts/statement-verification/split-freeze.json` | 划分、材料/指标/复看哈希 |
| `artifacts/statement-verification/metric-freeze.json` | 二分类三项主门槛、拒判/选择顺序 |
| `artifacts/statement-verification/review-v1.{jsonl,md}` | 261 条复看记录 |
| `artifacts/statement-verification/review-v1-summary.json` | 复看范围、发现、非独立声明 |
| `experiments/world-components/n4_corpus_v2/build_statement_verify.py` | 材料构建；复用 N5 |
| `experiments/world-components/n4_corpus_v2/verify_input.py` | 序列化/输入校验；no training |
| `experiments/world-components/n4_corpus_v2/train_verify_binary.py` | 二分类训练/选择/评测（本轮新增） |

**本轮已做：** 材料复看后的二分类训练、dev 选择、confirm 一次、20 源回归单列。

**第一轮结果：** dev 选中 epoch 12 / t_conf=0.53；confirm 整体 unsupported recall 0.9677、legal rejection 0.0484、legal pending 0；但 general 54/54 supported 全对、54/54 unsupported 只漏 1，定向 body 合法误拒 1/2、extra-action 2/2，20 源回归 unsupported 0/10。详见 [`statement-verification-binary-run.md`](statement-verification-binary-run.md)。**不把整体 pass 当成职责成立。**

**本轮不做：** source head、来源定位、ONNX/浏览器、服务接线、自动删句、换 u240、第二轮训练。

**已知限制：**

- 复看仍是同一助手，不是独立人工金标；N5 support 标签也不是人工金标。
- 3 条 `uncertain` 只是边界案例；本轮不声称具备不确定性识别能力。
- 定向类每 split 只有 4–8 条，类别指标会有波动；general 高分不能掩盖定向类别。
- N5 派生的 unsupported 多为“授权被移除”，难度低于“近似越权”；定向类别补了近似越权，但量小。
- confirm 的 C 族在 N5 评测中出现过（未参与 N5 训练）；它是源隔离的，但不是项目完全没见过的新家族。
- source head 未实现；来源编号正确性/完整性是后续独立验收。

---

## 7. 第一轮之后

1. 第一轮已按固定顺序选中 epoch 12 / t_conf=0.53，confirm 只跑一次；完整数字和逐例见 [`statement-verification-binary-run.md`](statement-verification-binary-run.md)。
2. 整体 confirm 过门槛，但 general 驱动；定向类别和 20 源回归没有过。**不跑第二轮，不逐轮补提示词，不接 source head/服务。**
3. 如果继续，应先解决目标分布训练样本/定向近似越权不足的数据问题，而不是继续调同一个头。
4. 通过职责层面的证据后，才讨论把判定用于改善输出；source head/来源定位另开一题。

下一项目标表达配对材料已建（124 对 / 248 条，结构审计 0），未训练；见 [`statement-verification-target-pairs-v1.md`](statement-verification-target-pairs-v1.md)。 目标臂已按 300 updates 跑完；新 confirm 检出 20/24、合法误拒 3/24、待复核 0/24，因合法误拒超线**不通过**；见 [`statement-verification-target-run-v1.md`](statement-verification-target-run-v1.md)。
