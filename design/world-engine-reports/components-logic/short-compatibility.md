# 新 D 线的 A/B/C 兼容提案

基于 `world-components-logic@d80a031` 实际源码；另已用远端引用核对 A `fc60a603` 和 C `457fc45b`。本文件是交接提案，没有修改 A/B/C 产品目录，也不注册第二套公共协议。D 的内部 `Completion` 与短句任务标识不进入现有闭合输出协议。

## B → D：全组输入和身份

当前 `schedule.ts` 的 results 输入已包含全组 `members[].actionText`，且名为 `rollRefs` 的字段实际包含 `targetId, rollId, result, eligible, admitted`。保留这些值；建议新 D 适配器从已有 `FrozenGroup`、`RollOutcome`、`PointWork` 装配以下内部数据，不由模型重新生成：

```ts
interface DGroupInput {
  binding: { worldId: Id; pointId: Id; version: number;
    checkpointRevision: number; requestId: Id; epoch: number };
  world: WorldState;                  // 同一结算前版本的完整状态
  group: {
    groupId: Id;
    closed: true;
    memberIds: Id[];
    alreadyActedIds: Id[];
    members: { memberId: Id; actionText: string;
      fragments?: { id: Id; text: string }[] }[];
    confirmedTargets: { sourceId: Id; targetIds: Id[] }[];
    judgments: RollOutcome[];         // 含未准入及已行动目标，原规则/阈值/资格基线
  };
}
```

`fragments` 只可来自被冻结 D02 原始片段，按原顺序组成与服务保存一致的 `actionText`，不能再分解已有行动冒充当时的原子尝试。适配器首先核服务接受来源与完整目标/判定集合；缺保存资料应触发恢复或未完成。D 校验成员集合、所有 source-target 判定配对、骰点范围/准入一致、已行动者不重复准入；这些结构检查不证明骰点的服务来源。

输出继续是 `action=act(text)|skip`、完整目标集合、`Record<memberId,string>` results 和六阶段 updates。未完成没有这些 wire 值。自然名为默认实验表示，引用版保留为独立子臂，未过门不替换。

## A：对齐已完成的部分阶段预览修复

D 基线 `d80a031` 中的 `SettlementGroup` 把个性/理智配对要求放在 wire 验证器，U5 完成、U6 未运行时会被拒绝。但进一步核对远端 **world-server@fc60a603c7e0b57805fffea0458192bcfebf6ffc** 后确认：A 已将配对与触发要求移至 `services/world/units.py::validate_unit`，`stage_unit` / `commit_point` 保留完整验证，而 `preview.py::preview_point` 已支持部分阶段。

因此当前提案是**按固定 A 版本同步已有能力并验证接线**，不需要另造 `preview_stage` API，也不能把 D 旧 schema 的拒绝报告为当前 A 的缺陷。沿用 `PreviewPointRequest` 的完整身份字段、已完成单元和当前单元的累计候选；A 从同一基线重新预览，不把上次预览再次应用。D 内部仍绑定 `stage/baseWorldHash/candidateHash/binding`，用于拒绝陈旧响应。

U5 的 `personalities` 可以非空、`sanities` 暂为空；这是部分预览，U6 未完成，不能提交。U6 依据新有效个性预测后，最终候选再次经过 A 的 `validate_unit` 和整点验证。不能用旧理智填空绕过要求。A 现有 `preview_over_budget` 的请求/响应上限继续适用；超限返回未完成，不能截短世界。

实验只读加载固定 A 纯逻辑用于离线预览，并记录实际源文件哈希；不启动 A 服务，不写数据库，不声称具有租约、服务回执或正式来源授权。正式 A/B 集成仍需核对 `preview_point` 身份/版本、全部累计单元、恢复和原服务门槛。

## D05 → D06 → C：两种不同的材料

D05 的短事实、`state/unchanged/transient/gap` 映射、D06 预览和评审标签只存在于本次候选/审计材料。映射由模型判断，程序核对事实与阶段/对象/候选引用及双向覆盖。`gap` 表示必须保留但协议不能表达，停止提交提案并留记录；不得创建长期行动史解决。

C 的正式输入建议保持 B 当前 `before/delta/after` 全量装配，并增加共同的正式来源锚点：

```ts
interface CommittedFactsForC {
  anchor: { worldId: Id; pointId: Id; previousPointId: Id | null;
    version: number; stateDigest: Digest };
  before: WorldState | null;
  delta: { timeAdvance: TimeAdvance | null;
    entityDeltas: Record<Id, EntityDelta> };
  after: WorldState;
}
```

全部材料来自同一次正式 `get_state` 链，A 适配器核原始 Δ 回放与来源。根点 `before=null`；后继必须前驱一致、版本加一、初始状态不变。现有 C 窄投影 `committed-narration.ts` 无法接受所有合法外貌、物品、任务/个性组合；应扩展 C 的输入支持并另做真实叙事模型实验，不能静默过滤这些事实。

单元六阶段完成只保存候选和进度；整个时间点必需槽位、结算单元、纯时间扫描都完成，才能 seal/commit。提交后绑定正式版本与点身份申请 C，ready 后继续合法关联段，全部关联段及原轮完成后才进入 D07。

`PointHandoff` 现明确区分 `model_completed` 和正式 `ready`。后者必须提供已接受的 `narration_submit` 规范化回执，并由 `verify_receipt` 核实实际服务 claim、generation、issued-at/fence 与当前门槛。本地自增 generation 只用于实验尝试隔离，不能代替服务 claim。回执同时绑定该点事实包摘要、当前请求/版本和本地尝试；布尔值不能冒充数字版本或 generation。

C 失败重试同一个事实包，保持已提交世界、冻结行动和骰点。恢复到新租约/请求时必须有权威重绑定回执和 `verify_rebind`，只允许相同世界/点/正式版本、前进 epoch 和不倒退的检查点；已有 ready 不自动打开新请求门槛。`recover_point` 是实验规范化回执名称，不是新增公共操作；A/B 适配器须从已有恢复/租约/门状态验证其依据。恢复前旧 generation 的 ready 无效。

D08 同时提供初始计划与经来源验证的剩余段计划；恢复后可追加合法关联段，既有冻结行动/时间只读保留，已 skip 槽位不重新分配。先前闭组提前牵连的成员不能阻挡仍未访问的正常槽位。具体来源证据与内部上下文见 [剩余段恢复](short-suffix.md)。

## 已有验收证据及边界

- `test_short_settlement.py`：D 基线继承的旧 A schema 经 Pydantic 2.13.4 解析证明 U5 不完整候选被拒绝、补齐 U6 后通过；固定当前 A 的部分预览另由 `test_short_preview.py` 验证；检查缺判定、共同争夺、失败副作用、位置图、记录解除、全任务、场外个性、纯时间和映射遗漏。
- `test_short_lifecycle.py`：正式事实回放 callback 必需、时间点完成屏障、检查点推进、关联段顺序、同事实叙事重试、取消/恢复/迟到 ready 隔离。
- `test_short_protocol.py` 及浏览器 `protocol-probe.html`：实际 TypeScript 输出解析/候选装配共 22 项通过，未完成拒绝；这些是工程测试，不含模型推理或服务提交。

完整计时仍包括 D 模型、程序/服务、C 生成、门等待和总请求；分项不能扣掉必须等待的 ready。未接真实 A/B/C 时不报告整链质量、叙事质量或完整 500ms 达标。
