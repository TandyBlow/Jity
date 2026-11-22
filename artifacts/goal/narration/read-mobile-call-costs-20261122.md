# 移动档的调用成本（2026-11-22，run35/36）

## 数据

同一套 0.6B + Intel gen-12lp 核显；run35 加 4× CPU 限速，run36 不加。逐调用耗时（毫秒）：

| 调用 | run35 s05 | run35 s06 | run36 s05 | run36 s06 |
|---|---|---|---|---|
| updates:position | 69,267 | 59,457 | 71,670 | 77,578 |
| results | 40,502 | 62,097 | 31,083 | 41,994 |
| continuation | 31,644 | 32,054 | 30,654 | 27,493 |
| updates:appearance | 20,644 | 14,456 | 20,872 | 21,224 |
| updates:tasks | 7,425 | — | 8,569 | 8,639 |
| updates:subtasks | 4,622 | — | 6,063 | 6,111 |
| 调用数 | 14 | 9 | 14 | 14 |
| 整轮等待 | 296.3 s | 298.5 s | 283.8 s | 267.9 s |

## 结论

1. 三个调用吃掉大头：position（59–78 s）、results（31–62 s）、continuation（27–32 s），合计约 120–170 s。
2. 要摸到 60 秒，必须同时：
   - 把六阶段更新合并成更少的调用（至少 position+appearance 合一）；
   - 移动档用程序 handback 跳过 continuation（省 27–32 s）；
   - 缩短 position 提示（当前是最大的 prefill）。
3. 即使三项都做，估算地板仍在 70–90 s：results 单独就要 30–60 s。**移动档 60 秒在当前 0.6B + 核显栈里很可能到不了**；再往下只能换更快的运行时或硬件，而不是改门槛。
4. 下一步原型（需批准）：`mobileSchedule` 评估臂——合并 position+appearance，程序 handback，量真实交还时间与质量。


## Prefill 占比（同一批证据的 generations）

- 移动档每次语义调用的 `promptMs`（prefill）通常高于 `predictedMs`（解码）：例如 1738 tokens 的调用 prefill 12.6 s、解码 1.9 s；1116 tokens 的调用 prefill 9.0 s、解码 2.6 s。
- 也就是说，省时间要省「输入」与「调用数」，不是省输出。合并 stage 能省一次调用的固定开销，但合并后的 prefill 仍按新增 tokens 增长；估算合并 position+appearance 净省 10–20 s。
- 结论不变：移动档 60 s 的门槛与运行时强耦合——只有更快的运行时（WebLLM 等）或更快的硬件才可能；wllama + 0.6B + 核显的组合到不了。
