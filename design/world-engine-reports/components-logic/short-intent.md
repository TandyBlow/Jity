# D02–D04 短意图实验接口与兼容证据

日期：2026-11-09。基线 `d80a03160c9d3f8a3386ad61349556dc399d9979`。本次活动实现为 `short_intent.py`，不调用旧计划表达器，不设置旧模型或旧方案回退。历史文件与原始证据不改写。

这是可调用的候选编排实现，不是模型能力验收。所有语义职责必须由接入的真实模型完成；缺模型时返回 `incomplete(model_unavailable)`。测试中的 `Script`、`FixtureSession`、骰点与预览回调明确为工程夹具，不用于训练、语义计分或性能声明。

## 组件接口

所有调用经共享 `ModelSession.call(component, payload)`，完整输入、实际模型/适配层/分词/精度身份、首次输出及失败/重试保存在共享日志。结果统一为 `Completion(result|empty|incomplete)`；组件模型的合法否定必须显式输出，缺输出不能当否定。

| 组件 | 完整输入上的增量 | 模型短输出 `value` | 程序职责与下游 |
|---|---|---|---|
| D02.1 | 世界、行动者、主角、玩家原文与 pending/consumed/expired、确认前缀、机会身份 | `act` / `skip` / `incomplete` | 校验输入；显式 skip 才返回 empty；act 进入 D02.2；显式语义 incomplete 保留未完成，绝不当 skip |
| D02.2 | 同一完整上下文、此前所有片段及绑定、可选反应约束 | `{kind:fragment,text}` / `{kind:end}` | 程序分片段 ID、保序；非空 act 必须明确 end；资源上限返回未完成，保留日志中的全部提议 |
| D02.3 | 上述内容、当前片段 ID 和原文 | `{verdict,references:[{role,entityId,start,end}]}` | 检查实体存在、文字跨度、主语身份出现、接收人类型；role 为 subject/object/tool/recipient/destination；文字与角色的语义一致由模型判断 |
| D02.4 | 完整原需求、全部片段及引用 | verdict、完整 fragmentIds、dependencies/conditions/requirements 的判断标签、定位到片段的问题码 | 步骤依赖、条件与原始要求覆盖由模型核对；程序检查全片段覆盖，无自动补句 |
| D02.5 | 同上，包括 D04 约束 | verdict、fragmentIds、actor/tools/objects/qualifiers/attempt 标签及定位问题 | 核对角色、工具对象方向、轻重限定与尝试语气；模型拒绝即未完成，不按关键字伪装语义判断 |
| D02.6 | 已通过两项审查的完整片段 | 无模型调用 | 仅以换行保序组合；一次行动机会、一次 `act(text)`；保存不可变 `FrozenAction` |
| D03.1 | 全部候选人物、冻结行动逐字原文、完整世界、组内冻结行动、已行动集及实际判定 | 每名人物 `{candidateId,relation:target|none}` | 全人物覆盖；不根据距离、已行动过滤；不接受当前源尚未实际产生的骰点 |
| D03.2 | 完整 D03 输入、关系判断、候选目标集 | verdict、完整 candidateIds、targetIds | 比对完整候选与目标集合；完成空集为 empty；未完成禁止骰点 |
| D04.1 | 已准入人物、完整相关威胁原文、所有实际判定及组内冻结行动、完整世界 | threatSourceIds、一个短约束句 | 核验威胁与冻结原文/实际回执对应；已确认行动直接复用；新增反应进入 D02.2–.6，不走普通 skip |

D02.4 的 `checks` 键固定为 `dependencies, conditions, requirements`；D02.5 固定为 `actor, tools, objects, qualifiers, attempt`。`issues` 为 `{fragmentId,code}` 列表。通过记录必须所有检查为 `pass`、无问题、片段覆盖完整。此类完整标签只能证明审查模型给出了判断，不能证明判断正确，仍需独立语义验证与真实训练。

D02.1 的显式语义未完成出口在 r3 结束后补齐，返回 `semantic_incomplete:D02.1`；调用错误、缺头或超时仍保持各自原因。对应新增标签的真实补训和评估须使用新冻结身份，不能沿用 r3 的两类头宣称已具备该判断能力。

