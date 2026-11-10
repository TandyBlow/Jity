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

## 2026-11-10：浏览器本地闭环与两档叙事模型实测

本轮在 `world-narration-model` 分支的工作树里跑通了「浏览器本地完整回合」，并把叙事模型从「格式兼容的旧 checkpoint」换成按同一输入格式训练的小模型。所有数字都来自真实 Edge + wllama + WebGPU（Intel iGPU），不是离线推理。

### 已落地

- `frontend/src/lib/world-engine/local/`：Python 状态内核的 TypeScript 移植（canonical 摘要、apply/preview/replay、时间推进）、v2 写入协议（lease、结算、提交、叙事认领）、`LocalGameSession`（复用真实 `ControllerDriver`）与 `LocalGameModel`（行动/目标/反应/结果/更新/继续/叙事七类任务）。
- `frontend/src/app/world-local/page.tsx`：可直接游玩的页面。加载 `dragon-raja-free-day.world.json`，本地跑两个 GGUF；每回合结算后把快照写进 `localStorage`，刷新恢复；全程不调用任何游戏 API。
- `wllama-engine.ts`：模型改为先 `fetch` 成 Blob 再交给 wllama（`directBlob` 默认 true），绕开 OPFS 配额错误；同时保留 `useCache` 开关。
- `narration-alignment.ts`：新增 `knownPositions`（在场但本回合没动的人不算「无事实站位」）与 `allowedEvents`（玩家已声明的动作动词可以在正文里出现）。
- `game-model.ts`：叙事改为句级修正——只删掉违反已结算事实的句子，保留其余文学正文；整段都不合格时才退回结算摘要。新增「不要复写事实清单」「不要写时间/地点/人物标题」「不要 Markdown」三项校验。
- `run-page-play.mjs`：无头 Edge 连跑 5 次真实行动，逐回合记录耗时、正文与修正说明，并在最后刷新验证存档恢复。

### 实测（同一台机器，WebGPU）

| 项目 | 数值 |
| --- | --- |
| 页面就绪（0.6B 语义 + 0.5B/1.5B 叙事） | 31–48 s |
| 单回合（结算 + 正文） | 33–60 s |
| 五连玩 | 全部完成，刷新后 `restored=true`，快照 ~780 KB |
| 0.6B 语义模型单任务 | 目标 5–6 s、结果 0–3 s、更新 10–15 s、继续 3–5 s |
| 1.5B 指令模型写 250–350 字 | 15–34 s |
| 0.5B LoRA 写 300–400 字 | 10–20 s |

### 失败与据此做的改动

- 1.5B 零样本会把提示里的「文风参考」和事实清单原样抄出来，5 个回合里 4 个被整段替换。删掉示例、把事实压成一段话后，抄袭消失但出现「时间：15:21 地点：西回廊」这类字段表 → 增加结构校验。
- 0.5B LoRA（199 行手写正文，按同一格式）能通过事实门禁，但对话内容与场景无关、重复句子多，不能作为产品正文。
- 旧的 0.5B「narration」checkpoint 只会续写 `【正文】` 旧格式，指令式输入下输出混乱；保留为对照，不进产品路径。
- `factcheck_yuyan.py`：把事实门禁搬到数据集侧，逐句标注「新增事件 / 未投影人物 / 未完成却宣称完成 / 未验证数字」。199 行金标里只有 6 行整行通过，说明手写正文本身就大量越界——这也是旧模型学会编造的原因之一。

### 数据与训练

- `build_instruct_rows.py`：把 199 行投影成「紧凑事实 → 正文」，prompt 与浏览器端逐字一致；手写正文经门禁过滤后 191 行可用。
- 7B 教师改写（Qwen2.5-7B-Instruct，4090D，5 批并发，473 s）产出 199 条，过滤后 197 条可用；两路合并成 `rows-v2.jsonl`（389 对）。
- 0.5B LoRA（r16，2 万步以内）在 4090D 上 10 s/epoch；dev 在第 2 轮最低（2.52），之后过拟合。
- 1.5B LoRA（r16，lr 1e-4，batch 4）40 s/epoch，dev 在第 4 轮最低（1.839），第 10 轮升到 2.359；采用第 4 轮权重。

### 1.5B LoRA 接进页面之后（2026-11-10 下半场）

- 合成：`merged15`（base + 第 4 轮 LoRA）→ GGUF f16 → Q4_K_M 941 MB；页面叙事模型换成它。
- 同一条链路（真实 Edge + WebGPU）五连玩两次：`page-play-15b.json`（每段 340 token）与 `page-play-15b-short.json`（220 token）。
- 每回合耗时：340 token 档 54–136 s；220 token 档 34–72 s（均值 52 s）。结算本身 20–30 s，正文首字在结算结束后 5–10 s 出现。
- 正文质量：句子通顺、有明显文学腔，人物对白连贯；仍会自行补道具和往事（护目镜裂纹、装订间、缆车广播），位置与任务完成的越界由门禁逐句删掉并在页面标注。
- 0.5B LoRA 对照：同样五连玩可跑完（33–60 s/回合），但正文是无关对话循环，不作为产品模型。
- 因此当前产品配置：语义 `Qwen3-0.6B`，叙事 `Qwen2.5-1.5B + LoRA`，两者都在浏览器里跑；页面只写 `localStorage`。

### 下一步

1. 训练数据补「同一条事实的多种写法」和「房间内可用道具」，减少模型自造道具的动机；每轮训练后都用 `run-page-play.mjs` 复测，不接受只看 dev loss。
2. 叙事提示里加入本回合结算结果原文，让模型复述已结算结果而不是自行编结局。
3. 语义侧：NPC 自主行动目前被「玩家必须点名」限制，等叙事稳定后放开，并给行动加可见范围约束。

## 2026-11-10（第二批）：主树集成与真实页面闭环

- 合入 05/01/02/03/04/07/08/09/10 分线提交；`game-model.ts` 的行动、牵连、反应、共同结果、六阶段更新改为分线处理器，删除单人结算捷径、文本行解析、关键词移动兜底和自动回合次数上限。
- 六阶段改为场景范围（主角 + 同地点 + 携带物 + 房内物品），地点表保持完整；范围写入 evidence。
- 玩家句子走向相邻地点而六阶段没有给出位移时，用结构化位置问题补进 position 阶段；`page-play-move-injected.json` 证明主角真的到了西回廊。
- 叙事改为两遍有界生成：自由稿 + 草稿改写稿；逐句事实支持过滤、对齐违规再剪、不足 80 字回退草稿。真实页面最近四轮全部回退（`low_support`）。
- 真实耗时：单回合 112–159 秒；`results` 13–14 秒、`updates` 65–75 秒、`narration` 23–62 秒；刷新恢复成功。
- 失败记录：0.6B 在 `results` 给物品写 effects、在 `updates` 把字面量 `id` 当实体、任务覆盖不全；1.5B LoRA 经常新增动作/对白/往事，逐句过滤后不足 80 字。
- 结论：闭环成立，正文未达标，首段可读文本 75–140 秒，超过一分钟要求。记录见 `integration-2026-11-10b.md`，证据在 `artifacts/local-game/`。
