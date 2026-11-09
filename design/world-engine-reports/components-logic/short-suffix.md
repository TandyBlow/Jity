# D08 初始规划与恢复后剩余段

本次只读核对的远端 B 为 `world-browser@871afa91f63fccf26cee0deb422e5dc9d8f6fe94`（`git ls-remote` 同值）；A 为 `world-server@fc60a603c7e0b57805fffea0458192bcfebf6ffc`。

B `schedule.ts::idlePointDecision` 在无当前 work 且本地 plan 缺失时调用 pointPlan。正常提交后递增 planIndex，已有计划的关联段直接继续，不需要模型重排。`controller.ts` 的恢复提交路径在没有已预留 successor 时清空未确认的未来 plan；C ready 后允许从服务返回的当前 round cursor 再规划剩余点。因此“frozenActions 非空就一律拒绝”只能用作初始规划边界，不能覆盖恢复后的合法后缀。

A `control.py::handle_begin_point`（641–675 行附近）核验合法操作阶段、无当前 work、合法新身份与 kind/time 组合，并从当前 round cursor/actedIds/visitedIds 建立工作状态；它没有把 normal 硬性限制为轮首。D 不再自行推定所有剩余段都不能为 normal，具体合法首段类型由 A/B 来源验证器提供。

## 内部接口

`propose_segments(session, context, allocate_point, verify_prefix=None)` 保持既有 pointPlan 项的 `pointId/kind/timeAdvance/actorIds` wire 字段。

- `planningScope="initial"`：默认兼容原实验调用；必须没有已行动、已访问、已冻结工作或 lockedPrefix。模型只提出初始计划，程序分配身份。
- `planningScope="remaining_suffix"`：必须有完整 `head`、`cursor`、`currentWorldHash` 和 `lockedPrefix`，且 `verify_prefix(copy_of_full_context)` 返回严格 True。缺证明在模型调用前返回 incomplete。

`lockedPrefix` 的必需字段为 roundId、orderHash、cursor、actedIds、visitedIds、frozenActions、head、points、currentWorldHash、allowedNextKinds。head 包含 pointId、kind、version、stateDigest；每个 points 项包含 pointId、previousPointId、kind、version、stateDigest、timeAdvance、actorIds、visitedIds；每个冻结行动包含所属 pointId、actionText 和 contentHash。来源适配器可保留实际判定、读回执和取消身份等额外材料。

程序复核：同一世界材料与冻结顺序摘要；当前 cursor 是第一个未访问槽位；逐点身份和版本连续；冻结行动归属及全覆盖；每点 actors 属于 visited；已访问槽位不重复；head 是前缀末点；新点 ID 不复用前缀。所有旧动作、骰点材料和时间保持只读。

`verify_prefix` 必须核对实际 A/B 来源、正式世界摘要、原轮冻结顺序、完整已确认材料、当前 cursor、没有待恢复的当前 work、C ready 与当前门槛，以及本次允许的 `allowedNextKinds`。本地摘要和助手草稿回执不能代替这个验证。该 callback 的正式 A/B 服务实现尚未接线；工程测试中的 True 验证器明确是测试替身。

模型只能追加未访问的槽位，visited 包括已经 skip 的槽位。新普通段槽位继续保序；旧点的全部实际 actorIds 包含被提前牵连的反应人物，不能当成自然槽位顺序来约束后续人物。例如 a 先行动并牵连 c、b 尚未访问，旧前缀含 a/c 不会阻止 b 后续合法行动。首 linked 必须承接经验证的 instant 前驱；首 normal 仅在来源验证的 allowedNextKinds 许可时接受。后缀建议不写回 visitedIds，遗漏槽位仍由 B 按现有调度处理。

## 验证与训练材料边界

新增工程反例覆盖：恢复 instant 前缀后追加 linked；缺来源/错 cursor/错版本/动作改写/陈旧世界拒绝；skip 槽位不得再次分配；新后缀重排、冻结人物重分配及旧 point ID 复用拒绝；不合法前驱类型拒绝；此前 a/c 共同结算后 b 合法继续；来源允许的 normal 首段。

作者数据新增 12 个**同来源** remaining_suffix 诊断。它们使用固定 A 原预览形成瞬时共同结算前缀，完整保留 a/b 冻结行动，让 off 的未访问槽位进入 linked。该变体明确改变了此前 off 的使用状态，未伪装成原诊断骰点历史的自然延续；所有 prefix/ready 证据标为作者夹具，未声称实际服务或 C ready。它们不是新增独立测试来源，不是纯时间 D06 模型实测，也不证明恢复后的真实浏览器链路已经通过。
