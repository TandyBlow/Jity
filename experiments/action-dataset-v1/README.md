# 动作分类数据集实验（lane 13）

本目录是独立数据实验，不是产品代码，也不改动作协议。目标是给 MiniRBT-H256 分类头准备**首批 300 条训练候选**：每条给一个角色此刻自己知道的信息（X），判断他下一步最可能立刻做的一件事（Y，0/1/2 步）。

审阅状态先写在最前面：**这些行在 01 100% 审查通过前不是可用的训练数据**。本目录不声称任何人工通过、不生成测试答案、不看 15 个留出目标。

当前交付状态：01 已审完 220 行（`01-audit-v1.jsonl` + `01-audit-v1b.jsonl` + `01-audit-corrections-v1.json`）：**132 行 pass、88 行 fail**。fail 集中在 82 条“把任务全做完再判 skip”的构造行、3 条把角色放进锁着的器材笼的不可达位置、2 对同 X 不同标签。来源哈希全部对得上。按 01 的要求，本目录**先只修一批 24 行的多样小批**（`cases/batch1/` → `rows/batch1-*.jsonl`），等 01 审这一批、确认配方改对了，再扩到 300。旧的 220 行配方已停用，原因见 §5。

## 1. 冻结输入

| 输入 | 来源 | 校验 |
|---|---|---|
| 唯一标签判据 | `results/action-dataset-20261111/criterion.txt` | sha256 `56092d0c…1d21c`（与 `criterion-freeze.json` 一致） |
| 115 细谓词 / 12 粗组 / skip | `results/action-dataset-20261111/labels-v1.json` | 脚本按文件重算数量，不符即报错 |
| 允许的 TRAIN 目标（48） | `results/action-dataset-20261111/01-train-goals-for-13.json` | split sha256 `b4680a9e…a8eb`；行内角色不得出现列表外的待办目标 |
| 世界快照 S₀ | `data/worlds/dragon-raja-free-day.world.json` | 文件 sha256 记录在每条构造行的 base 里 |
| 真实运行状态 | `results/product/evidence/*.json` 的 `snapshotAfterTurn.transport.pointStates` | 证据文件 sha256 + JSON 指针 + 本实验对快照的 sha256 |
| 训练侧文本序列化器 | `worktrees/04-settlement/experiments/action-next-step/serialize.py` | 只读导入，每行记录它的 `SERIALIZER_VERSION` 与文件 sha256 |

`labels-v1.json` 与 `criterion.txt` 只按原文件读取并记哈希，本目录不复制、不改写它们。13 没有收到、也不会索取 VALIDATION（10）/TEST（15）的目标名；`excludedActors` 只出现在池统计里，因为那几个角色的目标全在允许列表外。

## 2. 目录

```
experiments/action-dataset-v1/
├── tools/
│   ├── state_view.py     快照只读视图（房间、位置、槽位、随身物品）
│   ├── project_x.py      九槽 X 投影（键名与 04 loader 一致，不另立序列化器）
│   ├── loader.py         只读导入 04 的 serialize.py，渲染/候选指针都走那份代码
│   ├── provenance.py     证据扫描、sha256、快照去重、正文泄漏检查
│   ├── schema.py         冻结行格式、115 谓词、Y 校验、数据集统计
│   ├── transforms.py     构造场景用的确定性状态变换 + 事后不变量检查
│   └── cases.py          构造用例装配（状态 + 刚才事件 + 校验记录）
├── scripts/
│   ├── build_episodes.py 从真实证据抽取快照（含去重与泄漏检查）
│   ├── build_pool.py     生成无标签候选池 + 长度/覆盖统计
│   ├── build_rows.py     用例目录 → 行文件 + 每行来源记录
│   └── check_dataset.py  独立重算：行校验、来源哈希、重放 X、loader 渲染、目标排除
├── snapshots/            抽取出的真实快照（每个不同状态一个文件）+ index.json
├── pool/                 无标签候选池（candidates.jsonl / summary.json）
├── cases/
│   ├── batch1/           第一批 24 行（01 已审：20 pass / 4 fail，已按意见修）
│   ├── batch2/           第二批 32 行（A 10 / B 16 / skip 6）
│   └── *.jsonl           早期用例（skip 配方被 01 判 fail 的那部分见 §5）
├── rows/                 生成的行文件、每行来源记录、统计/复核报告
└── tests/                41 个快速单元测试
```

## 3. X：九槽，一槽一行

