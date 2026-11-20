# Jity Goal v11 运行期与部署事实

状态：active。日期：2026-11-20。基线：`agent@695e6bd4`。

本文回答执行 agent 最常问的三件事：什么能改、什么只能当参考、状态到底由谁负责。与 [`goal.md`](goal.md) 或旧文档冲突时，以 [`decisions.md`](decisions.md) 为准。

## 1. 产品路径

`/world-local` 是唯一交付页：

- `frontend/src/app/world-local/page.tsx`：浏览器本地完整游戏页；加载静态世界、启动本地 transport/controller、运行端侧模型、保存进度。
- `frontend/src/lib/world-engine/`：产品内核。
- 根 GM 控制台、`/world` 规则页、Python CAMP/DeepSeek 栈：历史或对照，不投入新玩法。

`/world` 的 552148c 验收、H2/A3-2 冻结和 Python v2 协议记录继续各自有效，但它们不证明浏览器本地产品、真实模型语义或 20 输入交付。

## 2. 运行期权威

**浏览器 TypeScript 内核是运行期唯一的 apply、merge、commit、replay 权威。**

- `frontend/src/lib/world-engine/local/state.ts`：`buildInitialState`（:83）、`applyPoint`（:906）、`replayWorld`（:952）、`pointEntityDeltas`、`stateDigest`。
- `frontend/src/lib/world-engine/local/transport.ts`：32 个 v2 操作；当前 31 个已实现。每个写操作在 draft 上执行，整笔成功后才替换已提交记录，拒绝的候选不会留下半状态。
- `frontend/src/lib/world-engine/local/session.ts`：`LocalGameSession` 在 `ControllerDriver` 之上加持久进度、写入前 checkpoint、多标签租约与恢复。
- `frontend/src/lib/world-engine/local/game-model.ts`：真实端侧模型端口；把一次任务输入变成经过 codec 校验的 JSON/text。

Python v2 内核降为**开发期差分预言机、金标向量与迁移参考**：

- `backend/app/world_app.py`、`backend/app/services/world/`、`backend/app/schemas/world/`。
- 用途：生成 `artifacts/goal/kernel-diff.json` 的冻结向量；对拍 `buildInitialState`、`applyPoint`、`pointEntityDeltas`、`replayWorld`、canonical digest。
- TS 与 Python 不一致时按 bug 调查，不按「Python 说的算」直接改 TS。运行期玩家看到的状态只来自浏览器记录。

## 3. 静态 S0

开局只读取、校验、封存静态世界，不动态生成。

- `frontend/src/lib/world-engine/local/world-loader.ts`：严格 JSON 读取；拒绝重复 key 和非契约数字；校验 `WorldState`/`WorldInitialState`；从 `initial` 重建 S₀；比对注册摘要；不一致一律拒绝开局，不是警告。
- `frontend/src/lib/world-engine/local/static-world-registration.ts`：登记资产路径、`stateDigest`、LF 归一化文件哈希、`initialDigest` 与实体计数。
- 当前资产：`data/worlds/dragon-raja-free-day.world.json`，页面路径 `/worlds/dragon-raja-free-day.world.json`。
  - 规模：26 个地点、14 个人物、74 件物品、73 个任务。
  - `stateDigest`：`3f65452daf352c636ac4b24dcefcfb1cc8633ee811a6613a34ce5c43ef233f4e`。
  - `fileSha256Lf`：`6262d5fcf088959bb427fbd2dfef7472bcf2cbf78edb9c76b98d4ea2b25db92e`。
- 该世界是公开开发与展示材料，不是未见独立终验世界。跨世界验收是否需要 held-out 世界族见 `decisions.md` 的 `pending-user` 项。

## 4. 浏览器执行链

```
玩家输入
  -> LocalGameSession (ControllerDriver)
     -> 调度：按理智排序、冻结整组、骰点准入
     -> LocalGameModel：七类语义任务，逐任务调用端侧模型
     -> LocalWorldTransport：draft 上 apply/merge/commit
     -> checkpoint：IndexedDB 写入成功后才消费响应
     -> 叙事：只读已提交的 S_{t-1}/Δ/S_t
  -> /world-local 页面流式显示
```

- `state-invariants/`：point-continuity、任务层级、可见性检查；G2 接入 restore。
- `turn-execution/`：目标识别、反应、共同结果、六阶段的模型端口与提交。
- `semantics/`：action/skip 与 settlement 的语义处理。
- `narration-input/`、`narration-generation/`、`narration-candidates/`、`point-narration/`：叙事输入投影、生成、候选选择、逐点写入。
- `persistence/`：IndexedDB 进度存储；默认写者租约 30 秒（`DEFAULT_LEASE_TTL_MS = 30_000`）。transport 内部的 claim/lease 常量另算，按代码为准。
- `progress-sync/`：可选的两设备同步；服务器只存不透明快照。

页面证据钩子：

