# H2 骰点事实与组处理进度读取契约提案

后续状态（2026-10-27）：本文件保留 R1 讨论历史。候选已由 B=`6b809dc`＋A=`0cb1951`
成套实现与消费，固定摘要为 `90291801…`；本轮约定的完整 H2 验收矩阵已通过，
当前证据与边界见 [固定组合验收记录](../../artifacts/h2-full-6b809dc-0cb1951/README.md)，
共同基线已在证据提交 `e377e46` 入库后[冻结](../../artifacts/h2-freeze-6b809dc-0cb1951.json)。
以下“未冻结/尚无候选”等表述均为提案当时状态。

日期：2026-10-26。版本：R1（纳入 A 完整只读答复，B 接纳其字段方案）。状态：**提案口径已收敛；未冻结，未改正式 wire/schema 或运行时**。A 的原答复见 [h2-a-read-contract-review.json](../../artifacts/h2-a-read-contract-review.json)。尚无新的 Python/导出/夹具候选提交、B 消费提交和共同契约摘要，不能据此宣称接口基线已冻结或 A3 已实现。

基线：A `be87679800bdfd313fb9c7bf24bd1317136b81e9`；B `cc70105`（`d6dce8c` 上的 H2 客户端首批，用户复核通过）；共同摘要 `abda455597e743f63da1c205ca7bc68044728c5f92a3cb7ae920440ef324eedd`（对应旧基线，本稿与客户端首批均未改变它）。客户端首批及历史读取子检查通过，完整 H2 仍未验收。用户独立复跑：[history.json](../../artifacts/h2-history-http-review-independent.json)（B 自跑记录另见 [h2-history-http-review.json](../../artifacts/h2-history-http-review.json)）。

## 1. 本次需要确定的结果

一次带有效租约的恢复读取，必须能区分：目标尚未确认、目标确认而未 roll、roll 已定稿而未处理扩张、反应原文已确认、子来源尚未处理完，以及整个组可闭合。缺字段/损坏与“确实还没执行”必须分开。

沿用 `get_context(includeRecovery=true)` 的 `PointRecovery.groups`，建议在每个 `FrozenGroupView` 增加 **必填** `rolls` 和 `progress`。不新增长期行动历史、不新增长期行动日志接口、不改变世界 Δ 或回放；原文仍只取当前/已预约后继的短期冻结工作。

## 2. 建议的字段形状

下列是候选消费形状，Python 仍为定义/导出权威。`RollOutcome` 复用现有字段及定稿规则，定义移动或消除循环引用由 A 决定。

```ts
interface FrozenGroupRecoveryExtension {
  rolls: RollOutcome[];
  progress: {
    // 当前执行的来源在首位，其后是暂停等待子来源的祖先。
    // 有序、无重复；不是 memberIds/frontierIds 的 ASCII 排序。
    sourceStack: Id[];
    threats: ThreatProgress[];
  };
}

type ThreatKey = { sourceId: Id; targetId: Id; triggerKey: Id };
type ThreatProgress = ThreatKey & (
  | { status: 'pending_roll'; rollId: null; reactionMemberId: null }
  | { status: 'reaction_pending'; rollId: Id; reactionMemberId: null }
  | ({ status: 'handled'; rollId: Id } & (
      | { actionDisposition: 'none'; reactionMemberId: null }
      | { actionDisposition: 'created' | 'reused'; reactionMemberId: Id }
    ))
);
```

`rolls` 每行的完整字段：`rollId / groupId / sourceId / targetId / triggerKey / ruleVersion / target / result / eligibilityBaselineDigest / eligible / admitted`。world/point/round/advance 从所属恢复包络与组作用域绑定，不能跨组混入。

| 字段/现有字段 | 权威来源及语义 | 空值含义 |
|---|---|---|
| `members[].actionText` | 已接受冻结原文，保持 UTF-8 字节；恢复不重写 | 对已确认成员缺失即停，不把它当许可重新生成 |
| `members[].targets` | 已接受的逐源完整目标集，包括程序分配的 triggerKey | `null`＝尚未确认目标；`[]`＝已确认无目标，不能重采样 |
| `rolls` | `world_rolls` 的不可变最终行；包括未准入、资格不满足及已行动目标的判定 | 必填 `[]` 表示本组确无已保存骰点，省略不等于空 |
| `progress.threats` | 已确认目标逐威胁的事务处理标记；每个目标恰有一项 | 无已确认目标才可 `[]`；不能靠缺项表示未 roll |
| `progress.sourceStack` | 服务端持久化并校验的有序 DFS 栈；作为点/组 checkpoint 元数据跨 epoch 保留，包含等待子树的祖先 | `[]` 只有在来源全部处理完时才合法，不等于组已 closed |
| `handled.actionDisposition` | `none`＝未准入；`created`＝本威胁首次接受目标行动；`reused`＝明确关联本组既有冻结行动 | handled 时必填，不能仅凭目标出现在 memberIds 推断 |
| `resultText / candidates` | 现有保存结果及完整候选；不改其确认边界 | 原方案允许尚未确认的结果/候选重算；已经保存的必须复用 |

