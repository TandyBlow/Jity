# 前端 CSS 地基重构 —— 问题清单

基线 commit：`60ce656`（Playwright 截图 + 尺寸探针，图不入库，探针 JSON 入库）
基线与尺寸数据：`docs/frontend-baseline/`

所有 A 类条目均已逐条读过代码或量过数值。B 类是产品问题，未做判断。

---

## 当前状态（2026-09-24 更新，接手先读这一块）

**已交付**：地基三件套（`60ce656`…`3d80f7b`）、6B 回放侧（`dc0a0a8`…`47a11ed`）、6A + 6D（`16c2e9c`）、
6E.4 层级 + 窄屏抽屉 + A11（`b9e90b8`、`431b8eb`、`933677b`）、
**A19/B7 空输入静默无反应（`612bb84`）**。

**验证状态**：后端 430 / 前端 43 / Playwright 30。**但那个 30 不含像素验收** —— 见文末"两个流程陷阱"，
`capture.spec.ts` 按字母序排在 `verify.spec.ts` 前面，会先把当前渲染覆写成基线，verify 再拿它跟自己对。

**下一步该做什么**：不是继续改前端。这套观察面已经能用了 —— 去跑 270 轮实验，让真实数据说明还缺什么。
前端需求的源头是研究课题（上下文工程与记忆管理），不是相反。

**若一定要继续改，剩下的按价值排序**：
1. ~~`useGameActions.ts:41` 输入框为空时静默无反应~~ → **2026-09-24 已修，`612bb84`**，见文末。
   顺带留了一条故意没修的：按钮 disabled 查 `pendingGenerate`，Ctrl/⌘+Enter 的守卫不查。
2. B4 四个页面的全局导航（范围仍未定：四页，还是三页）→ **代价已实测，见文末"B4 的实测代价"**。
3. 节点对比面板没有像素基线 → **已查清为什么现在做不出来，见同一节末段。**
4. 6E.1/2/3 的字号/间距/圆角像素合并 —— **不推荐**，理由见下文 6E 那节

**本文档读法**：下面的"问题清单"（A/B 两大类）是最早写成、部分已被后续实测推翻；
**以每节开头的日期和"已推翻"标注为准**，不要直接采信 A/B 清单里的数字。

---

## A. 已验证的缺陷

### 样式层（第 1、2 项会顺手修掉）

- **A1** `--line` 被引用 3 处（`globals.css:987,1026,1142`）但从未定义，fallback 到 `currentColor`，边框画成文字色
- **A2** `--text-muted` 被引用 1 处（`globals.css:1584`）但从未定义，该声明失效
- **A3** `.main-check-secondary` 在 `globals.css:1805` 和 `:1853` 重复声明
- **A4** 两个内容不同的 `@media (max-width:760px)` 块（`globals.css:1504`、`:1902`）
- **A5** `.start-here-btn`（`AnchorTree.tsx:63`）在 CSS 里零定义，全靠行内样式撑着
- **A6** `:root` 之外 126 处裸色值（37 处 hex + 89 处 rgb/rgba）
- **A7** 3 个 `infinite` 动画（`globals.css:273,459,1668`）未被 reduced-motion 覆盖；该块（`:195-201`）只处理场景背景视差，不关任何动画
- **A8** `.player-controls-row textarea:focus`（`globals.css:440`）设了 `outline: none` 且只改边框色 —— 唯一的输入框上键盘用户看不出焦点

### 交互缺陷

- **A9** `.player-controls` 是 `position: sticky; bottom: 0`（`globals.css:399-401`），高 150px，浮在内容之上；`.story-panel` 只有 `padding: 22px 28px`，没留底部空间 → 遮挡其下内容
- **A10** 剧情推进挂在 CSS 动画的 `animationend`（`StoryPanel.tsx:202`）→ 动画不跑流程就停，且无提示
- **A11** `MainCheckOverlay` 是全屏模态（`fixed inset 0`，z-80）但只有 `aria-label`，没有 `role="dialog"`、`aria-modal`、焦点陷阱、Escape
- **A12** 删 arc 无确认（`ArcEditor.tsx:28`），连带删掉其下所有 session 与 anchor
- **A13** "从此处继续"回退活会话无确认，随后 `window.location.href = "/"` 硬跳转（`useTimelineData.ts:124-136`）
- **A14** `loadNode` 无 in-flight 守卫（`useTimelineData.ts:43-52`）→ 快速点节点竞态，后到响应覆盖先到
- **A15** 时间线 tab 有 `role="tab"`，无 `aria-selected`/`aria-controls`/方向键（`timeline/page.tsx:81-85`）
- **A16** 切换战役静默丢弃当前编辑（`curator/page.tsx:29`）

### 错误与数据

- **A17** `useTimelineData.ts:57-59` 三处 `.catch(() => null)` 加 `:82-83` 的 `.catch(() => setArcs([]))` → 加载失败显示成空白树，与"确实没内容"无法区分
- **A18** `useCuratorEditor.ts:32` 战役列表加载失败只 `console.error` → 空下拉框和后端挂掉无法区分
- **A19** `alert()` 阻塞主线程（`useGameActions.ts:165`）；`window.prompt()` 用系统弹窗建存档槽（`SettingsMenu.tsx:37`）
- **A20** `filename` 是自由文本输入框（`curator/page.tsx:87`），直接当服务端写入路径，无校验、无覆盖警告
- **A21** `ReviewPanel.tsx` 硬截断 15 条锚点 + "…还有更多"，无展开入口
- **A22** session id 失效 → 静默新建自由模式会话，丢战役上下文（`useGameEffects.ts:53-61`）
- **A23** 同一套会话握手散落 4 处：`"jity_active_session_id"` 出现于 `useGameActions.ts:19`、`useGameEffects.ts:22`、`useTimelineData.ts:130`、`timeline/page.tsx:43`；`"campaign_entry"` 出现于 `useGameEffects.ts:44/47`、`AnchorTree.tsx:67`。全部无版本、无校验
- **A24** `generateFromNovel`（`api.ts:189-210`）绕过 `request()`，重解析 base URL 并重复实现错误处理；`api.ts` 内 9 个函数使用内联响应类型
- **A25** 时间线刷新间隔硬编码 2 秒（`useTimelineData.ts:110`），无暂停

### 结构

- **A26** `layout.tsx` 是裸 `<body>{children}</body>`，四个路由只能从 `/` 进、只能回 `/`
- **A27** `SidePanel.tsx` 是死代码（自 2026-09-10 `cf819d7` 起无任何引用，已全历史核实）
- **A28** `/curator` 有 22 个元素带行内样式，并借用 timeline 的页面外壳类（`.timeline-shell`、`.timeline-header`、`.timeline-layout`、`.clue-board`）—— 代码组织问题，非设计问题

### 可测量的体验缺陷

