# Tasks: goal-mobile-kernel-schedule

- [ ] 1. 探针 A：重编/升级 wllama wasm 到当前 llama.cpp WebGPU；手机模拟单测 position 调用，记录内核版本与 ≥2× 是否达成。
- [ ] 2. 探针 B：`mobileSchedule`（合并 position+appearance、程序交还），量整轮地板。
- [ ] 3. 组合验证：五回合 + 20 输入，记录交还时间与检查器/人工读。
- [ ] 4. 记录证据与 note；更新 D-023/D-030；达标则另开实现 change。
