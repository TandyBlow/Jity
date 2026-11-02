# 退役记录：Qwen3-0.6B

日期：2026-11-02。状态：**已退役，不再作为任何组件的候选、基线或对照臂。** 历史归档保留，用作退役证据。

## 结论

按本项目已归档的真实浏览器路径，Qwen3-0.6B 的单次生成延迟不适合交互回合：

| 场景 | 实测 | 来源 |
| --- | --- | --- |
| 叙事生成（29 次，真实 Edge＋wllama） | **mean 13.986 s、p50 13.497 s、范围 9.7–21.2 s**；加载 10.9 s；CPU 4 线程、n_ctx 4096、maxTokens 160、cache_prompt=false | `artifacts/narration-eval-recheck/README.md`、`run.json` |
| 叙事拆分实验（14 次） | **mean 10.2 s、p50 10.1 s** | `design/world-engine-reports/narration-split-experiment-design.md` §5 |
| N2 内容选择（单次） | **约 24 s** | `design/world-engine-reports/components/n2-content-selection.md` |
| 旧 benchmark 记录 | 仅 prefill 已约 **115 s**，远超 4 s 线 | `artifacts/benchmark/narration-trial-1791713208385.json` |

交互目标按既有记录为单次叙事约 **4 s**。10–14 s 已是目标的 2.5–3.5 倍，N2 的 24 s 更不成立。延迟不是一次抖动：多次运行、多个任务方向都复现。

## 口径

- 这不是“0.6B 权重在任何环境都不可用”的普遍结论；它是对**已归档的 Edge＋wllama＋CPU 配置**的退役决定。
- 重新考虑的条件：新的运行时/量化/上下文配置能给出**同任务、同判据、真实浏览器**的单次延迟与质量证据，并重新立项；不得仅因模型小或换了一个运行时就把 0.6B 放回候选表。
- 停止使用的原因不止延迟：N2 视角选择 4/16、叙事自然臂 10/16、任务目标原文丢失等质量问题也在归档中。延迟是硬门槛，质量失败是叠加理由。

## 当前文档的处理

- 已从 C 当前候选表/路线表的**候选列**移除：`component-contracts.md`、`model-training-runtime.md`、`README.md`。
- 历史 F 条目、历史实验报告与 `artifacts/**` 中的模型身份和耗时**不删除、不改写**——它们是退役依据；相关段落标注“已退役/仅历史证据”。
- 仍提及 Qwen3-0.6B（历史证据或退役说明）但不再作为候选的文档：`n2-content-selection.md`、`batch-delivery-registration.md`、`fix-round-1c41587.md`、`d2-gold-prep.md`、`design/browser-world-state-workflow.md`、`b3-prompt-eval-design.md`、`b2-runtime-design.md`、`browser.md`、`narration-split-experiment-design.md`。这些位置的数字保留；新工作不得据此把 0.6B 重新列为候选。

## 替代

- **叙事生成 N4**：Randeng-T5-77M 仍是唯一已有浏览器适配证据的生成候选（ORT-web＋sentencepiece-js＋KV 环）。质量未全绿，但延迟量级与浏览器路径可继续验证。
- **编码器任务头**：MiniRBT-H256 仍是候选；已实测否决的 N2 头不因本次退役改变。
- **其他生成任务（C1/C2/C4/C5/C6）**：生成骨干候选待定；先用 N4 的 T5 结果判断共享骨干是否够用，不预设 0.6B 或 1.7B。

## 不做

- 不删除历史归档来“让数字消失”。
- 不把 0.6B 的失败改写成通过。
- 不在当前页面门、H2 冻结或既有验收里改范围；退役只影响 C 的新组件选型。
