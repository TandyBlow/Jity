# WebLLM 1.7B：链路跑通（2026-11-22，run57）

## 结果

- 本地权重 + OPFS 缓存：1.7B 在约 5 秒内加载完成（30/30 分片、924 MB、WebGPU nvidia）。
- 单回合（s02）**22.0 秒**完成，驱动 problems 为空（此前的「no model file」是驱动的 .gguf 匹配盲区，已修正为同时认 `.bin/.json`）。
- 分调用：results 3.0 s、position 5.0 s、appearance 1.9 s、narration 2.0–2.3 s。对比 wllama 同类的 65–180 s/回合，量级完全不同。
- 代价与缺陷：正文里夹了空的 `<think> </think>` 标记（思考开关已关，仍偶尔输出空标记）；部分 targets/action JSON 解码失败走 fallback（1.7B 的格式能力）；这两项在 4B 上要重测。

## 结论

- 运行时这条路是通的，而且性能上限比 wllama 高一个量级。
- 下一步：4B（下载中）在 OPFS 上跑 s05/s06，量质量门与时间；若 4B 的 JSON 与事实表现达标，D-022 的推荐路线就从「换运行时」的假设变成实测。


## s05/s06 追加（run58）

- 两回合都在 11.8/12.6 秒内完成，但结算被 codec 拒绝：模型把 `label` 写成 `completed`（合法值是 achieved/partial/not_achieved/blocked/no_change）。这是 1.7B 的格式能力，不是运行时。
- 正文里仍夹空的 `<think> </think>` 标记。
- 结论不变：1.7B 证明运行时快，但结算格式需要 4B；4B 下载完成后直接测。


## 4B 加载（run59–61）

- 4B（2.2 GB、83 文件）已本地化到 `public/models/webllm/Qwen3-4B-q4f16_1-MLC/resolve/main/`。
- OPFS 后端：在 768 MB 报 `QuotaExceededError`；但页面实测 `navigator.storage.estimate()` 的配额是 10 GB、usage 0——所以是 OPFS 后端自身的坑，不是真的没空间。
- Cache API 后端的 4B 测试被宿主内存回收杀掉（系统 low memory），按回收规则未自行重启。
- 当前结论：4B 的加载路径还差最后一步验证；1.7B 已证明运行时可用（22 s/回合）。等用户允许后再试 Cache API 或持久化 profile。


## 4B 打通（run63，持久化 profile）

- 独立探针：4B 完整加载（74/74、2.2 GB、WebGPU）并生成「你好！」。
- 验收驱动加 `--profile` 后，4B 在同一 profile 的缓存上 6 秒加载完成（2.16 GB）。
- 产品单回合仍失败：`results` codec 报 `fact text must be non-empty`，28.6 秒结束——不是运行时问题，是 4B 的首轮输出格式/内容问题，下一步看 s05/s06 的原始输出再决定是否修提示。
