# Tasks: goal-micro-models-redesign

- [x] 1. schema 与四任务短输入定义（design.md；输入=句子+候选集）。
- [x] 2. 手标 300 条（四任务各 75）；对抗子集（换名/缺席/否定/指代/铜哨/医护附楼/干扰/多行为）。
- [x] 3. 阶梯：MLP 0.26M/0.52M、CNN 18K、GRU 31K；CNN/GRU 反超；MiniRBT 作共享编码上限（10M）。
- [x] 4. 共享编码实测（31 tokens）：WASM 1t 9.54 ms、4t 5.00 ms；encode 与头在同一图内计时；长度扫描未做（样本长度单一）。
- [x] 5. 运行时：WASM 1t 9.54 ms、4t 5.00 ms、WebGPU 14.79 ms。
- [x] 6. 真机：无可用设备，未测。
- [x] 7. 结论：共享编码毫秒级、每头微秒级；可换头顺序 judgment≈targets>intent>position；60 秒有余地，质量待更大标注；D-030 更新、归档。
