# N4.0 输入对 C6 的缺口（核对记录）

只读核对：`design/world-engine-reports/components/n4-input-packing.md`（`n4-input-pack-v0.1`）、`n4-narrative-dev.md`、`interaction-sample-v1.md`。
结论先说：N4.0 的输入能装“事实＋场景＋人物”，缺“玩家原话”“上一段正文”，事实类型里也没有“说话/失败/交接”。C6 的段落生成不能直接拿现有 N4.0 输入开跑。

## 1. N4.0 现在装了什么

`pack_narrative_input(case, plan, world, …)` 的输出包含：

- `facts`：`moved`（人物移动）、`outcome`（结果文本）、`sanity_changed`（方向）、`appearance_changed`、`personality_changed`、`no_change`、`time`（只写“时间经过”）；
- `sceneState` / `characterContext` / `perspective`；
- 分组 `G1｜f0 f1 …`、组后时间。

模型目标：**只写正文**；明确不写任务标题、数值面板、具体时长、字段名。面板本来就不在模型输出里。

## 2. 缺什么

| C6 需要 | N4.0 现状 | 后果 |
|---|---|---|
| 玩家输入原文（“我问学生B……”） | 没有该字段；真实记录里 `world_advances.input_text` 曾为 NULL | 模型不知道玩家问过什么、授权了什么，容易复述状态或编台词 |
| 上一段正文 | 没有；输入里没有任何叙事文本 | 第二点起无法承接，只能重新起头 |
| 说话事件（谁对谁说了什么） | 事实类型里没有 speech/dialogue | 对话只能退化成“结果”一句话，人物声音无法被约束 |
| 失败/受阻事件 | 没有 `attempt_failed` 一类；`outcome` 只给结果文本 | “把手不动”“没找到人”这类可观察失败无处安放 |
| 物品位置变化 | **已有途径**：`moved` 不限于人物，N1 也能从物品 `positionSet` 提取移动事实；信封从柜中到主角身上可以走 `moved` | 位置变化本身不缺；自动提取时需核对物品 `positionSet` 的 before/after |
| “管理员亲手交付”这类交付事件 | 事实里只有位置结果，没有“谁交给谁、怎么交”的可信来源；`outcome` 是任务结果文本，不覆盖交付动作 | 应先查现有事件与结果记录能否提供交付者/方式，**暂不新增物品交接事实类型** |
| `resultText` | 文档已知缺口 2：来源未接线，当前读 fixture | `outcome` 可能缺失，fail-closed 直接拒绝 |

不需要补的：面板。面板应由程序从已提交状态生成，N4 只交正文；两者分别验收（见 `acceptance-boundaries.md` §2）。

## 3. 对路线的影响

1. 在补齐上述字段前，不把 C6 的段落任务接到 N4.0 上跑，也不据此扩语料。
2. 补的顺序：先扩事实类型与输入字段（含 fail-closed 条件），再用校园三点样例做字节级输入/输出核对，最后才谈 N4 训练方案。
3. 已有 12＋88 例材料先做来源与授权范围盘点，能复用的复用；在输入契约未定前不新写训练语料。
4. 本文件只是 C6 的核对记录，不改 N4.0 共享文档；等 N4.0 盘点时把“模型只写正文、面板程序生成”写成正式约束。

## 4. 画夹场景新增的两项

- 第三人称限知下的可见性：N4 按地点链放事实，没有视线/子区域可见标记；见 `n4-integration-notes.md` §1。
- 任务受阻原因：`Task.status` 只有 pending/achieved，没有受阻原因字段；见 `n4-integration-notes.md` §2。
