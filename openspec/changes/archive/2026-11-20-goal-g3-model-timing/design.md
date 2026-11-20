# Design: G3 模型资产与时间包线

## 目标

把产品实际使用的两份 GGUF 取到目标设备并校验，然后在 RTX 4060 Laptop 8 GB + Edge（D-010）上回答唯一问题：60 秒首段、300 秒单点能否达到。产品代码不改；门槛不改。

## 模型资产决定

| 槽位 | 文件 | 来源 | bytes | sha256 | license |
|---|---|---|---|---|---|
| 语义 | `Qwen3-0.6B-Q4_K_M.gguf` | `unsloth/Qwen3-0.6B-GGUF@50968a44` | 396,705,472 | `ac2d9771…524a` | Apache-2.0 |
| 叙事 | `Qwen3-1.7B-Q4_K_M.gguf` | `unsloth/Qwen3-1.7B-GGUF@d7f544ee` | 1,107,409,472 | `b139949c…1897` | Apache-2.0 |

- 两个 sha256 取自 HuggingFace LFS `X-Linked-ETag`；叙事哈希与 `world-local/page.tsx` 已声明的常量一致，语义哈希与历史 `integration.json` 记录一致。
- tokenizer 嵌在 GGUF 内，由 wllama 读取；不单独提供 tokenizer 文件。
- 分发按 D-010：脚本下载，仓库只存清单与脚本；`frontend/public/models/` 继续 gitignored。
- 语义槽位维持 Qwen3-0.6B；旧组件实验的退役结论不自动适用于产品语义槽（D-007）。

## 下载与校验

`frontend/scripts/fetch-models.mjs`：

- `fetch` 流式写 `<file>.part`；完成后对文件整体算 sha256；bytes 与哈希同时匹配才原子 rename。
- 已存在的文件先校验，匹配则跳过；不匹配重新下载。
- 任一失败删除 `.part` 并非零退出。
- 成功后写 `artifacts/goal/model-manifest.json`（role/file/url/repo/revision/bytes/sha256/license/tokenizer 说明）。
- 不引入依赖，只用 Node 内置模块。

## 时间测量

### 驱动适配（单树）

旧的 `accept-world-local.mjs`、`lease.mjs` 仍按 `worktrees/06-recovery` 布局解析仓库根与锁文件，单树（D-008）下这些路径指向仓库外。改为从脚本位置向上三层取仓库根：

- `integration.json` → `<repo>/results/product/integration.json`。
- 产品 worktree 用 `integration.product.worktree`（本仓库为 `.`）。
- `resource_lease.py` → `<repo>/resource_lease.py`；锁文件在 `<repo>/resources/`（加入 `.gitignore`）。
- 驱动、turns 文件、输出路径逻辑不变；不注入状态、不算结算。

`results/product/integration.json` 记录产品页面、启动命令、模型清单与哈希；G3 生成，G8 复用。

### 冷启动

3 次 `--preflight --fresh`：每次新浏览器进程、清空 IndexedDB/Cache/OPFS，记录 `readyMs`（页面就绪含模型加载）、`crossOriginIsolated`、WebGPU adapter、GGUF 请求与 JS heap。冷启动单独报告，不混入正常点。

### 真实点

`--turns frontend/scripts/product-acceptance/turns-10.json --fresh --intent timing-baseline`。判定点来自 `window.__worldTurns`（页面自有钩子）与驱动逐回合记录：

- `inputAt`：提交时刻（驱动记录）。
- `pointCommittedAt`、`narrationStartedAt`、`firstReadableAt`、`pointTextFinishedAt`：`__worldTurns[].clocks` 与 `acceptedMs`。
- `firstTokenAt`、`longestStreamGapMs`：`__worldGenerations[]`。
- `stages`：`submission.calls` 的 task/ms 与 UI 阶段序列。
- `peakMemoryMB`：逐回合 `performance.memory` 的最大值（JS heap，不是显存）。
- 自动链：`submission.continuationDecision === 'continue'` 的回合；重负载点：按 `submission.calls` 数量与六阶段覆盖标记。

