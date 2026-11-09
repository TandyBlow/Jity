# D05 / D06 新短语义实验接口与状态交接

2026-11-09，基于 `d80a03160c9d3f8a3386ad61349556dc399d9979`。实现为 `experiments/world-components-logic/short_settlement.py`。本文件描述新实验路径；既有模型、数据、报告和实现保留为历史证据，不是本路径的语义回退。代码已经可调用；本文件所列证据是工程反例测试；实际任务训练与模型批次结论以冻结实验报告为准，不能据此宣称语义、真实 C 叙事、完整浏览器链或 500 ms 通过。

## 输入与完成状态

世界输入采用实际 `frontend/src/lib/world-engine/types.ts` 的 `WorldState`：包含完整 `initial`、当前 locations/items/characters、全部任务、全部 active/inactive 描述记录、时间。模型每次都收到完整 `context`，D06 还收到当前阶段之前的 A/B 预览状态、全部候选事实和此前阶段候选。不裁剪场外人物，不把初始描述与当前变化合并后丢失记录身份。

`Completion(result, value)` 表示完成且有明确判断/文字/引用；`Completion(empty)` 只表示明确完成而无输出；`Completion(incomplete, reason)` 表示未完成。模型的空包、缺字段、缺扫描对象、截断、超时、资源用尽和取消均不构成合法否定判断。D05 成员协议要求每人非空结果文本，因而只生成 `end`、无事实时记录接口不能表达该输出，不把它补成“没有变化”。D06 每阶段返回显式决定和覆盖记录，阶段零变化仍有这些判断证据；最后的六个空 `changes` 是已完成扫描的候选形态，不是错误默认值。

公共 `ModelSession` 保存全部输入、原输出、身份和失败；本模块没有按人独立结算、脚本结果或随机头回退。模型返回的 pass 保留为模型自查证据，不替代独立语义评审或人工签字。

## D05

`settlement_context(action_context, chain_completion, group_id=..., binding=...)` 将真实 D02→D03→D04 输出绑定到 D05：校验 FrozenAction 摘要、原文和全部已渲染片段完全一致，保留原始实际骰点字典，程序注入 groupId 和时间点版本。这个实验闭组标记不是服务正式闭组回执；正式接线仍由 A/B 确认。

`settle_joint(session, context, max_facts=32)` 接收 `context.world`、`binding` 和 `group`。group 必须具备 closed、groupId、完整 memberIds/members、每个成员的 confirmedTargets、所有实际 judgments、alreadyActedIds。新路径要求完整实际 A/B receipt：result、固定 target=11、reaction-d20-v1、groupId、triggerKey、eligibilityBaselineDigest、eligible/admitted 等字段；与 D03/D04 共用规则校验，并要求同一 groupId。若另带 value/threshold/passed 诊断字段必须与实际值一致；旧简化字典不能单独作为真实判定。passed 是可复核的骰点比较，绝不作为行动成功标签。拒绝准入与已行动目标判定同样纳入精确关系覆盖。

| 组件 | 模型输入（均另含完整组语境） | 模型 value | 程序职责 / 依赖 |
| --- | --- | --- | --- |
| D05.1 | 全部冻结行动、实际判定、资格、结算前世界 | checkedActionIds；relations[{sourceId,targetId,kind}]，kind 为 obstructs/supports/contests/depends | 核对完整行动覆盖、引用，不猜因果 |
| D05.2 | 上述输入、关系、全部原片段 attempts | judgments[{attemptId,label}]；label=achieved/partial/not_achieved/incomplete | 每项尝试均须覆盖；任一 incomplete 使整组未完成，不生成结果事实；完整首次判断留日志 |
| D05.3 | 全部输入、联合判断、已生成事实 | `{kind:fact,text:一条短事实}` 或 `{kind:end}` | 程序分配局部 fact ID，保留原文；到资源限但未 end 为暂停未完成 |
| D05.4 | 完整组、联合判断、全部候选事实 | verdict；checkedActionIds/checkedFactIds/checkedRollIds | 模型核因果、争夺、遗漏副作用与覆盖；程序核引用和覆盖 |
| D05.5 | 完整组与上述材料 | facts[{factId,memberIds}]；checkedMemberIds | 全事实和全成员对账，一个事实可属于多人 |
| D05.6 | 通过检查的事实与成员引用 | 无模型调用 | 按原事实顺序用换行组合现有 `Record<memberId,string>`；不增加连接词、动作或结论 |

