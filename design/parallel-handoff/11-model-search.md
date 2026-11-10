# 11-model-search 交接

## 问题

当前产品叙事模型是 Qwen2.5-1.5B 叙事 LoRA，历史基线是 Qwen3-1.7B。需要找这两者之外、能在同一个 Edge+wllama 运行时（浏览器 Blob 总容量上限约 2 GB）加载、中文小说叙事可能更好的 GGUF。不能按榜单或参数量猜正文质量；必须用 01/10 的同一公开冻结开发包、同条件采样、01 的 rubric 比较。

## 本轮实际交付

1. **官方来源与文件证据**：`experiments/narration-model-search/sources/capture_hf.py` 抓 8 个候选的 HF API、模型卡、config、tokenizer_config（含 chat template）、generation_config、LICENSE；`sources/hf/capture.json` 记录每个 URL、pinned revision、字节数、sha256；GGUF 文件记录 size + LFS sha256。
2. **候选登记与预筛**：`models/candidates.json` 由抓取证据 + 本地清单 + wllama wasm 架构表生成。批次 1 四型：Qwen2.5-1.5B-Instruct、InternLM2.5-1.8B-Chat、GLM-Edge-1.5B-Chat、Hunyuan-1.8B-Instruct；Gemma-3-1B gated 拿不到模板，MiniCPM5-2B 1.56 GB 超门，MiniCPM-2B 第三方 1.73 GB 超门。基线 `qwen3-1.7b-instruct` 本地哈希等于 unsloth LFS 哈希；产品 LoRA 只读复用。
3. **GGUF 算子证据工具**：`src/gguf_probe.py` 不加载权重读架构、量化、tensor 类型、模板 sha256、词表、上下文、参数量；`src/remote_gguf_head.py` 用 HTTP Range 从 pinned revision 只读文件头（8–16 MB）拿到真实架构/量化/模板，不下载整文件。实测：GLM-Edge 的 GGUF 架构是 `chatglm`（不是 glm4），Hunyuan 是 `hunyuan-dense`，Qwen3.5 是 `qwen35`；两者的模板都要求 `enable_thinking=false`；Qwen2.5 的 GGUF 模板与 base tokenizer_config 不同。`src/preview_templates.py` 再用 Jinja2 预演五个模板，确认冻结的 system+user 能渲染出完整 user 和 assistant 开头（预览非权威，HPC/09 为准）。`src/wllama_support.py` 从实际 `wllama.wasm` 提取 156 个 `llama_model_*` 架构（含 qwen2/internlm2/glm4/qwen35/hunyuan_dense/gemma3/minicpm），并明确“存在架构符号只算必要证据，真实加载由 preflight/09 证明”。
4. **冻结提示词**：`src/build_prompts.py` 校验 01 的 canonical 开发包（manifest/cases/rubric 三个哈希 + 每例 inputSha256），用训练同款 `yuyan-prose-result-v2` 序列化，空白按浏览器路径删除并记账，套 10 的 `chatml-instruct-v1` system/user。当前冻结 12/15 子集（`evidence/prompts-dev-v1/`，prompts sha256 `70475f91…`），三个无法序列化的 case 已单独报告 01（`results/11-model-search/requests/01-dev-package-canonical-delta.json`），并用 `src/propose_case_fix.py` 在内存副本上验证了最小改写可行（`results/11-model-search/requests/01-case-fix-proposal.json`），没有改 01 的包。
5. **批量执行器**：`src/screen.py` 启一个 `llama-server --jinja` 复用给全部 case；每个 case 保存请求体、原始响应、usage/timings、wall ms、finish_reason；每个模型保存 load 秒数、命令、server log tail、模型 sha256。**本线不运行它**；只在 10 的 HPC 上跑。
6. **机械汇总与复核输入**：`src/collect.py` 输出字数/句数/段数/句内重复/子句重复/耗时/tok/s，明确不产出 pass/fail（事实与文风由 01 判）；`src/make_review_input.py` 把一次 run 按 case 拼成 01 的 `NARRATION_QUALITY_ROWS` JSONL，拒绝缺例/多例/inputSha256 不一致，声明的 3 个排除例单列。
7. **HPC 请求**：`results/product/hpc-requests/11-model-search-preflight-001.json`（下载/哈希/GGUF 元数据/加载冒烟，明确非质量）；`11-model-search-quality-001.json`（`batch-2-subset12`，`readyToSubmit:true`，12/15 声明子集；不能声称完整 10/15 门）。
8. **运行时预算**：按 08 的 Blob 总容量约 2 GB，把候选 + 页面语义模型（Qwen3-0.6B，396,705,472 B）一起检查；五个候选 1.38–1.68 GB（含语义模型）全通过（`models/candidates.json` 的 `runtimeBudget`）。
9. **预注册**：`preregistration.draft.json` 冻结比较条件、基线、RUBRIC §6 晋级门（无硬错误 ≥10/15、文风不合格 ≤3、0 例无据实体、相对 Qwen3-1.7B 至少 2 例 fail→pass）、失败退出、资源估计。包/子集 pin 后升为 `preregistration.v1.json`。

