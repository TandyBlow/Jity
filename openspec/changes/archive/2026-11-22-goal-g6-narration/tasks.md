# Tasks: G6 叙事产品路径与质量

## 1. 产品路径

- [x] 1.1 页面正文与回合记录逐字一致（e2e）：页面把同一份逐点正文写进 `__worldTurns[i].points`，驱动比对去除 UI 注记与段落分隔后一致（`prose-identity-s02-20261122.json`，normalizedEqual=true）。
- [x] 1.2 运行期边界测试：叙事运行路径（narration-generation/point-narration/game-model/session/page）不 import `narration-quality`/gate（`runtime-boundary.test.ts` 通过）。

## 2. 样本

- [ ] 2.1 `summarize-narration.mjs` 从 G3/G5 运行提取 pointId、输入、正文、Δ 摘要、模型身份、计时、失败原因。
- [ ] 2.2 汇总 20+ 个真实点到 `artifacts/goal/narration/samples.json`；失败样本保留。

## 3. 读评

- [ ] 3.1 技术读评：四类跨回合检查逐点打分；硬事实错误按 acceptance 4.2 单列。
- [ ] 3.2 用户读评：读感 + 四类检查；用户 10 次独立输入单独记录（D-012）。
- [ ] 3.3 阈值未冻结：用户读评按 D-019 豁免，技术读评已记录（16 例 hard 13 / 5 例 hard 5）；不降级为运行时检查。

## 4. G6 后决定

- [ ] 4.1 事实门：未做新决定，D-004 原样输出继续生效（blocked on user）。
- [x] 4.2 候选状态已核对：TRAINED/CONSTRAINED 都 `productDefault:false`，`auto` 落回单次 raw 1.7B instruct 写作；1.7B/Q4_K_M 是实际交付文件。历史微调候选 qwen25-1.5b-narr 两轮实测均劣于默认：公版续写 65.8 s vs 39.8 s 且回声未改善；产品格式（s05/s06、skip）出现钥匙串/门缝等世界外幻觉，默认 1.7B 与状态一致（`read-15b-tuned-20261122.md`、`read-product-tuned-vs-default-20261122.md`）。该候选不进入交付。
- [x] 4.3 微调前基线完成；首次微调实验完成（集群 Qwen3-1.7B + 历史 199 行 LoRA）：公版 32.1 s vs 基座 39.8 s，但产品格式出现镜片细痕/红发转移等状态矛盾，判定不改善（`read-17b-lora-vs-base-20261122.md`）。集群流水线（训练/合并/转换/量化）已跑通；默认仍 raw 1.7B。

## Workflow follow-up

- 更新 `design/goal/ledger.md` R11/R12/R14 与 G6 行、`decisions.md`（事实门/模型变更）。
- `openspec validate "goal-g6-narration" --strict`，归档，按路径 commit，打 G6 tag。
