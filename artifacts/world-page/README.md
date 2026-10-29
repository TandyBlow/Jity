# 世界最小交互页验收（world-page）

`frontend/scripts/review-world-page.mjs` 的一次真实闭环记录。运行方式：

```
cd frontend
node scripts/review-world-page.mjs            # 完整：三个 Node 探针 + 真实浏览器闭环
node scripts/review-world-page.mjs --skip-browser   # 只跑探针
node scripts/review-world-page.mjs --out <path>     # 报告落点
```

脚本自举：uvicorn（`app.world_app:create_persistent_world_app`，服务端 checkout 由
`--server-checkout` 必填指定——旧默认 `.local/world-server-worktree` 已退役，缺失即拒绝起跑；
`WORLD_ALLOWED_ORIGINS` 按前端端口注入）→ `next dev`
（随机空闲端口）→ Playwright Chromium（`channel: msedge`，与 playwright.config 一致）。
报告（review.json）记录两侧 head/状态与全部前端/服务端源文件 sha256，绑定本 README
所述轮次的精确代码。

## 批次范围（对应用户四项）

1. **持续会话**：同一世界连续执行多条命令。`RuleWorldSession.submit()` 经
   `ControllerDriver.preparePlayerInput()` 轮换每命令分配计划
   （新 allocationKey + 清空 advance/input/round/point/group 槽位 id）；服务端
   `start_advance` 只拒绝活跃 advance/work，handback 后天然接受新回合。
2. **最小界面**：`/world` 页展示地点、精神值、任务、世界时间、人格与模板叙事
   （每行 v 版本号·时间推进），输入框 + 执行状态，支持命令提示（含当前可选路线
   与精神值门槛），拒绝原因与未识别命令就地显示。
3. **刷新续接**：worldId + 最新租约凭据存 sessionStorage；重载后
   `createRecovered` 走既有 H2 recover（先 lease_renew 续租，失败降级一次接管），
   叙事日志从服务端事实重建（list_points + narration_get + get_state）。
4. **默认规则＋模板**：默认全部走规则判定与提交模板叙事；「模型润色」为可选
   实验（wllama + 真实提示层），候选必须整体通过事实校验才被采纳，任何失败
   （含 120s 截止时间）回退模板。

## 浏览器闭环（review.json: browser.steps）

新世界（走廊/10，根叙事）→ 走到门厅（v1·+1秒，地点=门厅）→ 完成压力试验
在门厅被拒（`milestone_location_mismatch`，数值不变）→ 走到走廊 → **整页刷新**
（自动续接，4 行叙事全部由服务端事实重建）→ 完成压力试验（10→8，任务达成）
→ 勾选「下一次提交丢回执」+ 完成恢复练习（8→9；commit_point 回执被注入丢弃后
驱动以同一 requestId 重试，服务端 replay）→ 勾选「模型润色」+ 走到门厅（回合
完成，模板可用）→ 服务端核对：恰好 6 回合 7 点位、逐点叙事 ready、无重复消费
→ **客户端导航往返**（复核 r7）：SPA 离开 → 返回 → 重新初始化自动续接，
7 行叙事与状态（门厅/9）完整恢复。

## Node 探针（review.json: probes）

- **P1 连续会话＋丢回执**：一个世界两条命令（压力试验→移动），首个 commit_point
  回执注入丢失后同 requestId 重试 2 次、第二次全新 id；版本恰好 2、点位恰好 3。
- **P2 提交前放弃**：seal_point 回执被扣住（服务端已受理）即弃会话 → recover
  （持约续租）续走 → 恰好一次提交（版本 0→1），叙事就绪。
- **P3 handback 边界恢复**：两条命令后弃会话 → handback 边界 recover →
  恢复会话继续接「完成压力试验」（版本恰好 3，精神 8，任务达成）。

## 本批次连带发现并修复的缺陷

- **A 侧（world-server 31660cc）**：同一世界开新回合时，闭合行持久化直接解引用
  已被 handback 清空的 `record['advance']` → start_advance 整事务 500。改为回退
  读该回合已持久化的 advance 行。
- **A 侧（world-server 3734a52，复核 P1-1）**：轮换 round 的闭合行无条件捏造
  `kind='continue'`，把真实 handback 历史改写（复核实读：12 条已接受结论中 8 条
  变 continue）。修复后保留已记录结论，捏造 continue 仅作为无结论换轮的回退；
  回归测试先行复红（`test_new_advance_keeps_the_closed_rounds_recorded_conclusion`）。
  修复后验收库实读：12 条闭合回合全部 handback、0 continue、0 null。
- **B 侧 recovery（复核前批次已修）**：handback 边界的
  `recovery_history_advance_mismatch`——回合视图仍在而 advance 已为 null 时，
  历史 advance 绑定检查无对象，恢复被拒且驱动被 recoveryBarrier 闩死。advance
  为 null 时跳过该绑定（recovery.ts）。
