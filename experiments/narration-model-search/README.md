# 叙事模型搜索（11 线）

目标：在 Qwen3-1.7B 之外找**能在这个浏览器运行、中文小说叙事可能更好**的 GGUF 模型/量化配置。这里只做**离线筛选**，不是产品、不是质量验收、也不是 09 的浏览器验收。本目录的每个数字都来自可复跑的脚本或原始抓取，不按榜单/参数量推断正文质量。

## 当前结论（2026-11-10）

**还没有任何候选跑过生成**。本轮交付的是：官方来源与文件证据、候选/基线登记、冻结提示词工具、批量筛选执行器、HPC 请求、以及一个必须先解决的共享开发包缺陷（见下）。**不能**据此说某个模型更好或产品达标。

### 预筛结果（EXPLORATION-AND-ACCEPTANCE 的初始门）

| id | 文件大小 | 许可 | 架构（GGUF/wllama） | 结论 |
|---|---|---|---|---|
| `qwen25-1.5b-instruct` | 1,117,320,736 | Apache-2.0 | qwen2（GGUF 头已确认）/ 在 wasm 表中 | 进入批次 1；本地已有同哈希文件 |
| `internlm2_5-1.8b-chat` | 1,172,364,032 | 权重“学术+申请免费商用”，GGUF 仓库 Apache-2.0 | internlm2（GGUF 头已确认）/ 在 wasm 表中 | 进入批次 1；产品使用需许可决定 |
| `glm-edge-1.5b-chat` | 980,470,144 | GLM-Edge 自定义（商用需登记+署名） | **chatglm**（GGUF 头确认；不是 base config 名字暗示的 glm4）/ 在 wasm 表中 | 进入批次 1；产品使用需许可决定 |
| `hunyuan-1.8b-instruct` | 1,133,085,088 | Tencent Hunyuan 社区许可（不含 EU/UK/韩国） | hunyuan-dense（GGUF 头确认）/ 在 wasm 表中 | 进入批次 1；GGUF 是第三方量化，产品使用需许可决定 |
| `gemma3-1b-it-qat` | 1,003,541,152 | Gemma Terms，仓库 gated | 期望 gemma3 / 在 wasm 表中 | 未过门：config/tokenizer 401，拿不到模板；需接受许可/授权 token |
| `minicpm5-2b` | 1,561,318,368 | Apache-2.0 | 期望 minicpm（base config）/ 在 wasm 表中 | 未过门：超出 1,500,000,000 字节初批上限（超 61 MB） |
| `minicpm-2b-dpo`（第三方 Q4_K_M） | 1,729,503,200 | 仓库无许可标签 | 期望 minicpm / 在 wasm 表中 | 未过门：超尺寸，且许可不清 |

基线（不重复下载）：`qwen3-1.7b-instruct`（本地 sha256 `b139949c…` 等于 unsloth/Qwen3-1.7B-GGUF 的 LFS 哈希）与当前产品叙事 LoRA `product-narr-qwen25-1.5b`（`6ed2268d…`）。08 已实测浏览器 Blob 总容量上限约 2 GB；批次 1 候选都 ≤1.18 GB，和 1.5 GB 单文件门一致。4B 不再排。

**真实 GGUF 头证据**：`src/remote_gguf_head.py` 用 HTTP Range 只读文件开头（8–16 MB），从 pinned revision 直接读出 `general.architecture`、量化类型、tensor 类型、内嵌 chat template 与哈希；没有下载完整权重，也没有推理。四个候选都是 Q4_K_M（F32/Q4_K/Q6_K），没有未知 tensor 类型。GLM-Edge 的真实架构是 `chatglm`（可加载），Hunyuan 是 `hunyuan-dense`，其模板含 `enable_thinking`，批量执行时必须传 `chat_template_kwargs={enable_thinking:false}`；Qwen2.5 的 GGUF 内嵌模板与 base tokenizer_config 不是同一份（哈希 `d5495a1e…` vs `cd8e9439…`），以 GGUF 为准。

证据位置：`models/candidates.json`（由 `sources/hf/capture.json`、`models/local-inventory.json`、`models/wllama-support.json` 生成），官方卡片/配置/tokenizer 模板/许可证原文在 `sources/hf/<id>/`，每个抓取的 URL、revision、字节数、sha256 在 `sources/hf/capture.json`。

## 共享开发包：只认 01 的一份

01 已发布 `results/quality/dev-package-v1/`（15 例）：

- `cases.jsonl` sha256 `8dd2de92…`
- `manifest.json` sha256 `20da8db9…`
- `RUBRIC.md` sha256 `020c9ca9…`

我没有另建包。`src/build_prompts.py` 会先核对 manifest 哈希、manifest 里记录的 cases 哈希、以及每一例的 `inputSha256`，任何不一致直接退出。

**已发现 3 例无法用参考序列化器建提示词**（更早的 05 增量字段形状，不是模型结果）：

- `tide-continuity-tide-duty-t2`：`任务` 操作（应为 `完成任务/新增小任务`）
- `tide-continuity-tide-duty-t3`：`解除外貌` 是字符串（应为数组）
- `fixture-goggles-transfer`：`外貌` 操作（应为 `新增外貌`），而且它是唯一一例物品转交，不能静默跳过

