# WebLLM 运行时原型：HF 下载停滞（2026-11-22）

## 已发生

1. 适配器完成：`WebLlmInferenceEngine` + 页面 `runtime=webllm` 开关，`next build` 通过。
2. 第一次单回合冒烟（4B，Cache API）：`Quota exceeded`，模型一个字节没下。
3. 1.7B 冒烟（IndexedDB 缓存）：页面 900 秒未 ready，证据里没有任何模型请求。
4. 隔离探针（不经过产品页，直接 `CreateMLCEngine('Qwen3-1.7B-q4f16_1-MLC')`）：
   - 下载能启动、能进缓存；
   - 停在 `Fetching param cache[23/30]: 615MB fetched, 66%`，之后 27+ 分钟进度文本完全不动（仍写「90 secs elapsed」）。

## 结论

- 适配器代码路径是通的：WebLLM 能初始化、能拉权重、能进 IndexedDB。
- 阻塞在 **HF CDN 在约 615 MB 处停滞**，不是产品页或适配器的 bug。
- 继续这条路必须先解决模型分发：断点续传的本地下载 + 本地托管（改 `appConfig.model_list` 的 `model` 指向 `/webllm-models/...`），或换更小的模型确认全链路。
- 在下载问题解决前，4B 的质量与时间数据无从谈起。
