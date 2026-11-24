# Tasks: goal-mobile-kernel-schedule

- [x] 1. 探针 A：升级 wllama 4.0.0（libllama b12637）对比 3.8.1（b11364）：prefill 23.10 s vs 18.55 s（0.80×），核显无 Flash Attention；**未达 ≥2×，证伪**。证据 `artifacts/goal/narration/read-mobile-kernel-probe-20261124.md`。
- [x] 2. 探针 B：合并（f55b43e1）与程序交还（forceHandback）已是当前产品；run131 移动实测地板 s05 201.2 s / s06 161.7 s，70-90 s 估算被证伪。证据 `artifacts/goal/narration/read-mobile-schedule-probe-20261124.md`。
- [ ] 3. 组合验证：五回合 + 20 输入，记录交还时间与检查器/人工读。
- [ ] 4. 记录证据与 note；更新 D-023/D-030；达标则另开实现 change。
