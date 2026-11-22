# Design: G5 事实层校验

## 校验规则（results 读取器）

- **识别带**：事实断言某成员有识别带，而该成员的 effective appearance（initial + active changes）含「没有…识别带」，且事实本身没有否定 → 首次 repair，最终尝试丢弃并记 `contradicts_appearance`。
- **门状态**：事实写「紧闭/关着/锁着」且未否定，成员所在房间的外观含「门敞开/开着/打开」→ 同上。
- **占位句/状态行**：`isExampleFactText` 命中 `〈…做了什么…谁回应…〉`、`(id=`、`位置为`、`精神为`、`精神值`、`任务状态`、`待办=` → 当作无结果，repair 或丢弃。
- **归属**：标准叙事 prompt 明确物品/伤势/衣物属于本人；主角只拿自己的物品。
- **已发生**：行动原文只是意图；只有结算事实里的动作才算发生。

## 约束

- 规则只在事实层拒绝，不改写已提交状态；叙事仍原样输出（D-004）。
- 规则不追求通用 NLP；每条有具体审计案例与回归测试；无法判定的（触摸/摩挲等）记 unverified，不升 hard。
- s06 judgment/fact 不一致涉及自由文本与结构化字段的交叉核对，单列未修问题，不用脆弱启发式强判。

## 证据

- 16 例技术读评：`artifacts/goal/narration/read-16-20261121.md`；原始 `audit-16-raw-20261121.txt`、`audit-16-followup-raw-20261121.txt`。
- 回归：`settlement.test.ts` 的占位句、识别带、门状态用例；`prompt.test.ts` 的归属与已发生规则。
