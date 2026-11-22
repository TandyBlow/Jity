# WebLLM 1.7B：链路跑通（2026-11-22，run57）

## 结果

- 本地权重 + OPFS 缓存：1.7B 在约 5 秒内加载完成（30/30 分片、924 MB、WebGPU nvidia）。
- 单回合（s02）**22.0 秒**完成，驱动 problems 为空（此前的「no model file」是驱动的 .gguf 匹配盲区，已修正为同时认 `.bin/.json`）。
- 分调用：results 3.0 s、position 5.0 s、appearance 1.9 s、narration 2.0–2.3 s。对比 wllama 同类的 65–180 s/回合，量级完全不同。
- 代价与缺陷：正文里夹了空的 `<think> </think>` 标记（思考开关已关，仍偶尔输出空标记）；部分 targets/action JSON 解码失败走 fallback（1.7B 的格式能力）；这两项在 4B 上要重测。

## 结论

- 运行时这条路是通的，而且性能上限比 wllama 高一个量级。
- 下一步：4B（下载中）在 OPFS 上跑 s05/s06，量质量门与时间；若 4B 的 JSON 与事实表现达标，D-022 的推荐路线就从「换运行时」的假设变成实测。
