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
3. **`run_narrative_pipeline`**
   - N1(outcome) → N2(select + visible_other_actions) → N3 `plan_v3`/`check_plan_v3` → N4 `render_plan_input`；
   - `scene_context` 是显式输入（场景/人物个性/可见物）；**没有从状态猜场景**；
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
- `scene_context` 目前由调用方提供；从权威状态自动构建场景/人物上下文是下一层契约。
- 新输入 251–347 tokens（12 例管线预览），当前 v2 模型 `max_input=160`/`max_output=96` 不够；新训练建议 ≥384/≥128。
- 旧 v2 模型仍只认 `task_achieved` 等旧 kinds；`outcome` 的叙述质量要等新 N4 训练后才能声明。