- **A29** 单轮内容可能高过视口。真会话 1440×900 下 `.narration` 高 952px（视口 900px），选项列表 `top=1368`。
  **更正（2026-09-23）**：控制台**一次只渲染一个回合** —— `StoryPanel.tsx:154-206` 只映射 `output` 单个对象，没有历史数组，每轮整块替换（用户已确认）。所以这不是"历史堆积把选项挤下去"，而是**单轮旁白本身就读不完**。读完整段再选，是自然流程，**未必是缺陷**。降级为待定，见 B1。
- **A30** 宽度 <1100px 时记忆面板 `display:none`；1024 下剧情区拿到全宽 1024，但 `.scene-output`/`.option-list` 仍是 860 宽居中于 `left=82` —— **释放出的 360px 一点没用上，只变成左右各 82px 空白**

---

## B. 待回答的产品问题

每条给出：事实 → 现状可能正确的理由 → 需要你回答的问题。

- **B1 剧情区的滚动模型**
  事实：选项固定在内容流末尾，随剧情增长越沉越深（真数据线下 468px）。
  现状可能对：若产品本意就是让玩家回看历史（似读小说/回放），滚动是特性；研究场景下你也可能要靠滚动检查前面回合。
  **问**：跑到第 20 回合时，打开页面第一眼应该看到什么？

- **B2 记忆面板里 RAG 命中的归属**
  事实：`MemoryPanel.tsx` 把 RAG 检索命中（标题、分数、关键词）与玩家状态（NPC/物品/任务/长期事实）排在同一面板，位置在最末。
  现状可能对：本项目研究主题即上下文工程与记忆管理，把检索命中和状态放在一起**很可能就是研究仪表**，是有意为之。
  **问**：这是给玩家看的还是给你做研究看的？两者是否要分开？

- **B3 记忆面板在窄屏下隐藏**
  事实：<1100px 直接 `display:none`，无任何替代入口。
  现状可能对：若你的分析始终在 1536 宽屏上进行，这个分支永远走不到，那它是死代码而非缺陷。
  **问**：需要窄屏/移动端吗，还是可以明确不做？

- **B4 四个页面之间的关系**
  事实：`layout.tsx` 是裸 body，四个路由都只能从 `/` 进、只能回 `/`；`/curator → /timeline` 需退两次。
  现状可能对：若 curator 与 timeline 分属不同阶段、从不来回切，发散射状结构足够。
  **问**：实际工作流是什么？"生成战役 → 编辑 → 跑 → 看时间线"里哪几步会来回跳？

- **B5 `/dev-log` 的定位**
  事实：文档高 10515px（1024 下 11188px），12 条全展开；筛选条件不进 URL，刷新即丢。
  现状可能对：它是个人内部变更日志，长滚动无所谓，筛选也不值得分享。
  **问**：只给你看，还是团队/对外也要用？

- **B6 存档槽用系统弹窗**
  事实：`SettingsMenu.tsx:37` 用 `window.prompt("新存档名称:")`。
  现状可能对：可能只是临时实现，功能正常，不急换。
  **问**：换成正经界面，还是先留着？

- **B7 错误呈现策略**
  事实：`alert()` 阻塞 + `window.prompt()` + `console.error` 静默 + 内联 error，四种并存。
  现状可能对：研究阶段快速迭代，`alert` 最省事、最不可能漏看。
  **问**：你要"绝不能漏掉"，还是"别打断我"？

- **B8 时间线轮询**
  事实：2 秒写死，无暂停开关。
  现状可能对：自动播放观察模式需要它持续跟随。
  **问**：保留吗？非自动播放模式要不要关掉？

- **B9 视觉基线的视口**
  事实：当前基线用 1440×900 与 1024×768；实测你的屏幕为 1536×864（工作区 1536×816，浏览器视口约 1536×730）。
  1024×768 是你屏幕上不会出现的状态，用它当主要证据曾导致误读。
  **问**：基线是否换成 1536×730 加一个宽屏（如 1920×1080）？

---

## B 的答复与处置

- **B1 已答：要自动滚回顶部。** 原提问基于错误前提（以为剧情区会累积历史），已作废。事实：控制台一次只显示一个回合，整块替换。要求：**新一轮到达时自动滚回顶部**。
  → 新增 **A35**。注意这是**行为变更**，不属于 CSS 地基（地基的验收标准是外观零变化），归入第 6 项信息架构。
- **B2 做研究看，可以分开** → RAG 命中从玩家面板拆出。新增 **A31**。
- **B3 需要窄屏** → A30 由"待定"升级为**确认缺陷**；响应式正式纳入范围。
- **B4 未定** → 建议先做最小全局导航（统一顶栏放四个入口）。成本低、不锁定更多结构，可随时撤。
- **B5 只给本人看** → 日志的长滚动与筛选不进 URL **不构成问题**，降级、不排期。
- **B6 换** → `SettingsMenu.tsx:37` 的 `window.prompt` 换成界面内输入。新增 **A32**。
- **B7 不能漏掉** → 规则确立：**每个错误都必须可视呈现**。据此 A17、A18 优先级上升（静默 `console.error` 是直接违反项）；A19 中 `alert()` 的阻塞本身符合要求，要改的是统一呈现方式，不是取消弹出。
- **B8 需澄清自动播放是什么**（见下），待你确认跑实验走哪条路径。
- **B9 基线改为 1536×730（实际视口）+ 1024×768（窄桌面）**。1024 不再用于"诊断你的日常体验"，而是 B3 确认需要窄屏后的正式测试目标。

## 新增条目

- **A31** `MemoryPanel.tsx:71-104` 的 `RagHits`（检索命中、分数、关键词）与玩家状态同面板。B2 已确认研究用，应拆到独立界面。
- **A32** 存档槽创建用 `window.prompt`（`SettingsMenu.tsx:37`），B6 要求换成界面内输入。
- **A33 全前端没有任何滚动管理。** `scrollIntoView` / `scrollTop` / `scrollTo` 在整个 `src/` 零命中。
  `.story-panel` 是 `overflow-y: auto` 的滚动容器。回合替换时 DOM 内容整体换掉，但容器的滚动位置**不会被重置** —— 上一轮如果停在中间，新一轮也从中间开始显示，开头看不见。
  机制上确定（浏览器行为 + 代码零滚动管理）；**尚未端到端跑一次生成实测**，需要时加 mock 验证再定为缺陷。
- **A34 已撤回。** 原先据 B8 判为"删除时间线 2 秒轮询"，但 B8 的答复被误解，条目作废。`useTimelineData.ts:110` 的轮询**保持不动**。B8 整条已删（我理解错了"关掉"的意思）。
- **A35** 新一轮剧情到达时自动滚回 `.story-panel` 顶部（B1 已答"要"）。**行为变更，不属于 CSS 地基**，归入第 6 项。

## 进度（2026-09-23）