固定顺序：`角色 / 目标 / 地点 / 在场 / 物品 / 刚才 / 精神 / 个性 / 候选`。

X 的**键名就是 04 loader 冻结的形状**（`character / goals / place / present / items / recent / sanity / personality / candidates`）。本目录不维护第二份文本序列化器：训练输入由 04 的 `serialize.py` 渲染，`tools/loader.py` 只读导入它并记录版本与 sha256；`check_dataset.py` 用同一份代码复核每条 step 的 `object` 能否解析成候选下标。

投影只回答一个问题：**这个角色站在这里能知道什么**。因此：

- `在场`、`物品` 只取角色所在的最内层地点（沿容器链解析，和产品 `prompt.ts:roomOf` 一致）；别处的人物和物品不出现，**没有“不在场角色”清单**，不带其他房间的说明文字；
- `刚才` 只收**角色能看到/听到的场景句子**，两类：位置变化（`X 到了<目的地>`）和外观变化（`X：<可见描述>`）。引擎状态（任务完成、理智数值、个性改写）不是看见的东西，只留在来源记录里，**不进 X**；叙事正文永远不进 X；`刚才` 里出现“移动到/任务/已完成/位置变为”等引擎措辞会被投影直接拒绝；
- `目标` 是该角色自己的全部待办任务，写成 `任务id：目标文字`（id 留在文本里，审核能核对，模型也能对上）；
- `精神` 是该角色的理智值，`个性` 是初始个性 + 生效中的个性变化；
- `候选` 是可作 `object` 的 id 全集：同房间其他角色 + 同房间物品 + 自己随身物品。

`character` 里另带 `appearance`（初始外貌 + 生效外观变化）和 `holds`（随身物品）。04 现在的渲染函数只印 `id=name`，会忽略这两个键——已作为渲染请求写给 04（`results/action-dataset-20261111/13-to-04-x-shape.md`），本目录不自行改 04 的代码，也不另写一份。

## 4. 行格式与校验

行字段严格为用户给的十个：`rowId / source / worldId / characterId / x / y / yGroup / yRationale / labelSource / skipReason`。`rowId` 全局不重号：批次用 `b1-####`，整批用 `train13-####`（`build_rows.py --row-prefix/--row-start`），旧编号不复用。`y` 只有 `steps`，0/1/2 步，每步 `{action, object}`。

校验规则（`tools/schema.py`，`check_dataset.py` 会独立重跑）：

- `action` 必须是 115 个细谓词之一；粗组只出现在 `yGroup`（由第一步谓词派生，skip 行固定 `skip`），不能手写；
- `object` 必须落在该行 `x.candidates` 里的 id，或 `null`；不能是角色自己；不能凭空补 id；
- `steps` 最多两步；
- skip（`steps: []`）必须写 `skipReason`，且理由不能是“不知道/不明/随便”这类；非 skip 行 `skipReason` 必须为 `null`；
- `yRationale` 必须引用该行里真实存在的任务 id、候选 id/名字，或 `刚才` 事件，不能是空泛模板；
- 同一数据集内 `rowId` 唯一、X 不得重复；
- 角色没有任何待办目标的行直接拒绝：判据是“以他的目标为主要依据”，没有目标的角色不构成这条判据的证据，也不能再走“把任务全做完再判 skip”的旧配方。

每条构造行另有一个 `rowClass`（写在 `rows/provenance-*.jsonl`，不是行字段、不是新规则）：

- `A`：条件齐备，直接做目标里那一步；
- `B`：条件不齐（人不在、物不在、被锁、被拦），Y 是先创造条件的一步；
- `skip`：这个间隙里没有他该做的动作。

## 5. 来源：真实快照 vs 构造

`source` 只有两种值，记录在每行的来源文件里：

- `evidence-snapshot`：X 直接来自真实产品运行的已提交状态。行的 `source`、来源记录的 `source`、来源记录的 `derivation`（`committed-snapshot` / `committed-snapshot+transforms`）必须互相对得上。记录证据文件相对路径、证据文件 sha256、JSON 指针、pointId/roundId/trigger、产品自己的 `stateDigest`、该次运行的 `status`、本实验对快照的 sha256。同一状态在多份运行里出现时，主指针优先选 `status` 不是 `FAILED` 的那一份，其余位置连同各自状态列进 `copies`；
- `constructed`：X 来自 `data/worlds/dragon-raja-free-day.world.json`（或某个真实快照）+ 显式变换序列。记录 base 文件 sha256、按序的变换记录（op/实体/容器/文字/若有的可见句子）、随机种子、变换合法性检查结果和状态不变量检查结果。

