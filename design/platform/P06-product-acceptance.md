# P06 产品验收（候选复核）：规则叙事臂过关，模型叙事档与真机仍未验

**Question.** 当前候选（零参数 rules 叙事臂、单模型移动预算档）能不能过产品级验收？
我们自己的冻结构建为什么没跑成？哪些结论是回归、哪些是独立证据？

**Setup.** 两条路径：

1. **候选证据复核**：`artifacts/goal/narration-rules/scenarios8-rules.json`（另一 lane 在
   3177 上跑的 8 场景 rules 臂，`--allow-program`）。平台只读重算：`scenario_report.py`
   的状态/任务断言、`verify_run.py` 的模型与引擎、`summarize-timing.mjs` 的计时、
   `soak_report.py` 的回合与堆。
2. **自建冻结构建尝试**：`.local/real-build.ps1` 从 worktree HEAD 构建、自起 3180，
   用 `acceptance-sequence.py` 跑 4 回合新输入 → 2 回合移动模拟 → 10 回合 soak。
   构建身份：`artifacts/goal/platform/lab/build-manifest.json`；尝试记录：
   `acceptance-attempts.json`。

**Results.**

1. **rules 臂在冻结八场景上的回归结果（8/8 回合，0 failures）**

| 指标 | 结果 |
|---|---|
| driver 状态 / 回合 | COMPLETED，8/8，failures 0 |
| 状态断言 | **48/48** |
| 任务断言 | **14/14**，达成检查 3/3，false 0、missed 0 |
| 正文问题 | 0 回合 |
| 整回合等待 | 均值 **57.1 s**，最大 **83.9 s** |
| 首段可读（summarize-timing） | 8/8，最差 **13.5 s**（≤60 s） |
| 单点正文完成 | 8/8，最差 **158 ms**（程序正文，不是流式模型） |
| JS 堆 | 峰值 106.2 MB，8 回合漂移 **+64.7 MB** |

   这是**回归**：八场景从 D-061 起被反复用于修复，P01 已把它降为 regression-only。
   它证明 rules 臂没有破坏状态/任务，不证明泛化。

2. **但它不是模型叙事通过。** `verify_run --forbid-program` 返回 1：8 个回合全部
   `narrationModel=rules`、`source=program`、`programNarrationAccepted=true`。同时语义侧
   仍加载 semantic 引擎 497 次生成、发出 **106 条语义 LLM 提示**（13.3/回合）。所以：
   - 叙事“去 1.7B”在这一臂成立（旁白 0 权重）；
   - “语义去 LLM”不成立（LLM 提示仍在）；
   - 产品模型叙事档（1.7B）与 20 输入/八场景默认臂未在本轮复跑。

3. **自建冻结构建：三次尝试，两次挂起、一次被租约挡住。**
   - 22:40 用 3177（语义 worktree 的服务）跑 4 回合：page 加载 chunk 631 404，driver
     挂起 45 min、0 回合；平台按自己的 PID 停掉。证据
     `platform-holdout-4-20261128-224003.json`。
   - 22:58 用自建 3180（HEAD `ede2b110`，BUILD_ID `FvDH…`）：页面 ready 17.1 s、权重
     1/1、`crossOriginIsolated=true`，第一回合挂起 45 min、0 回合、无 failure，同时
     持有租约；平台按 PID 停掉。证据 `platform-holdout-4-20261128-225817.json`。
   - 23:03 重建到 HEAD `99e07273`（`bY6e…`），3180 ready；租约被叙事侧 rules-b
     （PID 40028，3/8）长期占用，平台不抢、不释放别人的租约，deferred。
   驱动缺首回合看门狗已记入 P02；平台侧 `acceptance-sequence.py` 加了 420 s/0 回合
   即杀自己驱动的保护。随后等待租约的后台 waiter 因系统低内存被 Claude Code 停止
   （未开始任何回合），按提示未自行重启；需要用户确认内存恢复后再跑。

4. **移动档与真机。** 移动模拟 2 回合未跑（同一租约阻塞）；真机流程已写成
   `design/platform/phone-acceptance.md`（代理、字段、通过口径、已知 WebGPU 限制），
   尚无真机证据。模拟条件不能替代真机。

**Status.**

| 验收项 | 状态 | 证据 |
|---|---|---|
| rules 臂状态/任务回归（8 场景） | 通过（regression） | `rules8-scenario-report.json` |
| rules 臂模型/引擎核验 | 通过（语义引擎在、旁白程序） | `verify-rules8.json` |
| rules 臂作为模型叙事验收 | **拒绝** | `verify-rules8-product-gate.json`（exit 1） |
| 1.7B 默认叙事臂 | 未跑 | — |
| 20 输入 / 八场景默认门 | 未跑（另有 lane 在跑 rules-b） | `acceptance-attempts.json` |
| 移动模拟 | 未跑 | phone procedure |
| 真机 | 未执行（需用户手机） | `phone-acceptance.md` |
| 10 回合稳定性 | 部分（rules 臂 8 回合堆漂移 +64.7 MB） | `rules8-soak.json` |

**Verdict.** 零参数 rules 臂在冻结八场景上保持了状态与任务回归，首段/单点计时远低于
门槛，可作为“叙事无 LLM”的候选；但它是程序正文，模型叙事档未验，语义仍有 106 条 LLM
提示/8 回合。自建冻结构建的首回合挂起是当前产品路径的阻塞缺陷，驱动看门狗与页面
首回合超时必须在驱动侧修复后才能给出完整验收。

**Artifacts.** `artifacts/goal/platform/eval/{rules8-scenario-report.json,
rules8-timing.json,rules8-soak.json}`、`artifacts/goal/platform/{verify-rules8.json,
verify-rules8-product-gate.json}`、`artifacts/goal/platform/lab/{build-manifest.json,
acceptance-attempts.json,acceptance-sequence.py}`、
`results/product/evidence/platform-holdout-4-20261128-{224003,225817}.json`。P06。