`members[].fragments` 若存在，必须以换行组合出逐字相同的冻结行动；片段 ID 跨人物唯一。没有片段来源的正式旧行动保留为一个整体尝试，不伪造片段。候选事实只在本次结算工作包内，不写世界、不新增长期行动史或知识库。关系矛盾或语义核查失败整体返回 incomplete，不覆盖冻结行动和骰点；重试策略由已冻结的公共实验计划控制。

## D06

`run_updates(session, context, settlement, preview, allocate_id, max_new_tasks=32, progress_sink=None)` 按 U1→U6 执行。`settlement` 必须绑定当前完整 context 摘要和相同 point/version；D05 成功候选包另带整个 facts/joint/associations/results 的 contentHash，D06 入口先复核，任何包内容变化均不沿用原审核。D06 返回包也有独立 contentHash，供后续工作保存/交接核对。摘要用于检测材料变动，来源真实性仍由冻结日志和 A/B 读取适配器证明。纯时间调用使用 `time_scan=True`、`timeAdvance`、`timeFact`，不导入行动组结果。

| 组件 | 模型输入（均保留全上下文、事实和当前预览） | 模型 value | 程序职责 |
| --- | --- | --- | --- |
| U1.1 | 全部人物、物品 | decisions[{entityId,change:bool}] | 精确全对象覆盖 |
| U1.2 | 全部需移动对象、决定 | positions[{entityId,position}] | 同时校验最终容器/相对位置图、槽位归属、同房间关系、循环；不逐个覆盖应用 |
| U2.1 | 全实体、全部有效外貌记录 | checkedEntityIds/checkedRecordIds；operations[{entityId,op,recordIds}] | op=keep/remove/add/replace；允许同实体多操作；旧记录只能引用该实体有效变化记录，初始不可解除/改写；重叠解除或保留/解除冲突拒绝 |
| U2.2 | 一项 add/replace 及当前候选 | 一条局部外貌/身体状态字符串 | 原文包装成 text；remove 无文本，程序分配变化 ID |
| U3.1 | 全人物、全部当前任务 | checkedCharacterIds；decisions[{taskId,label}] | label=pending/achieved；逐任务核全覆盖，不由子任务推导父任务；已达成任务不可撤销 |
| U4.1 | 所有已有任务作为可选父任务 | checkedParentTaskIds/checkedCharacterIds；needs[{parentTaskId,count}] | 全父任务显式 count，非负整数；总数超过资源限制暂停，不只做前几项 |
| U4.2 | 父任务、owner、所需总数、当前序号及已提出目标 | 一条具体目标字符串 | 每项均调用并保存；ID由程序分配，status一律 pending，不在本次 U3 冒充达成 |
| U5.1 | 有新任务达成时的全部人物/有效个性记录 | 与 U2.1 同形 | 包括场外人物；支持多操作和纯解除；无任务达成时由固定阶段规则不调用 |
| U5.2 | 一项个性 add/replace | 一条行动偏好变化字符串 | 不改初始个性，保留原文；模型提出的操作若有效偏好记录没有实际变化，拒绝而非暗中填理智 |
| U6.1 | 个性实际变化者、新的有效个性和全世界 | 0–100 整数 | 仅相应人物调用；拒绝 bool、浮点、字符串及越界，不取整、不夹断 |
| D06.P.review | 当前阶段候选和完整上下文 | verdict；checkedEntityIds | 模型检查语义，程序核该阶段候选覆盖；审核通过才能请求预览 |
| D06.P.mapping | 全事实、全部六阶段候选引用 | verdict；mappings[{factId,kind,targets}] | 见下文；完整后才生成现有 SettlementGroup 候选 |