自然名称为默认内部表示。`representation=references` 是可显式选择的实验表示，不代表旧引用版已经通过替换门。标记语法为 `[[entityId]]`，跨度必须精确覆盖标记；程序只按已验证跨度一次性替换为登记名称，替换结果不递归解释。跨度为 Python Unicode 码点；未来浏览器内部引用适配必须显式转换 UTF-16 索引。公开行动协议只有最终 `text`，不暴露该实验索引。

完整复杂意图可以作为一个片段，程序不强制拆分或裁为第一步。不设置“短句成功即完整行动成功”的规则。多个短片段必须连同原始需求通过覆盖检查后，才组合成同一个机会的行动。

## 可调用接口与状态

- `produce_intent(session, context, opportunity_id, max_fragments=8, representation='natural')` 返回 `Completion`。result.value 是不可变 `FrozenAction`；empty 是已完成 skip；incomplete 没有可提交行动。
- `action_wire(completion)` 仅适配完成结果为现有 `{kind:'act',text}` 或 `{kind:'skip'}`；未完成抛错。
- `analyze_targets(...)` 返回完整目标 ID 列表或完成空集；`targets_wire(...)` 适配为既有 `{targets:[{targetId}]}`。
- `produce_reaction(...)` 校验实际准入；已有确认行动返回同一冻结内容，不重新采样；新反应复用短意图和角色/步骤审查。
- `run_action_chain(..., roll_targets=callback)` 执行 D02→D03→程序骰点→D04→D03 递归扩组。仅所有源完成目标核对/所有实际判定处理后返回 `closed:true`。`max_sources` 是暂停限制，不是强制闭组或 handback。
- `restore_action(record, context, opportunity_id)` 仅恢复与同一上下文、机会身份及内容哈希完全一致的冻结候选，零模型调用、零骰点调用。被冻结文本或材料被改写则拒绝。

`context` 含 `world, actorId, protagonistId, advance, confirmedPrefix`；其他合法上下文原样保留。实际 `WorldState` 的 `initial`、全部实体字典、位置、初始外貌/个性、活动与已解除记录、全部任务和时间都原样送到模型，不投影为短摘要。实体名称仅从 `initial` 只读索引，当前状态不被重写。旧实验世界数组形状只为已有实验输入和工程夹具保留读取兼容，没有旧语义实现回退。

链返回 `memberIds, alreadyActedIds, members, confirmedTargets, judgments, closed, frozenActions`；每名成员保留原行动、行动哈希和渲染后的逐片段 `{id,text}`。片段 ID 加成员前缀避免跨人碰撞。D05 适配由 `short_settlement.py` 读取，新增 groupId/binding 由程序注入，不由模型生成。模型产生的文本永远不被骰点结果改写。

`roll_targets` 由 A/B 接入方注入，接收冻结源和已完整确认的目标元组，返回每个目标的原始实际回执。它不是本模块的语义回调：必须具备 `rollId,groupId,sourceId,targetId,triggerKey,ruleVersion,eligibilityBaselineDigest,result,target,eligible,admitted`，当前规则是 `reaction-d20-v1`、d20 ≥11 且 eligible 才 admitted。拒绝准入与已行动目标的判定同样保留。程序对骰点准入的核验不产生“行动成功”结论。真实服务接线与真实性核验仍属 A/B；本模块结构校验不能认证一个任意回调确实调用过服务。

## 关键反例与实际消费者证据

`tests/test_short_intent.py` 的 27 项反例覆盖：多步骤和条件原文保留、不可拆意图、消费状态、缺玩家输入、未明确结束、预算暂停、空行动、错实体/错跨度、合法引用中的语义审查拒绝、漏片段、引用与自然名称、冻结与恢复、全人物目标/已行动目标、当前源未来骰点泄漏、反应约束、完整威胁、复用确认行动、D02→D04 扩张、失败判定保留、目标失败不掷骰、canonical WorldState 无损交接、模型缺失。

