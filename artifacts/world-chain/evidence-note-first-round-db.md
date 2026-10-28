# 存证：首轮 harness 运行库的取证与销毁经过（2026-10-29）

本文记录二轮验收复核中「首轮 chain 段是否拼接记录」争议的取证结论、
被销毁主证据的存证内容，以及由此产生的处置决定。

## 一、时间戳映射（可在残存文件上复算）

harness 每次运行创建私有目录，目录名 = 起跑时刻 `Date.now()`（毫秒）；
artifact 的 `recordedAt` = 目录创建后下一行 `new Date().toISOString()`
（毫秒级 ISO 串）。两者应相差 0–2ms。

- `artifacts/world-chain/first-round.json` 的 `recordedAt` =
  **`2026-10-28T15:44:33.994Z` = epoch 1793202273994**，`phase: "both"`，
  `status: PASS_BOTH`。
- 对应运行目录 **1793202273993**（15:44:33.993，差 1ms）——该目录即首轮
  `--phase both` 单次运行的私有库目录。
- 复核对照的目录 1793202227188 = 15:43:47.188，比 artifact 来源早 47 秒，
  是同一次成功运行之前的又一轮失败尝试；`recordedAt` 的毫秒位（.994）
  与之不符。

## 二、被销毁目录的查询结果（引自 2026-10-29 验收会话的工具输出）

B 侧在 2026-10-29 复核轮中对该目录的 SQLite 查询输出（原文存于会话记录）：

- `worlds` 表恰两行：`world_1`（version 7，active_point_id point_45——
  动作场景终态）与 `world_48`（version 1，active_point_id point_54——
  链场景）。
- `world_rolls` 恰两行：`roll_57` person_a→person_c，result 14，target 11，
  admitted=1；`roll_59` person_c→person_a，result 2，target 11，admitted=0。

与 `first-round.json` chain 段逐项吻合：worldId=world_48、points=
root_50/point_54、firstRoll roll_57=14 admitted、rollsRolled roll_59=2。
即首轮 chain 段是**该单次运行的真实记录**，不是多 run 拼接。

旁证（均可独立复算）：`attempts` 字段为 for 循环退出自增值（修复前一轮
3 个世界时打印 attempts=4），首轮 artifact 的 attempts=2 反推单次尝试；
setup 415ms ≈ 单世界（v2/v3 实测约 450–520ms/世界）；v2/v3 各次运行的
链场景世界均从 world_48 起（动作场景消耗相同 id 序列）。

## 三、残存目录时间线（复核时点，解释拼接理论的来源）

| 目录尾号 | 本地时刻 | 内容 | 角色 |
| --- | --- | --- | --- |
| …2159356 | 23:42:39 | world_1+world_11；roll_20=11 准入、roll_22=14 **拒绝** | 失败前驱，写入被后续覆盖 |
| …2227188 | 23:43:47 | world_1；roll_10=11 准入、roll_12=2 拒绝 | chain-only 失败前驱 |
| …2273993 | 23:44:33 | world_1+world_48；roll_57=14 准入、roll_59=2 拒绝 | **artifact 来源，已被误删** |
| …3764613–4820944 | 00:09–00:27 | ZCode 复跑批次（含首次 17 准入单世界与最终 v2） | 修复轮运行 |

残存集合中不存在 roll_57=14 属实——恰因来源目录已被删除。

## 四、事故与处置

B 侧在 2026-10-29 查询该库后执行了 `rm -rf` 清理（当轮工作记录原话：
「kept other run dirs」），销毁了主证据，直接导致复核只能基于残存目录
重拼时间线并得出拼接结论。这是取证流程违规：**取证后不得删除原始数据；
先存证、后清理（或不清理）**。

处置决定（与复核指令一致）：

1. 首轮 chain 段数字（14/2、单世界）**不再作证据引用**，README 叙事以
   `first-round-v3.json`（完整插桩、库仍在、可复验）为 chain 的 canonical
   记录；
2. `first-round.json` 保留原样存档，本文为其 chain 段真实性的存证与溯源；
3. 其结论（attempts off-by-one 语义、单世界事实）仅作历史说明，不再进入
   验收叙事。
