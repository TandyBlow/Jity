# C8 独立评测场景：来源清单与排除依据

| 字段 | 值 |
|---|---|
| 对应设计 | R16（新评测集与验收数据） |
| 当前档位 | **方案 + 工具自检通过**；没有模型实验结果，没有接线 |
| 工作树 | `exp/c-fresh-eval`（编号 `c8`），HEAD `64405346fe63` |
| 本目录 | `artifacts/world-components/fresh-eval/` |

本目录目前只做第一件事：**把「哪些材料已经用过」清点成可复算的清单，并把它们变成能拦人的排除规则**。新场景本身还没写，人工核验表还没建，冻结还没做——这三件排在后面，见 §7。

---

## 1. 一句话机制

脚本按一张**手写来源表**逐个打开文件，记录文件哈希，从里面抽出两类东西：**整句文本**（进入子串排除）和**名字**（人物／地点／任务／物品，进入词表）。抽出来的整句去重后写成 `sources/exclusion-corpus.jsonl`，名字去重后写成 `sources/vocab-used.json`。以后每写一个候选场景，就把它的正文、名字、事实形状拿去和这两份东西＋十条旧题的事实签名比一次，命中任何一项就判 `rejected`。

---

## 2. 谁给了谁什么

| 提供方 | 给了什么 | 脚本怎么用 | 结果存在哪 |
|---|---|---|---|
| `frontend/src/lib/world-engine/runtime/` 的四个样本文件 | 三臂对照 10 题（`nv-*`）、事实核验题（`hv-*`）、拆分题（`ns-*`）、B3 四件套 | 整句进排除串；`name/goal/locations/roster` 进词表；十题另按事实形状登记签名 | `sources/exclusion-corpus.jsonl`、`sources/exclusion-scope.json` |
| `artifacts/narration-eval*`、`artifacts/world-page`、`artifacts/rule-facts`、`artifacts/b3-short` | 真机跑出来的生成文本与复核稿 | 递归取中文串，整句进排除串 | 同上 |
| `experiments/world-components/n4_*`、`n2_selection`、`artifacts/world-components/*.jsonl` | 训练语料、留出集、改写稿、契约样例 | 同上；`world.characters/locations/items/names` 与渲染输入表头（`人物=`／`地点=`／`视角=`）额外进词表 | 同上 |
| 主树 `D:/others/Jity/artifacts/{cohesion-split,decode-compare,statement-*,world-provenance,benchmark,smoke}` | A/B 侧历史训练与调参归档（本工作树里没有这些文件） | 只读，同样抽整句与名字 | 同上 |
| `design/world-protocol/v1/fixtures`、`frontend/src/lib/world-engine/*.ts` | 学校世界夹具（`world_school`、`person_a`…、走廊／大厅／门厅／教室） | 只取词表，不整句排除（夹具本身不是叙事题） | `sources/vocab-used.json` |
| `backend/data/campaigns`、`scripted_story` | 旧 TRPG 战役与开场剧本（龙族人名） | 只取词表 | 同上 |
| `design/**/*.md`、`artifacts/*.md`、H2 报告 | 报告与签署记录 | 只登记哈希；实测无中文叙事内容 | `sources/inventory.json` |

脚本是 `tools/build_inventory.py`；它**不扫目录树猜文件**，只认表里写的 39 条来源，所以清单可复述、可复核。

---

## 3. 三条排除规则

