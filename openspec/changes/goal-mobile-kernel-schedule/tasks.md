# Tasks: goal-mobile-kernel-schedule

- [x] 1. 探针 A：升级 wllama 4.0.0（libllama b12637）对比 3.8.1（b11364）：prefill 23.10 s vs 18.55 s（0.80×），核显无 Flash Attention；**未达 ≥2×，证伪**。证据 `artifacts/goal/narration/read-mobile-kernel-probe-20261124.md`。
- [ ] 2. 探针 B：`mobileSchedule`（合并 position+appearance、程序交还），量整轮地板。
- [ ] 3. 组合验证：五回合 + 20 输入，记录交还时间与检查器/人工读。
- [ ] 4. 记录证据与 note；更新 D-023/D-030；达标则另开实现 change。