- `window.__worldTurns`：逐点输入、计时、模型身份、分段来源。
- `window.__worldArm`：叙事模型/候选/模式与模型文件 sha256。
- `window.__worldGpu`：GPU/运行时信息。

## 5. 模型资产

当前页面声明的模型（`world-local/page.tsx`）：

| 用途 | 文件 | bytes | sha256 |
|---|---|---|---|
| 语义 | `/models/Qwen3-0.6B-Q4_K_M.gguf` | 396,705,472 | 待 G3 清单固定 |
| 叙事默认 | `/models/Qwen3-1.7B-Q4_K_M.gguf` | 1,107,409,472 | `b139949c5bd74937ad8ed8c8cf3d9ffb1e99c866c823204dc42c0d91fa181897` |
| 叙事故障备选 | `/models/qwen25-1.5b-narr-Q4_K_M.gguf` | 986,048,096 | `6ed2268db2e1277933094c8b3af3348c18d6c0689244679a393c2008a1af5a0b` |

- `frontend/public/models/` 当前为空；GGUF 被 gitignore。G3 必须取得或重建资产，并产 sha256/bytes/license/获取方式清单。
- 页面第 5 行的「narration 0.5B」「localStorage」是过期注释；实际默认叙事模型是 Qwen3-1.7B，持久化走 IndexedDB，G4 清理。
- 不静默换权重；模型变体必须是产品实际服务的文件，并在 `__worldArm` 记录 sha256。
- 不冻结组件数量、每步模型或调用总数。选择依据是质量、成本、本地可运行性和实测时间，不是架构方便。

## 6. 七项工作职责

职责不是七个模型。可以由单模型、多模型、共享骨干、提示、程序约束或检索组合承担；每次实际调用必须记录在案。

| 职责 | 输入 | 输出 | 当前落点 |
|---|---|---|---|
| 行动判断 | 最新工作状态、任务、个性、输入消费状态 | `act`/`skip` 与行动文本 | `local/semantics/actions`、`local/game-model.ts` |
| 目标识别 | 已确认行动、当前世界 | 目标实体/位置候选 | `turn-execution/port.ts`、`local/semantics/settlement` |
| 被迫反应 | 目标、服务骰点/资格 | 反应候选，供冻结 | `turn-execution/` |
| 共同结果 | 全组冻结行动、完整骰点 | 结果候选 | `turn-execution/` |
| 六阶段变化 | 工作态、阶段依赖 | 位置→外貌→任务→新小任务→个性→理智候选 | `local/state.ts` 的 apply、`turn-execution/` |
| 继续判断 | 当前世界、本轮变化 | `continue`/`handback` | `controller.ts`、`schedule.ts` |
| 叙事 | 已提交 S_{t-1}/Δ/S_t、视角约束 | 中文正文 | `local/narration-*`、`point-narration/` |

模型输出永远是候选：模型不设置持久 ID、骰点或阈值；程序负责确定性校验、应用、合并、持久化与回放。

## 7. 持久化与同步

- 本地：IndexedDB 进度存储（`local/persistence/`）；每次 transport 写入先 checkpoint，再允许 driver 消费响应；刷新或崩溃恢复重建 scheduler memory，不重放已冻结行动或骰点。
- 多标签：默认 30 秒写者租约；过期可接管；旧标签的写入被 fence 拒绝。
- 可选服务器同步：`/local-progress` 只存不透明快照，校验 CAS、父链、单调修订号；冲突时展示分叉，由玩家选择 `keep-remote` 或 `keep-local-fork`。
- 离线：首次静态资源与模型就绪后，禁用游戏计算端点与保存服务仍可游玩与本地保存。

## 8. 对照臂与不可作验收证据的部分

以下保留自有价值，但不能作为浏览器本地产品的验收证据：

- Python v2 服务、H2 恢复冻结、A3-2 签收、`/world` 规则页的 552148c 验收。
- 固定命令、规则结算、固定 handback、模板正文、脚本候选。
- 旧 B3/组件实验、best-of-N、旧叙事门与训练结果：只作历史证据或候选来源，状态以 [`ledger.md`](ledger.md) 为准。

任何改动若影响 A3-2 冻结产品源码、契约或 H2 断言，按原规则重新固定组合并重跑；这不等于把浏览器本地产品重新拉回 Python 权威。

## 9. 证据路径

- `artifacts/goal/timing-baseline.json`：G3 逐点计时。
- `artifacts/goal/kernel-diff.json`、`kernel-ops.md`：G2 差分与操作定案。
- `artifacts/goal/semantics/`：G5 冻结场景与原始输出。
- `artifacts/goal/narration/`：G6 样本、原始输出、读评与时间。
- `artifacts/goal/sync/`：G7 两设备快照、父链、修订号。
- `artifacts/local-game-delivery/manifest.json`、`design/world-engine-reports/local-game-acceptance.md`：G8 交付证据。

大文件、权重、原始日志不入 git；在仓库内保存清单、哈希、取得方法与必要证据。