U4 使用现有 Task.parentTaskId 能表达的任意同 owner 已有任务，模型判断目标是否有助于该父任务；并不强制只有根任务可以有子任务。模型选择的父任务必须存在于该阶段预览，不允许悬空引用。新任务保持 pending，避免依赖旧“同批新建并达成”语义。

`progress_sink` 在阶段候选形成、预览完成与失败时收到独立工作进度；这不是正式保存/提交回执。每次 preview 输入携带原绑定、baseWorldHash、候选摘要、完整已完成阶段列表和当前 stage。返回必须逐项匹配，且初始状态及实体集合不变。没有预览接口、预览错误或迟到版本均为 incomplete，不能直接沿用旧世界。恢复使用公共 `ModelSession.checkpoint()/restore()` 对身份、策略、输入及原完成结果进行核验，按完全相同输入重放成功语义调用，未完成调用不缓存；A/B 的 allocate_id 必须按相同 allocationKey 幂等。恢复后仍重新向 A 复验每阶段预览，不重新决定已冻结后果；跨时间点/模型身份材料拒绝。工程测试验证 U4 预览中断后续跑仅新调 U5/U6、六次预览仍全部执行，以及恢复后的陈旧预览和错误模型/版本身份被拒绝。

## 事实到状态映射

所有 D05 factId 与显式时间事实 ID 必须全局无重复，不能通过 ID 碰撞减少覆盖。每个事实恰好一条 disposition 判断，拒绝重复或冲突行：

- state：后果写入状态；targets 是 `{stage,entityId,operationId}` 引用，引用必须存在。
- unchanged：明确保持不变；targets 必须空。
- transient：仅本次结算经过；targets 必须空。
- gap：需要保留而现有协议无法表达，返回明确 interface_gap，停止接受该候选。

同一事实可映射多阶段、多对象，但同一行不得重复引用相同候选；多个事实可以共同支持一个候选。每个状态候选也必须至少有一个语义来源映射。程序只保证引用存在和双向覆盖，绝不把“有编号”当作语义正确。模型 mapping verdict 必须为 pass，独立语义评审仍单列。映射作为实验 sidecar，不塞入 C 的正式事实或长期世界状态。

`incomplete` 是显式语义标签时，D05.2 聚合仍保留所有逐尝试首次判断；真实 provider 将整体转换为 `Completion.incomplete('semantic_incomplete:D05.2:<按冻结顺序的attemptIds>')`，编排也防御自定义 provider 直接返回该原始标签包。缺覆盖、timeout 或非法输出保持独立错误，不能计为语义弃答命中。r3 的旧三类头没有此能力；新增类别需要独立真实训练和验证，见 [独立验收审查](short-acceptance-audit.md)。

## 现有协议适配与真实接口缺口

最终 `updates` 保持 position/appearance/tasks/subtasks/personality/sanity 六阶段，字段分别为 positionSet、appearanceChanges、tasksAchieved、subtasksAdded、personalityChanges、sanitySet。`assemble_wire` 将完整六阶段包装为现有 `SettlementGroup`，提供 taskCoverageIds 和条件性的全人物 personalityCoverageIds；不会数组后写覆盖。不修改 A/B/C 源码和公开协议。

**D 基线与当前 A 版本必须区分。** D 的 `d80a031` 基线继承的 `backend/app/schemas/world/v2/work.py::SettlementGroup.stages` 对任何候选要求 personalities/sanities 完全配对，因而其本地 parser 拒绝 U5 部分候选。初次系统 Python 缺 Pydantic；随后用已有 `/opt/anaconda3/bin/python3.12`、Pydantic 2.13.4 实际执行了该完整 parser 反例和最终六阶段候选接受测试，共 32 项全部通过。这个旧 schema 的拒绝不能归因为当前远端 A 缺少部分预览能力。

