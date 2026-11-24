# Proposal: goal-mobile-kernel-schedule

## Why

移动档 60 秒门槛在当前实现下实测 189–229 秒。三条线调研（2026-11-24）确认：wllama 3.8.1 已默认开 `cache_prompt`（近五回合平均命中 41–47%），WebGPU 已启用（全层 offload），静态块前置重排已试过且墙钟无改善；真正的时间在 updates 家族的动态状态（position 提示 2,220–11,595 字符，缓存无解）。剩余可信路径只有「新内核 × 调度合并」的组合。

## What Changes

- 探针 A：用当前 llama.cpp WebGPU 重编/升级 wllama wasm，手机模拟单测 position 调用，目标 ≥2×。
- 探针 B：实现 `mobileSchedule`（合并 position+appearance、程序交还跳过 continuation），量整轮地板。
- 组合验证：五回合 + 20 输入，检查 60 秒与质量。
- 预期：两项各 ~2× 时组合进入 30–60 秒；任一项不足则记录未过。

## Capabilities

（无；探针与验证，不先写产品代码。）

## Impact

- 探针阶段不动产品默认；若组合达标，另开实现 change 并更新 D-023。
- 风险：Intel Xe-LPG 的 Q4_K 内核有损坏报告；调度合并影响质量。
