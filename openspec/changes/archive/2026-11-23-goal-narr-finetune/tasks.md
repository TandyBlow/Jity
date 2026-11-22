# Tasks: goal-narr-finetune

## 数据

- [x] 1. 从 111 条真实提示去重出 84 条唯一提示（`.local/narr-train/unique.jsonl`）。
- [x] 2. 手写 84 条教师目标（`teacher-a.txt` / `teacher-b.txt`），排除 6/38/72，补 S1–S3 合法失败样本。
- [x] 3. 构造检查器形状并跑 `check-prose-facts.mjs`：84 回合 0 命中（`.local/narr-train/teacher-check.json`）。
- [x] 4. 生成 SFT 数据 `.local/narr-train/sft.jsonl`（84 行）；v2 `sft2.jsonl`（108 行）、v3 `sft3.jsonl`（148 行）。
- [x] 4b. 收紧 `assertKnownEntities`（缺省 outcome 视为断言），补 `settlement.test.ts` 两条断言；99 测试通过。

## 训练与转换

- [x] 5. 下载 `Qwen/Qwen3-1.7B`：shard1 3,441,185,608 B `169ad53e…ed5`、shard2 622,329,984 B `912becff…ff9`。
- [x] 6. 冒烟：2 行 1 epoch，编码/显存/保存通过。
- [x] 7. 三轮训练：v1 84 行 loss→0.39、v2 108 行→0.33、v3 148 行→0.09。
- [x] 8. 合并 LoRA → bf16 safetensors（v1/v2/v3）。
- [x] 9. 转 GGUF f16 → `llama-quantize` Q4_K_M：v3 1,107,408,768 B，sha256 `f4c0e366…3b38`。
- [x] 10. 替换评估臂文件，更新 `page.tsx` bytes/sha256，重建并重启 3177。

## 评估

- [x] 11. transformers 留出/同题生成：v3 在交接无结算与「只有诺诺看规则」两形状上干净。
- [x] 12. 产品 s05/s06：run85（v2）s06 结算中止；run86（+规则）误报后修门；run87（v2）s06 写「阿豹在巷里」；run88（base）复述+完成；run89（v3）0 问题、检查器 0、4.2 硬错 0；run90（v3 五回合）s06 结算中止，s02/s03/s05 未结算事件。
- [x] 13. 检查器 + 人工读评 + 计时：`artifacts/goal/narration/read-17b-lora-v2-20261123.md`。
- [x] 14. 更新 `decisions.md` D-022、`ledger.md` R01/R11。

## 收尾

- [ ] 15. `openspec validate goal-narr-finetune --strict`。
- [ ] 16. 归档 change；按路径提交；打 tag `goal-narr-finetune-20261123`。
