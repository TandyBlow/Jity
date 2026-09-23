# 前端 CSS 地基重构 —— 问题清单

基线 commit：`60ce656`（Playwright 截图 + 尺寸探针，图不入库，探针 JSON 入库）
基线与尺寸数据：`docs/frontend-baseline/`

所有 A 类条目均已逐条读过代码或量过数值。B 类是产品问题，未做判断。

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
