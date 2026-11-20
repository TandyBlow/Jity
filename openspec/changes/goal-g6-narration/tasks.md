# Tasks: G6 叙事产品路径与质量

## 1. 产品路径

- [ ] 1.1 断言页面显示正文逐字等于 `__worldTurns[i].text`（单元或 e2e）。
- [ ] 1.2 确认运行期只判空，无检查/裁改/补写；`narration-quality`/gate 不在运行时路径。

## 2. 样本

- [ ] 2.1 `summarize-narration.mjs` 从 G3/G5 运行提取 pointId、输入、正文、Δ 摘要、模型身份、计时、失败原因。
- [ ] 2.2 汇总 20+ 个真实点到 `artifacts/goal/narration/samples.json`；失败样本保留。

## 3. 读评

- [ ] 3.1 技术读评：四类跨回合检查逐点打分；硬事实错误按 acceptance 4.2 单列。
- [ ] 3.2 用户读评：读感 + 四类检查；用户 10 次独立输入单独记录（D-012）。
- [ ] 3.3 冻结四项阈值；未达标项保留，不降级为运行时检查。

## 4. G6 后决定

- [ ] 4.1 按 20+ 点硬错误率与用户读感，决定是否加事实门（新决定，不改 D-004）。
- [ ] 4.2 核对 beats/constrained/instruct/Qwen2.5-1.5B+LoRA/Qwen3-1.7B/Randeng-T5 真实状态；替换按 D-007 记录。
- [ ] 4.3 微调前在 HPC 做 5 条公开中文续写前后对照。

## Workflow follow-up

- 更新 `design/goal/ledger.md` R11/R12/R14 与 G6 行、`decisions.md`（事实门/模型变更）。
- `openspec validate "goal-g6-narration" --strict`，归档，按路径 commit，打 G6 tag。