## 导出 API（脚本 CLI，不是 TS 模块）

| 脚本 | 输入 | 输出 | 谁用 |
|---|---|---|---|
| `src/build_prompts.py` | 01 manifest + `--expect-manifest-sha256` + 可选 `--declare-subset` | `prompts.jsonl`、`prompts.manifest.json`、`whitespace-ledger.jsonl` | 11/10 |
| `src/screen.py` | prompts + prompt manifest + 模型路径/期望 sha | 每 case JSON + `run-manifest.json` | 10（HPC） |
| `src/collect.py` | run 目录 | `summary.json`、`summary.md`（无质量结论） | 11/01 |
| `src/make_review_input.py` | cases + run + prompt manifest | `review-rows.jsonl` + `review.manifest.json`（01 复核输入） | 11/01 |
| `src/gguf_probe.py` | GGUF 路径 | 架构/量化/tensor 类型/模板哈希 | 10/08 |
| `src/remote_gguf_head.py` | 候选 id | `models/remote-heads/<id>.json` + 模板原文（Range 读取，不下载整文件） | 11/10 |
| `src/selftest.py` | 无 | 11 项 PASS/FAIL | 11/06 复核 |

示例：

```bash
python -X utf8 src/screen.py \
  --prompts evidence/prompts-dev-v1/prompts.jsonl \
  --prompt-manifest evidence/prompts-dev-v1/prompts.manifest.json \
  --model-id internlm2_5-1.8b-chat \
  --model-path /scratch/models/internlm2_5-1_8b-chat-q4_k_m.gguf \
  --expect-sha256 ceb5ea45cddf01b024f6d5d082bcac2d3fffbc62e72fcfa543cfc6f84b805873 \
  --llama-server /scratch/llama.cpp/build/bin/llama-server --ngl 99 \
  --out evidence/runs/batch-1/internlm2_5-1.8b-chat
```

## 验证（实际跑过）

`python -X utf8 src/selftest.py` → 11/11 PASS：真实 GGUF 读取、wasm 架构表、gate 候选真实架构在 wasm 表内、错误 manifest 哈希拒绝、篡改 cases 拒绝、12 例子集冻结、collect 重复统计且无 pass、review 输入拼接与 3 个声明排除、GGUF 模板预演（5 个候选）、"screen --dry-run" 计划、registry 门一致性。没有模型推理，没有 GPU 占用。

## 限制与未验证

- 没有候选生成结果；没有质量、速度或"更好"的结论。
- 12/15 子集不是完整晋级门；三个 case 的缺陷在 01 手里。**不能用 12 例结果声称 10/15 门通过**。
- 离线模板由 llama-server 的 minja 渲染；wllama wasm 自带模板引擎的具体版本未固定。浏览器端最终以 09 的真实运行为准，preflight 只证明加载与基本生成。
- 许可只是对原文的阅读：InternLM（申请免费商用）、GLM-Edge（登记+署名）、Hunyuan（地域限制）进产品前需要决定；Qwen2.5 是 Apache-2.0。
- 页面/运行时/生成策略/训练文件都没改。

## 主 agent 需要做的接线

- **06/02/08**：先看 `models/candidates.json` 的候选与许可标记；没有质量结果前不要替换页面叙事模型。若 preflight/后续批次产出候选，接线点仍是 `NARRATION_MODEL`（`frontend/src/app/world-local/page.tsx`）和 02 的生成策略，由 06 合入；11 不写页面。
- **10**：按 preflight 请求下载/校验/加载冒烟；quality 请求当前不可提交，等 11 把 `readyToSubmit` 置 true 且 preregistration 与 prompts manifest 哈希一致。
- **09**：只在 11 报告某候选通过 RUBRIC §6 后，接 `/world-local` 做小验证；请求会带模型/模板/输入哈希与离线原始证据。不要为候选轮流占 4060。
- **01**：三个无法序列化的 case 需要修（或明确把它们从包里排除并更新 manifest/RUBRIC）；它们涉及唯一的物品转交例和两条连续例。