- **第 1 项 完成** `60ce656`／`90238f4`：Playwright 基线，视口 1536×730 + 1024×768（B9）。图不入库，探针 JSON 入库。
- **第 2 项 完成** `90238f4`：`src/app/styles.test.ts` 四条静态断言。新增"扫组件文件里的 `var()`"一条 —— 它抓到了 token 改名漏掉的 4 处 TSX 引用。
- **第 3 项 完成** `44721ea`／`0ddcb96`：token 层 + 文件拆分。两次都是**零像素差异**（6 页面 × 2 视口，容差 0）。
  - `globals.css` 1918 行 → 13 行；最大文件 `timeline.css` 634 行
  - 裸色值 111 行 → 81 行
  - `--line` 三处按"保持不渲染"处理（未定义 `var()` 会让整条 border 简写失效）
- **间距 / 字号 / 圆角 / 层级的 token 化：移到第 6 或第 10 项**，与像素改动一起做。理由：只改名不合并收益仅形式，要合并就改像素，而这一批的验收是零差异。
- **第 4 项 完成** `0ac0a7b`：`lib/api.test.ts` 16 条，纯 Node + 假 fetch，不用 jsdom。
- **第 5 项 完成**：把原本不渲染的东西用正确值激活。**这一批改变了像素，基线已重录。**
  - `--line` 三处边框恢复为 `var(--color-border)`（`.timeline-tabs`、`.story-tree-scroll`、`.story-node-detail`）
  - `.autoplay-banner span/small` 恢复为 `var(--color-muted)`
  - `.start-here-btn` 补真实样式（此前无任何规则，被 Tailwind preflight 抹成裸文字），同时删掉 TSX 里的行内样式
  - 量化：`.timeline-tabs` 高 52→53（那条边框），下方整体下移 1px；`.anchor-tree` 高 937→945。console/curator/dev-log **零变化**
  - 基线文件 `layout-probe-before.json` 已被 `layout-probe.json` 取代

**地基三件套（第 1–5 项）到此全部完成。** 下一步是第 6 项（主界面信息架构），间距/字号/圆角的 token 化并入其中。

## 自动播放是什么（回答 B8）

浏览器端自动跑完整场：URL 带 `?autoplay=1&session=…&turns=N&delay=MS&seed=S` 打开控制台即启用。
- 选项由 `lib/game/autoPlay.ts` 的 `chooseGoalAwareOption` 自动挑：中文关键词打分（推进 +12、继续/前往 +10、调查/进入 +9；等待 −8、拒绝/离开 −7、什么都不做 −10），加当前目标短语匹配（目标切成 2/3/4 字片段计数，上限 18），减最近用过的（−5），再加固定种子的抖动
- 骰子用 `seededRoll(seed + turn*7919)` **无界面判定**，结果按手动路径同样格式拼进行动文本
- 隔 `delayMs`（默认 200ms）自动生成下一轮，到 `turns`（默认 300）或 `game_over` 停；出错最多重试 10 次，指数退避上限 30 秒
- 控制台显示 `.autoplay-banner`，记忆面板多出「战役锚点」区块；`/timeline?autoplay=1` 是"实时观察模式"，**每 2 秒轮询**——那是 A25 里那个写死的 2 秒轮询唯一的用途

另有一条后端路径：`scripts/auto_play.py`。
**待确认**：跑实验你走哪条——浏览器 `?autoplay=1`，还是 `scripts/auto_play.py`？若只走后者，A25 的轮询在正常使用中永不激活，可降级。

---

## 第 6 项（重新定义）：记忆观察面

### 需求（2026-09-23 用户确认）

- **观察方式**：实时盯着看 + 跑完回头翻，两者都要
- **规模**：上百轮（如 270 回合）
- **要判断的**：① AI 记对了没有（幻觉）② 系统该记的记了没（去重/裁剪/合并有没有弄丢）③ 上下文里塞了什么（检索命中与分数）④ 状态怎么递变（NPC/物品/任务/事实 的增删与遗忘）

**结论：侧边栏面板做不到这件事。** 需要"实时侧 + 回放侧"两个面，且回放侧按轮次定位、可跨轮对比。6B 才是 270 轮实验真正用得上的那个，6A 是配菜但见效快。

### 能力盘点：数据在哪、现有接口给不给

| 判断维度 | 数据位置 | 现状 |
|---|---|---|
| ① AI 记对了没有 | 每轮的 `StoryOutput.memory_updates` | **纯前端可做** —— `/timeline` 节点详情已返回 `output` |
| ② 系统该记的记了没 | 相邻两轮节点详情的 `state` 对比 + ①的声明 | **纯前端可做**，需前端算 delta |
| ③ 上下文里塞了什么 | `model_outputs.retrieved_chunks_json` | **缺后端接口** —— `GenerateResponse.retrieved_chunks` 只回当前轮 |
| ④ 状态怎么递变 | 节点链上的 `state` 序列 | **纯前端可做**，需跨轮聚合 |

### 已验证的事实（后续可直接用）

- **`memory_updates` 前端收得到、类型定义齐全（`src/types.ts:46-55`）、全仓零组件渲染它。** 这是本次最大的发现。
- 456 条 `model_outputs`：**294 条（64%）有真实记忆变更**，162 条（36%）只有空的 `player_status_patch` 壳。字段频次：`npcs_upserted` 252、`world_facts_upserted` 247、`key_event` 292、`current_location` 291、`quests_upserted` 188、`items_upserted` 143、`items_removed` 3。
- `memory_updates` 是 **LLM 的声明**，不等于应用结果 —— 之后 `apply_output` 去重归一化，`enforce_state_caps` 还会裁到 20 物品/15 NPC/10 任务/15 事实。**两者不一致才是研究价值所在，界面要能看出差异。**
- `/timeline` 的 `TimelineNodeDetail` 已含每轮 `output`（含 `memory_updates`）与完整 `state`。
- `_memory_controller`（MOOM/NSB/PCB/SCORE 子系统的状态）被 `game_state/manager.py:163-166` 的 `sanitize_state` **主动从响应里剥离**，前端永远看不到。27 个会话里只有 4 个有内容，且 `narrative_pool`/NSB 摘要/PCB persona 全空。**用户知情，暂不处理。**

### 任务拆分

**6A 实时侧（`/` 记忆面板）**
- 6A.1 「本轮记忆变更」区块，渲染 `output.memory_updates`，置面板顶部；无有效变更时不显示。复用 `lib/game/format.ts` 的 `memoryDetail()`
- 6A.2 同一区块里标出**声明与应用结果的差异**（哪些被裁掉/去重掉了）
- 6A.3 `RagHits` 包进 `<details>`；默认展开（面板是观察窗口），收起状态记 `localStorage`
- 6A.4 现有 NPC/物品/任务/事实/最近事件分组折叠

**6B 回放侧（`/timeline`，270 轮实验的主力面）**
- 6B.1 按轮次定位（跳转到第 N 轮），现有节点树无此能力
- 6B.2 节点详情显示该轮的 `memory_updates`（目前只显示旁白/对话/选项/state 预览）
- 6B.3 相邻轮 state 差异对比（选两轮，看谁进来了、谁丢了、什么被裁了）
- 6B.4 某个 NPC/物品/事实/任务的存续轨迹（哪轮出现、哪轮消失）

