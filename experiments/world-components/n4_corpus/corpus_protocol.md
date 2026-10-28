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
| `plan` | 事实计划条目数组，`ref` 下标＋kind/entityId/name/值。由程序枚举**独立构造**（非状态差分反推），`planConstruction` 记录构造方法（声明）；权威证据由 `validate_plan_authority.py` 独立产出——把 plan 映射为 backend v2 `EntityDelta`/`TimeAdvance` 并经 pydantic 逐行校验，结果落 `authority-report.json`（含 contracts.py 源哈希与中文实体名→ASCII 草稿键映射），行内 `planValidation` 仅指向该报告 |
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
| `artifacts/world-page/*.json`＋`artifacts/world-chain/*.json`＋`artifacts/narration-http-review.json`（**整链真机归档**，复核轮 3 要求纳入） | 递归全部字符串值；C 树缺失时回退主树读取并记录实际路径，仍缺记 MISSING 不静默跳过 |

**Forbid 串剥注记变体**：含 `（…）` 的源串，剥注记后的核心串同样入源集——直接来自冒烟探针教训（`narration-freeform` = nv-cont-1 forbidden 串剥「（方向反转）」派生）。

**已知漏扫项（如实声明）**：TS 文件的类型代码与注释不扫；`world-page/`、`world-chain/` 等整链归档里的真机输入原文未扫；模板句式拼接代码（committed-narration 等）以短语人工核对补（「没有新的变化」教训即来源于此——本批种子空点句式已显式避开）。**去重结论只能表述为"在上述清单范围与规则下零命中"**；换名、方向反转等未穷尽派生由人工抽验补，不宣称独立证明。

**扫描规则**：语料侧只扫**内容字段**（text＋plan 的 name/from/to/at/goal/text；结构字段 kind/unit/ref/amount/entityId/rendered/scope 排除——短结构值如 kind="time" 会对长元描述串产生假方向命中）；源串 ≥4 字做逐字段**双向**子串检查（不拼接整行——拼接改变方向且掩盖字段边界）；<4 字（人名/短地名等 cast 词）不判失败只登记命中（设计目标=新词表零 cast 命中，命中即回改）。

## 3. 词表（全新，与 B cast 零交集）

人物：陈舟/苏晚/周砚/林望/沈青；地点：东门/水房/钟楼/侧院/柴房/石桥/碑亭；物品：铜铃/木匣/青瓷碗/油纸伞；任务 goal：把铜铃挂回钟楼/整理柴房/修缮石桥栏杆/清点碑亭石刻；时长：三/八/十二/二十五/四十分钟、一小时。构造器断言新词表与 dedup cast 集合零交。

## 4. 改写重叠率（复核信号，非硬门）

- **遮蔽单列**：人名、数值＋单位、任务引语「」三类先替换为占位符 ⟨N⟩/⟨V⟩/⟨Q⟩——它们本来就应原样保留（引语逐字、人名一致、数值与计划一致由校验器按忠实性单独核对），不计入重叠率。
- **算法**：字符 2-gram 集合重合率 = |bigrams(rewrite_masked) ∩ bigrams(seed_masked)| ÷ |bigrams(rewrite_masked)|，分母=改写行。同组 template-seed 行为种子基线。
- **用途**：ratio > 0.6 的行标 `review-flag`（人工看是否真的改写了），**不因此失败**；低于阈值不构成质量证明，只是不再触发复核。
- 防照抄机制=重叠率信号＋校验器逐类忠实核对＋协调人抽验三层。

## 5. 校验器逐类核对（corpus_check.py，v3 识别器白名单）

**判定模型（复核轮 2 翻转）：pass 只覆盖被受控识别模式完整识别且与计划一致的表达；任何未识别残句（无依据细节、否定、意图、换人物、错数值、新增事件）一律 needs-review，needs-review 不算事实通过。** 正文按逗号切段，每段必须被该句所引条目的识别模式 span **完整覆盖**；事件动词黑名单机制退役（覆盖缺失自动拦截未枚举的新增主张）。语料 schema v3：行携带独立构造的 `world`（before 注册表）与 `rawDelta`，`plan` 为同一生成器对 Δ 的投影（同源保证）；`planOnlyClaims` 承载非 Δ 计划条目（positioned 现状、no_change 空点断言）。哈希覆盖 plan/world/rawDelta/text；组级一致性含 world/rawDelta/planOnlyClaims。**负例自检十二例**（2 fail＋10 review：越界/漏覆盖/方向反转/人物交换/数值错/任务否定/新增事件/无依据细节/否定移动/意图冒充/否定空点/完成人物不符）必须以预期判定类被抓，否则报告作废（exit 2）。

## 6. 权威验证（validate_plan_authority.py，v2 apply 来源核对）

格式合法之外证明**事实来源合法**（复核轮 2 要求）。三阶段：①行 `world` 构造 before `WorldState`（pydantic 含 fixed_registry 一致性）；②**before 层来源核对**——moved 起点==注册表 home、sanity 旧值==注册表理智（−999 类必炸）、任务 goal 必须是该人物注册任务且 owner 一致且仍 pending、positioned 现状==before 位置、no_change 行 Δ 必须为空；③**A 侧 kernel `apply_point`** 把 rawDelta 应用到 before（KernelViolation=非法），after 核对（位置/理智/任务 achieved）。脚本以 `--server-tree` 钉 A 工作树（默认 `.local/world-server-worktree`），报告含 server HEAD＋apply.py sha256，逐行绑定 plan+world+rawDelta 组合哈希。

## 7. 首批规模与顺序

首批 26 组种子行＋1 行改写样例（走通改写全链），**流程试验性质，不预设足以训练 77M**。语料清单先交付协调人抽验（§1–§6 全部可见），通过后才开微调；批量改写在工具链获认可后进行。微调开工时的 tokenizer legacy 决策见方案表 §6（训练/评估/基线统一设置并重新验证）。
