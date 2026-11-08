# 排除规则自检（自动生成，勿手改）

工作树 HEAD：`ee16725640901bb66501134e83a68ac63ee80333`；脚本 `tools/exclusion_selftest.py`。

## 输入

- 排除串：13341 条（`sources/exclusion-corpus.jsonl`，sha256 `396685dd5ffab32c…`）
- 词表并集：4567 项（`sources/vocab-used.json`）
- 三臂十题：从 `narration-eval-samples.ts` 现场解析 10 条

## 结果

| 用例 | 期望 | 实测 | 命中规则 |
|---|---|---|---|
| `nv-move-1` | rejected | rejected | R1-substring, R3-signature |
| `nv-task-pers-sanity-1` | rejected | rejected | R1-substring, R3-signature |
| `nv-multi-1` | rejected | rejected | R1-substring, R3-signature |
| `nv-task-only-1` | rejected | rejected | R1-substring, R3-signature |
| `nv-refused-1` | rejected | rejected | R1-substring, R3-signature |
| `nv-empty-1` | rejected | rejected | R1-substring, R3-signature |
| `nv-cont-1` | rejected | rejected | R1-substring, R3-signature |
| `nv-cont-2` | rejected | rejected | R1-substring, R3-signature |
| `nv-cont-3` | rejected | rejected | R1-substring, R3-signature |
| `nv-multi-opposite-1` | rejected | rejected | R1-substring, R3-signature |
| 改名派生（nv-move-1 换名同形） (`deriv-renamed-move-2min`) | rejected | rejected | R3-signature |
| 改写派生（nv-empty-1 空点 5 分钟） (`deriv-paraphrase-empty-5min`) | rejected | rejected | R3-signature |
| 单位改名派生（5 分钟写成 300 秒） (`deriv-unit-renamed-300s`) | rejected | rejected | R3-signature |
| 新场景（三条事实、7 分钟） (`synthetic-fresh-ok`) | candidate | candidate | （无） |

十题完整性：True；每题 R1/R3 独立命中：True；派生仅 R3 命中：True；注记剥离回归：True。

**自检结论：通过**（三臂 10/10 被拦、两条派生均被拦、新场景未被误拦）。

## 边界

- 只证明这十条旧题与两条构造派生被规则拦下；不证明排除集完整
- R1 只做子串双向包含；改写后不共享子串的派生不会被 R1 抓到
- R3 只比事实形状；换一种形状的语义派生仍需人工核验
- 新场景判定为 candidate 只表示未被这三条规则命中，不构成验收