**6C 后端**：暴露历史轮次的检索命中与指标（`retrieved_chunks_json` / `token_count` / `latency_ms` / `word_count` 已在 `model_outputs` 里）。**只加接口，不动现有 `/sessions`。**

**6D 剧情区滚动**（原 1–3 条，不变）
- 6D.1 `.story-panel` 三段式：工具栏固定 / 剧情区自己滚动 / 输入栏固定成最后一行
- 6D.2 剧情区 ref，`output` 变化时 `scrollTop = 0`
- 6D.3 撤 `.player-controls` 的 `position: sticky`

**6E 排版与间距阶梯**（需先定数值，会改全站像素）
- 6E.1 字号：现在 14 个档位（10/11/12/13/14/15/18/20/22/25/28/31/32/38）
- 6E.2 间距：61 处 padding/margin → 4px 基数
- 6E.3 圆角：9 个值 → 3–4 档
- 6E.4 层级：z-index 现为 2/4/20/80/84/90

### 已知的坑（做之前先看）

- **窄屏抽屉的开关按钮没地方放**：`.settings-menu` 是 `fixed; top:18; right:22; width:min(360px, calc(100vw-32px))`，窄屏下几乎占满宽度。需要先决定按钮位置。
- 抽屉若做，**必须按模态处理**（`role="dialog"` + 焦点陷阱 + Escape + 焦点归还），否则就是重复交付 A11 那个缺陷。
- 抽屉 z-index 必须落在 **20（设置菜单）和 80（判定浮层）之间**。
- 6D 会改变像素；6E 更是全站。**基线要按"差异白名单"验收**，不能再用零差异：预先列出预期变化的元素与量级，实测只能命中白名单。

### 验证设施（已完成，直接可用）

- `frontend/e2e/verify.spec.ts` —— 对照 `docs/frontend-baseline/` 的像素比对，容差 0
- `frontend/e2e/capture.spec.ts` —— 重拍基线（`BASELINE_DIR=…`）
- `frontend/e2e/probe.spec.ts` —— 逐元素几何量测，输出 JSON
- `frontend/src/app/styles.test.ts` —— CSS/TSX 的静态不变量。**加一条：改 token 名后它才会抓到 TSX 里的引用**
- 跑任何 Playwright 命令**必须在 `frontend/` 目录**，在仓库根跑会加载错配置、连带把 Vitest 文件也吞进去

---

# 6B 执行清单（2026-09-23 定稿）

## 基线状态（已实测）

- 后端 `PYTHONUTF8=1 pytest`：**75 passed**
- 前端 `npx vitest run`：**35 passed**（4 文件）
- Playwright：**18 passed / 2.8 min**（`cd frontend`），之后 `git status` 干净
- 服务端读路径已实测：`GET /sessions/{id}/timeline` 18 节点 = 11.8 KB；`GET /timeline/{node_id}` = 14.6 KB
- `styles.test.ts` 裸色值实测**正好 81**，预算 81 —— **零余量，新 CSS 一个 `#hex`/`rgb()` 都不能加**

## 真数据实测（`backend/data/jity.sqlite3`，69 个有 output 的节点 / 27 会话）

按 `apply_output` 顺序 fold 后再比对声明与实际 state：

```
类别          唯一声明   缺失   缺失率   缺失时已满cap   该轮已满cap轮数
items            44      3     6.8%          0              0
npcs             64      0     0.0%          0              0
quests           43      0     0.0%          0              0
world_facts      97     28    28.9%         28             14
合计            248     31    12.5%
```

结论：**31 条缺失里 28 条来自 world_facts 顶满 cap 15**（`manager.py:176-179` 的 `[:15]` 截尾，`merge_by_name` 把新名字追加在末尾，截掉的正是新来的）。`npcs`/`quests` 缺失率 **0** —— 它们的 cap 从没碰到过。items 那 3 条与 cap 无关，机制未测。

legacy 字段（`items_gained`/`npcs_encountered`/`quests_updated`/`items_lost`）与 `memory_updates` 的重叠实测：

```
legacy_only 17    mu_only 132    both 99
```

即 legacy 只贡献 **17/248 = 6.9%** 的独有声明，不是"一半"。

## 三条被推翻的前述判断

1. **`diffDeclaration` 必须先 fold。** `apply_output`（`manager.py:70-74`）把 legacy 字段和 `memory_updates` 顺序合并，**后写的赢**。逐条单独比对会造出 **95 条假阳性 / 248 条**。按 apply_output 顺序 fold 后：applied 217 / missing 31 / **rewritten 0**。
2. **`rewritten` 实测为 0，不是一类结果。** 原先以为元凶是 `_normalize_status` 的中英状态映射（`持有`→`owned`），实测 `status` 只错 4 次。
3. **`_infer_world_facts` 在真实数据里命中 0 次**（`source == "system_inference"` 的 state 条目为 0）。侦察阶段的"它会很普遍"是过度推断。

## 新增发现（本轮）

- **270 轮下节点树当不了导航。** `timeline.css:90-98` 的树是纵向的，`.story-node` 是 `176×92px` + 28px 连接线，一个节点约 120px。线性 270 轮 → 一列约 **3.2 万像素**。`.story-tree-scroll`（`:75-82`）只有 `min-height:480px; overflow:auto`、**无高度约束**，所以滚的是整页。且全 `src/` 零 `scrollIntoView`/`scrollTop`/`scrollTo`（A33），**选中节点不会滚入视野**。→ 跳转必须配树内自动滚入视野，这是全仓第一处滚动管理。
- **`scripts/auto_play_lib/markdown_log.py` 已在记目标③和④**：每轮写 `### 状态变化`、`### Context Memory 快照`（`format_state`）、`### RAG Hits`（`format_rag_hits`，含 score/importance/keywords）。原「能力盘点」表（本文件 `:178-186`）写 ③「缺后端接口」，对离线路径不成立。**但 `formatting.py:51` 是 `items[:12]`，超过写「另有 N 项」—— 正好把 cap 丢件藏在里面。**
- **`state_json` 里存着 `_memory_controller`**（`generator.py:111`），只在响应边界被剥（`sessions.py:183`）。新接口直读 `state_json` 必须自己剥，否则把 NSB 叙事池/PCB persona 吐给前端。实测 detail 响应里确实已剥掉。
- **`state` 里还有一个 `_scene_prompt`**，`sanitize_state` 没管它（只 pop 了 `_memory_controller`），前端 `GameState` 类型里没有。
- `scripts/auto_play.py` 走 HTTP `/sessions/{id}/generate`（`auto_play_lib/api.py:30-41`）→ prompt 落盘的改动确实覆盖实验路径。

## 清单（18 项，按依赖顺序）

**第 0 commit**：本文件。

### 后端 · 上下文落盘（目标③）

