# N4 叙事 runner：N1 outcome/resultText → N2 → N3 → N4 输入

日期：2026-11-02。范围：接口与输入测试，**未训练、未调用模型**。

## 改了什么

1. **N1 `extract_facts(..., narrative_outcome=True)`**
   - 完成的 task 若带 `resultText`，产出 `kind="outcome"`、`resultText`，不再产出 `task_achieved + goal`；
   - 没有 `resultText` 时产出 **`task-outcome-unavailable`** 阻塞诊断，**不退回打印 goal**；
   - 默认 `narrative_outcome=False`，旧 v2 的 `task_achieved` 契约不变（selftest PASS）。
2. **N2 `visible_other_actions=True`**（opt-in）
   - 他人在同地的 `moved` / `outcome` / 可见外貌变化为 `may`；
   - 他人的 task goal/status 与内心状态仍不可见；
   - 旧 v2 臂不传该参数，行为不变。
3. **`run_narrative_pipeline` + `build_scene_context`**
   - N1(outcome) → N2(select + visible_other_actions) → N3 `plan_v3`/`check_plan_v3` → N4 `render_plan_input`；
   - 未显式给 `scene_context` 时，builder 从**权威状态 + 已选事实**构建：地点路径/外貌、人物外貌/个性/inventory、可见物；
   - **present 不是全员扫描**：视角主体 + 携带已选事实的在场实体。100 个无事实 NPC 同处一地不会进入 present（测试覆盖）；
   - 天气/风/光/时段不在 `WorldState` 里，由显式 `environment` overlay 提供；缺失就省略，**不发明天气**；
   - 任务 goal/ID 不进入 N4 输入；时间只写“过去了一会儿”；视角按实际主角名。
4. **`run_pipeline_v2(..., visible_other_actions=False)`**
   - 参数已加，默认 False；旧 v2 路径与 selftest 不变。

## 测试

`test_pipeline_narrative.py`（真实 `make_pipeline_state` + `make_point`）：

- 有 `resultText`：N1 产出 **1 条 `outcome`**，N2 选 1 条，N3 1 组，N4 输入含：
  ```text
  1. 管线甲把铜铃挂回了钟楼。
  视角：管线甲（第三人称限知）；只写管线甲的内心，他人只写可见动作。
  ```
  **不含** goal “把铜铃挂回钟楼”，不含 `task_achieved`。
- 缺 `resultText`：runner `status=incomplete`、`reason=n1-cannot-express`、阻塞码 `task-outcome-unavailable`，**没有 input**。
- 旧 N1 默认仍产出 `task_achieved`，证明旧 v2 未被破坏。

运行：

```text
narrative pipeline input test: PASS
```

## 边界

- 这是 **输入/接口测试**，不是质量评测；N4 模型还没有在这个新输入上训练。
- `scene_context` 现可由 `build_scene_context` 从状态 + 已选事实构建；天气/风/光/时段仍需显式 `environment` overlay，不在 WorldState。
- **跨组件缺口：`WorldState.Task` 当前没有 `resultText` 字段。** N1 的 outcome 测试用的是组件 dict fixture；真正的 Pydantic 状态会拒绝这个额外字段。生产化需要 B/server 在 Task 契约加入 resultText（完成的 task 必填），否则 N1 只能在 fixture 里验证，不能宣称端到端。
- 100 NPC 场景只证明 present 不做全员扫描，不证明模型叙事质量。
- 新输入 251–347 tokens（12 例管线预览），当前 v2 模型 `max_input=160`/`max_output=96` 不够；新训练建议 ≥384/≥128。
- 旧 v2 模型仍只认 `task_achieved` 等旧 kinds；`outcome` 的叙述质量要等新 N4 训练后才能声明。
