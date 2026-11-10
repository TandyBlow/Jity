# best-of-N 分析报告

- 生成时间：2026-11-10T12:15:55.086Z
- 批次：b01
- 预注册 SHA-256：`b1079ca6ac39b68c220b2e23004131d84a90e6abc5a119518b5a7b93c56242b3`
- 检查器（机械，不是人工）：`c363360ee1ce6fbb460be91bb461f700d9f81226253807ec2027b998744e4873`
- 收益状态：**not_evaluated**

| case | 有效重复率 1-c/6 | 簇 | 事实合格 | 合格簇 | 同质门 |
|---|---|---|---|---|---|
| frozen-row-0012 | 0.333 | 4 | 0 | 0 | false |

## 发现分类总计（机械检查器）

| kind | count |
|---|---|
| fact.move_omitted | 1 |
| fact.personality_omitted | 6 |
| fact.time_missing | 6 |
| review.micro_action | 6 |
| review.pronoun | 1 |
| review.tone | 1 |

## 六个原始样本

### frozen-row-0012 (long_text)

| seed | 判定 | 事实 | 文风 | 待复核 | 必述覆盖 | 首 token ms | 总 ms | 文本 SHA |
|---|---|---|---|---|---|---|---|---|
| 17 | fail | 2 | 0 | 1 | 1/3 | 9727.352496236563 | 11983 | `73df7e315e92` |
| 29 | fail | 2 | 0 | 1 | 1/3 | 41.63921996951103 | 520 | `c2ea4c892319` |
| 43 | fail | 2 | 0 | 2 | 1/3 | 41.62045568227768 | 1322 | `0381870a9abd` |
| 61 | fail | 2 | 0 | 2 | 1/3 | 46.660467982292175 | 1791 | `145d0c38fdbe` |
| 79 | fail | 2 | 0 | 1 | 1/3 | 41.24122858047485 | 1125 | `d113c3b5fa59` |
| 97 | fail | 3 | 0 | 1 | 0/3 | 41.25695675611496 | 530 | `7dfca68bedcc` |

## 各 arm

| arm | trials | 选中事实合格率 | 选中可读合格率 | 平均覆盖 | 平均重复 | 平均调用墙钟 ms |
|---|---|---|---|---|---|---|
| N=1 | 0 | 0% | 0% | 0.00 | 0.00 | 0 |
| N=2 | 0 | 0% | 0% | 0.00 | 0.00 | 0 |
| N=4 | 0 | 0% | 0% | 0.00 | 0.00 | 0 |

## 停止/收益

```json
{
  "benefit": {
    "status": "not_evaluated",
    "reasons": [
      "arm_test_not_allowed:fewer_than_two_cases"
    ],
    "betterArms": [],
    "armTestGate": {
      "allowed": false,
      "reason": "fewer_than_two_cases"
    },
    "cases": 1,
    "casesWithDiversityGate": 0,
    "zeroQualifiedCases": 1
  },
  "stop": {
    "stopCurrentScheme": true,
    "effectiveRepetitionAbove80": [],
    "note": "preregistered stop also needs a second comparable experiment without improvement; one batch alone does not expand N"
  }
}
```

## 限制

- 机械检查器不是人工审读；`pending` 不通过。独立复核请求见 `review-request.json`，人工状态 pending。
- HPC 耗时不是浏览器耗时；60 秒首可读 / 300 秒整回合必须由 09 在同一产品页实测。
- 本批模型不是浏览器产品权重；产品结论需同条件复测。
