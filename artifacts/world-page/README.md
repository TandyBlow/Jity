# 世界最小交互页验收（world-page）

`frontend/scripts/review-world-page.mjs` 的一次真实闭环记录。运行方式：

```
cd frontend
node scripts/review-world-page.mjs            # 完整：三个 Node 探针 + 真实浏览器闭环
node scripts/review-world-page.mjs --skip-browser   # 只跑探针
node scripts/review-world-page.mjs --out <path>     # 报告落点
```

脚本自举：uvicorn（`app.world_app:create_persistent_world_app`，服务端 checkout 默认
`.local/world-server-worktree`，`WORLD_ALLOWED_ORIGINS` 按前端端口注入）→ `next dev`
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

## 已知边界

- 无头环境下 wllama 加载可能挂起（r6 轮以模板呈现，即回退路径的实证）；带
  COOP/COEP 的多线程 wasm 不在 /world 生效（仅 /benchmark 配置）。
- 叙事日志重建假定逐点叙事已就绪；提交后叙事未完成时刷新会显示
  「叙事状态：pending/failed」占位行（GET 事实，不伪造文本）。
