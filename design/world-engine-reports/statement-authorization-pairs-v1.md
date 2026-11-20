# 陈述—授权配对输入 v1（2026-11-05）

**本轮不训练。** 只把已完成的对齐表整理成“明确陈述 + 相关授权”的配对输入，并回答一个问题：这批输入和此前二分类实验是不是实质相同。

结论：**实质相同。** 20 条候选全部已存在于二分类回归集，标签 20/20 一致，其中 12 条授权逐字相同。因此没有理由再训一次。

## 1. 输入口径

每条配对是一行，字段为：

| 字段 | 含义 |
| --- | --- |
| `candidateText` | **原文写法**，不改字、不补主语；片段就保留片段（可包含句首逗号） |
| `contextText` | 该片段所在的原始段落，取 `regression-v1.jsonl` 的 `fullText` |
| `candidateSlots` | 主体、对象或部位、状态或动作、位置、否定、条件、`也` 的并列前项 |
| `subject` | `{text, status, recoveredFrom}`；`status` 只取 `explicit / recovered / unresolved` |
| `authorization` | 固定的 `F`（事实）/ `S`（场景）/ `V`（可见）包，带 `sourceId` |
| `minimalScope` | 判定这条需要比较哪些片段 |
| `insufficiency` | 仅 unsupported 有：缺口类型 + 一句话依据 |
| `relatedness` | 仅 unsupported 有：哪几条证据相关、相关在哪、为什么还不够 |
| `label` | `supported / unsupported` |

## 2. 20 条

### Unsupported 10

| ID | 候选（原文） | 缺口 | 相关证据 | 为什么不够 |
| --- | --- | --- | --- | --- |
| U01 | `小雨落在天窗外` | position-relation | S2 小雨、V5 天窗、V7 门槛 | 承认雨和天窗；缺“落在天窗外” |
| U02 | `在铜灯下` | position-relation | S3 铜灯、V2 铜灯 | 承认铜灯存在；缺位置关系；主体未写 |
| U03 | `清晨的薄雾还没散` | missing-state | S1 清晨、S2 薄雾 | 承认清晨和薄雾；缺“还没散” |
| U04 | `，袖口被雨浸透` | object-mismatch | F3 衣领被雨浸透 | 状态逐字相同，部位从衣领换袖口 |
| U05 | `，手腕上沾着盐沫` | object-mismatch | F1 灯罩蒙了灰、F2 掌心出汗 | 同主体；部位换手腕 |
| U06 | `，手背上沾着水沫` | object-mismatch | F5 鬓发被雾打湿 | 同主体；部位换手背 |
| U07 | `，袖口被雨浸透` | object-mismatch | F3 衣领被雨浸透 | 同 U04，另一主体 |
| U08 | `，蹲到雾堤的钟架下` | extra-action | F1 潮渡→雾堤、V6 钟架 | 承认移动到雾堤；缺蹲下姿态和钟架下 |
| U09 | `，钟绳绷直了` | result-state | F2 重新系紧、V1/V7 钟绳 | 主体对象都对；缺“绷直” |
| U10 | `，玻璃上不再有雾` | negative-state | F3 擦亮灯罩、F4 一切如旧 | 玻璃不在可见清单；缺否定状态 |

### Supported 10

| ID | 候选（原文） | 主体状态 | 支撑 |
| --- | --- | --- | --- |
| L01 | `清晨的薄雾里` | unresolved | S1 清晨、S2 薄雾 |
| L02 | `浓雾里` | unresolved | S2 浓雾 |
| L03 | `清晨的薄雾` | unresolved | S1、S2；正文“还没散”不在候选内 |
| L04 | `沈砚的手背上也沾了铜油` | explicit | F2；F1 只核对“也”的前项 |
| L05 | `衣领湿了，肩头也湿了` | recovered | F1 逐字 |
| L06 | `手背沾了泥，帽檐也沾了泥` | recovered | F1 逐字 |
| L07 | `指尖沾了墨` | recovered | F2 |
| L08 | `手背上沾着盐沫` | recovered | F3 |
| L09 | `袖口沾了盐沫` | recovered | F4 |
| L10 | `鞋底沾了湿石板的水` | recovered | F1 |

主体状态分布：explicit 5 / recovered 11 / unresolved 4。