三条硬规则：

1. 不是实际回放就不写 replay；本目录没有 replay 来源。
2. 构造时预设的动作不能进入 X：`build_rows.py` 只根据 base + `transforms` 造状态，标签字段完全不参与状态生成；X 里出现的每一条 `刚才` 都对应一条被记录的变换。
3. 构造状态只用“这个角色能到的地方、能搬到的东西”：不把他传送到进不去的房间，也不靠把他所有任务标成已完成来制造 skip。

`build_episodes.py` 还会做正文泄漏检查：把该次运行所有叙事正文的 8 字窗口与 X 中每个字符串比较，只有“叙事里有、快照里没有”的窗口才算泄漏（叙事本来就由状态生成，普通重合不是泄漏）。当前 9 个快照、14 个角色投影结果：0 条泄漏。

### 5.1 220 行审计的处置

- 82 条 skip（全在 `cases/02-skip.jsonl`）**废弃**：它们把角色所有任务标成已完成再判 skip，按 01 规则 14 不构成“他会做什么”的证据。`cases/02-skip.jsonl` 保留为历史，不再进行文件。
- 122 条直接/条件行（`cases/03-direct.jsonl` 73 条 + `cases/04-condition.jsonl` 49 条）pass，保留为后续 300 行的主体；配方确认后按新 X 重建。
- 5 条 fail 已修：3 条笼内不可达位置（`d-043`、`d-061`、`e-012`）删除——笼门锁着、笼内物品不在同一房间的物品表里，移出笼外就看不到担架/安全绳，没有解锁变换可写，所以没有诚实的改法；2 对同 X 不同标签各删一条（`d-013`、`d-035`）。剩下的 133 条（11 真实 + 122 构造）全部有 01 的 pass 结论。

## 6. 已登记的协议缺口（不自行解释）

这些是 X/Y 定义本身还没定的地方。本目录按“能无歧义构造的行先做、受影响的行登记不做”处理：

1. **候选只有裸 id 时，编码器不知道名字对应哪个 id**。04 的序列化器在两处同时给出 `id=名字`：各槽条目和 `候选` 槽。这是当前实际处理，不是已批准的新格式；若用户决定候选只给裸 id，行文件需要重新生成。
2. **跨地点移动目的地是否允许进入候选**。未决。因此本目录的 `object` 从不指向另一个房间的地点；`移动` 行用 `object: null`，目的地不进入 Y，也不进入评分。batch1 里有 2 条这样的行（`b1-r-002`、`b1-b-004`），等 01 判这个约定。
3. **单一 goal 槽位怎样选当前相关目标**。`目标` 槽列该角色全部待办任务（带 id），不替角色挑一个。
4. **被省略的对话内容和物品接收人怎样表达**。Y 只有 `action`+`object`，说不出“说了什么”；`object` 记为接收人（在场角色 id）或物品。所有言语类行都受这条限制。
5. **编码器位置长度（现在有实测数字）**。batch1 的 24 行用 04 的序列化器渲染后：字符长度 min 453 / p50 692 / p90 1202 / max 1458。04 的 `measure_tokens.py --stub-tokenizer` 对同一批给出 p50 694、p100 1460，而 04 的登记规则是 `maxLen = ceil(p100/32)*32` 且 **cap 384**，即当前 24/24 都要截断才放得进。更糟的是 04 的渲染顺序把 `候选` 放在最后，截断最先切掉的正是 `object` 要指向的候选表。三个可选方向（都不由 13 定）：(a) 抬高 maxLen 并按槽位预算截断，`候选`/`刚才` 最后切；(b) 压 X（候选只印 id、物品不印位置、目标只留相关 1–2 条），实测 p50 可降到 445、max 831，仍超 384；(c) 改结构输入（各槽分开编码 + mask），不再是单串文本。
6. **时间没有独立槽位**。冻结的九槽里没有时间，但有些目标按时间点成立（曼施坦因的停赛通知在 15:45）。当前把 `；时间=2009-10-17T15:20:00` 追加在 `地点` 槽文字后面，让模型能看到当前时刻；这是本轮的实际处理，不是已批准的新格式。若用户决定加时间槽或把时间放进 `刚才`，行文件重新生成。
7. **有 3 个 TRAIN 目标在 S₀ 已经是 achieved**（`task_chu_line`、`task_lin_sent`、`task_lu_rules`），变换里只有“标成完成”没有反向操作，所以它们永远不会出现在 X 里、也无法被任何行引用。48 个目标的覆盖上限是 45，不是 48。
8. **skip 与“先创造条件”的边界**。本目录只把“这个间隙里没有他该做的动作”写成 skip，并且必须写清阻塞事实：等人、被拦、按规则不能动（守位/中立观察）、时间点未到、伤得动不了。目标需要去别处或需要别人时，不写 skip，写 `移动`/`请求`/`提问`。batch1 的 5 条 skip 是这条边界的探针，等 01 判；如果 01 认为其中某条其实是 `等待`/`观察`，本目录按判决改，不自己扩权。