1. `PromptMeta` 加 `sections: dict[str,str]` / `final_prompt: str`，都带默认值。
   **不能改函数签名**：`tests/test_memory_wiring.py:104,122` 解包 `_build_prompt` 的 5 元组；`tests/test_local_examiner.py:96,114` 解包 `_execute_llm_or_scripted` 的 3 元组。加字段不破，改元数必破。
2. `builder.py` 末尾把 `ordered_sections` 塞进 `meta.sections`；`_run_narrator_stage` / `_execute_single_llm` 把**实际发出的串**塞进 `meta.final_prompt`。
   注意实际发出的不只是 sections 拼接 —— `director_support.py:158-160` 的 `_inject_direction` 往前面又插了一段 `## 导演指令`。
3. `model_outputs` 加 `prompt_sections_json` / `prompt_text` 两列（CREATE TABLE `schema.py:72-86` + `_COLUMN_MIGRATIONS` `:105-129`；迁移器 `:143-144` 无条件跑，已确认）。打通写入：`_record_and_finalize` 从 `meta` 取，`_store_error` 两个失败点（`agent_pipeline.py:139/145`）同样落盘。
   体积：270 轮 × 约 15–25KB × 2 列 ≈ 8–13MB。
4. `outputs.py` 加按 `model_output_id` 取行的读方法 + 测试（照 `test_branching_timeline.py` 的 `Database(tmp_path/…)` 模式）。**目前 `model_outputs` 全仓没有任何读路径。**

### 后端 · 接口

5. `/timeline/{node_id}` **加字段**（不改路由，纯增量）：`retrieved_chunks` / `token_count` / `latency_ms` / `word_count` / `prompt_sections` / `prompt_text`。走 `story_turns.model_output_id` 左连接。
6. 新路由 `GET /sessions/{id}/memory-trace`：每节点 `{node_id, parent_id, depth, turn, is_on_active_path, held:{四类名字}, declared:{五类名字}, cap:{四类上限}}`。**不带 prompt 正文**。**必须剥 `_memory_controller`**。
7. **声明比对放后端**（原设计是前端纯函数，改）：在 `apply_output` 旁边、复用 `_normalize_memory`/`merge_by_name` 的同一批函数算 fold 与 diff，接口回结果。
   理由：前端实现要在 TS 里重写这套语义，一旦漂移，错的是**研究结论**且界面上看不出来 —— 本轮已经在 Python 里复现过一次这种错误（95 条假阳性）。

### 前端 · 类型

8. `types.ts`：StoryOutput 补 5 字段（`items_gained`/`items_lost`/`npcs_encountered`/`quests_updated`/`npc_relations_delta`）；`NPCMemory` 补 `disposition`（`normalization.py:70` 会把它映射成 `relationship`）；`TimelineNodeDetail` 补上下文字段；新增 `MemoryTraceResponse`。

### 前端 · 回放面

9. `useTimelineData` 加第二节点槽（`compareNode` / `loadCompareNode`）。
10. 轮次定位 + **选中节点滚入视野**。轮次不唯一（e2e fixture 里 id 5/6 都是 turn 4），优先 `is_on_active_path`。
11. **回合列表视图**（剧情 tab 内树 / 列表切换，只列活跃路径，分支时切回树）。数据全在 `timelineNodes` 里，不用新接口。
12. `MemoryDelta`：声明全集 + 被丢掉的那些。**主视图是 `world_facts N/15` 顶满告警 + 本轮被丢的声明列表。**
13. 本轮注入的上下文区块：按段落列字数/token + RAG 命中与分数 + prompt 全文折叠。
14. 轮询刷新选中详情（`useTimelineData.ts:92-115` 目前只刷列表，跑长局时详情静默过期）。
15. 节点对比（`diffStates`）。
16. 存续轨迹 tab（第 4 个 tab）。
17. tab 无障碍（A15）：`aria-selected` / `aria-controls` / 方向键。

### 验收

- 后端项：`PYTHONUTF8=1 pytest`（75 条基线）
- 前端纯函数：`npx vitest run`（35 条基线）
- UI 全部落完后重录 `/timeline` 基线 + 差异白名单
- `fixtures.ts:271` 的 `startsWith('/sessions/<id>/timeline/')` 兜底会吞掉新路由，mock 必须排在它前面；`storyOutput`（`:68-79`）要补 `memory_updates` 和上下文字段

## 执行记录（2026-09-23）

后端 7 项全部完成，4 个 commit：

| commit | 内容 |
|---|---|
| `dc0a0a8` | 本文件的 6B 修订 |
| `0e29177` | 第 1–4 项：prompt 落盘（`PromptMeta` → `model_outputs` 两列 → 读方法 + 测试） |
| `82a2ef9` | 第 5 项：`/timeline/{node_id}` 加 `context` |
| `3975eb9` | 第 6–7 项：`/memory-trace` + fold 语义抽成共用函数 |

后端测试 **429 passed**（基线 420 + 新增 9）。服务端迁移已在真实的 `jity.sqlite3` 上跑通，两列均已存在。

### 执行中发现的三件事

1. **`recorded` 不能按"有没有 model_outputs 行"判。** 每个旧回合都有行，只是两列为空。必须按内容判（`bool(prompt_text or sections)`）。已实测：真实库里 18 个旧节点全部正确落在 `false`。
2. **第 7 项的 fold 直接抽成了 `GameStateManager.declared_updates`，`apply_output` 也改成调它。** 这样"合并顺序"只有一个来源，轨迹接口和落库不可能各说各话 —— 比在测试里盯两套实现更彻底。
3. **`output_json` 跨了 schema 版本。** 真实库里老回合的 `option_checks` 是 `1d20 ≤ 12` 且带一个 `normal_target` 键，而当前 `story_options.py:47` 生成的是 `1d20 ≥ N`。渲染历史节点时要注意，别以为是当前契约。（顺带：`sanitize_state` 只 pop 了 `_memory_controller`，`_scene_prompt` 会漏给前端。）

### 轨迹接口的实测数字（176 会话 / 249 节点，走 HTTP）

```
类别          declared   missing
items              48        3
npcs               64        0
quests             43        0
world_facts        97       28
TOTAL             252       31   (12.3%)
```

world_facts 的 28 条缺失与离线脚本的结论一致。总声明数比离线脚本的 248 多 4 条（items 上），未追 —— 不影响判断，但知道有这 4 条的出入。

## 前端批次的实际差异（探针实测）

我预先写了一份白名单（`.turn-navigator` 让左列下移约 52px、tabs 多一个按钮等），**实测与预期不符**。下面按实测记录。

探针 `docs/frontend-baseline/layout-probe.json` 是唯一可比的客观证据（改动前那份备份在 `test-results/probe-before.json`）。实测只有 5 条变化，全部在 `timeline-story`：

```
.timeline-shell          top  0   -> -26
.timeline-header         top  32  -> 6
.timeline-tabs           top  132 -> 106
.timeline-tab-panel      top  205 -> 179
.story-timeline-layout   top  205 -> 179
```

