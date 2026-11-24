# Design: goal-mobile-kernel-schedule

## 调研结论（2026-11-24）

- wllama 3.8.1：`cache_prompt` 默认开，同一 worker 跨调用复用；近五回合平均命中 41–47%，同回合相邻 77–87%；WebLLM 无缓存、每次全量重算。
- WebGPU 已自动启用（V3，全层 offload）；手机模拟跑的是核显 WebGPU。
- 「静态块前置」重排已实测：命中 22%→40%，墙钟无改善，已回退。
- 剩余成本集中在 updates 家族的动态状态；缓存对它无效。

## 组合路径

```
一回合 200 s ≈ 动态 token 量 × 内核吞吐 + 解码 + 串行等待
内核：llama.cpp WebGPU 的 MMVQ/k-quant prefill（2026-05/06 落地），Intel/AMD 核显 1.5-3x
调度：position+appearance 合并、程序交还，地板 70-90 s
组合：200 s × 1/2 × 70/90 ≈ 30-60 s（两项各约 2x 才够）
```

## 风险与证伪

- Intel Xe-LPG Q4_K 损坏报告：探针 A 的第一项检查。
- 调度合并的质量影响：探针 B 后跑五回合读评。
- 若内核只有 1.3×、调度 1.3×，组合仍 >60 s，记录未过，不宣称通过。

## 判定

- 探针不改产品默认；组合达标后另开实现 change。