`tests/test_short_protocol.py` 调用 `tests/short_protocol_probe.cjs`，只读编译本分支实际 `structured-output.ts` 和 `schedule.ts`（以及现有 API contract），将新 Python 适配器产物交给真实 TypeScript 消费者。22 项通过，包括：action/skip、目标集合/空集、反应原文、D05 成员结果、D06 批量及六阶段逐项、D07 continue/handback、D08 time/pointPlan、非法三态包装与模型骰点字段拒绝、阶段乱序拒绝。新六阶段候选与原 `assembleCandidates` 的结果逐字段完全一致，原 `checkUpdatesStages` 未发现悬空引用。

消费者探针产物为 `artifacts/world-components-logic/short-semantics-20261109/protocol-probe.json` 与 `.html`，记录源码 SHA、Node/TypeScript 版本。HTML 内嵌同一实际消费者代码并支持浏览器重跑；Node 成功不代替浏览器实际打开验收。探针全为工程夹具，真实模型调用 0，不证明 D 语义、C 叙事或完整 500ms。

## 尚未通过及接入提案

1. 自主 D02.2、反应 D04 和语义审查头尚需独立训练、来源分组验证及实测。旧给定计划表达成绩不迁移。
2. `FrozenAction` 是本实验内部不可变候选；A/B 的 acceptedSources/sourceEpoch/sourceAttempt、状态版本及封存仍是正式权威，不得把本地 hash 当服务已接受证明。
3. A/B 正式调用 D04 时需提供全部相关威胁、实际判定、完整冻结组。当前 B 的 reaction 输入较窄，具体兼容提案应扩充适配器输入，公开反应输出仍为原始行动文本，无需改变结果 wire。
4. 完整浏览器模型链、正式服务保存恢复和 C ready 时序仍需接线验收。本模块不提交世界、不新增长期行动史、不调用叙事。

## D06 窄头程序包装补充

`short_heads_updates.py` 只消费 `Completion` 原始标签或引用，不生成或修补 JSON。它在程序中组装既有 U1.2、U2.1、U5.1 和 D06.P.mapping 结果；其他组件由对应包装器承担。`assemble_update_head(provider, component, payload)` 的 provider 是低级真实训练头入口；未训练头、空输出、错误类型、预算终止都返回 incomplete，不兜底 keep 或 unchanged。

| 聚合接口 | 低级训练头 | 输出 |
|---|---|---|
| U1.2 | `.container`、`.slot`、`.relative_entity` | 现有实体或槽位引用；程序保留完整候选实体/初始记录/当前状态 |
| U1.2 | `.slot_mode`、`.relative_mode`、`.relation`、`.audit` | none/select；空间关系标签；pass/reject |
| U2.1、U5.1 | `.next_op` | keep/remove/add/replace/end；每实体可多项操作，必须显式结束 |
| U2.1、U5.1 | `.record_more`、`.record`、`.audit` | more/end、仍未处理的活动记录引用、pass/reject |
| D06.P.mapping | `.kind`、`.more`、`.target`、`.audit` | state/unchanged/transient/gap；more/end；现有阶段候选引用；pass/reject |

低级输入保留全部原字段，并以 `originalPayload` 保存完整输入、`semanticQuery` 保存当前对象与已经产生的工作材料。引用头约定 `candidates` 为合法候选列表，因此原始阶段候选仍保存在 `originalPayload.candidates`，不能因同名字段覆盖而丢失。候选枚举只提供现有实体/槽/记录/候选变化引用，不枚举动作、结果、因果或固定语义答案。选择后同时核验完整位置图；描述操作完整对账每一条旧记录；映射完整对账每条事实和每个候选后果。存在合法映射编号仍不证明语义正确。

`tests/test_short_heads_updates.py` 的 13 个工程测试覆盖同时位置变更、环、非法容器/槽、多项增加、纯解除、替代/保留、旧记录漏查、空记录显式保留、资源暂停、事实/候选映射、纯时间、接口缺口、审查拒绝和未训练头。标签均为声明的测试替身，未作为模型能力或性能证据。
