# N09 零参数叙事臂接入真实页面：3/3 回合、只加载 0.6B、正文 554–593 字

**Question.** N07 的零参数候选能否在 `/world-local` 真实页面上跑完整回合，且不加载、
不调用任何叙事语言模型？

**Setup.** `?narrationCandidate=rules`（内部实验臂，不是玩家设置），输入
`turns-3.json`（观察／移动／对话），验收驱动
`accept-world-local.mjs --allow-program`。规则臂完全不创建叙事引擎：`narration()` 在
引擎分支之前返回；页面把 `narrationEngine` 传成 `undefined`，证据里
`narrationModel=rules`、每回合 `source=program`。

**Results.**
- **只请求 1 个模型**（0.6B 语义，`models.requests=1`）；1.7B 对照运行是 2。
  `readyMs` 7.5–10.4s；三个回合全部 `problems=[]`。
- 每回合等 46.3–67.7s，全部花在 0.6B 结算上；规则叙事本身 0.07 ms/point。
- 每回合正文 554–593 字：场景只出现一次（位置、右墙、护目镜、诺诺各 1 次）、
  12 条 NPC 结算结果全部带结果短语、4 条时间行。
- 回合正文去重放在页面：只对**状态句**（现在在／屋里有／也在／贴着…）去重；同一事件
  真发生两次时，结果句保留。
- 修复/决定：
  1. 验收驱动新增 `--allow-program`：程序正文不是模型段，证据记录该标志，
     不能伪装成模型通过。
  2. 去重从生成端移到页面拼接：每 point 仍写完整场景，回合拼接时去掉重复状态句。
  3. 规则臂直读 `resultsText`，不受 `prompt.ts:229` 的 120 字结算截断影响；
     1.7B 臂仍受影响（23/117 个 point 丢结果标签）。
- 输入投影缺陷（两臂共有）：`declaredSafe` 会把“再抬头打量巷口和器材棚方向”整段丢弃，
  留下“看清楚，。”的悬空逗号。规则臂只做去尾标点，不补内容。

**Interpretation.**
- 产品路径已经能在一回合内完成“零叙事模型”的正文，且证据可核对（一个模型请求、
  `source=program`、无叙事引擎）。这是“去掉 1.7B”从离线实验走到真实页面的第一步。
- 仍不是可交付的叙事质量：句子是电报体，NPC 结果一句一条，开场句有时被输入投影截断。
  这些正是微模型要接的渲染任务（N08 的三个可枚举操作）。
- 产品默认未改：规则臂只在 URL 实验开关下可用；切换默认需要八场景、二十输入、
  离线、恢复、重生成与移动端的完整验收。

**Caveats.** 只跑了 3 个回合、一个世界；结算仍用 0.6B（本阶段允许）；`--allow-program`
是驱动的实验开关，不等于产品验收通过；移动端与离线尚未跑。

**Artifacts.** `artifacts/goal/narration-rules/{n09-evidence-slim.json,turns-3.json}`
（精简证据：每回合正文、`narrationModel=rules`、`source=program`、每回合 4/4/2 次
`task=narration, source=rule`、`models.requests=1`；完整 6.6MB 原始文件同目录
`smoke-rules-3i.json` 未入库）；
代码 `frontend/src/lib/world-engine/local/rules-narration.ts`、`game-model.ts`
（`narrationCandidate=rules` 分支）、`page.tsx`（`dedupeProgramPoints`）。N09。
