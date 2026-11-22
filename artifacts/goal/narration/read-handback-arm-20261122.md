# 早交还评估臂：首轮原型结果（2026-11-22，run37/38）

## 开关与实现

- URL 开关 `schedHandback=player`，只在显式开启时生效；默认路径不变。
- 实现：回合到达 `assess_continuation` 时，用程序发出的 `round_conclusion_conclude{kind:'handback'}` 代替 continuation 模型调用（`schedule.ts` 的 `continuationDecision`，`forceHandback` 经 `controller.ts` 与 `local/session.ts` 透传；页面记录 `schedHandback:'player'`）。
- 评估臂不做自动链：玩家回合（主角点 + 全组点）结束后直接交还，不再产生 `continue` 的自动轮。

## 结果（base 1.7B，`offscreenPolicy=skip`）

| 回合 | 整轮等待 | 第一点完成 | 第二点完成 | 自动轮 |
|---|---|---|---|---|
| run37 s05 | **45.0 s** | 39.2 s | 44.9 s | 无 |
| run37 s06 | **41.1 s** | 27.2 s | 40.9 s | 无 |
| run38 s02 | **37.5 s** | 35.0 s | 37.3 s | 无 |
| run38 s03 | **40.7 s** | 22.3 s | 40.5 s | 无 |
| run38 s04 | **36.9 s** | 31.1 s | 36.6 s | 无 |

对照：同题 run27（默认调度）s05 137.6 s、s06 168.7 s。5/5 个回合 ≤60 s。

状态一致性：run37 回合收尾后 `round_3` 的 `cursor=14=order.length`、`concluded={kind:'handback'}`、`advance=null`、`phase='complete'`；run37 的第二回合与 run38 的三回合提交均被接受，说明交还后可以再次行动。前端全量测试 1252 passed / 17 skipped。

## 局限与必须说明的点

1. **自动链被整体跳过**：默认调度的 2–5 个自动轮（R10）不会发生。这是产品取舍——自动推进是特性，不是纯开销。
2. 结论由程序强制，但持久记录显示 `closedBy:'model'`（类型只有 model/cancel）；评估臂身份靠证据里的 `schedHandback:'player'` 区分，产品化时要改成可区分的来源。
3. 质量不变：同一 1.7B、同一提示，s06 仍把被拒的「递电台给阿豹」写成已发生；检查器 run37 报 0（其类别仍不含这类错误）。
4. 样本是 5 个回合、单机单浏览器；未测刷新恢复、两设备、离线。

## 结论

- 60 秒口径在笔记本档可以通过「玩家回合结束即交还」达到（36.9–45.0 s），代价是放弃自动链。
- 下一步产品决策：a) 接受无自动链的调度；b) 有限自动链（例如只允许一轮、或给自动链设 15 秒预算）；c) 保持默认并接受 65–180 秒的回合。D-024 需要用户选。
