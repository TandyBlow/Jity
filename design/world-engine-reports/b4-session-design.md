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

## 3. 失效、停止与销毁

- **心跳失效（onLost）**：lease 失效是会话级事件——`onLeaseLost` 立即 abort 在途推理（sessionSignal），推理调用以 AbortError 定局、`consumeModelOutput` 不执行（迟到引擎 settle 由队列丢弃），驱动循环以 error 终态 settle；claim 失效只停该心跳并上报 hook，不打断会话（controller 会重领）。
- **epoch 守卫**：`stop()`/`dispose()` 递增会话 epoch；观察层与心跳 hook 在 epoch 变化后不再改状态；stop 后到达的 transport 响应直接以会话已关闭拒绝——旧会话的迟到回执既不喂心跳也不被 driver 采纳。
- **stop()**：停心跳 → abort 在途推理 → 循环以 `{kind:'stop', reason:'session_stopped'}` settle；`dispose()` = stop + `port.dispose()`（引擎释放）。stop 后 `run()` 拒绝。

## 4. 验收场景（session.test.ts）

固定 transport（脚本化信封流）+ fake engine（可控 hold）+ ManualClock + fake driver（脚本化步骤，经真实观察包装/端口/心跳）：

1. 装配自动性：create_world 信封自动起租约心跳、narration_claim fresh 自动起 claim 心跳、submit 自动停。
2. 长推理保活：引擎调用持锁期间时钟越过 lead → 续租完成，生成随后正常结束。
3. claim 换代/换点：新代同点 update、换点 stop+start（续租请求带新 pointId 证明）。
4. lease 丢失：续租收 stale_epoch → 在途生成被 abort（调用方 AbortError、迟到引擎 resolve 丢弃）、循环 error 终态、onLeaseLost hook 触发。
5. 重复启动与迟到回执：并发 `run()` 恰一个循环同一 promise；stop 时在途的生成与续租都迟到 settle——无新调度、无状态回写、无未处理拒绝。