| 规则 | 怎么算 | 拦什么 |
|---|---|---|
| **R1 子串（v2，事后版）** | 三种方向分别判：**完全相等**→命中；**候选被排除串包含**（候选是旧材料的一段）→命中；**排除串被候选包含**→只有该排除串 **≥8 个汉字**才算命中，更短的记作提示（`R1-short-phrase`）。排除串里带（注记）的，先剥注记再比一次 | 直接照抄、整段复用、把旧句嵌进新句。8 字下限的理由：夹具任务目标只有 5 字，若不设限，任何点名称沿已登记任务的候选都会被自己的素材判死（`c8d04` 实测）。**这条是看过候选之后才改的，原版 v1（任意方向包含即命中）保留在 `tools/screening.py`，两版判定差异见 `diagnostics/rule-diff.md`；v2 只能用于规则开发，不能用它证明候选自身独立** |
| **R2 词表** | 候选的人物、地点、任务、物品名逐个查 4,567 项词表并集（分桶只表示「在那个位置被观察到」，判定用并集） | 换名字不换内容时，名字本身先被拦；也防止新场景撞回「走廊／大厅／陈舟／顾北汀」这些旧词 |
| **R3 事实签名** | 只用**本点原始 Δ 产生的事实**拼签名 `(kind 计数 \| 涉及人物数 \| 时长折算秒数)`；未变化实体的现状读数（`at`／理智现值）只作引用，不进签名。签名表里一个签名对应**全部**旧题 ID（不覆盖），自检还要求每条旧题的命中列表包含它自己 | 保守拦截事实形状照旧的候选，包含只换人名地名的派生，也拦住换时间写法（2 分钟 ↔ 120 秒）的派生 |

十条旧题的签名（`sources/exclusion-scope.json` 里可复查）：

```
nv-move-1               moved*1                                   |1|120s
nv-task-pers-sanity-1   personality_changed*1+sanity_changed*1+task_achieved*1 |1|60s
nv-multi-1              moved*1                                   |1|60s   ← 只算 person_a 的移动
nv-task-only-1          task_achieved*1                           |1|30s
nv-refused-1            none                                      |0|1s
nv-empty-1              none                                      |0|300s
nv-cont-1               moved*1                                   |1|2s
nv-cont-2               none                                      |0|120s  ← 该点只有现状陈述，没有新增变化
nv-cont-3               none                                      |0|300s  ← 与 nv-empty-1 同形，口径无法区分
nv-multi-opposite-1     moved*2                                   |2|3s
```

改成「只算变化」之后，`nv-cont-3` 与 `nv-empty-1` 撞成同一个签名（两者都只有时间流逝），这是统一口径的已知代价，不是本批夹具的问题。碰撞表在 `selftest-report.md`，两条 ID 都保留，不做覆盖。

**但签名只说明形状**：`sources/three-arm-provenance.md` 核对后发现，十条旧题**没有一条**能绑定到已存的权威读取——样本的 `stateDigest` 是占位值（全 `f`），引用的 `hall`／`task_intro`／`task_shelf` 在夹具里不存在，登记的轨迹与归档里也没有可绑定身份的同一个点。所以十条的“变化签名依据”全部是 `undetermined`：签名相同只能写“按当前转换口径同形”，不能写“派生”。

### 走一遍：一个「只换名字」的候选会被怎么判

候选：`id=deriv-renamed-move-2min`，人物「寒枝」，地点「南堤／旧坊」，正文「寒枝从南堤来到旧坊。」，事实 `moved` 一条，时间 2 分钟。

1. **R1**：拿「寒枝从南堤来到旧坊」去比 13,341 条排除串。没有任何一条包含它、也没有它包含的旧串 → 不命中。
2. **R2**：「寒枝」「南堤」「旧坊」查 4,567 项词表，都不在 → 不命中。
3. **R3**：签名 `moved|1|2minute`，与 `nv-move-1` 全等 → **命中**，判 `rejected`，理由记录为「与 `nv-move-1` 同形」。

这个构造例只换了名字，属于旧题派生。一般情况下，R3 同形只是保守排除条件，不能单凭它证明来源相同；独立来源也可能同形而被拦。

再走一个应当放行的：`synthetic-fresh-ok`，三个人物、`moved + task_achieved + sanity_changed`、7 分钟。R1／R2／R3 全不命中 → 判 `candidate`（**只是没被这三条规则拦住，不等于验收通过**）。

---

## 4. 自检结果（可复跑）

命令：

```
python artifacts/world-components/fresh-eval/tools/build_inventory.py --check
python artifacts/world-components/fresh-eval/tools/exclusion_selftest.py
```

