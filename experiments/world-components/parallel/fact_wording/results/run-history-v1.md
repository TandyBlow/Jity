# 运行历史（c4 / N4）

记录每次真正启动过的运行，包括中断、重跑和被覆盖的产物。缺失的字段写“未知”，不补造。

## 1. 预检阶段（协议 v2 工具）

| 次序 | 时间 | 命令 | 结果 | 原因 / 备注 |
|---|---|---|---|---|
| 1 | 2026-11-08 下午 | `scripts/run_preflight.py` | **中断** | P4 判定脚本路径按工作树根拼接，实际清单路径是仓库相对路径 → `FileNotFoundError` |
| 2 | 同日 | 同上 | **中断** | `BeamResult` 字段名写错（`best_live_at_stop` vs `best_live_score_at_stop`） → `AttributeError` |
| 3 | 同日 | 同上 | 跑通 | 产物随后被第 4 次覆盖；中间文件的哈希**未保存，未知** |
| 4 | 同日 | 同上（加入 X1 归档对照、重建清单后） | 跑通 | `preflight.json.manifestSha256 = 40fb8211…`（v2 清单） |

预检产物目录固定为 `artifacts/fact-wording/preflight/`，第 3 次运行的文件已被第 4 次覆盖，**无法恢复**。

## 2. v3 工具重跑（协议冻结前）

| 次序 | 命令 | 结果 | 备注 |
|---|---|---|---|
| 5 | `scripts/preflight_beam2.py` | 通过 11 组 | 新增 T10（取整边界）与 T11（严格停止） |
| 6 | `scripts/run_preflight.py`（v3 清单） | 通过 P1–P9 + X1 | `manifestSha256 = a0ed91d4…`，X1 五条文本与 token 数一致 |

## 3. cf24 诊断第一轮

| 项 | 值 |
|---|---|
| 启动 | 2026-11-08 15:00:02（本机时间） |
| 命令 | `env/Scripts/python.exe -X utf8 scripts/run_diagnostic.py`，后台运行、stdout 重定向到临时日志 |
| 运行目录 | `artifacts/fact-wording/diagnostic-r1/20261108T150002-a0ed91d4/` |
| 协议 / 清单 | v3 `b1644af5…` / `a0ed91d4…` |
| 顺序规则 | cf24 契约文件行序 1–85；单元内先 greedy 后 beam2；每单元每臂一次 |
| 中途事故 | 清理空目录时误删了该运行目录下的 `env.json` 与 `run.json`（`raw.jsonl`、`order.jsonl`、`failures.jsonl` 因被进程占用未删除）。运行未中断；结束后按同一进程写出的 `run.json` 补回 `env.json`，并在报告里说明这两个文件是事后补写 |
| 结果 | 见 `results/diagnostic-r1-report.md` 与运行目录下 `raw.jsonl`/`analysis.json` |

时间与耗时以 `raw.jsonl` 内每行 `seconds` 和 `order.jsonl` 时间戳为准；本文件只记事故与次序，不改写原始数据。