## 3. 完整性与下一动作

| 状态 | 必须满足 | B 恢复后的下一动作 |
|---|---|---|
| 来源 `targets=null` | 有冻结行动原文；该源没有确认目标对应的进度项 | 对该源调用 targets，复用原文，不调用 action/reaction 重写原文 |
| `pending_roll` | 目标与 trigger 已确认；rollId=null；不存在同键已保存最终行或已确认 roll 引用 | 对原键执行 create_rolls；不生成新 triggerKey |
| `reaction_pending` | rollId 指向本组同键最终行且 admitted=true；对应反应尚未被接受 | 仅生成尚未确认的目标反应，再确认扩张；已有成员原文不得覆盖 |
| `handled/none` | 最终行 admitted=false；reactionMemberId=null | 不生成反应；骰点仍传给 results |
| `handled/created` | 最终行 admitted=true；reactionMemberId=targetId；本威胁是该成员唯一的首次接受因果边 | 复用已接受原文，从已保存的子来源栈继续；不再次生成原文/压栈 |
| `handled/reused` | 最终行 admitted=true；reactionMemberId=targetId；显式关联该成员在本组已经接受的冻结行动 | 不生成反应、不覆盖原文、不重复压栈；保留原 admitted |
| sourceStack=[]，closed=false | 每个成员目标已确认、每个威胁 handled、判定行完整 | close_group，无模型重采样 |
| closed=true | sourceStack=[]，frontierIds=[]，全部威胁 handled | 复用已存结果/候选，或只重算尚未确认的 results/updates |

补充约束：

1. 所有数组必填，禁止默认补空。rollId、完整威胁键均唯一；`threats` 按 `(sourceId,targetId,triggerKey)` ASCII 排序作稳定传输，**这个顺序不是执行顺序**。`rolls` 也按同键排序。
2. `threats` 与每个非 null `members[].targets` 的并集一一对应。每个非 pending_roll 项必须引用 `rolls` 中恰一行，且每条 roll 恰被一个进度项引用；不存在另一个键复用 rollId。
3. 沿用定稿约束 `admitted == (eligible && result >= target)`，`reaction-d20-v1` 阈值为 11。候选实现须给 RollOutcome 本身补齐阈值校验，并核对同键重发的 rule/target/原 eligibility 绑定。恢复不用当前 actedIds/memberIds 重算并翻转旧 admitted。
4. 接受一个新成员行动时，同一事务保存原文、唯一 `created` 完整威胁键/rollId 接受边并压栈，同时把本组其他已经定稿、admitted=true 且指向该成员的待反应关系标为 `handled/reused`。例：C 预掷 D/E 均通过，D 子树先接受 E，则旧 C→E 明确 reused，原 admitted 保持 true。新 roll 若在签发时目标已实际行动或已接受本组行动，按该时刻冻结资格得到 eligible=false，记录最终判定及 handled/none；尚未 roll 的关系不能因为已有行动就漏掉骰点。
5. `created` 接受边对每个非发起成员唯一且无环；`reused` 威胁边可以成环，但不生成第二次人物行动，也不压栈。sourceStack 首项为当前来源，尾项为发起者，除非全部结束；相邻栈帧必须由 created 接受边证明父子关系，不能用成员或 rollRefs 的排列推断。每源按 `(targetId,triggerKey)` 固定选择下一个待处理威胁，不靠批量返回顺序。
6. `frontierIds = ASCII排序的集合 { sourceStack 内 targets=null 或本源仍有非 handled 威胁的来源 }`。局部已完成、只等待子树的祖先保留在栈中而不进 frontier。例如 D 未分析、C 只等待 D 时 stack=[D,C]、frontier=[D]；若 C 还剩 E，frontier=[C,D]。这与 T07 的 frontier=[F]、完整栈=[F,E] 相容。R0 的集合等式撤回。B 调度只使用有序 sourceStack；现 A 服务 frontier 恒空的占位实现不能作权威依据。
7. 闭组或已 stage 的组：sourceStack=[]，所有威胁 handled。不能因为结果/候选已存在，就隐去未准入的骰点。
8. 恢复 `members[m].rollRefs` 明确定义为 m 发出的全部已保存 roll 的身份投影，sourceId=m，包括拒绝判定，并与同 source 的 rolls/progress 逐键核对；`extend_group.admittedMember.rollRefs` 是本次接受该成员反应的入向依据，targetId=memberId、sourceId=请求源。T07 恢复样本体现前一种归属。B 不拿身份引用替代完整判定，也不凭它的排列猜测 DFS/首次接受父边。

