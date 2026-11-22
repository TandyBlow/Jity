# s06 合法失败：根因在结算层（2026-11-22）

## 发现

run37/run39 的 s06（输入「我把领用台上的红色电台递给阿豹，让他转交给裁判」，阿豹是未知实体）里，`results` 模型的原始输出：

- run37：`judgments:[{memberId:'lu', label:'achieved', reason:'我成功将红色电台交给阿豹并让他转交给裁判。'}]`，`facts:[{outcome:'completed'}]`。
- run39：`facts:[{text:'路明非部分成功完成任务', outcome:'completed'}]`。

叙事正文与结算一致——它照抄了一个错误的结算。**这不是叙事事实错误，是 G5 结算错误**：未知实体没有被拒绝，动作被判成功。

## 开发门

`accept-world-local.mjs` 新增 `expect:'legal_failure'`：该回合的 results 原始输出里出现 `outcome:'completed'` 或 `label:'achieved'` 就记 `legal_failure_not_enforced`，并写入命中文本。run39 命中，问题字段：

```json
{"problems":["legal_failure_not_enforced"],"legalFailure":{"completed":["路明非部分成功完成任务"],"achieved":[]}}
```

## 影响

1. 质量路线（D-022）必须覆盖 G5 语义；只换叙事模型或只做叙事微调不会修掉这类错误。
2. 开发期正文检查器（D-021）无法从正文发现这类问题，场景级的结算检查是必要的补充。
3. 合法失败的能力仍不达标：R01 的「未知实体不能靠叙事变成事实」正反例中，反例现在有自动证据。
