# 排除规则自检（自动生成，勿手改）

工作树 HEAD：`01e0a92fd88a77a4b6aec5799bc9266170ab8be1`；脚本 `tools/exclusion_selftest.py`。

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

## 签名碰撞（同一签名保留全部旧题 ID）

| 签名 | 旧题 |
|---|---|
| `none|0|300s` | nv-cont-3, nv-empty-1 |

`nv-cont-3` 与 `nv-empty-1` 都只有时间流逝，按变化口径必然同形；两者是否能互相替代，取决于它们的变化事实依据（见 `sources/three-arm-provenance.md`）。

**自检结论：通过**（三臂 10/10 被拦、三条派生均被拦、新场景未被误拦、每题 R3 命中列表含自身：True）。

## 边界

- 只证明这十条旧题与三条构造派生被规则拦下；不证明排除集完整
- R1 只做子串包含；改写后不共享子串的派生不会被 R1 抓到
- 签名相同只说明形状相同；旧题本身的变化事实依据见 sources/three-arm-provenance.md（十条均为 undetermined）
- R3 只比事实形状；换一种形状的语义派生仍需人工核验
- 新场景判定为 candidate 只表示未被这三条规则命中，不构成验收
