# 事实—陈述核对：目标表达配对材料 v1（2026-11-05）

**本轮材料已复看并冻结训练协议；不扩材料、不换模型、不加 source head。** 目标是把训练/选点从 N5 派生 general 转到真正要处理的四类表达；旧 20 源和失败片段仍只作回归，不拿来补答案。

---

## 1. 总量

| 类别 | train | dev | confirm | 合计 |
| --- | --- | --- | --- | --- |
| body（身体描写） | 20 对 / 40 条 | 5 对 / 10 条 | 6 对 / 12 条 | 31 对 / 62 条 |
| background（背景引用） | 20 / 40 | 5 / 10 | 6 / 12 | 31 / 62 |
| visible-state（可见物状态） | 20 / 40 | 5 / 10 | 6 / 12 | 31 / 62 |
| extra-action（额外动作） | 20 / 40 | 5 / 10 | 6 / 12 | 31 / 62 |
| **合计** | **80 对 / 160 条** | **20 对 / 40 条** | **24 对 / 48 条** | **124 对 / 248 条** |

每对固定一正一负：supported 124、unsupported 124。

配对方式（每类）：

| split | authorization 对 | statement 对 |
| --- | --- | --- |
| train | 10 | 10 |
| dev | 3 | 2 |
| confirm | 3 | 3 |
| **合计** | **64** | **60** |

- **authorization 对**：正文和候选完全相同；正负只差授权内容。
- **statement 对**：facts/scene/visible 完全相同；正负只差候选/正文里的一个关键点。

---

## 2. 四类怎么让标签依赖授权

### body

**auth**：同一句身体描写；正例 facts 里有对应身体/外貌事实，负例把这条事实换成同主体的移动事实，事实数量不变。

```text
正文：阿棠的袖口湿透。
候选：袖口湿透
正：F1=袖口湿透；F2=把纸伞扶正  → supported
负：F1=从渡口来到茶棚；F2=把纸伞扶正 → unsupported
```

**statement**：授权不变，候选换成另一句身体描写。

```text
正：F1=手腕被缆绳勒出红痕；候选=手腕被缆绳勒出红痕 → supported
负：同一组 facts；候选=手背被灯油烫起小泡 → unsupported
```

### background

**auth**：正文和候选不变；正例场景包含该背景，负例把场景换成另一种天气，scene 数量不变。

```text
正文：河雾里，阿棠把缆绳拖回。
候选：河雾里
正：S1=夜；S2=河雾 → supported
负：S1=夜；S2=细雨 → unsupported
```

**statement**：场景不变，候选换成另一种天气。

```text
正：S2=雨声；候选=雨声里 → supported
负：S2=雨声；候选=风声里 → unsupported
```

### visible-state

**auth**：物件始终可见；正例场景里有“物件+状态”，负例只给“物件”而不给状态，scene 数量不变。

```text
正文：纸灯已点亮，阿棠把灯罩擦亮。
候选：纸灯已点亮
正：S1=夜；S2=纸灯已点亮；V1=纸灯 → supported
负：S1=夜；S2=纸灯；V1=纸灯 → unsupported
```

**statement**：场景状态不变，候选换成另一个状态。

```text
正：S2=风灯亮着；候选=风灯亮着 → supported
负：S2=风灯亮着；候选=风灯灭了 → unsupported
```

### extra-action

**auth**：候选动作在 facts 里出现才合法；负例换成另一个动作，或只给物件存在+另一个动作，facts 数量不变。

```text
正文：阿棠把鱼筐推开。
候选：阿棠把鱼筐推开。
正：F1=把鱼筐推开；F2=鱼筐在灶边 → supported
负：F1=把鱼筐扶正；F2=鱼筐在灶边 → unsupported
或
负：F1=鱼筐在灶边；F2=把鱼筐扶正 → unsupported
```

**statement**：授权不变，候选换成另一个动作。

```text
正：F1=把灯罩系紧；候选=闻溪把灯罩系紧。 → supported
负：同一组 facts；候选=闻溪把灯罩擦亮。 → unsupported
```

---

## 3. 负例不是靠删事实

结构审计逐对检查：

- auth 对：facts/scene/visible 的**数量完全相同**；不允许靠删一条事实制造负例。
- statement 对：facts/scene/visible **完全一致**；只有候选/正文变化。
- 负例机制统计：移动事实替换身体事实、另一种天气替换场景、物件替换状态、另一个动作/物件存在替换动作；没有“负例少一条事实”的样本。
- 审计 `issueCount=0`，具体检查见 `audit-target-v1.json`。

---

## 4. 直接支持的容易正例保留

四类各保留“事实/场景原文就写了”的容易正例：

