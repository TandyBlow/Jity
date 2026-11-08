# c3 交接页（只读状态）

日期：2026-11-08。分支 `exp/c-organize-plan`。基线提交见本文件所在目录的 `git log`。

**c3 已停止扩展工具与实验。** 没有新材料就保持当前状态。B 重训未获批准，不自动进入。

---

## 1. 当前状态：三项独立、全部未就绪

`python -X utf8 check_round_ready.py` 的输出就是状态本身，不另外解释：

| # | 状态 | 就绪 | 依据 |
| --- | --- | --- | --- |
| 1 | **留出待交付** | NO | 包已到（`artifacts/holdout-a-v1`，12 源）；卡在**人工语义签认**：c3 不再读 AI 草稿，需要单独的 `semantic-review-signoff.json` |
| 2 | **人工签认待完成** | NO | 有签认记录，但 `signerKind='ai'`、`signoffClass='audit-only'` |
| 3 | **计划训练检查点缺失** | NO | `freeze/checkpoint-adoption.json` 不存在；取证 `not-found-locally` |

```
模型能力实验：BLOCKED（未就绪：留出待交付、人工签认待完成、计划训练检查点缺失）
```

门状态：`PROVISIONAL_AI_REVIEW_ONLY`。`acceptance.json` 的 `gateReason` 写明是哪一条在挡。

---

## 2. 交接保留点一：`humanVerdict` 现在是 AI 草稿

`runs/r2/signoff-form.json` 与 `runs/r2/signoff.json` 里那 10 条 `humanVerdict`（8 × `new-content-fail`、2 × `unsure`）**是 AI 写下的草稿**，不是任何人的签认结论。

实际签认人必须：

1. 逐条读原文与证据，**确认或改写**每一条结论；
2. 留下身份、日期、审阅版本（`signer` / `date` / `reviewedCommit`）；
3. 明确勾选“逐条看过”（`iReviewedEachRow: true`）。

**只把 `signerKind` 改成 `human` 不构成人工签认**，工具也会拒绝：

- `apply_signoff.py` 在 `signerKind=human` 但 `iReviewedEachRow` 不为 true 时拒绝写出签认记录（实测：`missing: ["iReviewedEachRow"]`，退出码 1）；
- `gate_rules.py` 另外拒绝“签名串里带代理标识”的记录（`AI`、`代理`、`Codex`、`Claude`、`GPT`、`harness`、`bot` 等），即使它写着 `human`；
- 回归检查 `python -X utf8 gate_rules.py` 7/7，其中一条就叫 `test_changing_signer_kind_alone_does_not_open_the_gate`。

## 3. 交接保留点二：人工身份只是必要条件

即使有人真的签了，也不等于门就开、更不等于可以跑模型：

- `T09`（`墨`/`干纸`）保留 `unsure` 时，按冻结判据**该条不通过**，会继续留在 `openItems`；未决项按冻结规则处理，不会因为“要开门”被改判。
- 门 `OPEN` 只表示“复核流程已由人封版”，不表示所有条目通过，也不解锁模型实验——那要 `check_round_ready.py` 三项全绿。
- 谁能改判：只有签认人本人。不能为了开门把 `unsure` 写成 `paraphrase-ok`。

所以不要承诺“填了 human 门就会开”。正确的说法是：**填了 human 只可能让第 2 项变绿，第 1、3 项仍各自独立。**

---

## 3b. 2026-11-08 审阅后的修正（本轮）

| 问题 | 修法 | 回归检查 |
| --- | --- | --- |
| 改一个字段就能放行留出语义复核 | c3 不再读 AI 草稿的 verdict；新增 `semantic-review-signoff.json`，要求人工身份+日期+审阅版本+`iReviewedEachSource`，并绑定 `packageSha256`（manifest + 12 个 pair 文件）；理由不得照抄草稿模板 | `test_regressions.py` T1–T4 |
| 旧语料缺失时去重预检照常通过 | A 侧 `old_texts()` 三个语料缺任何一个或抽出 0 条就拒绝运行；`manifest` 记录每个语料的 sha256 与条数（本次 120+137+45=302） | 生成日志 `dedupeFactTexts=302` |
| 文本检查器缺 `sanity_changed`，`moved` 跨句误判 | 补 sanity 分支（症状词、无数字）；`moved` 要求 from/to 同句且 from 在前 | T5–T7 |
| 冻结件不校验材料 | `check_round_ready` 重算 manifest+pair 文件哈希与 `packageDigest`，不符即“留出冻结件已过期” | T8 |
| 12 源的门线未预登记 | `--freeze` 写入 `gateRule`：`max(8, ceil(0.8N))`，本次 12 源 = **10/12**，冻结时登记，不许挑选子集 | T9 |
| A 侧生成日期写成游戏内时间 | `createdAt`/`producedAt` 改为构建时的 UTC 时间；游戏内时间单列 `worldInternalTime` | 见 `manifest.json` |

另外：检查器升到 `c3-text-conformance-v3`，判据单列为 `freeze/criteria-v3.json`；`criteria-v2.json` 保持原样作为 R2 历史记录。R2 的 AI 审计签认因此显示“所钉文件已变”，仍只作审计。

## 4. 只接收三类外部进展

| 进展 | 到货后走哪条路径 | c3 是否会自己产生 |
| --- | --- | --- |
| A 的新留出包 | 已到 v1：六族（结构/点链/证据/授权/隔离/双计划）全过，只差人工语义签认，见 `runs/r3/holdout-acceptance.json` | 不会 |
| 实际人工签认 | 填表 → `apply_signoff.py` → `apply_review.py` | 不会（AI 草稿不算） |
| 可归因检查点 | `freeze/checkpoint-adoption.json` + `check_adoption.py` | 不会（取证已结束） |

没有新材料就保持当前状态。B 重训仍未批准。

---

## 5. 本轮冻结了什么

- 判据：`freeze/criteria-v2.json`（`c3-text-conformance-v2`，代码哈希在文件里；改了检查器会被 `run_experiment.py` 的漂移检查拦下）。
- 探针：`freeze/tamper-probes.json` 11 条，11/11 按预期（9 硬判、1 复核判失败、1 `unsure`）。
- 留出验收：`validate_holdout.py` 含生成过程与人工语义复核两道闸；bigram 只是筛查。
- 检查点采纳：`check_adoption.py` 要求哈希被三处记录字段指向，基座哈希直接拒绝。

## 6. 复现命令（不需要模型、不需要 GPU）

```bash
python -X utf8 run_experiment.py       # 18 计划 + 20 负例 + 18 参考正文 + 11 探针 + 固定策略
python -X utf8 apply_signoff.py        # 校验签认表（当前会被拒或标 audit-only）
python -X utf8 apply_review.py         # 重算门状态与逐条结论
python -X utf8 gate_rules.py           # 门规则回归 7 条
python -X utf8 check_round_ready.py    # 三项状态，退出码 0 才允许跑模型
```