**全部是同一个 26px，方向相同 —— 是页面被滚了 26px，不是任何元素变了尺寸。** 原因是新增的 `scrollIntoView`：挂载时自动选中活跃节点，随后把它滚进视野。`.story-timeline-layout` 的 height 两次都是 690（被详情面板的 `max-height:100vh-40px` 钉住），height/width/contentHeight 全部不变。

其它 5 个页面（含 `timeline-anchors`/`timeline-clues`）**探针零变化**。第 4 个 tab 按钮不改变 `.timeline-tabs` 的盒子（flex 容器宽度由父级决定），所以探针看不到它 —— 但 PNG 会变。

### 两个流程失误，记下来

1. **改动前的基线 PNG 被我这次重录直接覆盖了**（图不入库，没有副本）。所以像素级的 before/after 比对**不可复现**，只剩探针 JSON。下次改 UI 前先把 `docs/frontend-baseline/*.png` 复制到 `test-results/` 再动手。
2. **探针原先不测树盒子和导航条**，所以 `.story-tree-scroll` 新增的 `max-height` 到底有没有影响，这次没法直接量。已把 `.turn-navigator` / `.story-tree-scroll` 加进 `probe.spec.ts` 的选择器列表。

`SHOTS` 原先在 `capture.spec.ts` 和 `verify.spec.ts` 各写一份，已合并到 `fixtures.ts` —— 之前加一个截图忘了加对应的 verify 会静默漏掉。

## 6B 完成（2026-09-23）

10 个 commit，`dc0a0a8` → `c244ed9`。18 项全做完。

全绿：**后端 430 passed**（基线 420）、**前端 43 passed**（基线 35，5 文件）、**Playwright 20 passed**（基线 18，多了 `timeline-trace`）、`tsc --noEmit` 干净。

### 交付面

| 面 | 内容 |
|---|---|
| 后端 | `model_outputs` 两列存 prompt；`/timeline/{node_id}` 加 `context` / `memory` / `declared` / `caps`；新 `/memory-trace` |
| 导航 | 轮次跳转 + 上一/下一轮 + 选中滚入视野 + 树/列表切换 |
| 单轮 | 声明 vs 落库（含 cap 占用与「未落库」标记）+ 本轮注入的上下文（分段字数 / RAG 分数 / prompt 全文） |
| 跨轮 | 节点对比（增/删/改字段）+ 存续轨迹 tab（实体首末轮、消失标记、逐轮存续条） |
| 无障碍 | 四个 tab 补 `aria-selected` / `aria-controls` / 方向键 |

### 三处实现与计划的偏离（都是实测逼出来的）

1. **`declared_updates` 抽成 `apply_output` 与轨迹接口共用，节点详情直接回算好的 fold 结果。** 原计划让前端做 `diffDeclaration` —— 那要在 TS 里重写一遍 `_normalize_memory` 的语义，而本轮已经在 Python 里复现过一次这种错误（95 条假阳性）。现在前端一次合并逻辑都没有。
2. **第 14 项从「轮询刷新选中详情」改成「跟随时间线头部」。** `story_turns` 的行提交后不可变（只有 `update_active_turn_snapshot` 改根节点，`timeline.py:51-62`），重拉同一个节点没有意义；真正会过期的是"选中位置被跑到后面去了"。
3. **`MemoryDelta` 对"本轮无变更"也显示一行。** 原计划是"无变更时不显示"，但那会让"没有变更"和"还没加载"长得一样 —— 而 36% 的回合确实没有记忆变更，这本身是研究数据。

### 没做的

- `TurnContextPanel` 与 `MemoryDelta` 排在节点详情最末（旁白/状态之后）。研究用途下它们应该在顶部，但那要重排现有面板，属于纯 UX 决策，没擅自做。
- 轨迹 tab 的存续条在 fixture 的 4 节点下只有 4 格；270 轮下会折成多行热力图，**没在真实长局上看过**。

## 6A + 6D 完成（2026-09-23）

### 6D 剧情区滚动（含 A35）

`.story-panel` 从"整块滚动 + 输入栏 sticky 浮在上面"改成三段：工具栏固定 / `.scene-output` 自己滚 / 输入栏是最后一行。A9 的遮挡是**结构上消失**的，不是靠补 padding。

`.scene-output` 加 ref，`output` 变化时 `scrollTop = 0`（A35）。

探针实测（`console@1536x730`）：

```
.story-panel    contentHeight 1452 -> 730    overflowY auto -> hidden
.scene-output   height        1232 -> 510    overflowY visible -> auto
.memory-panel   contentHeight 1943 -> 2526
```

新增 `e2e/story-scroll.spec.ts`：先把剧情区滚到底（断言 `scrollTop>0`），点一个选项生成下一轮，断言 `scrollTop === 0`。这条是 A35 唯一的行为验证 —— 截图看不出来。

### 6A 实时侧面板

- 「本轮记忆变更」置面板顶部：分类列出声明，未落库的标红并带徽章，每类带 `落库 N/cap`（满时标红）
- 五个分组折叠（NPC / 物品 / 任务 / 长期事实 / 最近事件），RAG Hits 同样折叠
- **折叠状态统一存 `jity_memory_folds` 一个键**。文档只要求 RAG Hits 持久化，但让一个记住、四个不记住更糟

后端为此把 `GenerateResponse` 也补上了 `memory` / `declared` / `caps` —— 与节点详情同一批函数算的，前端依旧零合并逻辑。`STATE_CAPS` 提到 `game_state/defaults.py` 作为唯一来源，`routers/sessions.py` 改为引用它。

### 顺带发现的一个静默失效（未修）

`useGameActions.ts:41` 的 `if (!sid || !nextAction.trim() ...) return;` —— **输入框为空时点「生成下一幕」什么都不会发生，且界面上没有任何提示**。按钮也没有 `disabled`。写 A35 的测试时撞上的（原本用按钮触发，测试失败得很莫名）。归入 A19/B7 那类错误呈现问题，本批没动。

### 仍未覆盖

- 1024 下记忆面板仍是 `display: none`（A30/B3 确认需要窄屏，但那需要抽屉方案，属于另一次改动）
- 抽屉必须按模态处理（`role="dialog"` + 焦点陷阱 + Escape），否则是重复交付 A11

## 6C 已由 6B-5 交付（2026-09-23 核实）

文档里 6C 要的就是 `retrieved_chunks_json` / `token_count` / `latency_ms` / `word_count` 四项。实测 `/sessions/{id}/timeline/{node_id}` 的 `context` 已经全部返回，另外还多了 `prompt_sections` / `prompt_text` / `recorded`。路由形状没动，现有 `/sessions` 响应只是多了键。

```
retrieved_chunks   list   5 条
token_count        int    5839
latency_ms         int    0
word_count         int    21
额外：prompt_sections, prompt_text
```

**6C 不再单列，本项作废。**

## 6E 重新实测：文档里的四个数字全错

| | 文档说 | 实测 |
|---|---|---|
| 字号档位 | 14 | **17 档 / 100 处** |
| 圆角 | 9 | **13 个 / 59 处** |
| z-index | 6 | **9 个 / 10 处** |
| 间距 | 61 处 | **25 个值 / 280 处**（15 个值不是 4 的倍数） |

