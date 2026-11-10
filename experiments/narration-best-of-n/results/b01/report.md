# best-of-N 分析报告

- 生成时间：2026-11-10T15:21:41.909Z
- 批次：b01
- 预注册 SHA-256：`b1079ca6ac39b68c220b2e23004131d84a90e6abc5a119518b5a7b93c56242b3`
- 检查器（机械，不是人工）：`92eccd94daa58ed9d075ce91d9be93ec96fc260fb9866b767b07700567219d5f`
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

## 证据与整作业耗时

| batch | calls | raw sha | run wall ms | observed gaps |
|---|---|---|---|---|
| b01 | 6 | `b2324fa56b90` | 76000 | 0 |

`observed gaps = 0` 也可能是旧 runner 没有记录 `gapBeforeMs`，不代表没有空档；b01 的 44 s 调用间空档见 `hpc-record.json` 与 `cause-analysis-b01.md`。

## 六个原始样本

### frozen-row-0012 (long_text)

| seed | 判定 | 字数 | 事实 | 视角 | 文风 | 待复核 | 必述覆盖 | 首 token ms | 总 ms | 文本 SHA |
|---|---|---|---|---|---|---|---|---|---|---|
| 17 | fail | 52 | 2 | ok | 0 | 1 | 1/3 | 9727.352496236563 | 11983 | `73df7e315e92` |
| 29 | fail | 20 | 2 | ok | 0 | 1 | 1/3 | 41.63921996951103 | 520 | `c2ea4c892319` |
| 43 | fail | 62 | 2 | ok | 0 | 2 | 1/3 | 41.62045568227768 | 1322 | `0381870a9abd` |
| 61 | fail | 94 | 2 | reject | 0 | 2 | 1/3 | 46.660467982292175 | 1791 | `145d0c38fdbe` |
| 79 | fail | 50 | 2 | ok | 0 | 1 | 1/3 | 41.24122858047485 | 1125 | `d113c3b5fa59` |
| 97 | fail | 22 | 3 | ok | 0 | 1 | 0/3 | 41.25695675611496 | 530 | `7dfca68bedcc` |

## 各 arm

| arm | trials | 选中事实合格率 | 选中可读合格率 | 平均覆盖 | 平均重复 | 平均调用墙钟 ms |
|---|---|---|---|---|---|---|
| N=1 | 0 | 0% | 0% | 0.00 | 0.00 | 0 |
| N=2 | 0 | 0% | 0% | 0.00 | 0.00 | 0 |
| N=4 | 0 | 0% | 0% | 0.00 | 0.00 | 0 |

每个 N arm 评估全部 C(6,N) 子集，不用种子前缀；补充定义见 `analysis-addendum-arms.md`。

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
    "source": "RESTART-AFTER-REVIEW.md",
    "sourceSha256": "20238282a0069cf34f40e49d8ab1691e2fc35de47faf99a0762a68ff30d016ce",
    "note": "stopCurrentScheme=true: no N expansion and no rerun of this zero-qualified scheme; keep the six raw outputs. A scheme stop is not product completion."
  }
}
```

## 限制

- 机械检查器不是人工审读；`pending` 不通过。独立复核请求见 `review-request.json`，人工状态 pending。
- HPC 耗时不是浏览器耗时；60 秒首可读 / 300 秒整回合必须由 09 在同一产品页实测。
- 本批模型不是浏览器产品权重；产品结论需同条件复测。
