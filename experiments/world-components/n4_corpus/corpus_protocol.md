# N4 成句语料构造协议（首批）

日期：2026-10-29。依据：[方案表](../../model-training-runtime.md)（N4 例外条款）、[C任务边界](../../README.md)样本隔离、2026-10-29 语料设计评审六项要求。本协议约束 `build_seeds.py`（构造）、`corpus_check.py`（行校验）、`dedup_check.py`（去重）三工具与语料 JSONL 形状。

## 1. 行 schema（JSONL，每行一对象）

| 字段 | 约束 |
| --- | --- |
| `sourceGroupId` | 组 ID。**同一事实种子的模板行与全部改写行共用**；`split` 在组级一致（校验器强制），训练/开发验收按组隔离，禁止按行随机拆分 |
| `rowOrigin` | `template-seed`（程序渲染）或 `rewrite`（改写）——逐行标记 |
| `rewriter` | `program`（种子行）或 `zcode-model`（改写行，如实标注；模型改写进入训练依据方案表 N4 例外条款） |
| `task` | 本批全部 `n4-sentence` |
| `split` | `train` 或 `dev`（组级） |
| `plan` | 事实计划条目数组，`ref` 下标＋kind/entityId/name/值。由程序枚举**独立构造**（非状态差分反推），`planConstruction` 记录构造方法，`planValidation` 记录所过结构校验（README 叙事输入锚点的离线记录等价要求） |
| `text` | 正文 |
| `planRefs` | 逐句回指：句子按句号切分后每句引用的 plan 下标数组。**引用存在≠事实忠实**，忠实由校验器逐类核对＋人工抽验 |
| `mustExpress` / `mayMention` / `mustNotAdd` | 三类标注齐备（必述下标／可选下标／禁止新增主张的文字描述） |
| `hashes` | `plan`（canonical JSON sha256）＋`text`（sha256），校验器重算比对 |
| `purpose` | 用途记录（一行一写） |
| `overlap` | 仅改写行：见 §4 |

## 2. 排除清单（dedup_check.py 扫描源，版本钉 commit）

| 源 | 提取字段 |
| --- | --- |
| `frontend/src/lib/world-engine/runtime/narration-eval-samples.ts`（nv-*，HEAD 7af52d7） | mechanical/reference/forbidden 数组/goal/mayMention/note 全部字符串 |
| `frontend/src/lib/world-engine/runtime/narration-eval-validation.ts`（hv-*，同上） | 同上 |
| `frontend/src/lib/world-engine/runtime/narration-split-samples.ts`（ns-*，同上） | requiredFacts.phrase、mustNotFabricate、描述文本 |
| `frontend/src/lib/world-engine/runtime/b3-samples.ts`，同上 | 任务 goal、appearance、描述 |
| `artifacts/narration-eval-recheck/run.json`（归档采纳稿/参照/生成文本） | 递归全部字符串值 ≥4 字 |
| `artifacts/narration-split-baseline.json`（程序基线输出） | 同上 |

**Forbid 串剥注记变体**：含 `（…）` 的源串，剥注记后的核心串同样入源集——直接来自冒烟探针教训（`narration-freeform` = nv-cont-1 forbidden 串剥「（方向反转）」派生）。

**已知漏扫项（如实声明）**：TS 文件的类型代码与注释不扫；`world-page/`、`world-chain/` 等整链归档里的真机输入原文未扫；模板句式拼接代码（committed-narration 等）以短语人工核对补（「没有新的变化」教训即来源于此——本批种子空点句式已显式避开）。**去重结论只能表述为"在上述清单范围与规则下零命中"**；换名、方向反转等未穷尽派生由人工抽验补，不宣称独立证明。

**扫描规则**：源串 ≥4 字做双向子串检查；<4 字（人名/短地名等 cast 词）不判失败只登记命中（设计目标=新词表零 cast 命中，命中即回改）。

## 3. 词表（全新，与 B cast 零交集）

人物：陈舟/苏晚/周砚/林望/沈青；地点：东门/水房/钟楼/侧院/柴房/石桥/碑亭；物品：铜铃/木匣/青瓷碗/油纸伞；任务 goal：把铜铃挂回钟楼/整理柴房/修缮石桥栏杆/清点碑亭石刻；时长：三/八/十二/二十五/四十分钟、一小时。构造器断言新词表与 dedup cast 集合零交。

## 4. 改写重叠率（复核信号，非硬门）

- **遮蔽单列**：人名、数值＋单位、任务引语「」三类先替换为占位符 ⟨N⟩/⟨V⟩/⟨Q⟩——它们本来就应原样保留（引语逐字、人名一致、数值与计划一致由校验器按忠实性单独核对），不计入重叠率。
- **算法**：字符 2-gram 集合重合率 = |bigrams(rewrite_masked) ∩ bigrams(seed_masked)| ÷ |bigrams(rewrite_masked)|，分母=改写行。同组 template-seed 行为种子基线。
- **用途**：ratio > 0.6 的行标 `review-flag`（人工看是否真的改写了），**不因此失败**；低于阈值不构成质量证明，只是不再触发复核。
- 防照抄机制=重叠率信号＋校验器逐类忠实核对＋协调人抽验三层。

## 5. 校验器逐类核对（corpus_check.py）

planRefs 下标有效（含句数=refs 行数）；mustExpress ⊆ 被引用并集；人物归属（条目 name 出现在其被引用句）；方向（moved 的 from/to 均出现）；数值（amount+unit 出现，接受汉字/阿拉伯数字表驱动映射）；引语（task goal 逐字出现）；组级一致性（split/plan/purpose）；哈希重算；三类标注齐备；改写行附加 rewriter/overlap 检查。**内置负例自检**（下标越界、必述漏覆盖两坏行必须被抓，否则报告作废）。

## 6. 首批规模与顺序

首批 24–32 组种子行＋2 行改写样例（走通改写全链），**流程试验性质，不预设足以训练 77M**。语料清单先交付协调人抽验（§1–§5 全部可见），通过后才开微调；批量改写在工具链获认可后进行。