## 3. 防泄漏控制

1. **负例证据不为空**：最小 2 条、最大 16 条；没有一条靠空列表泄露标签。
2. **负例证据必须相关**：每条 unsupported 都写 `relatedness`，指明相关证据的 `sourceId` 和相关方式（同主体 / 同对象 / 同状态换部位 / 同目的地 / 同场景物换状态），并说明为什么不够。
3. **同段共享同一个授权包**：`t01`（U01/U02/L07）、`v01`（U08/U09/L09）、`v02`（U03/L03）各自的三条或两条配对使用逐字相同的 `authorization`；证据存在与否无法区分标签，只能比较候选与证据。
4. **候选不改写**：20 条全部通过“原文逐字包含”检查；没有把 `，袖口被雨浸透` 补成 `周宁的袖口被雨浸透`。
5. **主体不升级**：`recovered` 保留 `recoveredFrom` 出处；`unresolved` 不填答案。
6. 结构审计问题数 **0**。

## 4. 与二分类实验的重叠

逐条比对 `regression-v1.jsonl` 与 `pairs-target-v1.jsonl`：

| 项 | 数量 |
| --- | --- |
| 候选文本已存在于旧材料 | **20 / 20** |
| 标签与旧材料一致 | **20 / 20** |
| 授权与旧材料逐字相同 | **12 / 20** |
| 授权有增减（裁到相关证据） | 8 / 20 |

结论：

- 判定单位仍然是“一个候选跨度 vs 一个事实列表”，没有改变；
- 12 条连输入字节都相同，只是输出标签从“二元”换成“缺口类型”；
- 8 条只是把证据裁到相关项，候选和标签都没变。

**因此这批输入不构成新的比较单位，不能作为再训一次的理由。**

真正改变比较单位需要至少一条：

- 20 条之外的留出材料（本批 20 条全部来自同一批对齐源，没有 train/dev/test 划分余量）；
- 输出标签不能从给定主体字段直接读出（现在主体是输入，模型只需比对，难度已被人工标注拿掉）；
- 每种缺口类型有足够条数支撑拟合与选点（现在 extra-action 1 条、result-state 1 条、negative-state 1 条、missing-state 1 条）。

## 5. 这轮留下的东西

保留：

- **标点切分基线**：20 源 A0 回归 93/95，作为候选切分工具复用；仍只是当前回归表现，不等于语义抽取已解决；
- **真实失败案例**：`t01` / `v01` / `v05` 加料、`train-r2` 部位替换、`t19` 背景加状态、`v02` 持续否定，这些来自真实 u240 输出，可直接用于后续核对研究。

不保留：

- 学习型抽取器这一支（已结束，不重跑）；
- 把抽取成功当成事实核验成功；
- 自动扩容。

遇到多跨度或主体无法恢复时，保留原文并标 `unresolved` 待处理，不强行拼出确定陈述。

## 6. 边界

- 不训练；不研究证据检索（本轮把检索误差排除掉）；
- 不接 source head、不接服务、不自动删句；
- u240、编辑层、质量标记维持原状，质量仍标未核验；
- 人工陈述边界与主体标注是**隔离实验条件**，不算系统能力。

## 7. 文件

| 文件 | 内容 |
| --- | --- |
| `artifacts/statement-verification/statement-authorization-pairs-v1.jsonl` | 20 条配对输入 |
| `artifacts/statement-verification/statement-authorization-pairs-v1-summary.json` | 计数、缺口类型、审计结果 |
| `artifacts/statement-verification/statement-authorization-overlap-v1.json` | 与旧材料的逐条重叠比对 |
| `experiments/world-components/n4_corpus_v2/build_statement_authorization_pairs.py` | 生成与结构审计 |
| `experiments/world-components/n4_corpus_v2/audit_authorization_pairs_overlap.py` | 重叠审计 |

关键哈希：

```text
pairs-v1.jsonl        62b2b803003a4d46afe5de04ae5ec81829c3304eebff0ee0a2def530c1d64282
pairs-v1-summary      30043244bbafb575cc883dcbc4d4c56fbedbbbcd9607ad82e049a6d7a069bf2e
overlap-v1            6a0419bd4bf0b9894edf85fcf0fd320832111ad3e9ea9741aa45f3647483a5cf
```