| 用例 | 期望 | 实测 | 命中规则 |
|---|---|---|---|
| 十条旧题（从 `narration-eval-samples.ts` 现场解析） | 全部 rejected | **10/10 rejected** | 十条各自被 R1 与 R3 独立命中 |
| 改名派生（nv-move-1 换名同形） | rejected | rejected | 仅 R3 |
| 改写派生（nv-empty-1 空点、5 分钟、新措辞） | rejected | rejected | 仅 R3 |
| 新场景（三条事实、7 分钟、新名字） | candidate | candidate | 无 |

`--check` 复核 571 个文件的哈希漂移：`drift=0`，登记来源全部找到；并重新抽取后比对保存的排除串、词表与规则。完整证据：`selftest-report.json`／`.md`、`verification.log`。

复核时修正了注记剥离前的错误匹配门槛，并加入“注记插入句中”的回归探针。自检现在要求恰好解析登记的十个不同题号、每题 R1/R3 均命中、两条构造派生仅 R3 命中，才可通过；输入中同时记录规则与检查脚本哈希。

输入哈希（详见报告）：
- 排除串 13,341 条，`sources/exclusion-corpus.jsonl` sha256 `396685dd…`（自检报告内为全值）
- 词表 4,567 项，`sources/vocab-used.json` sha256 见报告
- 三臂文件 `narration-eval-samples.ts` 哈希见报告

---

## 5. 失败与缺口（如实登记）

| 缺口 | 影响 | 现在的处理 |
|---|---|---|
| 历史去重协议点名的 `artifacts/world-chain/*.json` 在当前工作树和主树未找到 | 那份整链归档的文本无法进入排除串；其他检出和 Git 历史未核实 | `inventory.json` 的 `knownSourceGaps` 与 `exclusion-scope.json` 的 `knownLimits` 明确登记，覆盖为 `undetermined` |
| 只出现在散文里、没写进结构化字段的人名可能漏收 | R2 可能漏拦一个旧名字 | 标注为已知限制；新场景用全新词表 + 人工核验补 |
| R1 只做子串包含 | 完全改写的派生不会被 R1 抓到 | 由 R3 与人工核验补 |
| R3 只比事实形状，且时间单位不归一化 | 形状不同或等价时间换单位的语义派生不会被抓；同形独立来源也可能被拦 | 人工核验表逐条判；不将自动规则视为来源证明 |
| 主树 `artifacts/` 是另一个检出的文件 | 换机器／换检出后哈希可能漂移 | 路径记作 `main-tree:` 前缀；`--check` 会报漂移而不是静默通过 |
| 十题之外还有 `hv-*`／`ns-*`／`b3-*` 三族旧题 | 只把它们算进 R1 排除串，没做逐题签名 | 已在 `exclusion-scope.json` 的 `threeArmSiblings` 登记；要逐题签名需另开一轮 |
| 绑定已登记夹具的夹具必然复用夹具里的人名地名 | 词表闸对它们恒为命中 | `source-bound` 模式只把命中记为「已登记复用」并逐项列出；它只表示来源绑定状态，**不表示独立性通过** |
| 本批没有正式独立来源 | 六条只能作诊断，不能作正式评测题 | 已在 `diagnostics/report.md` 逐条写「独立性：undetermined」；正式评测题须另找可核实的独立来源（不必限定等 R01） |
| 旧题十条的变化事实没有权威读取 | 签名只说明形状；不能拿它证明派生，也不能说旧题历史可靠 | `sources/three-arm-provenance.md`：十条全部 `undetermined`，锚点是占位值、`hall`/`task_intro`/`task_shelf` 在夹具里不存在 |
| 判定器不查理智方向、不查“全部完成”类总结句 | 这两项预期无法程序判定 | 已交 `diagnostics/grader-handoff.md`（两个反例 + 修复后重跑旧题基线的要求） |
| 子任务 pending 不在 `c8d06` 的事实包里 | 不能要求模型写出、也不因省略扣分；“全部完成”只按“超出输入支持”判 | `diagnostics/diagnostics.json` 的 `notRequiredBecauseNotInInput` / `beyondInputSupport` / `humanEvidenceOnly` 三栏；核验表与核验包同步 |

