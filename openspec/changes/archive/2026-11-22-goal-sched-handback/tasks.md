# Tasks

## 1. 原型

- [x] 1.1 映射回合生命周期：controller/schedule、session/transport、continuation 路径与最小改动点。
- [x] 1.2 实现评估开关 `schedHandback=player`：主角点结算并叙事完成后结束回合；默认路径不变。
- [x] 1.3 页面证据记录：交还时点、后台/延后点、状态摘要与回放一致性。
- [x] 1.4 单测：开关关闭时行为不变；开关开启时回合在主角点后关闭。

## 2. 测量

- [x] 2.1 生产构建，`next start -p 3177`。
- [x] 2.2 以 `schedHandback=player&offscreenPolicy=skip` 跑 s05/s06，记录提交→再次可行动、首段、单点时间。
- [x] 2.3 与 run27–34 的整轮等待对照，写入证据与 D-024。

## 3. 校验与收尾

- [x] 3.1 `npx vitest run` 与 `openspec validate goal-sched-handback --strict` 通过。
- [x] 3.2 按路径提交，打 tag `goal-sched-handback-20261122`。
- [x] 3.3 `openspec archive goal-sched-handback --yes`（或在用户决定前保持 active 并在 decisions 记录状态）。
