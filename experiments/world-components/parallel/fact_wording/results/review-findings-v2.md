# 第二轮评审问题的核对与处理（v1）

> 对象：`9702183` 的远端静态复审（未跑推理、未跑完整测试）。
> 三条意见**全部成立**，已修；本轮仍不重判、不运行验收。

## 1. 断点恢复仍会覆盖原始元数据（成立）

**机制**：恢复分支虽然跳过了“启动时写 `run.json`”，但收尾仍用本进程新建的
`run_meta` 写回 `run.json`。`startedAt`、`loadSeconds`、`runnerSha256` 都是本次
进程的值，原运行的身份会被替换。

**处理**（`scripts/run_diagnostic.py`）：
- 恢复时读取原 `run.json`，以它为底稿；
- 保留 `startedAt`、`loadSeconds`、`runnerSha256`、`env` 等原始字段；
- 另记 `resumeCount`、`resumedAt`、`runnerSha256AtResume`、`loadSecondsAtResume`；
- 收尾只追加 `finishedAt`；恢复的运行记 `finalProcessWallSeconds`，不改写 `wallSeconds`；
- 原 `env.json` 也不再覆盖：恢复进程写 `env-resume-<n>.json`。

**边界**：这只是代码修正，没有用恢复路径实际跑过模型；没有新的恢复运行证据。

## 2. 验收 po01 / po02 来源仍不准（成立）

`world.json` 只记录最终位置，没有动作记录：
- `item_rope.afterPosition = loc_ferry_pier`：绳子在栈桥；“沈砚把绳子拖回栈桥”是补的。
- `item_fishbasket.afterPosition = loc_market_stalls`：筐在摊棚；“阿棠把筐放下”是推的。

**处理**（v2 登记已重生成）：
- `po01`：`authored=true`，`provenance=authored`，写明“afterPosition 只给终点位置，拖绳动作是人工补的”；
- `po02`：`provenance=derived`，写明“afterPosition 只给摊位，放筐的人与动作是推导的”；
- 其余字段、重叠结果不变（17 条仍全部独立，`problems` 为空）。

## 3. 盲判包仍展示模型看不到的数值（成立）

r1 的理智单元在包里显示 `12→9`，但模型输入只有“胸口发闷”这类描述。

**处理**：
- 生成器对 `sanity_changed` 去掉 `from`/`to`，改为“状态变化（数值未提供给模型）”；
- 每批加固定 `judgingNotes`：只依据 fact 与 scene；新增未给出的动作/状态/人物/物品/地点算失败；复述算失败；输入未给出的数值不作为“数值正确”的依据，出现具体数值按新增处理；无法判断记 U，U 不算通过；
- 重新生成两份 `blind-v2/`（各 17 批、170 条、`adjacentSameFact=0`、`numbersHidden=true`），**未判**。

## 状态

- `9702183` 保留，修复作为新提交追加；不重写历史。
- 仍未做：v1 判词重判、验收 v2 运行、真实已提交状态的 N3→N4。
