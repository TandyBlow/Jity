# 动作分类数据集实验（lane 13）

本目录是独立数据实验，不是产品代码，也不改动作协议。目标是给 MiniRBT-H256 分类头准备**首批 300 条训练候选**：每条给一个角色此刻自己知道的信息（X），判断他下一步最可能立刻做的一件事（Y，0/1/2 步）。

审阅状态先写在最前面：**这些行在 01 100% 审查通过前不是可用的训练数据**。本目录不声称任何人工通过、不生成测试答案、不看 15 个留出目标。

## 1. 冻结输入

| 输入 | 来源 | 校验 |
|---|---|---|
| 唯一标签判据 | `results/action-dataset-20261111/criterion.txt` | sha256 `56092d0c…1d21c`（与 `criterion-freeze.json` 一致） |
| 115 细谓词 / 12 粗组 / skip | `results/action-dataset-20261111/labels-v1.json` | 脚本按文件重算数量，不符即报错 |
| 允许的 TRAIN 目标（48） | `results/action-dataset-20261111/01-train-goals-for-13.json` | split sha256 `b4680a9e…a8eb`；行内角色不得出现列表外的待办目标 |
| 世界快照 S₀ | `data/worlds/dragon-raja-free-day.world.json` | 文件 sha256 记录在每条构造行的 base 里 |
| 真实运行状态 | `results/product/evidence/*.json` 的 `snapshotAfterTurn.transport.pointStates` | 证据文件 sha256 + JSON 指针 + 本实验对快照的 sha256 |

`labels-v1.json` 与 `criterion.txt` 只按原文件读取并记哈希，本目录不复制、不改写它们。13 没有收到、也不会索取 VALIDATION（10）/TEST（15）的目标名；`excludedActors` 只出现在池统计里，因为那几个角色的目标全在允许列表外。

## 2. 目录

```
experiments/action-dataset-v1/
├── tools/
│   ├── state_view.py     快照只读视图（房间、位置、槽位、随身物品）
│   ├── project_x.py      九槽 X 投影 + 两个确定性序列化档位
│   ├── provenance.py     证据扫描、sha256、快照去重、正文泄漏检查
│   ├── schema.py         冻结行格式、115 谓词、Y 校验、数据集统计
│   ├── transforms.py     构造场景用的确定性状态变换 + 事后不变量检查
│   └── cases.py          构造用例装配（状态 + 刚才事件 + 校验记录）
├── scripts/
│   ├── build_episodes.py 从真实证据抽取快照（含去重与泄漏检查）
│   ├── build_pool.py     生成无标签候选池 + 长度/覆盖统计
│   ├── build_rows.py     用例目录 → 行文件 + 每行来源记录
│   └── check_dataset.py  独立重算：行校验、来源哈希、目标排除、统计
├── snapshots/            抽取出的真实快照（每个不同状态一个文件）+ index.json
├── pool/                 无标签候选池（candidates.jsonl / summary.json）
├── cases/                人工编写的用例目录（标签只在这里出现）
├── rows/                 生成的行文件、每行来源记录、统计报告
└── tests/                42 个快速单元测试
```

## 3. X：九槽，一槽一行

固定顺序：`角色 / 目标 / 地点 / 在场 / 物品 / 刚才 / 精神 / 个性 / 候选`。

投影只回答一个问题：**这个角色站在这里能知道什么**。因此：

- `在场`、`物品` 只取角色所在的最内层地点（沿容器链解析，和产品 `prompt.ts:roomOf` 一致）；别处的人物和物品不出现，**没有“不在场角色”清单**，不带其他房间的说明文字；
- `刚才` 只收有结构字段的房间内事件（位置/外观/个性/任务/理智）；每条事件都写明它来自哪一次已提交变化，别的房间的事件直接丢弃；叙事正文永远不进 X；
- `目标` 是该角色自己的待办任务（含上级 id 与层级深度）；已完成任务不列；
- `精神` 是该角色的理智值，`个性` 是初始个性 + 生效中的个性变化；
- `候选` 是可作 `object` 的 id 全集：同房间其他角色 + 同房间物品 + 自己随身物品。随身物品出现在候选里（否则“装备/使用自己手里的东西”无法表达），但不出现在 `物品` 列表里。

序列化器 `action-x-v2` 是训练与推理共用的唯一文本形式：纯函数、稳定排序、不静默截断。两个档位：

- `full`：不截断（行里保存的结构化 X 本身都不截断）；
- `tight`：只截断描述性文字（外貌 40 / 目标 40 / 环境 40 / 在场外貌 20 / 物品外观 0 / 事件 40 / 个性 40），被截断的字段计数写进该行来源记录；实体和候选列表永不裁剪，标签指向的 id 一定还出现在文本里。

## 4. 行格式与校验

行字段严格为用户给的十个：`rowId / source / worldId / characterId / x / y / yGroup / yRationale / labelSource / skipReason`。`y` 只有 `steps`，0/1/2 步，每步 `{action, object}`。

校验规则（`tools/schema.py`，`check_dataset.py` 会独立重跑）：

- `action` 必须是 115 个细谓词之一；粗组只出现在 `yGroup`（由第一步谓词派生，skip 行固定 `skip`），不能手写；
- `object` 必须落在该行 `x.candidates` 里的 id，或 `null`；不能是角色自己；不能凭空补 id；
- `steps` 最多两步；
- skip（`steps: []`）必须写 `skipReason`，且理由不能是“不知道/不明/随便”这类；非 skip 行 `skipReason` 必须为 `null`；
- `yRationale` 必须引用该行里真实存在的任务 id、候选 id/名字，或 `刚才` 事件，不能是空泛模板；
- 同一数据集内 `rowId` 唯一、序列化后的 X 不得重复。