- body：`袖口湿透`，F1 就是 `袖口湿透`；
- background：`河雾里`，S2 就是 `河雾`；
- visible-state：`纸灯已点亮`，S2 就是 `纸灯已点亮`；
- extra-action：`阿棠把鱼筐推开。`，F1 就是 `把鱼筐推开`。

审计中 `directEasy` 四项全为 true。它们会进入训练，防止核对器把正常表达也拒绝掉。

---

## 5. 来源与模板族划分

每类 9 个模板族：

| 类别 | 模板族 |
| --- | --- |
| body | limb / stain / mark / trace / bandage / bruise / cloth / mud / scratch |
| background | prefix / suffix / mid / through / notcleared / light / stop / drift / strong |
| visible-state | prefix / suffix / when / semicolon / see / onlythen / zhe / wait / at |
| extra-action | e1–e9（不同动作结构和字段） |

每类 5 个 train 族、2 个 dev 族、2 个 confirm 族；族大小 4（train）、2/3（dev）、3/3（confirm）。**整个族只进一个 split**，不是同一模板换人名再换 `sourceId`：

- `sourceGroupId` 跨 split：0；
- `templateId` 跨 split：0；
- 同一 `fullText` / `candidateText` 跨 split：0；
- 每族 4/2/3 对，族内只做词槽变化，族间模板结构不同。

---

## 6. 旧数据怎么放

- **20 源回归**：`regression-v1.jsonl` 原样保留，36 条；新目标材料与它们没有 exact fullText/candidate 重叠；不进入 train/dev/confirm，不照着补答案。
- **general 迁移评测**：`general-capability-v1.jsonl` 298 条，来自原 general 的 dev 190 + confirm 108；supported 149 / unsupported 149。它是迁移评测，不是能力保持证明，**不参与新 dev 选点/阈值，不参与新 confirm**；也不再叫“能力保持集”。
- 原 general train 不进入本轮目标训练。

---

## 6.5 训练前复看与判定范围

复看范围：**64 对 / 128 条**——36 个模板族各至少一整对，`when / see / through / notcleared` 四个重点族全部对，confirm 全部 24 对 / 48 条。复核者仍是同一助手，记录为 **“复看”**，不是独立人工金标。

**判定范围（写死）：**

- 标签只判 `candidateText` 在上下文中的含义；
- `fullText` 只帮助恢复主体和语境，**不是授权来源**；
- 不判整段正文是否干净；
- body 的正文只帮助恢复主体，授权仍是 F1 身体事实；
- `when` 的时间、`see` 的感知、`through` 的遮挡、`notcleared` 的“还没散”都在候选之外；候选只取状态/背景/动作本身，不把这些额外语境当成授权。

**重点句框检查：**

| 句框 | 发现 | 标签 |
| --- | --- | --- |
| when | “把门闩落下时”是时间框；候选是 `铜铃响着`，由 scene 状态项授权 | 不改 |
| see | “看见”是感知框；候选是 `炉火亮着`，由 scene 状态项授权 | 不改 |
| through | “隔着晨雾”是遮挡/语境框；候选是 `晨雾`，由 scene 背景项授权 | 不改 |
| notcleared | “薄雾还没散”的“还没散”是持续状态，**在候选之外**；候选 `薄雾` 由 scene 授权。若判整句，这句会多出未授权持续状态；本任务不判整句 | 不改 |

**body 状态变化检查：** 9 个 body 族代表正例都是身体状态/变化，不只是静态外貌照抄，例如“指节被麻绳勒得发白”“袖口湿透”“额角起了青包”“手背被竹篾划出血痕”“衣摆湿了”。没有改成只收外貌句。

**复看中做的两处材料内修正（标签仍 unsupported）：**

- `tgt:visible-state:train:train-04:p02`：候选“窗纸补好” → “窗纸揭过”；F1 是“把窗纸补好”，避免动作结果与状态重叠。
- `tgt:visible-state:confirm:confirm-02:p03`：候选“窗纸糊好” → “窗纸换过”；同一原因。

confirm 全部 48 条逐对检查，未发现需要改标签的项；`labelChanges=[]`。复看记录：

- `review-target-v1.jsonl`（128 条）
- `review-target-v1.md`
- `review-target-v1-summary.json`

---

## 7. 训练协议（复看后冻结）

- **初始化**：同一个 MiniRBT-H256 基座，**不加载上一轮 general 检查点**；模型/头/损失/优化器不变。
- **冻结对照**：上一轮 `ckpt-verify-binary/selected.pt` + 其 `t_conf=0.53`，在新 target confirm 上评一次；不调阈值。
- **数据**：target train 80 对 / 160 条；target dev 20 对 / 40 条；target confirm 24 对 / 48 条；general 迁移评测 298 条；20 源回归 36 条。
- **训练预算**：固定 **300 次更新**，每 **25 步**评 target dev（12 次）；target train 160 条 / batch 32 = **5 steps/epoch**，所以是 **60 epochs**。上一轮也是 300 updates；但新数据下是 60 epochs，不能写成“12 epochs 相同曝光”或“60 steps”。不设第二套预算。
- **dev 选点**：沿用冻结规则——target dev 上先满足 `unsupportedRecall≥0.80`、`legalRejection≤0.05`、`legalPending≤0.15`，再按 recall 最大、legal rejection 最小、legal pending 最小、最早 step、最低 `t_conf` 选。
- **confirm 整数门槛**（24 正 / 24 负）：