- **B 侧 WorldSession（复核前批次已修）**：恢复成功后的 `recoveryTerminal`
  永久短路后续 run()，恢复会话永远接不了新命令。移除短路；恢复失败仍由驱动
  barrier 守住。
- **B 侧 RuleWorldSession/controller（复核前批次已修）**：恢复会整体替换驱动
  memory 对象，会话侧持有的旧引用上写入 playerInput、读取 playerAdvance 全部
  落空（表现为回合静默 world_complete 或 `rule_input_identity_missing`）。
  提交通道改经驱动自有 `preparePlayerInput()`，行动作用域改读驱动活引用
  `driver.playerAdvance`。
- **页面润色实验**：wllama 加载/生成挂起时无界等待会阻塞命令回合；加 120s
  截止时间，超时按失败回退模板。

## 复核修复轮（2026-10-28，三处 P1）

1. **历史结论不变**：见上方 A 侧 3734a52；回归=pytest 红转绿 + 每次验收后实读
   sqlite 断言无 continue 覆写。
2. **跨分页刷新**：`rebuild` 原来只读第一页并把页末项当 head——超过 100 点的
   世界状态面板显示旧 head。提取 `runtime/world-reads.ts#readAllPoints`（完整
   分页＋游标不前进守卫），页面接入；vitest 回归覆盖 250 点跨 3 页、101 点短页
   终止、单页、整页卡死四个用例。
3. **客户端导航往返**：模块级 `booted` 跨实例保留导致重挂载永远停在 boot，且
   effect 无卸载清理。改为组件级 `bootedRef`＋代际取消（`generationRef`/
   `disposedRef`，卸载停会话且新代接管不误停旧代会话），attach 失败路径按实例
   停止；页面补「返回控制台」Link。回归=review 脚本 r7：SPA 离开 → goBack 返回
   → 重新初始化自动续接 → 7 行叙事与状态恢复（review.json: spa-roundtrip）。

## 竞态修复轮（2026-10-28 复核补充，r8）

导航修复仍留一处异步竞态：代际检查只在 `attach()` 整体返回后执行，其内部各
`await` 之后仍会无条件创建会话、发布 `activeRef`、写页面状态。受控复现序列：
旧代挂起在 `get_state` → cleanup、新代开始恢复 → 新代先完成并发布引用 →
旧代读晚到，继续创建旧会话覆盖引用 → 外层发现旧代失效并按实例清理 →
`activeRef=null`，新会话存活但页面失去引用。

修复：`BootstrapCancelled` 信号贯穿 `attach`/`rebuild` 的每个 `await` 边界——
`get_state` 返回后、创建会话前、发布 `activeRef` 前、`setPhase('ready')` 前各闸
一次；`attachOnce` 对自己创建的会话兜底 `stopOwned`（取消/恢复拒绝/终态都不
泄漏心跳中的会话，且按实例判断不误清新代引用）。回归=review 脚本
**r8 `late-attach-race`**：路由拦截扣住旧代挂载的首读 → 三段导航使新代先完成 →
真实转发放行旧代读 → 断言状态/日志原样、下一条命令照常提交 v7。

## 二次复核轮（2026-10-28，两项 P1 收口）

上一轮修复自身仍有两处缺陷，本轮收口：

1. **`stale` 没有传进 attach（P1-1）**：effect 调用点漏传，全部闸门吃默认值
   死寂。修复=**参数必填化**（`attach`/`rebuild` 的 `isStale` 无默认值——漏传
   在 tsc 编译期即红；运行时漏传等价于传 undefined，第一个闸门 TypeError），
   自动恢复传代际 `stale`，手动续接按钮传「组件已卸载」判断；`connectNew`
   同族加固（创建后/attach 返回后/发布前闸门 + catch stopOwned，引用发布
   统一后置）。回归=r8 附加确定性判据：放行后窗口内旧代 rebuild 逐点读
   增量必须为 0（闸门死寂时旧 attach 走完恢复并 rebuild，增量 ≥1 转红，
   与按钮/渲染时序无关）。
2. **恢复期间取消泄漏会话（P1-2）**：取消检查放在 `attachOnce` 之外时，恢复
   成功返回后才发现取消，异常绕过清理块——会话照常持有租约心跳。修复=
   闸门移入 `attachOnce` 的 try 内（`session.attach()` 返回后立即检查），任何
   取消都经 catch `stopOwned` 停止自己创建的会话。回归=**r9
   `cancelled-recovery`**：路由扣住旧代挂载恢复流程的 get_context（恢复悬挂
   中）→ 新代完成 → 真实转发放行 → 新代会话照常提交 v8 → **断开活跃会话后
   100s 窗口内 lease 续租必须为 0**（服务端 TTL 120s、lead 30s → 泄漏会话
   恢复完成后 ~90s 首次续租，必然落入窗口；修复版旧会话已死，零续租）。
   恢复中途的读在 attach 返回前发出、任何闸门都拦不住（软诊断记录，不作
   断言——判据设计曾在此处犯「零恢复读」错误，经服务端日志+URL 诊断证伪
   后改为心跳判据）。

