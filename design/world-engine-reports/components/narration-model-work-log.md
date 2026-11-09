# 浏览器本地完整游戏：准备日志

准备核对时间：2026-11-10T00:35:23+08:00。本轮仅修订 goal 与准备分支，没有启动 goal 实现、推理实验或 HPC 训练。

## 分支与工作树

- 任务分支：`world-narration-model`。
- 基线及当前 HEAD：`1ab6ca791f97529a7bffed1f4837bf81a28badcb`。
- 独立工作树：`D:/others/Jity/.local/world-narration-worktree`。
- 主检出仍为 `D:/others/Jity` 的 `world-server`，未切换、清理或带走其他任务改动。
- 分支创建前目标分支、目标工作树路径均不存在；创建后原始检出干净。
- 本地缓存的 `origin/world-components` 与所选基线一致；本轮未 fetch 或检查实时远端，不将缓存当作远端同步证明。
- 新任务分支仅在本地创建，尚未推送、未设置 upstream、未新增提交。
- 用户允许提前建分支；goal 文件保留本地，不要求提交。其余准备文件也尚未暂存或提交，不能称为已发布交付；正式实现和产物版本化沿 goal 第 0 节执行。

## 准备文件

以下五份从主检出复制而来，复制前确认目标均不存在，复制后逐字节及 SHA-256 一致。此工作树成为后续实现的工作位置；主检出保留原文件，没有移动或删除。

| 文件 | 准备时 SHA-256 |
|---|---|
| `design/narration-single-model-goal.md`（v8，本地任务书） | `af08cd5671f70521d36f1cb920a4ebe16b887b6355d385c42cd59292f7b8c77d` |
| `design/world-engine-reports/components/narration-input-adapter.md` | `f5ea74addf1ca7a4a0d9201389717d09060c0a0cfe8e6bec1eaf8aad60a91f7f` |
| `data/worlds/dragon-raja-free-day.world.json` | `6262d5fcf088959bb427fbd2dfef7472bcf2cbf78edb9c76b98d4ea2b25db92e` |
| `data/worlds/README.md` | `f9ec9a29763e3fae4e81aab0b2706deac473061c6e895bef6932ae6583ff6022` |
| `scripts/build_free_day_world.py` | `3049a9cc364780638b899eca7da129c6a8121d2645a0de2b2cf8ae6ac3116086` |

v8 已核对：同题格式配对、固定行 id/目标/划分、金标进入验收与完成条件、长输入质量分层、输入依赖投影差分、四项输入版本清单、goal 不要求提交。历史权重与新权重比较不直接作结果块因果结论。

## 已确认的开工依赖

准备工作树中运行 `python -X utf8 scripts/build_free_day_world.py` 未通过导入：`ModuleNotFoundError: No module named 'app.services.world'`。所选基线是叙事来源，未含 `world-server` 的 Python 状态服务；不能将主检出原有的成功校验误写为新工作树已可独立运行。

可定位的内核来源为主检出提交 `fc60a603c7e0b57805fffea0458192bcfebf6ffc`。本轮只核对该提交存在：

- `backend/app/services/world/state.py`，Git blob `6aabbbcc71308b56da34d5199fbd274b3abef7da`。
- `backend/app/schemas/world/contracts.py`，Git blob `0e23aa73524ee1f22d23bd57b57f36638c0ac8d4`。

正式实现时先按来源提交审查、复用必要内核及其依赖，再在本工作树复跑素材校验与浏览器移植。不要只复制这两个文件就假定依赖齐全；不要以读取主检出的未提交工作文件来掩盖工作树缺口。本轮没有合并该分支，也没有实现浏览器内核。

## 下一步（等待正式执行）

1. 复核远端、来源提交和数据侧实际版本，保留本地 goal；将需要受版本控制的规格、素材和实现按独立改动提交。
2. 补齐已识别的内核依赖并复跑静态素材校验。
3. 按 v8 生成金标和真实投影、冻结公开诊断样本及长度分层，再开展有证据的实现与训练选择。

此清单不是已开工承诺，不替代用户后续启动 goal 的指令。

## 2026-11-10：v10 同步与执行入口修正

用户要求修正 v9 并提供新的 `/goal` 启动文本。本轮只修改任务书、配套规格和本日志，没有启动训练、提交或推送，也未改动现有实现。

- 当前任务分支仍为 `world-narration-model`；同步前观察到 HEAD 已推进至 `3ca3d8eee7fbd408e4fb076b3e79762bc52395f7`，并有 `frontend/src/lib/world-engine/runtime/wllama-engine.ts` 修改及 `frontend/public/`、`frontend/src/lib/world-engine/local/` 未跟踪工作。本轮保留这些成果；上文“尚未新增提交”等描述仅对应最初准备时点，不能据此回退分支。
- 主检出 goal 从 v9 修为 v10，执行工作树从 v8 同步到同一 v10。此前两个版本备份在主检出的 `.local/goal-backups/`，不依赖临时目录。
- goal SHA-256：`e37264ad0399164f98da2ec5d01b7de7a2790e02a9e6027aba8f3367ad9295c6`。
- 输入适配规格 SHA-256：`5f100d6b0656b846cc94cefa512b8f91a39e6fb209162668fb46c61e6c632bb3`。
- 两份文件在主检出与执行工作树逐字节一致；12 项修订条款核对通过。goal 继续保留本地、不要求提交。
- v10 对实际采用的导出、量化或降精度做验证，不强制 ONNX、4 比特或统一绝对误差阈值；保留异常调查和实际浏览器质量要求。D 线数据可经质量检查用于训练，旧资格门禁可有依据地调整，隔离诊断不得冒充最终通过。
- 在当前工作树重跑 `python -X utf8 scripts/build_free_day_world.py`，仍报 `ModuleNotFoundError: No module named 'app.services.world'`。该依赖尚未补齐；后续执行先按来源提交取所需状态构建/摘要代码及依赖并复测，不把文档核对通过当成素材在本工作树运行通过。

后续执行从现有工作树与最新日志继续，不重建分支、不清理未知改动。优先完成真实可玩闭环并暴露实际生成效果，按 v10 的完整产品与质量要求持续推进。
