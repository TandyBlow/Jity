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
| **R1 子串** | 候选正文（≥4 个汉字）与 13,341 条排除串做**双向包含**比较：候选含排除串、或排除串含候选，都算命中。排除串里带（注记）的，先剥注记再比一次 | 直接照抄、保留连续子串的片段复用；不保证拦住改标点 |
| **R2 词表** | 候选的人物、地点、任务、物品名逐个查 4,567 项词表并集（分桶只表示「在那个位置被观察到」，判定用并集） | 换名字不换内容时，名字本身先被拦；也防止新场景撞回「走廊／大厅／陈舟／顾北汀」这些旧词 |
| **R3 事实签名** | 把候选的事实拼成 `(按 kind 排序并保留重复 \| 涉及人物数 \| 时间量+单位)`，和十条旧题签名全等即命中 | 保守拦截事实形状照旧的候选，包含只换人名地名的派生 |

十条旧题的签名（`sources/exclusion-scope.json` 里可复查）：

```
nv-move-1               moved                                  |1|2minute
nv-task-pers-sanity-1   personality+sanity+task                |1|1minute
nv-multi-1              at+moved                               |2|1minute
nv-task-only-1          task_achieved                          |1|30second
nv-refused-1            （无事实）                              |0|1second
nv-empty-1              （无事实）                              |0|5minute
nv-cont-1               moved                                  |1|2second
nv-cont-2               at                                     |1|2minute
nv-cont-3               at                                     |1|5minute
nv-multi-opposite-1     moved+moved                            |2|3second
```

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

---

## 6. 产物清单

```
artifacts/world-components/fresh-eval/
├── README.md                     本文
├── sources/
│   ├── inventory.json / .md      39 条来源、571 个文件的 path/sha256/bytes/rows/抽取计数
│   ├── exclusion-corpus.jsonl    13,341 条排除串（含来源编号与字段名）
│   ├── vocab-used.json / .md     4,567 项已用词表（6 个分桶 + 并集）
│   └── exclusion-scope.json      规则文本、十题签名、已知限制
├── selftest-report.json / .md    自检逐项结果与输入哈希
├── verification.log             来源复算、自检和回归检查的命令与输出
├── .gitattributes               保留本目录文件原始字节，避免哈希随换行转换漂移
└── tools/
    ├── build_inventory.py        来源表 + 抽取 + 清单生成（--check 校验漂移）
    ├── exclusion_selftest.py     规则自检；--candidates <json> 可对候选批量判
    └── test_exclusion_selftest.py 注记剥离和旧题漏解析的回归检查
```

---

## 7. 下一步

1. **筛场景**（TASK 第 2 步）：先从已提交状态或已登记夹具中查找未参与训练/调参的独立来源，登记 `entityId / fieldPath / pointId` 及使用历史，再按多人物、多地点、可见性、任务、关系、玩家关注制作覆盖表。每条候选过 `exclusion_selftest.py --candidates` 并保存命中理由。不能为了绕过词表或签名而换名、改时长、拼装新事实；找不到合格来源就登记缺口，不凭空补造世界记录。
2. **人工核验表**（第 3 步）：首批 ≤10 条，固定编号，登记来源、输入、标注者、核对项；标注者不能是参与调参的人。
3. **一次性冻结**（第 4 步）：输入清单 + SHA-256 + 去重证据一起固化，之后只读，并从训练材料里物理隔离。

来源历史无法核实、缺失归档影响无法排除时，保持 `undetermined`。本目录的合成自检输入只是规则探针，不进入正式候选或评测集。第一步提交只归档来源审计与规则机制，不表示新评测集已冻结或独立性已获证明。