字号 17 档：10/11/12/13/14/15/18/20/22/24/25/28/31/32/38 px，外加 `0.8rem` / `0.84rem` 两个（`timeline.css:854`、`story-panel.css:259` —— 混在 px 文件里的 rem）。

### 6E.4 层级：已完成，零像素差异

`tokens.css` 加 `:root` 的应用层级，替换 6 处：

```
--layer-scene       -2   .scene-background
--layer-brand        4   .game-brand
--layer-menu        20   .settings-menu
--layer-modal       80   .main-check-overlay
--layer-modal-card  84   .main-check-card
--layer-top         90   .real-dice-wrapper
```

`.story-node` 的 `z-index:1` 和骰子的 0/1/2 是**组件内部叠放**，留在原处。

验收是**零像素差异** —— 只跑 `verify.spec.ts` 不重录，7/7 通过。

间距的间隙是刻意的：窄屏抽屉必须落在 `--layer-menu` 和 `--layer-modal` 之间。

### 6E.1/6E.2/6E.3 未做，需要先定数值

这三项合计会改动 **280 处间距 + 100 处字号 + 59 处圆角**，等于全站每一块都位移。后果：

- 验收从"差异白名单"退化成"全是白名单"，白名单就失去意义了
- 我只能对比两个视口的截图，做不了真正的视觉 QA
- 它对本项目的研究课题（上下文工程与记忆管理）零贡献

**建议：不做整批合并。** 纯 token 化（只改名、不改值）也能做，但文档自己也说了"只改名不合并收益仅形式"。真觉得某处难看时再做那一处。

## A30 / B3 窄屏抽屉 完成（2026-09-23）

<1100px 时记忆面板不再直接消失，改成模态抽屉。

- 开关按钮放在剧情区工具栏 `.toolbar-row`（与「回溯上一步」并列），窄屏才显示。放固定右上角会和 `.settings-menu` 直接重叠 —— 两者在窄屏下都是 `fixed`
- 抽屉是 `role="dialog"` + `aria-modal="true"`，Tab 锁在内部、Escape 关闭、关闭后焦点归还给触发按钮。抽出的 `useModalFocus` 是通用的，A11（`MainCheckOverlay` 缺同一套东西）可以复用它
- `z-index` 用 `--layer-drawer: 40`，落在 `--layer-menu`(20) 和 `--layer-modal`(80) 之间 —— 这正是 6E.4 那批 token 存在的理由
- 视口重新变宽时抽屉自动关闭。否则 `display: none` 会把焦点陷阱留在不可见元素里
- 遮罩色抽成 `--color-scrim`（`check-overlay.css` 一并改用它），裸色值预算 **81 → 80**

新增 `e2e/memory-drawer.spec.ts` 四条：触发按钮存在、打开后焦点进入且 Escape 归还、连按 8 次 Tab 焦点不出抽屉、关了再开不丢焦点。

`SHOTS` 支持 `only: ["1024x768"]` 按视口裁剪，并新增 `console-drawer` 一条；`?memory=1` 可在加载时打开抽屉（与 timeline 的 `?tab=` / `?node=` 一致）。

### 本批像素差异（探针实测）

```
console@1024x768  .scene-output  top 49->50  height 548->546
console@1024x768  .narration     top 141->142
console@1024x768  .dialogue-list top 785->786
console@1024x768  .option-list   top 1087->1088
```

只有 4 条，全部是工具栏里多了那个按钮导致整行高 1px，下面所有内容下移 1px。**`console@1536x730` 零变化**（按钮不显示）。

## A11 顺手修掉

`MainCheckOverlay` 是全屏 `fixed` 层，但只有 `aria-label` —— 键盘用户进去出不来，而掷骰动画期间卡片上连一个可见控件都没有（`phase !== "prepared"` 时 返回/掷骰 都不渲染）。

复用 `useModalFocus`：`role="dialog"` + `aria-modal="true"` + Tab 锁内 + Escape 关闭（等同于「返回」）+ 焦点归还。`.main-check-overlay` 加 `outline: none`（它是纯程序化焦点目标，不是键盘可达控件 —— 和 A8 那个文本框的情况不同）。

新增 `e2e/check-overlay.spec.ts` 三条。

**写这个时发现钩子本身有个 bug**：`onClose` 原先在 effect 的依赖里，而调用方传的都是内联箭头函数（`onCancel={() => setCheckingAction(null)}`、`onClose={() => setMemoryOpen(false)}`），每次渲染都是新引用 → effect 每次渲染重跑清理 → **把焦点甩回遮罩背后的元素**。已改成用 ref 持有 `onClose`，依赖只剩 `[open]`。

## 已知不在本批

- **真正未加工的 LLM 原文全库没存**（`raw_output_text` 存的是 `output.model_dump_json()`，同样打过 pydantic 默认值）。补它要动 `LLMClient.generate` 的返回。关乎目标① 不是③。
- 已跑的 69 个节点没有 prompt 落盘，第 13 项**只对以后跑的回合有效**。
- 6D 剧情区滚动 / A35 自动滚回顶部，仍在第 6 项但不在 6B。

---

# A19/B7 空输入静默无反应（2026-09-24，`612bb84`）

**问题**：输入框为空时点「生成下一幕」，按钮是亮的，但点了什么都不发生、也没有提示。
`useGameActions.ts:41` 的 `if (!sid || !nextAction.trim() || generating.current) return;` 把它静默吞掉。

**改动**（全在 `StoryPanel.tsx`，四处）：

- 抽出 `const hasAction = action.trim().length > 0;`
- 按钮 `disabled` 补 `|| !hasAction`
- textarea 的 Ctrl/⌘+Enter 守卫补 `&& hasAction`
- `.player-controls-hint` 按 `hasAction` 切换文案（空时提示「先输入行动，或直接点上方选项」）

新增 `e2e/generate-guard.spec.ts` 两条：空 → disabled；填字 → enabled；只填空格 → 又 disabled；
外加一条**空输入时选项按钮仍然可用** —— 防的是过度禁用把选项路径一起堵死。

**故意没修**：按钮的 disabled 查 `session.pendingGenerate`，Ctrl/⌘+Enter 的守卫不查，两者本来就不一致。
本次只统一了 `action` 那一半。统一 `pendingGenerate` 是行为变更，不在这条的范围里。

## 这个改动会改像素，而且知道是哪 3 张

`story-panel.css:75` 有 `.player-controls-row button:disabled { cursor: not-allowed; opacity: 0.55; }`。
e2e fixture 下 `#action` 是空的、按钮原本启用，加 `!hasAction` 后它变灰。一次性探针实测：
`opacity 1 → 0.55`，按钮截图字节 `2764 → 2528`。

