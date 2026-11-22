# Proposal: goal-narr-finetune

## Why

D-022 的剩余路线只剩「按当前叙事投影构造数据的定向微调」或收尾。集群 SSH 不可达（WinError 10060），HPC 路线无法推进；本机有 RTX 4060 8 GB、CUDA torch、peft 与 llama-quantize，可以在产品同款投影上完成一次本地微调对照。现有失败（状态复述、被拒动作写成已发生、凭空细节）在 1.7B/3B/4B × builtin/constrained/trained 全部组合上复现，提示层手段已穷尽。

## What Changes

- 用 84 条真实叙事提示（`artifacts/goal` 中的 111 条去重）构造 SFT 数据；教师目标按当前投影规则手写，覆盖正常行动、部分完成、合法失败（未知实体）三类。
- 数据先过开发期检查器 `check-prose-facts.mjs`：84 回合 0 命中后才进入训练。
- 在本机对 Qwen3-1.7B 做 LoRA（peft、bf16、gradient checkpointing）；编码与浏览器路径一致：brief prompt 走 `chatml()` 包装，再走 Qwen3 模板（`enable_thinking=false`）。
- 合并 LoRA → `convert_hf_to_gguf.py` → `llama-quantize Q4_K_M`，替换评估臂文件 `frontend/public/models/qwen3-1.7b-narr-lora-Q4_K_M.gguf`，同步 `page.tsx` 的 bytes/sha256。
- 评估：transformers 生成看留出提示；产品页 s05/s06 两回合跑 `accept-world-local.mjs`，记录检查器、人工读评与计时。默认模型不变（D-007）；是否替换默认由实测另行裁决。

## Capabilities

### New Capabilities

（无；本次是数据/训练/评估工装，不改变产品行为契约。）

### Modified Capabilities

（无。）

## Impact

- 本地工作区（gitignored）：`.local/narr-train/`（数据、脚本、LoRA、merged）、`.local/qwen3-1.7b-hf/`、`frontend/public/models/qwen3-1.7b-narr-lora-Q4_K_M.gguf`。
- 跟踪文件：`frontend/src/app/world-local/page.tsx`（评估臂 bytes/sha256）、`artifacts/goal/narration/` 证据、`design/goal/{decisions,ledger}.md`。
- 不改默认模型、不改调度、不改验收门槛。