| 指标 | 允许范围 |
| --- | --- |
| 无依据检出 | 至少 **20/24** |
| 合法误拒 | 至多 **1/24** |
| 合法待复核 | 至多 **3/24** |

- general 迁移评测只做迁移观察，不参与选点；20 源回归单列；confirm 不用于调阈值。四类分别逐例。
- 即使 confirm 总体过线，只要目标类别集中失败，不能宣布职责成立；即使新 confirm 通过、旧回归仍 0/10，也不能说已经解决实际表达核对。
- 不接 source head、不接服务、不自动删除。

协议文件：`training-protocol-target-v1.json`（300 updates / 25-step eval / 60 epochs）。

### 7.1 第一轮执行结果

训练已按 300 updates 跑完，选中 step 150 / `t_conf=0.50`；新 confirm：

| 指标 | 结果 | 整数门槛 |
| --- | --- | --- |
| 无依据检出 | 20/24 | 过 |
| 合法误拒 | **3/24** | **失败** |
| 合法待复核 | 0/24 | 过 |

**总体不通过。** 旧 `selected.pt` 在同一新 confirm 上是 7/24 检出、8/24 合法误拒、4/24 待复核；新模型有改善但仍未过线。general 迁移评测的合法误拒 145/149（独立检查点，不是遗忘结论）；20 源回归检出 9/10，但合法误拒 17/24。详见 [`statement-verification-target-run-v1.md`](statement-verification-target-run-v1.md)。

不接 source head/服务，不跑第二轮。

---

## 8. 审计结果

| 项 | 结果 |
| --- | --- |
| 总对数/条数 | 124 / 248 |
| 标签 | 124 supported / 124 unsupported |
| 类别 | 每类 31 对 |
| split | train 80 / dev 20 / confirm 24 对 |
| 模式 | auth 64 / statement 60 对 |
| 族 | 36 个；family 跨 split 0；template 跨 split 0 |
| 文本/候选跨 split | 0 |
| auth 字段数量差 | 0 |
| statement 授权差 | 0 |
| 候选不在正文 | 0 |
| gold source 缺失 | 0 |
| 旧回归 exact 文本重叠 | 0 |
| 直接容易正例 | 四类都有 |
| 审计问题 | **0** |

哈希：

```text
pairs-target-v1.jsonl        746c0f0754bbae536d34a513280e714f6c33eb3c92804cb37aec46efac79a603
general-capability-v1.jsonl  259ecbd03f82a33b53a7d57b19b15766eb9f873fad63ee6489e2382be212d5fb
audit-target-v1.json         50f5e9cc1a82ad6aa7a1b4b0c4589836433e9be4265464c7637c93ccf41797c2
split-freeze-target-v1.json  0c0d3a99ce14a8aec9d6b08c241bbfee26cf857b5a3e2f89de7a31f739f2439c
review-target-v1.jsonl       cb3662667e71e7eb41e568ef644b252264eec8407ab9f061d7e80d5223ac3578
review-target-v1-summary    3045018d8df3190e1e537ad53ec9342d877ad67d5ff9ca6e16657b22ab124717
training-protocol-target-v1  8f38a05196cd5c042a7c98a1a593ee7ebcbebdab2a4eaa571773e09ffb5bf353
regression-v1.jsonl          6e060bb7ab6c666e9cf9f317ef1e18f5009e9722559d76be5920174482d27a58
```

材料由助手按模板构造并做结构审计；**独立人工语义复核尚未完成**。下一轮训练前若要做复看，应另记复核者，不改历史冻结。

---

## 9. 文件

| 文件 | 内容 |
| --- | --- |
| `artifacts/statement-verification/pairs-target-v1.jsonl` | 124 对目标表达材料 |
| `artifacts/statement-verification/general-capability-v1.jsonl` | 298 条 general 迁移评测 |
| `artifacts/statement-verification/regression-v1.jsonl` | 原 20 源回归，未改 |
| `artifacts/statement-verification/audit-target-v1.json` | 0 问题审计 |
| `artifacts/statement-verification/split-freeze-target-v1.json` | 划分/计数/哈希冻结 |
| `experiments/world-components/n4_corpus_v2/build_target_pairs.py` | 材料构建脚本 |