已核对并固定当前远端 `world-server@fc60a603c7e0b57805fffea0458192bcfebf6ffc`：A 已将完整阶段的配对及条件校验移到 `services/world/units.py::validate_unit` 的采纳边界，`SettlementGroup` 允许部分预览。因此具体兼容提案是对齐 A 已完成的 wire/预览/采纳边界修复，B 在每次阶段调用时绑定该版本、时间点和当前候选前缀；无需另造一套公开阶段协议。不得填旧理智以掩饰尚未执行的 U6。正式 A/B 服务接线仍未在本实验中修改或验证。

`short_preview.py` 提供 `offline_preview(base_world, binding, point=registered_point, group_id=..., actor_ids=...)`。它从本地既有 Git 对象读取固定 A 原始源码，校验文件 SHA-256，在独立模块空间加载，不改 A 源文件；共享 contracts/canonical 必须与固定 A 字节相同。实际调用原 `preview_point`，经过原 `point_entity_deltas` 共同单位合并及 `apply_point` 位置/记录/任务处理，完整 U6 再执行原 `validate_unit`。这不是手写状态替身，也不是正式 A 服务或提交；不访问 DB、不获取租约、不生成 C 文本。调用者必须提前冻结完整 point/time 元数据及真实组成员，不能由预览器猜身份或时间。

每次预览从同一原始前态重算整个完成阶段前缀，因此时间只推进一次、记录只应用一次；候选先前前缀不可被重写。新记录/任务 ID 碰撞拒绝，正式 schema/合并/apply 错误、来源不符、资源预算和未提供元数据均成为 incomplete。A 对可选字段进行标准化，适配器先校验完整 initial 模型未变，再保留调用者 initial 原始字段表示；不补写初始语义。`authority_identity()` 输出固定来源及 13 个文件 SHA-256，必须随实验冻结快照；events 记录每次真实预览耗时、请求/响应字节数、A 投影摘要和完整单元校验状态。

`test_short_preview.py` 的 7 项独立测试已通过：真实 D06 编排驱动原 A 的六阶段、U5 未生成理智时允许预览而完整单元拒绝、原合并入口拒绝多单元争夺同一物品的冲突位置、原完整组规则拒绝重复演员、同时移动环、纯时间仅一次推进、旧来源/重写候选/ID 碰撞拒绝。测试模型仍是显式工程替身，不能用这些结果声称模型语义或生产整链通过。

纯时间 `SettlementGroup(groupId=None)` 当前不允许移动与外貌；模型若在纯时间提出这两类变化，本模块记录 interface_gap，不擅自编造行动组绕过限制。纯时间仍完整扫描任务，必要时新增任务、扫描全人物个性、更新真正变化者理智。现有协议若需支持时间导致的外貌变化，应独立提出兼容修订。

一个结算单元六阶段完成仅产生候选和工作进度。点级 seal/commit、关联段、C 生成/ready、D07 时序不在这里提前发生。C 只能消费 A 正式提交的同一时间点前态、原始变化、后态和合法元数据；本模块不调用 C，也不向其发送候选事实或预览。

## 验证范围

`test_short_settlement.py` 使用新建合成工程夹具，覆盖闭组完整实际判定（包括拒绝及已行动者）、多片段逐项判断、失败事实副作用、争夺审核拒绝、全成员事实关联、显式 end/预算中止、同时移动循环与相对位置、纯解除/多操作、全任务/父子独立、多个 pending 子任务、场外个性及理智、非法数值、纯时间条件联动、陈旧预览、接口缺口和双向事实映射。还实际调用 D02→D03→D04 编排接口，把其原始输出传入 D05 和完整六阶段；模型与预览均是明确工程替身，不是语义成绩。

真实任务头训练及上游驱动批次由冻结实验入口单独报告，本文件中的工程测试不为其代签。离线固定 A 预览已可用；正式 A/B 服务接线、C 模型叙事、生产保存恢复及整浏览器墙钟仍未通过。工程测试秒数不是完整请求延迟，离线模型批次也不能扣除必要 C ready 或服务成本来声称完整 500 毫秒目标。