15 张基线里受影响的是 3 张：`console--1536x730`、`console--1024x768`、`console-drawer--1024x768`。
**其余 12 张不可能变**，理由是结构性的：`StoryPanel` 全仓只被 `src/app/page.tsx` 一个文件 import，
所以它的标记只出现在 `/` 这一条路由上，而 `/` 的截图一共就这 3 张。

## 我在这条上犯的错：基线备份放错了地方

动手前把 15 张 PNG 备份到了 `frontend/test-results/`。**`playwright.config.ts` 没设 `outputDir`，
用的是默认值 `test-results`，而 Playwright 每次启动都会清空重建它。** 备份在下一次跑测试时就被删了，
随后 `capture.spec.ts` 又覆盖了 `docs/frontend-baseline/` —— **改动前的 15 张因此丢失。**

正确做法：备份放到 runner 管不到的地方（仓库外，或 `frontend/` 下另建目录并加进 `.gitignore`）。
要补 before/after，源码在 git 里：把改动过的文件临时换回 HEAD 版本，
`BASELINE_DIR=<仓库外目录> npx playwright test e2e/capture.spec.ts` 渲染出"改前"再比。

## 两个流程陷阱（都实测过）

1. **整套 `npx playwright test` 的像素验收是恒真的。** 按字母序 `capture.spec.ts` 先跑，把当前渲染写进
   `docs/frontend-baseline/`，`verify.spec.ts` 再拿这份跟自己对，`maxDiffPixels: 0` 永远成立。
   **必须单独跑 `e2e/verify.spec.ts` 才算验收。**
2. **`probe.spec.ts` 的 `afterAll` 无条件覆写被 track 的 `layout-probe.json`。** 代码没动时它是确定性的
   （2026-09-24 实测：整套跑完 `git diff --stat` 为空），但改了几何之后再跑，改动前的探针基线就没了。

本次实测的基线：后端 **430 passed**；前端 **43 passed / 5 files**；Playwright **30 passed**；
新增 spec **2 passed**；`e2e/verify.spec.ts` 单独跑 **8 passed**；`tsc --noEmit` 干净。

---

# B4 的实测代价（2026-09-24，五路并行审计）

**这不是"加一条导航栏"，是"引入一个全局垂直偏移量，然后重算全站每一处 viewport 高度预算"。**

顶栏本身只占 2 个文件；真正的工作量是下面这些**被 `100vh` / `position: fixed` / `sticky top` 写死、
需要重算的规则**，散在 9 个 CSS 文件里：

| 位置 | 为什么被影响 | 处理 |
|---|---|---|
| `layout.css:6` `.app-shell { height: 100vh }` | 整页正好一个视口，顶栏占掉 56px | 改 `calc(100vh - var(--nav-height))` |
| `timeline.css:1079-1086` `@media ≤760px { .app-shell { height: auto } }` | **压过上面那条 calc**（timeline.css 在 layout.css 之后 import） | 同样要减 |
| `settings-menu.css:2-5` `.settings-menu { fixed; top: 18px }` | 被顶栏压住 | `top: calc(var(--nav-height) + 18px)` |
| `layout.css:28-31` `.scene-background { fixed; inset: 0 }` | 背景图盖住顶栏 | `inset: var(--nav-height) 0 0 0` |
| `timeline.css:308-311` `.story-node-detail { sticky; top: 20px }` | 在 `/timeline` 上**不在** `.app-shell` 内，头部被盖 36px | `top` 与 `max-height` 都要加 |
| `timeline.css:963-970` `.clue-board { sticky; top: 32px }` | 同上，被盖 24px | 同左 |
| `timeline.css:193-195` `max-height: calc(100vh - 220px)` | 那个 220px 没算顶栏 | 减 `--nav-height` |
| `story-panel.css:87` `padding: clamp(56px, 12vh, 132px)` | 12vh 被顶栏吃掉一截 | 待定 |
| `base.css:5-12` `html, body { min-height: 100% }` | 与裸 `body` 规则同特异性，且 `tokens.css` 在它**之前** import | body 规则必须写进 base.css |
| `check-overlay.css:15-18`、`memory-panel.css:334-345` | 卡片 `top:24px`、抽屉头部 `top:0` 落在顶栏带里 | **由分层解决**，不靠偏移 |

**分层是硬约束**：`.app-shell` 有 `isolation: isolate`，里面的判定浮层(80)、记忆抽屉(40)全被困在这一个
层叠上下文里。顶栏只要 z-index 比它高，模态就被顶栏压住，A11 当场作废。所以顶栏和 `.app-shell` 必须
**同层**，靠 DOM 顺序让壳子在后 —— 也就是 `layout.tsx` 里 `<AppNav/>` 必须写在 `{children}` 之前。
另外 `.story-node` 有 `position: relative; z-index: 1`，所以顶栏也不能是 `z-index: auto`。

**代价分布不均**：约三分之二在控制台 —— 它的 `height:100vh`、`isolation`、两个 fixed 子元素、
一条窄屏媒体查询，全是为"这一页正好等于一个视口"服务的。`/timeline`、`/curator`、`/dev-log` 三页
加起来只需要两个 shell 各加一行 padding，再加三条 sticky 偏移。**"四页还是三页"值得在动手前再定一次。**

**审计排除掉的（都是好消息）**：

- Tailwind v4.3.0 的 preflight 里**一个 `body` 选择器都没有**，`body { display:flex }` 安全
- `src/` 里**零个 Tailwind 工具类**，全是项目自有 kebab 类，不存在工具类冲突
- e2e 里**没有任何裸 anchor / `getByText` / 全文档文本定位**，顶栏加链接不会劫持 locator。
  唯一的硬失败是 `verify.spec.ts` 的 15 张截图。理论上唯一暴露的是 `check-overlay.spec.ts:26/33/43`
  那个不限定的 `getByRole("dialog")` —— 只要顶栏不引入 `role="dialog"` 就安全

## 对比面板的像素基线为什么现在做不出来

原计划是加 `?compare=1` 再补一张 shot。查下来有四处要改，而且**只加 `?compare=1` 会产出废图**：

1. `NodeCompare` 只在 `compareNode && selectedNode && 两者 id 不同` 时才渲染真表，
   否则渲染一句「基准和当前是同一个节点」。
2. `fixtures.ts:426` 是 `if (path.startsWith(...timeline/)) return json(timelineNodeDetail)` ——
   **任何 node id 都返回同一个常量**，它的 `id` 硬编码是 7。所以选中任何节点，拿回的 id 都是 7。
3. 于是基准再取活跃节点 7，两者永远相同 → `fixtures.ts:426` 必须先改成按 node id 返回不同的 detail。
4. shot 的 URL 必须带 `?node=`：`useTimelineData.ts:115-117` 的 `targetId` 在缺 `requestedNodeId` 时
   会落到 `active_node_id`，只写 `?compare=1` 还是同一个节点。

取基准的正确路径是 `StoryTimeline.tsx:96` 那条 `loadCompareNode(active_node_id)`，
**不是** `pinCompareNode()`（后者正是把 selectedNode 自己钉成基准）。