---

## 6. 产物清单

```
artifacts/world-components/fresh-eval/
├── README.md                     本文
├── sources/
│   ├── inventory.json / .md      39 条来源、571 个文件的 path/sha256/bytes/rows/抽取计数
│   ├── exclusion-corpus.jsonl    13,341 条排除串（含来源编号与字段名）
│   ├── vocab-used.json / .md     4,567 项已用词表（6 个分桶 + 并集）
│   ├── exclusion-scope.json      规则文本、十题签名（含全部同形 ID）、已知限制
│   └── three-arm-provenance.json/.md  十条旧题的变化事实依据核对
├── selftest-report.json / .md    自检逐项结果与输入哈希
├── diagnostics/                  六条诊断夹具 + 缺口 + 核验表（0 条正式题，未冻结）
│   ├── diagnostics.json          六条定义（来源、参数声明、核对要求）
│   ├── report.json / .md         内核结果、三种状态、两版判定
│   ├── rule-diff.md              R1 v1 与 v2 的逐条判定差异
│   ├── fact-provenance.json/.md  原始 Δ / 变化事实 / 现状引用 对账
│   ├── gaps.json / .md           缺口：叙事投影 4 条 + 手写包与投影契约不一致 1 条
│   ├── review-table.md           人工核验表（标注者列留空）
│   ├── review-packets.md         六条逐条核验包（before／Δ／after、事实、检查）
│   ├── expectation-review.md     程序实际检查什么、不覆盖什么、交人工什么
│   └── grader-handoff.md         判分缺口交接（两个反例，给判定器维护方）
├── verification.log             来源复算、自检和回归检查的命令与输出
├── .gitattributes               保留本目录文件原始字节，避免哈希随换行转换漂移
└── tools/
    ├── build_inventory.py        来源表 + 抽取 + 清单生成（--check 校验漂移）
    ├── exclusion_selftest.py     规则自检；--candidates <json> 可对候选批量判
    ├── build_diagnostics.py      诊断夹具核验：内核 + 事实对账 + 两版规则 + 核验包
    ├── build_three_arm_provenance.py  旧题变化事实的权威来源核对
    └── test_exclusion_selftest.py 注记剥离和旧题漏解析的回归检查
```

---

## 7. 当前状态与下一步

**已交付**：六条诊断夹具、零条正式独立评测题、未冻结（见 `diagnostics/`）；核验材料已整理完毕，等待人工逐项判定。诊断不等于评测：`source-bound` 只表示来源绑定状态，`accepted by apply_point` 只表示增量被内核接受，`not-committed` 表示本批全是假设点、没有 round/group/settle/points 记录，独立性一律 `undetermined`。

**下一步**：
1. 按 `diagnostics/review-table.md` 做人工核验（标注者不得参与调参），逐项填「通过／不通过／无法判断」；`无法判断` 不算通过。
2. 正式评测题另找可核实的独立来源：要能追到来源文件、点位身份和使用历史，且能证明未参与训练或调参。不限定只能等 R01。
3. 缺口（`diagnostics/gaps.md`）交对应模块；能力补齐后必须重新核验来源独立性，不能自动晋升为正式题。
4. `c8d04` 的数值方向、`c8d06` 的父/子任务同时保留：目前只能人工判定；判分缺口已交维护方，修复后要重跑受影响旧题基线并记录判分器版本变化。
5. 未核项一律记 `待核验`；本轮不追加候选、不运行模型。

来源历史无法核实、缺失归档影响无法排除时，保持 `undetermined`。本目录的合成自检输入只是规则探针，不进入正式评测集。本轮提交只归档来源审计、规则机制与六条诊断夹具，不表示新评测集已冻结或独立性已获证明。
