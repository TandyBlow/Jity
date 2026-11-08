# 语义独立性复核（待人工）

本目录的 `semantic-review.json` 是 **AI 草稿**，`reviewer.kind = "ai"`。c3 的
`validate_holdout.py` 只接受 `reviewer.kind == "human"`，所以在有人签之前，这个包会被判
`not-admissible`（`PKG-semantic-review-not-human`），**不会**被冻结。

人工需要做的事：

1. 逐个来源读 `pairs/<id>-authorized.json` 的事实文本，并与旧材料对照
   （`.../organize-wording/controllability-v1.jsonl`、`pairs-v2.jsonl`、c3 的
   `freeze/sources.json`）。
2. 判断该来源是否与旧材料在**事件语义**上独立（不是“字面不同”，而是“说的是不同的事”）。
3. 把每个来源的 `verdict` 改成 `independent` / `semantic-duplicate` / `unsure`，
   在 `note` 里写明与哪条旧材料不同、为什么；把 `reviewer` 改成真实身份并加 `date`。
4. 任何 `semantic-duplicate` 或 `unsure` 都会让整包被拒；宁可退回重做，不要放行。
