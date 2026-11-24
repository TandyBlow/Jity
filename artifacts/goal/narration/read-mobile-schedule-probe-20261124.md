# 探针 B：mobileSchedule 与移动地板（2026-11-24）

## 代码状态

- position+appearance 合并已在产品里：`f55b43e1`（2026-11-12，"position and appearance are one question, not two prefills"）。
- 程序交还已在产品里：`forceHandback`（session.ts，URL 臂 `schedHandback=player`）。
- 结论：探针 B 没有新实现可做；"mobileSchedule" 就是当前构建。

## 移动实测（run131，当前构建）

- 条件：Edge headless、核显（`--gpu-lite`）、CPU 4× 限速；`narrationModel=semantic`（单模型 0.6B）、`schedHandback=player`、`offscreenPolicy=skip`、`settlementUnknownRule=1`；s05/s06 两回合。
- 结果：s05 201.2 s（accepted 132.8 s）、s06 161.7 s（accepted 116.7 s）；驱动 problems 均为 `accepted_over_60s`。
- 对比：D-023 的估算地板 70-90 s 被证伪；现有合并+交还后的真实地板是 160-200 s 量级。

## 判定

- 探针 B 完成（无新实现；实测地板 161.7-201.2 s）。
- 与探针 A（内核 0.80×）合并：组合路径无法达到 60 秒。

## 20 输入移动套件（run133–137，完整 20/20）

- 5 个 chunk 顺序完成：chunk1 run133、chunk2 run134、chunk3 run135、chunk4 run136、chunk5 run137。
- 20/20 回合全部 `accepted_over_60s`；交还 137.1–272.1 s（中位约 200 s）。
- 五回合子集 s02–s06：166.1 / 231.9 / 232.6 / 187.3 / 196.5 s。
- 结论：移动档在同一 60 秒口径下 20/20 不达标，与探针 A（内核 0.80×）、探针 B（无新实现）一致；组合路径证伪。
