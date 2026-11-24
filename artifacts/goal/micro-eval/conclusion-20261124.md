# micro-eval 结论（2026-11-24）

## 数据

- 300 条自写（作者与规则同一人，独立性未满足）：unknown_person 166、unknown_place 76、multi_turn 62、compound 52、implicit 50、context 50。
- 已知弱点：context 部分样本只有 1 个在场人物；multi_turn 样本直接出现姓名——对复杂语言理解的考察偏弱。
- `merge_rows.py` 校验 300 行、0 错误。

## 结果（300 条；10M 为 int8、0.6B 为 Q4，ORT/浏览器）

| 系统 | targets | destination | negated | 三字段全对 | 单次耗时 |
|---|---|---|---|---|---|
| 纯规则 | 269 | 263 | 262 | 227 | <0.2 ms |
| 10M 模型 | 218 | 207 | — | — | ~4 ms（浏览器） |
| 规则+10M | 280 | 263 | 262 | 225 | 混合 |
| 规则+10M（cue 门控） | 275 | 263 | 262 | **229** | 混合 |
| 0.6B | 145 | 233 | 278 | 103 | 1998 ms |
| 规则+0.6B 否定 | 269 | 263 | 278 | 214 | +2 s/次 |
| 规则+10M+0.6B 否定 | 280 | 263 | 278 | 230 | 按需 |
| 规则+10M（cue）+0.6B 否定 | 275 | 263 | 278 | 222 | 按需 |

- 0.6B 解析 299/300，p95 2518 ms；`eval-06b.log`、`results-06b.json`。
- 复现口径修正：评估改用 int8 模型（与协议 sha 一致）；fp32 对照的 10M 为 223/208/153，int8 为 218/207/148（-5 行）。

## 混合的回退问题（复核轮指出）

- 规则 targets 为空且期望为空：66 行，模型误加目标 6 行；规则为空且期望非空：30 行，模型答对 17 行。
- 三字段全对：规则 227 → 混合 225（-2）；规则对/混合错 5 行，规则错/混合对 3 行。
- cue 门控（只有代词/省略线索才回退）后 targets 275、三字段 229，修掉了回退的净损失；代价是 targets 少 5 行。

## 判定

- 规则仍是主干；10M 单独不如规则；混合在 targets 上最好，但三字段被回退误报吃掉 2 行，门控后 229 最高（不含 0.6B）。
- 0.6B 单独弱（三字段 103），否定字段最好（278）；按需用于否定时，混合从 225 到 230（+5），但 cue 门控版本从 229 到 222（-7）——300 行内是噪声级差异，且每次多 2 s。
- 作者与规则同一人、数据对复杂语言考察偏弱：以上只作方向；独立/更难的测试集与云端对照仍是下一步。
- 云端未跑。

## 复现

```bash
python artifacts/goal/micro-eval/merge_rows.py
python artifacts/goal/micro-eval/run_eval.py
python artifacts/goal/micro-eval/analyze_hybrid.py
python artifacts/goal/micro-eval/make_06b_data.py
bash artifacts/goal/micro-eval/run_06b.sh 0 25 50 75 100 125 150 175 200 225 250 275
python artifacts/goal/micro-eval/score_06b.py
python artifacts/goal/micro-eval/analyze_combos.py
```
