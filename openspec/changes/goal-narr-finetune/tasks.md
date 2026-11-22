# Tasks: goal-narr-finetune

## 数据

- [x] 1. 从 111 条真实提示去重出 84 条唯一提示（`.local/narr-train/unique.jsonl`）。
- [x] 2. 手写 84 条教师目标（`teacher-a.txt` / `teacher-b.txt`），排除 6/38/72，补 S1–S3 合法失败样本。
- [x] 3. 构造检查器形状并跑 `check-prose-facts.mjs`：84 回合 0 命中（`.local/narr-train/teacher-check.json`）。
- [x] 4. 生成 SFT 数据 `.local/narr-train/sft.jsonl`（84 行）。
- [x] 4b. 收紧 `assertKnownEntities`（缺省 outcome 视为断言），补 `settlement.test.ts` 两条断言；99 测试通过。

## 训练与转换

- [ ] 5. 下载 `Qwen/Qwen3-1.7B` HF 权重到 `.local/qwen3-1.7b-hf`（sha256/bytes 记录）。
- [ ] 6. 冒烟：2 行 1 epoch，确认编码、显存与保存路径。
- [ ] 7. 正式训练：5 epochs，保存 LoRA adapter。
- [ ] 8. 合并 LoRA → bf16 safetensors。
- [ ] 9. 转 GGUF f16 → `llama-quantize` Q4_K_M，记录 bytes/sha256。
- [ ] 10. 替换 `frontend/public/models/qwen3-1.7b-narr-lora-Q4_K_M.gguf`，更新 `page.tsx` 的 bytes/sha256，重启页面服务。

## 评估

- [ ] 11. transformers 留出提示生成，人工读评（复述/捏造/被拒动作）。
- [ ] 12. 产品 s05/s06：`accept-world-local.mjs --turns turns-semantics-s05-s06.json`，评估臂 `qwen3-1.7b-narr-lora`。
- [ ] 13. 检查器 + 人工读评 + 计时，写 `artifacts/goal/narration/read-17b-lora-v2-20261123.md`。
- [ ] 14. 更新 `decisions.md`（D-022 记录）、`ledger.md`（R10/R14 质量行）、`design/README.md` 如需。

## 收尾

- [ ] 15. `openspec validate goal-narr-finetune --strict`。
- [ ] 16. 归档 change；按路径提交；打 tag `goal-narr-finetune-20261123`。