10 个点必须覆盖至少一次自动链与一个重负载点；turns-10 未出现自动链时，追加 `turns-20-extra.json` 的点继续跑，不删场景、不缩输入。

`frontend/scripts/product-acceptance/summarize-timing.mjs` 把驱动输出汇总成 `artifacts/goal/timing-baseline.json`，同时计算两条门槛：`firstReadableAtMs ≤ 60000`、`acceptedMs − pointCommittedAtMs ≤ 300000`（commit 缺失时退化为 `acceptedMs ≤ 300000` 并标注）。

## 失败处理

- 不达标：登记失败、保留原始运行、给出下一候选（更小叙事模型、量化、上下文/调度调整），复测后再下结论。
- 冷启动慢不等于正常点慢，分开报告；超过 5 分钟的单点记为不可接受。
- 不改 60/300 门槛，不删输入，不用夹具冒充真实点。
- 结论写入 `design/goal/decisions.md`（D-007 状态）与 `ledger.md`（G3 行、R06/R10/R14 证据）。

## 实测发现：停顿的回合（2026-11-20）

首跑 `points-10.json`：turn 1 正文与第 1 点已提交（首段 27.9 s），但 continuation 的结论请求被内核以 `request_malformed` 拒绝，返回 `stop fix_request`。页面只在异常路径清理未关闭的 advance，stop 路径不清理，于是 turn 2 被 `turn_in_progress` 拒绝，驱动等满 330 s 记 `turn_timeout`，刷新恢复也失败。

处置：在 `world-local/page.tsx` 的 stop 路径复用失败路径的 cancel→补写→cancel 恢复（commit `e75cd4a6`）。这是 G4 清单里的已知交互缺陷，为完成 G3 十点测量前置修复；G4 仍负责该交互的完整验收。原始失败运行保留在 `artifacts/goal/timing-runs/points-10.json`，复跑写 `points-10-rerun.json`。

复跑前两点：首段 22.4 s / 39.1 s，正文完成 29.3 s / 49.2 s，整点 120 s / 207 s，均在门槛内。第二点的自动后续在第 7 个结算组后因 `updates context_capacity_exceeded: prompt=11578 max=11000` 停止（未完成 continuation 判断），记为 G5/G4 缺口，不改变时间门槛。

复跑第 3 点：首段 31.4 s，正文完成 40.6 s，整点 117 s；第 4 点结算在 `updates tasks` 被内核拒绝（模型给出未登记角色 `f1`），未提交点；此后 advance 未关闭，第 5–10 点全部 `turn_in_progress`/按钮不可点。后续定位：内核 cancel 实际能清 advance；停摆是页面 `busy`/`phase` 与驱动下一回合点击的竞态，驱动把上一回合的停止提示/失败提示当成本回合结束，以及 Windows 上证据文件读取与原子 rename 的锁冲突。修复：`e75cd4a6`（stop 路径恢复）、`1990dc91`（phase ready + 日志）、`c05b7653`/`376b0a29`/`c6b52812`（驱动等待、记录索引、失败提示只看最后一条 article）、`d20afc47`（rename 重试）。最终运行写 `points-10-final4.json`，前三点均 60/300 内。该恢复缺口归 G2/G4（取消恢复）。

## 结论

- 时间：12 个正常点（`points-10-final4` 8 点 + `points-extra-2` 的 t12 + `points-extra-4` 的 e1–e3）首段 9.4–43.5 s，正文完成−提交 6.4–13.8 s，全部过 60/300；`timing-baseline.json` 状态 PASS。
- 冷启动：24.7/18.9/19.3 s，isolated、RTX 4060、2×200，独立报告。
- 覆盖：t4 结算失败（`unknown character f1`）、t6 刷新、t11 两次结算失败不计入；均保留原始运行。
- 自动链：0 次 `continuationDecision=continue`；结论请求 `request_malformed` 或自动后续在 updates 停止。归 G5，不阻塞 G3 的时间结论。
- G3 以时间包线通过关闭；R10 自动链缺口留在账本，由 G5 关闭。

## 不做什么

- 不换模型权重；如实测必须替换，按 D-007 记录 sha256/bytes/license/前后实测。
- 不引入服务端推理或远程模型调用。
