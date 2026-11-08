# 判分缺口交接（给判定器维护方，自动生成，勿手改）

c8 只保留诊断材料，不修改判定器、不修改生产投影。下面两个反例都来自本批诊断的事实包，可以直接作为回归用例。

判定器：`frontend/src/lib/world-engine/runtime/narration-alignment.ts`（sha256 309ca19f…，本批未运行，结论来自阅读源码）。

## 反例一：理智方向写反不被拦

**事实包（c8d04 第三点同型，去掉人格/任务后仍成立）**

```json
{
 "facts": [
  {
   "kind": "sanity_changed",
   "name": "C",
   "from": 30,
   "to": 26
  },
  {
   "kind": "at",
   "name": "C",
   "location": "一号教室"
  }
 ],
 "time": {
  "amount": 2,
  "unit": "minute"
 }
}
```

**输入句**：`C的精神值从26升到30。`

**应判结果**：违规（方向写反：事实是 30→26 下降）。建议违规种类沿用 `wrong_number` 或新增 `direction_reversed`（sanity 分支）。

**当前行为**：通过。`narration-alignment.ts:396-403` 的 `wrong_number` 只检查句中数字是否属于 `{from, to}`；26 和 30 都在集合里，顺序不被检查。

## 反例二：把父任务达成写成“全部任务完成”不被拦

**事实包（c8d06 第三点）**

```json
{
 "facts": [
  {
   "kind": "sanity_changed",
   "actorId": "person_c",
   "name": "C",
   "from": 30,
   "to": 28,
   "fieldPath": "characters.person_c.sanity",
   "fromValue": 30,
   "toValue": 28
  },
  {
   "kind": "task_achieved",
   "actorId": "person_c",
   "name": "C",
   "taskId": "task_c_root",
   "goal": "安全度过校园中的这段时间。",
   "fieldPath": "characters.person_c.tasks.task_c_root.status",
   "fromValue": "pending",
   "toValue": "achieved"
  },
  {
   "kind": "personality_changed",
   "actorId": "person_c",
   "name": "C",
   "changeId": "c8d06_relief",
   "text": "暂时放松了对周围的警戒。",
   "fieldPath": "characters.person_c.personalityChanges",
   "toValue": "c8d06_relief"
  }
 ],
 "time": {
  "amount": 3,
  "unit": "minute"
 }
}
```

**输入句**：`C完成了任务「安全度过校园中的这段时间」，校园里的所有任务都完成了。`

**应判结果**：违规。两点理由都要写到：（1）事实只支持 `task_c_root` 达成；（2）子任务 `task_wait_noon` 仍为 pending，不能说“所有任务完成”。

**当前行为**：通过。`narration-alignment.ts:439-444` 只要句子里绑上任意 `task_achieved` 事实就放行；不点人物的总结句（“全部任务完成”）被第 433 行注释显式排除在检查范围外。

**额外问题（契约，不是判定器能单独解决的）**：本批事实包只含父任务的 `task_achieved`，子任务 pending **根本不在包里**（`committed-narration.ts` 只发 `task_achieved`，不发任务状态）。所以即使判定器加了“全部完成”规则，也缺一条可核对的 pending 事实。要修需二选一：

1. 投影补一条“任务状态”事实（或允许 `task_pending` 类事实），判定器据此比对；
2. 明确产品口径：父任务达成时不允许叙述引申到子任务，按措辞规则（而非事实比对）拦。

## 修复后的要求

- 两条反例都加成回归用例，必须判违规；本批六条诊断的事实包可直接复用。
- 重跑受影响的旧题基线（至少 `nv-task-pers-sanity-1`、`nv-task-only-1`），并记录判分器版本变化（文件哈希 + 行为变更说明）。
- 若修改了事实包形状（增加 pending 事实），旧题基线同样要重跑，并同步更新 `sources/three-arm-provenance.md` 的结论。
- c8 不代改判定器；修复完成后由维护方给出新版本证据，c8 只做引用。
