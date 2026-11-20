# Proposal: G6 叙事产品路径与质量

## Why

叙事是最大风险：G3/G5 的真实运行已出现 `internal_note_in_prose` 标记、自动后续在 updates 停止导致正文被截断、以及未经过质量读评的模型正文。D-004 已冻结运行期原样输出；G6 要证明产品路径逐字等于模型返回，并用 20+ 个真实点做事实与文风读评，再由用户决定 G6 后是否加事实门。

## What Changes

- 冻结产品叙事路径：`LocalGameModel` 原样写入器/`productDefault` 候选；运行期只判空，不检查、不裁改、不补写（D-004）。
- 验证页面显示正文逐字等于 `__worldTurns[i].text`/模型返回（单元/ e2e 断言）。
- 汇总 20+ 个已提交点（G3 final4/extra、G5 语义套件）到 `artifacts/goal/narration/samples.json`，逐点附输入、已提交 Δ 摘要、模型身份、计时。
- 四类跨回合检查：状态一致、无捏造、视角/秘密、文风/自然度；硬事实错误按 acceptance 4.2 记录；失败保留。
- 用户读评（D-012）：用户读感 + 四类检查；G6 后按实测决定是否加事实门（新决定，不改 D-004）。
- 核对 beats/constrained/instruct/Qwen2.5-1.5B+LoRA/Qwen3-1.7B/Randeng-T5 的真实状态；微调前在 HPC 做 5 条公开中文续写对照。
- 记录模型/程序/检索/模板/编辑/重试各自贡献。

## Capabilities

None. 产品行为由 D-004 固定且已实现；本变更是质量评估与可能的提示/模型调整。`skip_specs: true`，原因记录于此。

## Impact

- 新增：`frontend/scripts/product-acceptance/summarize-narration.mjs`、`artifacts/goal/narration/`（样本、原始输出、读评、时间）。
- 修改（如需）：`local/game-model.ts`、`local/narration-*` 的提示或候选选择；不新增运行时叙事检查。
- 文档：`ledger.md` R11/R12/R14 行、`decisions.md`（事实门/模型变更时）。