已写 `results/11-model-search/requests/01-dev-package-canonical-delta.json` 给 01。当前冻结的是**在看任何模型输出之前就声明的 12 例子集**（`subset-declaration.json`），只作为子集证据；完整 10/15 晋级门必须等 01 修好或明确确认子集。没有把 05 的事实改写成另一种形状。

## 比较条件（已冻结在 `preregistration.draft.json`）

- 序列化：`yuyan-prose-result-v2`（`experiments/narration-runtime-v2/src/v2_render.py`，训练同款），空白按浏览器路径删除空格/Tab/U+3000 并逐字段记账。
- 对话包装：10 的 `chatml-instruct-v1` system + `【已结算输入】` + 序列化正文 + `请写出这一回合的正文。`
- 模板应用：每个模型**自己的 GGUF chat template**，由 `llama-server --jinja` 渲染；不手写 ChatML。
- 采样：greedy（`temperature=0, top_k=1, top_p=1, seed=42, max_tokens=320, n_ctx=8192`），停止符 `<|im_end|>`/`<|endoftext|>`。
- 判定：01 的 `RUBRIC.md` + 01 独立复核；11 只产原文和机械汇总，不签发通过。

## 文件与复跑

```
experiments/narration-model-search/
├── sources/capture_hf.py           # 抓 HF API/卡片/config/tokenizer/许可证，记录 revision+sha256
├── sources/hf/                     # 原始抓取字节 + capture.json
├── src/gguf_probe.py               # 不加载权重读 GGUF：架构/量化/tensor 类型/模板哈希/参数量
├── src/inventory_local.py          # 已下载 GGUF 的只读清单（sha256 + GGUF 元数据）
├── src/wllama_support.py           # 从实际 wasm 提取 llama_model_* 架构表
├── src/remote_gguf_head.py         # 远程 GGUF 头/元数据/模板的 Range 读取（不下载整文件）
├── src/build_candidates.py         # 生成 models/candidates.json 并应用预筛门
├── src/build_prompts.py            # 校验 01 包哈希 -> 冻结 12 例提示词（subset-declaration.json）
├── src/screen.py                   # llama-server --jinja 批量执行器（仅 10 在 HPC 跑）
├── src/collect.py                  # 机械汇总：字数/句数/重复/耗时，不判质量
├── src/make_review_input.py        # 把一次 run 接成 01 的 batch harness 输入（{id,input,text}）
├── src/selftest.py                 # 10 项离线自检，无模型推理
├── src/make_requests.py            # 写 10 的 HPC 请求 JSON
├── models/candidates.json          # 候选/基线/预筛结论/运行时上限
├── models/remote-heads/            # 每个候选的 GGUF 头摘要 + 内嵌 chat template 原文
├── evidence/prompts-dev-v1/        # 冻结的 12 例提示词 + 哈希清单 + 空白账本
├── subset-declaration.json         # 12/15 子集的预先声明和三个排除原因
└── preregistration.draft.json      # 比较条件、晋级门、失败退出、资源估计
```

复跑（本机，无模型推理）：

```bash
cd experiments/narration-model-search
python -X utf8 src/selftest.py
python -X utf8 src/build_prompts.py \
  --manifest D:/others/Jity/.local/parallel-local-game/results/quality/dev-package-v1/manifest.json \
  --expect-manifest-sha256 20da8db9051740a48901bf143fdff5fde01aac2accc691409e74c9acba386dc7 \
  --out-dir evidence/prompts-dev-v1 \
  --declare-subset subset-declaration.json --skip-serializer-errors
python -X utf8 src/screen.py --dry-run --model-id qwen25-1.5b-instruct \
  --prompts evidence/prompts-dev-v1/prompts.jsonl \
  --prompt-manifest evidence/prompts-dev-v1/prompts.manifest.json
```

真实批量执行（只在 HPC，10 提交）：请求见
`results/product/hpc-requests/11-model-search-preflight-001.json`（下载/哈希/GGUF 元数据/加载冒烟，**非质量**）和
`results/product/hpc-requests/11-model-search-quality-001.json`（质量批次，`readyToSubmit:false`，等 01 修包/确认子集）。

## 明确没做

- 没跑任何模型生成；没有候选的正文、速度或质量比较。
- 没跑浏览器；09 只接通过质量门后的少量候选。
- 没改页面、runtime、02 生成、04/07 约束、10 训练文件。
- 许可证结论只是对抓到的许可证原文的阅读，不是法律意见；InternLM/GLM/Hunyuan 进产品前需要用户/产品决定。

## 下一步（有证据就推进，不空转）

1. 01 修 3 例或确认 12 例子集 → 重跑 `build_prompts.py` 并 pin `preregistration.v1.json`，把 quality 请求 `readyToSubmit` 置 true。
2. 10 先跑 preflight（下载 4.4 GB、哈希、GGUF 元数据、加载冒烟、实际 tok/s）。
3. preflight 通过后按冻结条件跑质量批次；01 独立复核。
4. 只有达到 RUBRIC §6 的候选才交 09 的 `/world-local` 浏览器小验证；其余候选保留负面证据，不轮流占 4060。
