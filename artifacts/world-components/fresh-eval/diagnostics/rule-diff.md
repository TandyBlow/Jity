# R1 两版规则与逐条判定差异（自动生成，勿手改）

## 版本

| 版本 | 定义 | 何时出现 |
|---|---|---|
| **v1** | 候选正文（≥4 汉字）与排除串任一方向包含即命中；剥注记变体同样比对 | 首次筛候选时使用 |
| **v2** | 相等→命中；候选被排除串包含→命中；排除串被候选包含时，仅当该排除串 ≥8 汉字才命中，更短记 `R1-short-phrase` | **看过候选之后**才写，属事后规则变更 |

两版都保留时间归一化（R3 折算秒数），差异只在 R1。

## 逐条判定

| 项 | 点 | v1 | v1 命中 | v2 | v2 命中 | 差异 |
|---|---|---|---|---|---|---|
| `c8d01` | c8d01_p1 | source-bound | 无 | source-bound | 无 | 相同 |
| `c8d02` | c8d02_p1 | source-bound | 无 | source-bound | 无 | 相同 |
| `c8d03` | c8d03_p1 | source-bound | 无 | source-bound | 无 | 相同 |
| `c8d04` | c8d04_p1 | rejected | R1-substring | source-bound | 无 | **不同** |
| `c8d05` | c8d05_p1 | source-bound | 无 | source-bound | 无 | 相同 |
| `c8d06` | c8d06_p1 | source-bound | 无 | source-bound | 无 | 相同 |
| `c8d06` | c8d06_p2 | rejected | R3-signature | rejected | R3-signature | 相同 |
| `c8d06` | c8d06_p3 | source-bound | 无 | source-bound | 无 | 相同 |

## 差异明细

- `c8d04` / `c8d04_p1`：v1 判 rejected，v2 判 source-bound
    - v1 命中：候选句 `C完成了任务「坚持到中午十二点。」` 含排除串 `坚持到中午`（来源 s03）

## 首跑结果（事后无法复原的部分）

首次筛这六条时用的是 **R1 v1 + 全包签名**（现状读数也进签名），当时输出为：`candidate=0 fixtureBound=6 rejected=0`——六条全部通过，一条也没被拦。那次只有控制台摘要，没有单独存成文件；本表的 v1 列是**按 v1 的 R1 规则重跑**的结果，但签名已换成变化口径，所以 v1 列不是当时那次运行的逐字复现。

改口径后出现两处翻转，都记在下面：
- `c8d04`：v1 的 R1 判 rejected，v2 放行（规则变更造成）。
- `c8d06_p2`：全包签名下不撞旧题，变化口径下与 `nv-cont-2` 同形（`none|0|120s`）而判 rejected。

## 结论口径

- v2 是看过候选之后写的，**不能用 v2 的结果证明候选自身独立**。
- 本批在 v1 下 1 条被拦（c8d04），在 v2 下通过；该差异只作规则开发记录。
- 时间归一化（2 分钟＝120 秒）不属放宽，两版都保留，并由 `deriv-unit-renamed-300s` 用例守住。
