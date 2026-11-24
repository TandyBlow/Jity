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

## 任务级浏览器打分器探针（2026-11-24）

- 页面 `/micro-probe`，10 例：direct 3、pronoun 2、absent 1、empty 1、negation 2、compound 1；int8/ORT，模型加载 653 ms，单次 3–50 ms（首条含预热）。
- 原始打分器 **5/10**：direct-1/2、absent-1、empty-1、pronoun-2 正确；失败——direct-3（点头，秦越 -1.0 未过阈）、pronoun-1（「他」+双在场，两人都正分）、negation-1（否定句仍给诺诺 6.96）、negation-2（多出芬格尔）、compound-1（多出芬格尔）。
- 结论：int8 打分器目前不能当「提议者」；在否定/代词/复合上过报。产品 v1 改为「规则提议 + 打分器校验 + 弃权回 LLM」：规则给出目标后用打分器确认（阈值 0），不确认就回退；否定/缺席/多代词规则直接弃权给 LLM。模型仍是参与者，但不是最终决定者。
- 提高模型角色的前提：用产品口径的第一人称动作、否定与复合样本重训，并做「不确定即弃权」的阈值校准。

## 单回合任务耗时分布（2026-11-24，micro=1）

- results 14 次 97.8 s；action 29 次 81.4 s；updates 26 次 55.1 s；targets 11 次 6 ms。
- 结论：targets 微型化对回合耗时没有影响；下一步先做 results/updates 的微型路径，再拆 action；reaction 含在 action 调用内，随后拆。

## 真实语义输入/输出采集（2026-11-24）

- `?record=1` 包裹语义引擎，记录每次 `complete(prompt) → raw`；一轮默认 LLM 路径回合得到 79 对：results 21、updates 18、action 24、targets 11、reaction 1、continuation 4；回合 251.5 s。
- 任务拆分与训练计划见 `task-decomposition.md`；数据在 `records.jsonl`（银标，需更多回合与人工复核）。

## 校验后的训练样本（2026-11-24）

- `?record=1` + 每调用 `semanticCalls`：133 次语义调用，**99 有效 / 34 无效**。
- 无效原因：`repair_requested` 15、`action_is_task_goal` 12、`empty_targets` 12、`no_visible_candidates` 8、`target_unknown` 5、缺席人物/物品 4、`target_self` 3、`repair_failed` 1。
- updates 的无效位置例：`lu@lane/slot_body`、`caesar@red_rally/slot_waist`——模型把实体自己的槽位当成容器槽位；这类原始输出不能当标签。
- results 标签：partial 11、achieved 9、no_change 1（21 条 judgment）；action 40 条 act、0 skip（本轮偏斜）；facts 12 条、appearances 0。
- 结论：训练前必须按引擎校验过滤；当前有效样本量小（results 21、action 41、updates 有效位置有限），需要更多回合与人工复核。

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
