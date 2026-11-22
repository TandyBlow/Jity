# Design: goal-invented-check

## Context

见 proposal。检查器已有 `prompt` 与 `prose`；新增一条按词表比对的规则，成本为零、可解释。

## Decisions

1. **窄词表**：只收高频、可判定的氛围词；宁可漏报不误报。
2. **必须同时满足「正文有、提示无」**：提示里本来就有的词不算编造。
3. **与既有类别并列**：只出 JSON 报告，不进运行期（D-021）。

## Risks / Trade-offs

- [词表覆盖有限] → 报告里写明这是启发式，人工读评仍是最终依据。
