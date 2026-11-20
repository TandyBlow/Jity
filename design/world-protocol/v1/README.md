# 世界引擎阶段 0：冻结契约 v1

依据：[开发方案 v0.3.1](../../browser-world-state-workflow.md)。本目录用于协议、夹具和可执行存储约束的评审，不是已接入游戏的引擎。

## 定稿决定

- 所有结论都含 `closedBy` 与 `cancelReason`。模型 continue/handback 使用 `model/null`；手动取消只能为 `handback/cancel/非空原因`。取消是结束，不是预算暂停。
- 当前头认领统一为 `head`，包括根点。根点 `advanceId=null`，`fenceEpoch` 必须是正整数。历史认领为 `history`，epoch 必须为空；不根据确认时的头位置更改签发模式。
- 当前版本使用 Python 定义及验证契约，浏览器消费导出的 Draft 2020-12 JSON Schema；无 TS apply，也没有新增运行路由。

## 产物及生成方式

| 文件 | 作用 |
|---|---|
| `world-protocol.schema.json` | 通过 `#/$defs/类型名` 引用初始世界、精确状态摘要投影、增量、检查点、提交/preview/结论请求、认领等类型 |
| `storage-contract.sql` | 独立内存 SQLite 中执行的九张表约束规格；包含根点 NULL/唯一约束、叙事 claim 模式、取消来源及根点叙事门槛 |
| `canonical-vectors.json` | 独立手写的规范 JSON、UTF-8 十六进制和 SHA-256 固定向量，以及非法输入 |
| `fixtures/school.initial.json` | 封存学校世界：7 个地点、10 件物品、6 个人物；世界规模只是夹具，不是产品限制 |
| `fixtures/school.initial-state.json` | 规范化 `WorldState` 的开局状态；包含不可变 initial 与当前实体状态，不含叙事/调度元数据 |
| `fixtures/associated-points.json` | A/B → C/D → E/F 的分段、检查点、骰点及必需执行顺序 |
| `fixtures/advance-chain.json` | 已确认 continue、后继 automatic、模型 handback 和手动 cancel 的可区分记录 |
| `fixtures/time-only.json` | 独立及链中段的纯时间点、任务/个性/理智联动、明确的新时间及期望状态 |
| `fixtures/task-normalization.json` | 同点新增父子任务，子任务后续达成的阶段输入和唯一最终编码 |
| `fixtures/description-changes.json` | 历史变化替代、纯解除、同点临时变化折叠的输入/期望值 |
| `fixtures/frozen-action.json` | 反应引入成员后遭遇新威胁，文本与既有成员保持不变的反例 |
| `fixtures/claims.json` | 根点认领、续约/交接、根点门槛和空 linked 叙事成本的协议输入/期望值 |
| `fixtures/requests.json` | 两种完整提交、preview 和结论请求，包含阶段覆盖信息及全部绑定 |

源定义在 `backend/app/schemas/world/contracts.py`。数值使用有限安全整数，接受精确的 `1.0`，拒绝布尔值充当整数；原始 JSON 通过 `parse_json` 用 Decimal 保留小数精度并拒绝重复键、非法 Unicode 和非有限值。不要先用普通浮点解析不可信数值后再校验精度。

从仓库根目录执行：

```powershell
python -X utf8 backend/scripts/export_world_protocol.py
python -X utf8 -m pytest backend/tests/test_world_protocol_contract.py backend/tests/test_world_protocol_storage_contract.py -q
```

导出脚本不读取模型、数据库、网络或当前时间。世界与期望结果是作者给定的固定数据；规范向量的 expectedCanonical 独立手写，哈希仅由这些字节计算，不调用待测编码器生成预期答案。更新后须审查产物差异；测试只读取固定向量，不自动刷新预期值。

## 精确状态投影与规范化

`WorldState` 是状态摘要唯一输入形状：engineVersion/schemaVersion/worldId/protagonistId/time/initial/locations/items/characters。initial 保存完整 S₀；当前地点保存描述变化，物品还保存直接位置，人物还保存个性变化、理智和任务映射。已提交描述变化含 sourcePointId/sourceSequence/active，按时间追加；初始描述不改写。

`canonical_bytes` 只编码已经按 schema 规范化的 JSON，不猜测游戏语义。控制字符使用六字符 `\u00xx`，不转义中文、emoji、斜杠或 U+2028/U+2029，不做 Unicode 归一化。schema 展开位置的空字段、排序集合、对新增任务做稳定拓扑排序，并省略空增量操作。完整状态与增量不能使用同一个“全局删 null”策略，纯解除的 text=null 必须保留。

新增任务的拓扑层次指本次新增数组内的依赖深度，挂在既有父任务上的新任务为第 0 层；父先子后，同层按 ASCII ID 排序。新增又达成只在 subtasksAdded 带 achieved；模型阶段候选里的新增任务则只能为 pending，不能绕过后续任务扫描。

最终 apply、时间算术、无操作相等判断和临时变化的 pointProjection 折叠属于阶段 1。本目录提供其已知输入与期望结果，当前测试不声称已证明一个尚未实现的 apply 等价性。

## 校验边界

| 层级 | 当前可检查 | 后续需要的上下文 |
|---|---|---|
| JSON Schema | 字段类型/范围、额外字段、结论来源、根点空字段、认领 mode/epoch、主要阶段字段组合 | 不支持跨数组 ID 比较和历史查库 |
| Python 契约 | 初始世界固定 ID、联合位置环、引用及任务树；检查点游标/成员；增量任务交叉/排序；请求自身绑定、全人物扫描覆盖 | 不把请求自身一致当作与数据库当前头一致 |
| SQL 契约 | 根点/后继唯一、跨世界外键、持久化枚举、取消原因、claim epoch 空值组合、根点门槛 | 不实现实际租约计时、所有权交接或提交事务 |
| 阶段 1–3 | 使用本目录夹具对照实现结果 | 同字段历史 supersedes 生效检查、预分配 ID 所有权、阶段重算、头/版本/租约有效性、原子提交与恢复 |

JSON Schema 里无法表达的历史引用/成员比较由 Python 和未来事务服务负责，不能把 schema 成功作为全部契约成功。原始动作文本只在实验夹具中用于说明规则，不是运行存档的长期行动历史。

## 十一部分设计的夹具落点

| 原始部分 | 固定输入/验收入口 |
|---|---|
| 世界状态 | school.initial；联合环、未知容器、错误口袋、任务父节点反例 |
| 状态与时间线 | 根点及 associated-points，storage-contract 的前驱/世界约束 |
| 自然语言更新 | description-changes 与 canonical 的纯解除向量 |
| 行动顺序 | associated-points 的 order/cursor/visited/acted；重排输入取当前理智 |
| 被迫行动与共同结算 | pendingGroup、roll_cd、闭组与成员检查 |
| 瞬时时间点 | P1/P2/P3 的 kind/boundary/duration，空 linked 续段成本 |
| 六步状态更新 | requests 的六阶段候选、task-normalization 和 time-only |
| 连续推进 | advance-chain、结论请求及跨 round 输入消费检查 |
| 叙事 | 根点门槛、head/history claim、纯时间任务达成的允许叙事 |
| 回放与重生 | 初始/纯时间期望状态、规范字节及哈希；实际 apply 在阶段 1 验收 |
| 小模型工作流 | 固定候选和全人物扫描覆盖；本阶段无模型推理 |

阶段 0 锁定的是契约、输入及预期结果。阶段 1 验证状态内核，阶段 2 验证实际控制器，阶段 3 验证 SQL 事务、租约、认领续期和恢复；这些运行验收不能由本阶段的 schema/约束测试代替。
