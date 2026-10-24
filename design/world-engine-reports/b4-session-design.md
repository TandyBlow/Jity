# B4 会话装配设计补充（B 侧）

状态：2026-10-25，分支 `world-browser`。批次一范围（用户指令）：装配 driver、model port 与双心跳为单一会话模块；统一观察成功与错误信封并向心跳供给凭证/过期回执；接通失效、停止与销毁；固定 transport + fake engine + ManualClock 验证接线。本文是 [分工文档](../browser-world-state-work-split.md) §四 B4 行的实现层补充。

## 0. 交付边界

本批交付 `runtime/session.ts`（`WorldSession`）：组合根 + 观察层 + 生命周期。**不重新验证** controller/schedule 的业务行为（T01–T08/H1 已覆盖）——会话测试用脚本化 fake driver 驱动**真实的**观察包装、HeartbeatScheduler、SerialInferenceQueue 与 RuntimeWorldModelPort，只证明接线自动触发。页面接线（React 状态、UI 事件）与真实 TTL/接管不在本批；H2 单独验收。

## 1. 组装与单循环

`WorldSession(transport, port, options)` 构造时装配：

- **观察 transport**：包住调用方传入的 transport，driver 的每次交换（成功与错误信封）过 `observe()`（§2）；
- **信号绑定的 model port**：`generate(task, key, input)` 转发到 `port.generate(…, sessionSignal)`——取消权在会话，driver 接口不变；
- **driver**：默认工厂构造真实 `ControllerDriver`（initialMemory 前缀/holder 可配），`createDriver` 可注入替身；
- **HeartbeatScheduler**：时钟可注入（默认 `SystemHeartbeatClock`），renew 走原始 transport（不经观察层——心跳自己的 adopt 已消费回执，避免双写）。

`run()` 单飞：在跑时重复调用返回**同一个** in-flight promise，会话任何时刻至多一个 driver 循环；循环在 driver 终态（await/stop/error）时 settle，可再次 `run()`（await 边界后继续），心跳跨 run 存续——等玩家输入期间租约仍需续租。`step()` 不直接暴露（会话拥有循环）；命令经 `deliver()` 转发。

## 2. 信封观察（观察层职责）

每次交换后从信封提取心跳状态，全部动作由**信封内容自动触发**：

- **租约建立**：`create_world`/`lease_acquire` 成功的 `data`（LeaseGrant 三字段）→ 记录会话自持 token/epoch 并 `startLease`（token 是客户端自持凭证，信封 `world.lease` 只有 epoch+过期）。
- **租约续期回执**：任何带 `world.lease != null` 的信封 → `updateLease`（freshness 守卫拒回退）；`world.lease == null` 且租约心跳在跑 → 停租约与 claim 心跳（租约消失即栅栏全部 claim，driver 的 adoptState 同步作废 claim）。
- **claim 生命周期**：`narration_claim` fresh（replayed=false 且带 claimToken、head 模式）→ 同点 `updateClaim`、**换点 stop+start**（换代重领是不同 scope，不做代次比较）；`narration_submit`/`narration_delete` 成功 → 停 claim 心跳（令牌已消费）。
- **错误信封**：`stale_epoch`/`lease_invalid` → 停双心跳（租约已死，driver 自行走 reacquire followup）；`claim_fenced`/`claim_expired`/`cache_missing` → 停 claim 心跳（controller 的 finish_own_narration 路径自然重领，新 claim 经观察层重启心跳）。

## 3. 失效、停止与销毁（修复轮语义）

- **会话唯一命名空间**：模块级计数器 + 时间戳生成默认命名空间（`requestIdNamespace` 可注入）；driver requestId 前缀与心跳 ID 同源，两个默认会话在共享服务端上无幂等键碰撞。
- **心跳失效（onLost）**：lease 失效进入**显式失联态**——停双心跳、epoch+1 隔离在途、abort 推理与调用信号，循环以 `lease lost: <code>` error 终态 settle；claim 续期冻结。会话保持可 run（controller 重取租约的恢复路径），下一次 LeaseGrant 观察清除失联态。claim 失效只停该心跳并上报，不打断会话。
- **隔离是双极性定局替换**：在途调用的 settle（成功或错误）在 epoch 变化后一律替换为隔离错误——迟到错误信封不以 WorldApiError 抛回，errorReaction/adoptState/followup 写入无从触发；观察层入口在关闭后拒绝新调用。两层守卫独立拦截同一可观察结果。
- **调用信号竞速**：每个 raw 交换与调用 signal 竞速（signal 传给 transport），stop/失租即刻定局调用方；raw 迟到 settle 前挂 catch 吞掉。
- **信封 epoch 核对**：`world.lease` 只在 `fenceEpoch === 自持 epoch` 时绑定更新；更高 epoch = 自持 token 已死（失联处理），更低 epoch 忽略——旧 token 永不升级绑到新 epoch。
- **stop()**：终态关闭（epoch+1、pendingTerminal、心跳停、信号 abort）；`dispose()` = stop + 引擎释放。

## 4. 验收场景（session.test.ts）

固定 transport（脚本化信封流）+ fake engine（可控 hold）+ ManualClock + fake driver（脚本化步骤，经真实观察包装/端口/心跳）：

1. 装配自动性：create_world 信封自动起租约心跳、narration_claim fresh 自动起 claim 心跳、submit 自动停。
2. 长推理保活：引擎调用持锁期间时钟越过 lead → 续租完成，生成随后正常结束。
3. claim 换代/换点：新代同点 update、换点 stop+start（续租请求带新 pointId 证明）。
4. lease 丢失：续租收 stale_epoch → 在途生成被 abort（调用方 AbortError、迟到引擎 resolve 丢弃）、循环 error 终态、onLeaseLost hook 触发。
5. 重复启动与迟到回执：并发 `run()` 恰一个循环同一 promise；stop 时在途的生成与续租都迟到 settle——无新调度、无状态回写、无未处理拒绝。
