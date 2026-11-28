# P07 独立产品验收矩阵：7 项通过、1 项部分、2 项失败、1 项阻塞、1 项未复跑

**Question.** 不重跑重型实验的前提下，用仓库里的冻结证据独立复算，产品验收的每一项到底是
通过、失败、还是没测？

**Method.** 只读复算：`scenario_report.py` 重算八场景状态/任务断言；`summarize-timing.mjs`
重算 20 输入计时门；`verify_run.py` 重算模型/引擎/LLM 调用；直接解析离线、断 API、两设备、
移动代理、真机与刷新恢复证据。大型原始证据保留本地，仓库内只放哈希摘要。没有启动浏览器，
没有抢租约；平台自己的冻结构建尝试见 P06。

**Matrix.**

| 验收项 | 结果 | 证据 | 独立复算 |
|---|---|---|---|
| 20 输入计时 | **PASS** | `09-turns20-pi.json` | 20/20；首段最差 13,732 ms；单点正文最差 191,232 ms；0 未完成 |
| 20 输入刷新恢复 | **PASS** | 同上 `refreshRestore` | entries 20→20、historyStable、tasksStable、stateRestored |
| 八场景状态/任务（rules 臂） | **PASS（regression）** | `scenarios8-rules.json` | 状态 48/48、任务 14/14、达成 3/3、正文问题 0 |
| 八场景状态/任务（micro 臂） | **PASS（regression）** | `evidence-independent-scenarios-11.json` | 状态 48/48、任务 14/14、达成 3/3、正文问题 0 |
| 离线 | **PASS** | `10-offline-pi.json` | 2/2、offline=true、failures 0、刷新恢复 2/2 |
| 服务器关闭（断 API） | **PASS** | `g8-block-api-rerun-20261122-…json` | 2/2、saveServiceBlocked=true、failures 0、1.7B 权重 2/2 |
| 两设备分叉 | **PASS** | `artifacts/goal/sync/two-device-20261121.json` | status PASSED、choice keep-local-fork、failures 0 |
| 移动代理（4× CPU + gpu-lite） | **首段 PASS，整回合未达 60 s** | `evidence-mobile-proxy-1/2.json` | 2/2 完成；首段 22.1–33.1 s；整回合等待 218.6–278.1 s |
| 移动默认档刷新恢复 | **FAIL** | `smoke-mobile-defaults{,-rerun}-20261127.json` | 4 回合后刷新：history 4→0、tasks 空、overallRestored=false，两次都失败 |
| 真机手机 | **FAIL** | `evidence-phone-1..6.json` | 全部 FAILED/无状态；click 30 s 超时、page_error、empty_text、no_entry_added |
| 1.7B 默认臂 20 输入/八场景 | **未复跑** | — | 本轮没有窗口；旧证据只作历史 |
| 平台冻结构建 4+2+10 | **阻塞** | P06/`acceptance-attempts.json` | 首回合挂起两次；后台 waiter 因低内存被停止 |

**Findings.**

1. **单模型档的 20 输入计时确实过门。** 20/20 首段最差 13.7 s、单点正文最差 191.2 s，
   `summarize-timing` 判 PASS；刷新 20→20，history/tasks 稳定。这一份证据是
   `narrationModel=semantic` 的单模型臂，不是 1.7B 默认臂。
2. **八场景 48/48 与 14/14 在两个臂上都成立**（rules 57.1 s 均值、micro 64.7 s 均值），
   但这是 regression：八场景自 D-061 起参与修复，不能当泛化通过。
3. **离线、断 API、两设备都有通过证据。** 断 API 用的是 1.7B 默认臂，2 回合完成、
   权重 2/2、无 failures；两设备是 2026-11-21 的协议级证据（当前 2026-11-27 文件只是
   a/b 快照对照，不是完整分叉流程）。
4. **移动代理过首段、不过整回合 60 s。** 两回合的首段 22.1–33.1 s（≤60 s），但整回合
   218.6–278.1 s；按 D-023 未裁定的移动门槛，只能记“首段通过、整回合未达标”。
5. **移动默认档刷新恢复是硬失败。** 两次 4 回合后刷新都出现 history 4→0、任务清空、
   `overallRestored=false`；与单模型档 20/20 恢复形成对照，说明问题在配置/路径，不是
   验收脚本偶发。
6. **真机没有通过证据。** 7 份 Android 证据全部失败：按钮 30 s 超时、page_error、
   空正文、没有新增条目。真机流程已写在 `design/platform/phone-acceptance.md`，
   仍需用户设备复跑。
7. **语义依赖仍在。** 20 输入单模型臂 305 条语义 LLM 提示（15.25/回合）；rules 臂 8 回合
   仍有 106 条（13.3/回合）、semantic 引擎 497 次生成。叙事侧 rules 臂是程序正文
   （`verify_run --forbid-program` 拒绝），不能记模型叙事通过。

**Verdict.** 产品验收**未通过**：7 项通过、1 项部分（移动代理首段过、整回合未达 60 s）、2 项失败（移动默认档刷新、真机）、1 项阻塞
（自建冻结构建）、1 项未复跑（1.7B 默认臂的 20 输入/八场景）。通过项里 20 输入与移动
代理都来自单模型/移动预算臂；1.7B 默认叙事臂的完整门与真机性能仍是空缺。要把状态改成
“通过”，至少需要：修移动默认档刷新、真机跑通 2 回合并留证据、自建冻结构建修掉首回合
挂起后跑完 4+2+10。

**Artifacts.** `artifacts/goal/platform/eval/{turns20-pi-timing.json,
scenarios11-micro-report.json,rules8-scenario-report.json,mobile-proxy-summary.json,
mobile-defaults-refresh-summary.json,phone-failures-summary.json}`；
`artifacts/goal/platform/verify-rules8*.json`；原始大文件见各摘要里的 sha256/bytes 与
本地路径。P07。
