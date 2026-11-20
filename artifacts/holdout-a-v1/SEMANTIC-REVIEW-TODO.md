# 语义独立性复核（待人工签认）

本目录有两份文件，不要混用：

| 文件 | 谁写 | 作用 |
| --- | --- | --- |
| `semantic-review.json` | A 侧（AI） | **草稿**，`reviewer.kind = "ai"`；c3 不读它的结论 |
| `semantic-review-signoff.json` | 人 | **正式签认**；c3 只认这一份 |

`semantic-review-signoff.template.json` 是空表，已绑定当前包的哈希（`packageSha256`）。

人工需要做的事：

1. 逐个来源读 `pairs/<id>-authorized.json` 的事实文本，并与旧材料对照
   （`.../organize-wording/controllability-v1.jsonl`、`pairs-v2.jsonl`、c3 的
   `freeze/sources.json`；逐条最相近旧句和相似度见 `semantic-review-evidence.json`）。
2. 判断该来源是否与旧材料在**事件语义**上独立（不是“字面不同”，而是“说的是不同的事”）。
3. 复制模板为 `semantic-review-signoff.json`，逐源填写 `verdict` 与 `reason`
   （理由不能照抄草稿里的同一句模板，c3 会拒），填 `reviewer.identity`、`reviewer.date`、
   `reviewedCommit`，并保持 `iReviewedEachSource: true`。
4. **不要改 `packageSha256`**。任何 pair 文件变动都会让签认失效，c3 会判 `PKG-semantic-signoff-stale`。
5. 任何 `semantic-duplicate` 或 `unsure` 都会让整包被拒；宁可退回重做，不要放行。
