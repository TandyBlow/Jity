# micro-eval 结论（2026-11-24）

## 数据

- 300 条自写评测集（作者与规则同一人，独立性限制如实记录）：unknown_person 166、unknown_place 76、multi_turn 62、compound 52、implicit 50、context 50（一条可多标签）。
- 字段：targets / destination / negated；`merge_rows.py` 校验 300 行、0 错误。

## 结果（300 条，ORT CPU）

| 系统 | targets | destination | negated | targets+dest 行级 |
|---|---|---|---|---|
| 纯规则 | 269/300 | 263/300 | 262/300 | 235/300 |
| 10M 模型 | 223/300 | 208/300 | 无 | 153/300 |
| 规则 + 模型 | **280/300** | 263/300 | 262/300 | **246/300** |

- 分组（targets，规则 / 模型 / 混合）：context 38/17/40；multi_turn 55/35/59；compound 48/43/52；implicit 48/49/50；unknown_person 147/113/154；unknown_place 76/72/76。
- destination 由规则主导（263），模型单独 208。
- 混合的增益：规则为空时用模型回退，在 context、multi_turn、compound、implicit 上补 1–24 行。

## 判定

- 规则仍是主干；模型单独在三项上都不如规则，但作为回退在指代/多轮/复合构造上补点，混合最好（targets 280/300）。
- negated 只有规则提供（262/300）；模型没有该字段。
- 作者与规则同一人，数据分布偏向规则能处理的构造；结论只作方向。独立作者数据仍是下一步。
- 0.6B 与云端两臂未跑，协议的五方案还缺两臂。

## 复现

```bash
python artifacts/goal/micro-eval/merge_rows.py
python artifacts/goal/micro-eval/run_eval.py
```