**两项回归的实证矩阵**（隔离单一缺陷逐一复跑）：修复版 r8 计数 0+r9 零续租
双绿；仅去恢复返回闸门（隔离 A）r9 红（`got 2 lease renewals in 100s`）；
漏传（隔离 B）reload 处即 TypeError 红（必填化的运行时表现，tsc 同样红）。

## SPA 进入隔离轮（2026-10-28，r10）

跨源隔离是**文档创建时定型**的属性。`next.config.ts` 只为 `/benchmark` 与
`/world` 的响应加 COOP/COEP；从 `/`（无隔离头）经客户端路由进入 `/world`
时，既有文档不会因新页面的响应头获得隔离——`crossOriginIsolated` 仍为
false，`SharedArrayBuffer` 不可用，多线程 wasm 路径全程缺失（单线程预填实测
约 200ms/token，模型叙事大概率超时回退模板）。此前的 r7 只覆盖
「已在隔离文档内往返」，覆盖不到这一入口。

修复：`/world` 挂载时自检隔离，失败即 `location.reload()` 一次——重载后的
文档由 `/world` 的响应头创建，天然隔离；`sessionStorage` 护栏防循环，
存储被禁时无法防循环故宁可不重载、只降级提示（不静默）。重载后世界凭已存
租约自动续接，叙事仍全部由服务端事实重建。

回归=**r10 `spa-entry-isolation`**：真实浏览器整页载入 `/`（断言未隔离）→
用设置菜单开合作 hydration 判据 → `next dev` 暴露的
`window.next.router.push('/world')` 做软导航（与 `<Link>` 同一个 App Router
动作；控制台目前没有进入 /world 的链接）→ 自检重载后断言：隔离为真
（`navigationType=reload`）、护栏已清除、7 行叙事与门厅/9 全部恢复。

探针自身的三处取证经验（写在这里防重犯）：

1. `history.pushState` + 手派 `popstate` **不会**驱动 App Router（它不认没有
   内部 `__NA` 状态的条目）——页面停在控制台、WorldPage 从未挂载，诊断里
   表现为 `flag:null` 且 body 仍是 GM 控制台。旧版探针正是这样失败的。
2. `window.next.router` 在 hydration 前已存在，但此时派发会抛
   `Router action dispatched before initialization`（未捕获的 pageerror，
   URL 不变）。判据必须先等一个只在 hydration 后生效的交互（本探针用设置
   菜单的开合）。
3. 自检的整页重载会销毁执行上下文，`page.waitForFunction` 会直接报错——
   隔离轮询改在 Node 侧做，把导航中的 evaluate 异常当作「正在重载」吞掉。

**实证矩阵**：不装载自检修复跑完整脚本 → 软导航成功、世界照常恢复，但
隔离恒为 false、无 reload，r10 在 60s 轮询后红于隔离断言（此前 10 步全绿，
`spa-entry-diagnostic` 记录 pathname/flag/body）；装载修复后 13 步全绿。
本轮同时把关：前端全量 **565** 项、`tsc --noEmit`、`next lint`、`next build`
通过。lint 顺带清掉规则事实切片遗留的 5 处测试 `any` 与 1 处 `prefer-const`
（自 2a6eff2/c25ede4 起 `npm run lint` 在本地即已失败，前端 CI 的 lint 步骤会红）。

## 复核签字（2026-10-28，B=552148c）

用户独立验收通过，签字文档：[signoff-552148c.md](signoff-552148c.md)。

- 关闭两项 P2：SPA 进入 `/world` 不隔离；缺响应头时降级静默（告警被 boot
  清空）。复核实测：软导航后自动重载、隔离生效、护栏清除；缺头环境只重载
  一次且告警持续可见。
- 复核实跑：15 个源码摘要全匹配、565/565、双 tsc、lint 通过（仅 warning）；
  `world-browser` 与 origin 一致、工作树干净。
- 边界：**B 批次通过，整体 CI 未闭环**。B 单树导出检查在 `api-contract.json`
  报 drift、backend 75 个失败全在 v2 契约/恢复/导出用例；根因是 R1 契约已镜像
  （`88311b2`）而本分支 backend 仍在 `cabb04c`（A 的 `4739ae4` 未合）。下一步由
  A 在临时集成 checkout 组合 **A=`3734a52` + B=`552148c`**，收绿 backend 与
  world-interface。

## 已知边界

- 无头环境下 wllama 加载可能挂起（r6 轮以模板呈现，即回退路径的实证）；
  `/world` 与 `/benchmark` 现在都带 COOP/COEP，SPA 进入 `/world` 时由挂载
  自检整页重载一次进入隔离文档（部署缺响应头时降级为单线程提示）。
- 叙事日志重建假定逐点叙事已就绪；提交后叙事未完成时刷新会显示
  「叙事状态：pending/failed」占位行（GET 事实，不伪造文本）。