## 4. 服务端事务与复制边界

- 读取必须来自一个一致事务快照，同时覆盖 fence、current/successor 的工作清单、成员/目标原文、处理进度和判定行。每个点独立绑定其锁定 baseline/time/inputProjectionHash，后继使用预约的未来基线。
- `pending_roll` 只能表示真的尚未执行。roll 创建必须在同一事务保存最终行及相应威胁关联；若已确认的 roll 关联指向缺失/损坏行，读取/恢复必须明确报错，不能降格成 pending_roll 后重新掷骰。
- 目标确认与初始 threat 项、roll 最终行与进度关联、反应原文与 created/reused 接受关联及栈变化，分别随对应操作原子保存。sourceStack/progress 持久化为服务端点/组 checkpoint 元数据，浏览器不上传任意进度，也不从原文或数组顺序重建它。
- 普通读取仍隔离旧 epoch。`restore_required` 继续只暴露已接受来源清单，不暴露旧 epoch 原文；restore 后重新读取当前 epoch originals 和完整事实。不可变 roll 行可跨 epoch 按原键复用，不能重新抽样或复制出第二个判定身份。
- 新的进度投影不改变原文复制请求形状。progress 作为服务端 checkpoint 元数据跨 epoch 保留，restore 校验相同作用域、baseline/time/inputProjectionHash、accepted 引用及载荷绑定后，才读取当前 epoch originals+rolls+progress；不能仅因正文复制成功就认为进度正确。
- 引用行缺失返回 `frozen_work_missing`；内容哈希、进度关联或栈不一致返回 `frozen_work_corrupt`，不降格重采样或抛出无协议的 LedgerMismatch/500。`get_context` 当前未声明这两码，后续候选必须同步扩大错误表及夹具，不能先让运行时返回未声明错误。
- 保留 B 最后一次**完整 recovery** 对账；按 A 提议 create_rolls 不递增 checkpoint revision，因此 revision 相同不证明判定/进度快照没变。复制与读取仍需服务端一致 SQL 事务，客户端对账不能代替它。
- 提交/取消按当前点实际消费的组清理短期原文/进度引用，保留未消费当前/后继工作。既有 rolls 及世界 Δ 的保留策略不变，不把 actionText 放入它们或幂等结果。

## 5. 固定例子与 A/B 共同验收矩阵

| 断点/反例 | 必须读取的事实 | 预期恢复 |
|---|---|---|
| C 原文已确认，targets 未确认 | C.targets=null，stack=[C]，threats=[] | 只问 C 的 targets |
| C.targets=[] 已确认 | stack=[]，无威胁/判定 | 直接 close，不重问 targets |
| C→D 目标已确认、roll 前 | pending_roll；stack=[C] | 同键首次 roll |
| C→D roll 已落库、反应确认前 | reaction_pending；固定 roll/eligibility/admitted | 仅生成尚未确认的 D 反应 |
| D 原文已接受、D.targets=null | C→D handled/created/member=D；stack=[D,C] | 从 D.targets 继续，C/D 原文不变 |
| D 完成，C 仍有 E 未 roll | D 已确认空目标；stack=[C]；C→E pending_roll | 只处理 C→E，不再次分析 D |
| C→D 未准入或 D 已实际行动 | 完整非准入判定，handled/member=null | results 含该骰点；无 D 反应 |
| C→D→C 环/同组两源威胁同一人 | 每个源键及其原判定、接受/去重关联 | 不重复人物行动，不覆盖原文，不翻转旧 admitted |
| C 预掷 D/E 均准入，D 子树先接受 E | D→E created、旧 C→E reused，created 边唯一且无环 | E 原文/接受/压栈仅一次；旧 C→E admitted 不变 |
| E 已接受后才首次 roll C→E | 新行按签发时资格 eligible=false，handled/none | 保留本条骰点，不生成 E 反应，不改旧骰点 |
| 闭组尚未 results | 栈空、全部目标/判定/处理状态完整 | 只生成 results，再 updates |
| 已 stage / 已封存 / 已预约后继 | 原候选、结果、各自完整判定/进度与基线 | 原样接续，不把合同标本当真实事务 |
| roll 存在但 progress 写入丢失，或反之 | 同事务约束/恢复失败证据 | 原子性保证两者同在；异常必须停 |
| 漏字段/漏骰点/重复键/错组/错 trigger/错基线 | 读取完整性校验 | 零模型调用、零结论/提交写入；不得默认空 |
| 栈/集合不符、跳过未处理来源、已确认反应的原文缺失 | 服务端进度与 payload 校验 | 明确停，不据集合猜顺序 |
| 当前+后继在复制期间 epoch/revision 变化 | 服务端围栏、一致快照、B 二次 context 对账 | 不混合快照，旧持有者迟到写入拒绝 |

