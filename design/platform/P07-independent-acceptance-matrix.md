# P07 独立产品验收矩阵：6 项通过、2 项部分、2 项失败、1 项阻塞、1 项未复跑

**Question.** 不重跑重型实验的前提下，用仓库里的冻结证据独立复算，产品验收的每一项到底是
通过、失败、还是没测？

**Method.** 只读复算：`scenario_report.py` 重算八场景状态/任务断言；`summarize-timing.mjs`
重算 20 输入计时门；`verify_run.py` 重算模型/引擎/LLM 调用；直接解析离线、断 API、两设备、
移动代理、真机与刷新恢复证据。大型原始证据保留本地，仓库内只放哈希摘要。没有启动浏览器，
没有抢租约；平台自己的冻结构建尝试见 P06。

**Matrix.**

| 验收项 | 结果 | 证据 | 独立复算 |
|---|---|---|---|
| 20 输入计时（三门槛） | **部分通过** | `09-turns20-pi.json` | 首段 20/20（最差 13,732 ms）；单点正文 20/20（最差 191,232 ms）；**控制权交还 0/20**（66.7–200.0 s） |
| 20 输入刷新恢复 | **PASS** | 同上 `refreshRestore` | entries 20→20、historyStable、tasksStable、stateRestored |
| 八场景状态/任务（rules 臂） | **PASS（regression）** | `scenarios8-rules.json` | 状态 48/48、任务 14/14、达成 3/3、正文问题 0 |
| 八场景状态/任务（micro 臂） | **PASS（regression）** | `evidence-independent-scenarios-11.json` | 状态 48/48、任务 14/14、达成 3/3、正文问题 0 |
| 离线 | **PASS** | `10-offline-pi.json` | 2/2、offline=true、failures 0、刷新恢复 2/2 |
| 服务器关闭（断 API） | **PASS** | `g8-block-api-rerun-20261122-…json` | 2/2、saveServiceBlocked=true、failures 0、1.7B 权重 2/2 |
| 两设备分叉 | **PASS** | `artifacts/goal/sync/two-device-20261121.json` | status PASSED、choice keep-local-fork、failures 0 |
| 移动代理（4× CPU + gpu-lite） | **首段 PASS，整回合未达 60 s** | `evidence-mobile-proxy-1/2.json` | 2/2 完成；首段 22.1–33.1 s；整回合等待 218.6–278.1 s |
| 移动默认档刷新恢复（历史构建） | **FAIL** | `smoke-mobile-defaults{,-rerun}-20261127.json` | 4 回合后刷新：history 4→0、tasks 空、overallRestored=false；当前版本未复验 |
| 真机手机 | **FAIL** | `evidence-phone-1..6.json` | 全部 FAILED/无状态；click 30 s 超时、page_error、empty_text、no_entry_added |
| 1.7B 默认臂 20 输入/八场景 | **未复跑** | — | 本轮没有窗口；旧证据只作历史 |
| 平台冻结构建 4+2+10 | **阻塞** | P06/`acceptance-attempts.json` | 首回合挂起两次；后台 waiter 因低内存被停止 |

**Provenance（按证据分别记录）.**

| 证据 | 代码提交 | 模型/配置 | 设备/运行时 |
|---|---|---|---|
| 20 输入 | `c74dbcf6` | 单模型 `semantic`（0.6B） | 桌面 Edge，wllama |
| rules 八场景 | `c0052682` | 叙事 `rules`（0 权重）+ semantic | 桌面 Edge，wllama |
| micro 八场景 | `a7c82a7b` | micro 臂（seed 11，Ledger D-074） | 桌面 Edge，wllama |
| 离线 | `d4a3241c` | 单模型 `semantic` | 桌面 Edge，offline |
| 断 API | `f54bf3cb` | 叙事 `qwen3-1.7b` | 桌面 Edge，saveServiceBlocked |
| 两设备 | 未记录 gitHead | `semantic` + `/models/Qwen3-0.6B-Q4_K_M.gguf` | 两个浏览器配置 |
| 移动代理 | `cbdfb440` | 叙事 `qwen3-1.7b-narr-lora` | 4× CPU 节流 + gpu-lite |
| 移动刷新（历史） | `7bd98293` | `qwen3-1.7b-narr-lora` | 移动模拟/默认档 |
| 真机 | `96abd3e8` | `qwen3-1.7b-narr-lora` | Android UA |

这些提交不是同一个构建；矩阵的每一项只对该行提交/配置/设备成立，不能合并成“当前版本通过”。

**计时口径修正（2026-11-28）.** `summarize-timing.mjs` 只查首段 60 s 与单点 300 s，
不查控制权交还。新增 `timing_gates.py` 后三门槛独立计算：首段 20/20、单点 20/20、
控制权交还 **0/20**（66.7–200.0 s，最差 199,954 ms），整体不通过。二十条的
`firstReadableAtMs` 与 `narrationStartedAtMs` 全部相等：按页面代码，前者记首次非空文本、
后者记首次叙事进度回调，二者相同不等于玩家已看到可读正文；需要把“首个进度回调 /
首段非空 / 首个完整可读句 / 控制权交还”拆成四个时钟，不能用一个相等值当首段证明。

**Findings.**

1. **单模型档只过了首段与单点，没过控制权交还。** 首段 20/20（最差 13.7 s）、单点正文
   20/20（最差 191.2 s），但控制权交还 0/20（66.7–200.0 s）。这一份证据是
   `narrationModel=semantic` 的单模型臂，不是 1.7B 默认臂；`summarize-timing` 的 PASS
   不能代表产品延迟要求满足。
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

**Verdict.** 产品验收**未通过**：6 项通过、2 项部分（20 输入三门槛只过首段与单点，
控制权交还 0/20；移动代理首段过、整回合 218.6–278.1 s）、2 项失败（历史移动默认档刷新、
真机）、1 项阻塞（自建冻结构建）、1 项未复跑（1.7B 默认臂的 20 输入/八场景）。通过项
来自单模型/移动预算臂或历史构建；1.7B 默认叙事臂的完整门、控制权交还 60 s 与当前版本
移动刷新仍是空缺。要把状态改成“通过”，至少需要：修控制权交还、修移动默认档刷新、真机
跑通 2 回合并留证据、自建冻结构建修掉首回合挂起后跑完 4+2+10。

**Artifacts.** `artifacts/goal/platform/eval/{turns20-pi-timing.json,
scenarios11-micro-report.json,rules8-scenario-report.json,mobile-proxy-summary.json,
mobile-defaults-refresh-summary.json,phone-failures-summary.json}`；
`artifacts/goal/platform/verify-rules8*.json`；原始大文件见各摘要里的 sha256/bytes 与
本地路径。P07。
