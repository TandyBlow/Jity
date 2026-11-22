# Design: goal-legal-check

## Context

见 proposal。run37 的 s06 证据里，`results` 的原始输出为 `{"judgments":[{"memberId":"lu","label":"achieved","reason":"我成功将红色电台交给阿豹…"}],"facts":[…,"outcome":"completed"]}`；run39 为 `completed`（「部分成功」）。叙事的正文与结算一致，所以开发期正文检查器报不出问题。D-021 只允许开发期检查，因此把门放在验收驱动里，不进运行期。

## Goals / Non-Goals

- Goals：让「合法失败」场景在验收时能自动发现结算层的错误成功。
- Non-Goals：不修复结算（G5 的模型/提示问题，属 D-022 范围）；不改运行期；不扩展到任意场景的合法性推理。

## Decisions

1. **检查结算原始输出，而非正文**：正文只是照抄结算；检查正文会漏掉根因。替代方案（在 `check-prose-facts.mjs` 加类别）抓不到，因为叙事提示里的事实本身就是错的。
2. **按场景 `expect` 开关**：只对声明 `legal_failure` 的回合生效，避免把正常回合的部分完成误报。替代方案（所有回合都检查 completed）会产生大量假阳性。
3. **只记问题、不改回合结果**：驱动照常记录 `problems`，不中止。

## Risks / Trade-offs

- [合法失败回合里可能有无关的合法完成] → 当前夹具的 s06 是单一非法动作；若将来夹具含多动作，需要按 actor/action 细化。
- [模型措辞变化导致漏报] → 以 `outcome`/`label` 字段为准，不靠文本匹配。

## Migration Plan

不适用。

## Open Questions

无。