## 7. 复现

```powershell
# 0) 依赖：仅 Python 3.12 标准库；测试用 pytest；loader 渲染需要 04 的工作树存在
# 1) 抽取真实快照（只读共享证据目录）
python -X utf8 experiments/action-dataset-v1/scripts/build_episodes.py
# 2) 生成无标签候选池（套用 01 的 TRAIN 目标列表）
python -X utf8 experiments/action-dataset-v1/scripts/build_pool.py `
  --allowed-goals ../../results/action-dataset-20261111/01-train-goals-for-13.json
# 3) 用例目录 → 行文件（有任一校验失败就不写成功标志）
python -X utf8 experiments/action-dataset-v1/scripts/build_rows.py `
  --catalog experiments/action-dataset-v1/cases/batch1 `
  --allowed-goals ../../results/action-dataset-20261111/01-train-goals-for-13.json `
  --out experiments/action-dataset-v1/rows/batch1-candidates.jsonl `
  --provenance-out experiments/action-dataset-v1/rows/batch1-provenance.jsonl `
  --report-out experiments/action-dataset-v1/rows/batch1-report.json
# 4) 独立复核行文件（重算哈希、重放构造、loader 渲染、重查目标排除、重跑统计）
python -X utf8 experiments/action-dataset-v1/scripts/check_dataset.py `
  --rows experiments/action-dataset-v1/rows/batch1-candidates.jsonl `
  --provenance experiments/action-dataset-v1/rows/batch1-provenance.jsonl `
  --allowed-goals ../../results/action-dataset-20261111/01-train-goals-for-13.json
# 5) 单元测试
python -X utf8 -m pytest experiments/action-dataset-v1/tests -q
```

## 8. 未做 / 未验证

- 没有跑任何模型、GPU、HPC；没有训练。
- 没有真实 tokenizer 的 token 长度；只有 04 字符代理档（`--stub-tokenizer`）的数字。
- 只有一个世界（`world_dragon_raja_free_day`），跨世界泛化**未测**，不能声称。
- 真实快照只覆盖同一局的前 3 分钟（15:20–15:23），所以“真实来源”的行在状态族上高度集中，这一点在 `pool/summary.json` 里按去重数报告，不当作多样性证据。
- 现有 189 行（133 条 01 pass 的重建集 + batch1 24 + batch2 32）：A 104 / B 75 / skip 10，skip 比例 5.3%；覆盖 44/48 个目标有 A，31/48 有 B。3 个目标因 S₀ 已 achieved 无法覆盖（见 §6 第 7 条），`task_lin_leave` 有 B 无 A（伤者走不了）。
- skip 来源窄：9 个角色里只有 4 类能只靠 X 推出“此刻没有该做的动作”（伤者、时间未到+不离岗、守窗口、守旗台）。189 行里只有 10 条 skip，离“约 30%”很远；要么承认“守位/等人时的观察”算 skip，要么接受更低比例，这需要 01 判，不硬凑。
- batch2 的 X 长度：p50 619 字符、max 1055，仍超过 04 的 384 cap。
- 行是候选数据；审查（01 100%、03 随机 10% 盲审）与最终接受都不由本线完成。

## 9. 交接记录

- 起点提交：`73d00f97`（本线 dispatch 的 baseCommit）。
- 本目录只被本线修改；不改产品文件、不动其他工作树、不跑 GPU/HPC、不新增付费资源。
- 中间交接文件：`design/parallel-handoff/13-action-dataset.md`，共享结果：`results/action-dataset-20261111/13/completion.json`、`results/action-dataset-20261111/13-to-01-repair-batch1.md`、`results/action-dataset-20261111/13-to-04-x-shape.md`。