## 6. 请求 A 确认及后续交付顺序

冻结前必须明确下面三项。A 已在原任务给出完整文字方案，B 接纳并纳入本稿；**这是提案语义收敛，不是候选接口基线冻结**。原答复已归档，后续仍须落实 Python 定义/导出/共享夹具、B 消费及新摘要。

| 冻结前置 | A 必须明确的内容 | 必须能解释的反例 |
|---|---|---|
| 栈与 frontier 的权威 | sourceStack 的精确定义、保存位置/可信读取来源、推进规则，以及 frontierIds 的确定性映射 | T07 的 `[F,E]` 与 frontier=[F]；局部已完成但仍等待子树的祖先 |
| 反应接受与去重 | 原行动的唯一接受依据；多源同目标、环、批量预掷骰后如何识别已接受反应/复用既有行动；原 admitted 不翻转 | C 预掷 D/E 都通过，D 子树先接受 E，回到 C 时不得再生成 E |
| 事务与拒绝规则 | roll 与进度、反应原文与栈推进、跨 epoch 原文复制/接受引用的一致性；缺失与损坏分别如何拒绝及其 registry 声明 | roll 存在但进度丢失，复制正文存在但接受引用/栈损坏；不得降格重采样或返回未声明错误 |

第 6 节逐字段问题的 A 答复与 B 处置如下：

1. 完整 RollOutcome、全部已保存结果、必填且可证明的空数组：A 同意，B 纳入；独立模块及 reaction-d20-v1 阈值校验随 Python 候选落实。
2. 三态、有序持久化栈及 frontier 精确公式：A 给出，B 纳入 §2/§3；不拿当前占位实现当实现证据。
3. actionDisposition、唯一 created 接受边、reused 不重复压栈、批量例子及两种 rollRefs 归属：A 给出，B 纳入 §3/§5。
4. checkpoint 元数据权威、原子保存、复制绑定及两个明确拒绝码：A 给出，B 纳入 §4；get_context 扩表/夹具仍待候选实现。
5. **尚无新候选提交或摘要。** 当前仍只可指认本稿开头的旧基线。字段共识不代替候选交付；下一步固定 A 的 Python/导出/夹具提交、B 消费提交、新摘要及协议版本策略，通过共同检查后再冻结。T07/T09 双样本需补完整事实、进度和真实 SQLite 操作构造的断点，新增多源复用/环/批量/事务中断矩阵，不把录制响应当事务证据。

顺序保持：**双方确认本读取契约 → A 更新 Python/导出物/共享夹具与摘要、B 同步消费并保留停止守卫 → A3 实现真实复制与围栏 → SQLite 刷新/接管全链联调**。未确认前不单方修改正式契约；不新增长期行动历史，B3 全量继续暂缓。

## 7. A/B 对接记录

- B 已向既有 A 任务 `01a1674c-45a7-71c0-97ff-22590ce54b38` 请求本提案的只读核对，明确不恢复旧任务、不改代码/正式 schema。
- A 首轮确认完整 rolls 和显式进度确需补充；给出了上述 T07 的两处语义区别。R1 已撤回 frontier 与完整栈相等的假设，并区分恢复与入组请求的 rollRefs 归属。
- B 随后直接核对了 A 任务的审批界面：实际待批是 `codex_tui.send_message_to_thread` 将六段只读评审意见发送回本 B 任务；界面要求该消息工具的交互许可，未显示进一步审批理由。它不是命令执行、文件修改或契约确认。最近失败的 shell 命令另属工作目录错误，不能拿它解释这项审批。
- B 已取消六次消息回传，未选择 Allow、未修改审批设置。取消后任务工具确认 A 的 `activeFlags=[]`；改为 A 在原任务内给出文字结论、B 只读获取。定位与处置记录见 [h2-contract-coordination.json](../../artifacts/h2-contract-coordination.json)。此事由 B 自行排查，不需要用户提供隐藏任务的审批材料。
- A 随后已在原任务给出完整只读文字答复，B 通过 read_thread 取得并归档 [h2-a-read-contract-review.json](../../artifacts/h2-a-read-contract-review.json)。A 明确：消息工具返回 `user cancelled MCP tool call`，没有发送/批准成功依据，也没有更具体的权限要求原因；本稿不推测其原因。
- B 接纳 A 提出的三项具体语义并修订本稿。**客户端首批已验收，R1 未冻结，完整 H2 未验收。** 本轮只改提案/记录，不重复运行已验收源码测试，不新增长期行动历史，B3 全量继续暂缓。A 当前只有 SQL/core/work 基础，真实 create_rolls、accepted/frozen、复制及完整恢复投影仍需 A3 实现，不能把提案口径当作既有能力。
