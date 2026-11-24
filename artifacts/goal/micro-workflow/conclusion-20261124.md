# micro-workflow 第一版（2026-11-24）

## 已接入

- 浏览器 BERT 分词器（`local/micro/tokenizer.ts`）：与 Python `BertTokenizer` 逐项对照 24/24（特殊 token、ASCII、标点、中文、截断）。
- ORT-WASM 运行时（`local/micro/runtime.ts`）：动态 import（避开 Next 预渲染的 ORT URL 问题）、int8 模型缓存、`release`、加载/推理计时；一个运行时服务所有任务。
- targets 微型端口（`local/micro/targets.ts`）：规则命中 → `source=program`；无法解析（缺席名字、多在场代词）→ int8 句对打分 → `source=micro`；仍不确定 → 弃权回退 LLM 并记原因。
- 页面开关 `?micro=1`（默认关，LLM 路径不变）；资源 `public/micro/minirbt-vocab.txt`（109 KB）与 `pair-scorer-int8.onnx`（10.5 MB）。

## 真实回合（`?micro=1`，桌面档）

- 输入「我把水壶递给诺诺。」：COMPLETED，三次运行 169–254 s，无失败。
- targets 11 次调用：6 次进入微型规则（动作证据 issue 含 `micro_targets`），其中 1 次给出非空目标（tomiyama → shen），其余规则判空；无缺席名字/双代词场景，**模型打分路径未触发**；无 LLM 回退。
- `window.__microStats/__microEnabled` 未被验收驱动捕获（评估时为空）；规则路径由动作证据的 issue 码证明。

## 未完成

- 模型打分路径的真实回合验证：需要规则弃权的输入（缺席名字或双在场代词）。
- results / updates / continuation 的微型路径；action / reaction 拆分。
- 统计汇总（rules/micro/LLM 次数与耗时、首载 vs 回合耗时）；当前首载只到 session 加载。
- 20 输入开/关对照与移动档。

## 复现

```bash
cd frontend && npx next build && npx next start -p 3177
node scripts/product-acceptance/accept-world-local.mjs \
  --base http://127.0.0.1:3177 \
  --turns ../../artifacts/goal/micro-workflow/one-turn.json \
  --out ../../artifacts/goal/micro-workflow/evidence-micro-one.json \
  --query micro=1 --fresh --allow-page-sha-mismatch --allow-unknown-page
```