## 5. 来源：真实快照 vs 构造

`source` 只有两种值，记录在每行的 `rows/provenance-v1.jsonl` 里：

- `evidence-snapshot`：X 直接来自真实产品运行的已提交状态。记录证据文件相对路径、证据文件 sha256、JSON 指针、pointId/roundId/trigger、产品自己的 `stateDigest`、本实验对快照的 sha256；
- `constructed`：X 来自 `data/worlds/dragon-raja-free-day.world.json`（或某个真实快照）+ 显式变换序列。记录 base 文件 sha256、按序的变换记录（op/实体/容器/文字）、随机种子、变换合法性检查结果和状态不变量检查结果。

两条硬规则：

1. 不是实际回放就不写 replay；本目录没有 replay 来源。
2. 构造时预设的动作不能进入 X：`build_rows.py` 只根据 base + `transforms` 造状态，标签字段完全不参与状态生成；X 里出现的每一条 `刚才` 都对应一条被记录的变换。

`build_episodes.py` 还会做正文泄漏检查：把该次运行所有叙事正文的 8 字窗口与 X 中每个字符串比较，只有“叙事里有、快照里没有”的窗口才算泄漏（叙事本来就由状态生成，普通重合不是泄漏）。当前 9 个快照、14 个角色投影结果：0 条泄漏。

## 6. 已登记的协议缺口（不自行解释）

这些是 X/Y 定义本身还没定的地方。本目录按“能无歧义构造的行先做、受影响的行登记不做”处理：

1. **候选只有裸 id 时，编码器不知道名字对应哪个 id**。当前在两处同时给出名字：各槽条目写 `名称（id=…）`，`候选` 槽也写 `名称（id=…，类型）`。这是本轮的实际处理，不是已批准的新格式；若用户决定候选只给裸 id，行文件需要重新生成。
2. **跨地点移动目的地是否允许进入候选**。未决。因此本目录的 `object` 从不指向另一个房间的地点；`移动` 行用 `object: null`，目的地不进入 Y，也不进入评分。
3. **单一 goal 槽位怎样选当前相关目标**。`目标` 槽列该角色全部待办任务（带上级），不替角色挑一个。
4. **被省略的对话内容和物品接收人怎样表达**。Y 只有 `action`+`object`，说不出“说了什么”；`object` 记为接收人（在场角色 id）或物品。所有言语类行都受这条限制。
5. **编码器位置长度**。实测 X 字符长度（中文近似上界）：`full` 777–1489，p50 984；`tight` 712–1372，p50 925。MiniRBT-H256 是 BERT 编码器，常见位置上限 512，两个档位都放不下完整体 X；真实 token 数要由 04 用实际 tokenizer 量。缩小 X 会改变冻结的 X 定义，需要用户决定，13 不自行改。
6. **skip 与“先创造条件”的边界**。本目录只用两种可辩护的 skip：该角色已无待办目标且现场没有需要回应的变化；或最后一项待办刚在 `刚才` 里完成、其余待办都不由他推动。不把“目标需要去别处/需要别人”写成 skip——那是 `移动`/`请求`/`询问` 行。

## 7. 复现

```powershell
# 0) 依赖：仅 Python 3.12 标准库；测试用 pytest
# 1) 抽取真实快照（只读共享证据目录）
python -X utf8 experiments/action-dataset-v1/scripts/build_episodes.py
# 2) 生成无标签候选池（套用 01 的 TRAIN 目标列表）
python -X utf8 experiments/action-dataset-v1/scripts/build_pool.py `
  --allowed-goals ../../results/action-dataset-20261111/01-train-goals-for-13.json
# 3) 用例目录 → 行文件（有任一校验失败就不写成功标志）
python -X utf8 experiments/action-dataset-v1/scripts/build_rows.py `
  --catalog experiments/action-dataset-v1/cases/catalog-v1.jsonl `
  --allowed-goals ../../results/action-dataset-20261111/01-train-goals-for-13.json
# 4) 独立复核行文件（重算哈希、重查目标排除、重跑统计）
python -X utf8 experiments/action-dataset-v1/scripts/check_dataset.py `
  --rows experiments/action-dataset-v1/rows/train-candidates-v1.jsonl `
  --provenance experiments/action-dataset-v1/rows/provenance-v1.jsonl `
  --allowed-goals ../../results/action-dataset-20261111/01-train-goals-for-13.json
# 5) 单元测试
python -X utf8 -m pytest experiments/action-dataset-v1/tests -q
```

## 8. 未做 / 未验证

- 没有跑任何模型、GPU、HPC；没有训练。
- 没有真实 tokenizer 的 token 长度，只有字符长度。
- 只有一个世界（`world_dragon_raja_free_day`），跨世界泛化**未测**，不能声称。
- 真实快照只覆盖同一局的前 3 分钟（15:20–15:23），所以“真实来源”的行在状态族上高度集中，这一点在 `pool/summary.json` 里按去重数报告，不当作多样性证据。
- 本目录的行是候选数据；审查（01 100%、03 随机 10% 盲审）与最终接受都不由本线完成。

## 9. 交接记录

- 起点提交：`73d00f97`（本线 dispatch 的 baseCommit）。
- 本目录只被本线修改；不改产品文件、不动其他工作树、不跑 GPU/HPC、不新增付费资源。
- 中间交接文件：`design/parallel-handoff/13-action-dataset.md`，共享结果：`results/action-dataset-20261111/13/completion.json`。
