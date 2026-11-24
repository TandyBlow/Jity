# Tasks: goal-micro-nlu-collaboration

- [x] 1. 浏览器落盘语义 prompt（run138，20 输入）；抽 20 输入对应的调用样本。
- [x] 2. 四任务标注集（银标）：action 11、targets 41、position 15、results 31；行为分割无独立调用，记为缺；手标未做。
- [x] 3. 规模阶梯：<1M 0.52M（CV 32/41）、10M MiniRBT（CV 30/41）、100M MacBERT（无 CV，全量训练）；0.6B 基线单次 2.37 s 桌面 / 7.73 s 移动。
- [x] 4. 浏览器 harness（ORT-WASM 单线程）：<1M 0.10 ms、10M 196.4 ms、100M 2,439 ms；加载 241/532/2,402 ms。
- [x] 5. 真机：无可用设备，未测（如实记录，停止该任务）。
- [x] 6. 结论：哈希头微秒级成立；编码器类数百 ms-秒级；混合流水线有条件可能，未验证；D-023/D-030 更新、change 归档。
