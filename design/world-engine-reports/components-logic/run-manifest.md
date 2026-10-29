# D / L3 开跑前 run-manifest 提案（首批 D02–D05 范围链）

日期：2026-10-30（Asia/Shanghai）。状态：**仅方案提案，未运行**；L3 继续暂停，执行须用户/总指挥恢复指令。本提案按总指挥 2026-10-30 指令编写：列清实际调用事件、重复次数、等待、模型与环境身份、输入版本、预算及准备缺口。依据：[验证协议](evaluation-plan.md) §1 六门与 §7 测量纪律、[候选表](model-selection.md) §8 依赖图与逐项预算、[L1 架构](architecture.md) §3 屏障。本提案本身是**协议门材料**：经独立复核后冻结为带哈希的 `artifacts/world-components-logic/run-manifest-l3-first.json`，此后新增实验臂或改门槛须升版。

## 1. 实际调用事件清单（逐事件；全部计入请求墙钟 t1–t0）

程序屏障不经模型，与模型调用分开记账（架构 §6）；P-13 与探针类等待不计入完成性能成功。

| ID | 类型 | 事件 | 重复模型 | 局部预算草案 |
| --- | --- | --- | --- | --- |
| P-01 | 程序 | 段起始/顺序采纳（round 沿用冻结顺序，关联段同序） | 1/段 | ≤10 ms |
| P-02 | 程序 | 身份分配 / begin / Python 时间预览（时间先行） | 1/段 | ≤10 ms |
| P-03 | 程序 | discover 确认并冻结源行动原文 | 1/act | ≤10 ms |
| P-04 | 程序 | 目标确认（含空集）→ 服务端骰点/准入 roll | 1/冻结源 | ≤10 ms |
| P-05 | 程序 | 反应候选原文冻结 | 1/新准入且未行动者 | ≤10 ms |
| P-06 | 程序 | close_group 闭组 | 1/闭组（全部来源与威胁处理完） | ≤10 ms |
| P-07 | 程序 | stage_unit 保存完整候选（只提升工作游标） | 1/单元 | ≤10 ms |
| P-08 | 程序 | 本段槽位/边界判断（skip 与单元完成同汇入） | 每机会/单元后 | ≤10 ms |
| P-09 | 程序 | 纯时间扫描封存/提交时间点 | 未完成时间扫描时 | ≤10 ms |
| P-10 | 程序 | commit 原子提交完成点 | 1/完成点 | ≤10 ms |
| P-11 | 等待 | 外部只读叙事 ready（W_r，计入请求并注明归属） | 1/提交点 | 实测 |
| P-12 | 程序 | D07 结论原子确认 / continue 后继创建重排 | 1/round 完成 | ≤10 ms |
| P-13 | 探针 | 取消/迟到/恢复隔离路径 | 按协议 §6 探针 | 单列 |
| M-01 | M01 | D02 act/skip 判别 | 1/人物机会 | ≤40 ms/批 |
| M-02 | M02 | D02 行动正文 | 0–1/机会（判别 act 才调） | ≤50 ms |
| M-03 | M01 | D03 关系打分（**每个冻结源各 1–K 批，含空目标源；反应源同计**） | 1–K/源 | ≤40 ms/批 |
| M-04 | M02 | D04 反应候选 | 1/新准入且未行动者 | ≤50 ms |
| M-05 | M02 | D05 全组统一后果计划 | 1/闭组（仅一次） | ≤50 ms |
| M-06 | M02 | D05 成员表达 | 1–B 批/闭组 | ≤50 ms/批 |
| M-07 | M01/M02 | D06 六阶段逐阶段（含纯时间扫描分支；全覆盖对账不减） | 0–K 批/触发阶段 | ≤50 ms/批 |
| M-08 | M02 | D07 拟行动生成 | 0–1/round（round 及关联段全部完成后） | ≤50 ms |
| M-09 | M01 | D07 双条件判别（与 M-08 共享编码待实测） | 0–1/round | ≤50 ms |
| M-10 | M02 | D08 时间/分段提议（段起始适用位置） | 0–1/段 | ≤30 ms |

## 2. 重复次数（冻结前必须写死的工作负载规格）

以下参数在清单冻结时逐项写死为整数，`null = 未定且不得开跑`；测量次数按协议 §7 执行（正式性能比较每个登记规格的微节点与完整请求各 ≥20 个可比完整观测；冷启动 ≥3；探索热任务 ≥5、链级 ≥3；执行顺序按冻结种子交错各臂）：

| 参数 | 含义 | 冻结值 |
| --- | --- | --- |
| `personOpportunities` | 每段人物机会数（含 skip 路径） | null |
| `frozenSourcesPerRound` | 每 round 冻结源数（行动源 + 反应源；D03 按此计数） | null |
| `chainLevels` | 连锁扩张级数（闭组前） | null |
| `d06TriggeredStages` | D06 触发阶段数（0–6，另列纯时间扫描） | null |
| `autoRounds` | 自动后续轮数（continue 触发；请求边界含其全部成本） | null |
| `K` / `B` | D03 每源批数上限 / D05 表达批数上限 | null |
| `attemptsPerSpec` | 每规格完整观测数（正式 ≥20） | null |

## 3. 等待项

- **W_r 叙事 ready**（P-11）：计入 t1–t0，归属外部叙事，逐次记录；不得移到表外。
- **加载/切换**：模型权重冷加载、任务切换、缓存命中/失效按事件单列；若发生在 t0 后必须计入完整请求。
- **重试**：仅解析/结构失败或暂时运行错误，上限 1 次并独立附表（协议 §6）；首呼为主成绩。
- **取消/迟到**：P-13 探针路径与超时事件保留完整起止时间，计入性能全集、不计入完成成功。

## 4. 模型与环境身份（身份门材料）

| 项 | 登记 | 现状 |
| --- | --- | --- |
| M02 | `IDEA-CCNL/Randeng-T5-77M-MultiTask-Chinese` / `06d379d…`，6 文件 SHA-256 已验真 | ✅ 载荷验真；❌ 加载/推理未验证 |
| M01 | `hfl/minirbt-h256` / `446e1b4…` | ❌ 权重未下载、未验真；任务头未训练（随机头不得进语义比较） |
| M03/M04 | 已登记身份 | ❌ 未下载（对照臂，非前置） |
| 分词/导出 | SentencePiece/WordPiece 路线、ONNX 工具链版本 | ❌ 未验证 |
| 依赖锁 | 本机（Windows）独立 venv + 版本/分发哈希 | ❌ 未生成（r2 的 ARM64 锁属原实现者机器，不迁移） |
| 设备 | CPU/内存/GPU/线程/并发 | ❌ 未核实 |
| 代码 | 分支 commit、`lab.py`/适配器源文件哈希 | 冻结时写入 |
| 提示词/输出约束 | 模板来源、240/300/600 汉字与结构 schema 版本 | 冻结时写入 |

## 5. 输入版本（来源门/输入门材料）

- **首轮 80+10 来源组**：case 清单、anchorCase、split 与 `stageCut/availableFacts` 投影版本、输入 SHA-256 —— ❌ 全部未创建；创建后按协议 §2.2 登记并冻结。
- **投影器**：allowlist 截点投影（D03 前无未来骰点/准入，D02 前无未来行动等，协议 §4.1）—— ❌ 未实现/未验证。
- **42 题开发草稿**：保持 `pending`，待**用户本人**逐题复核，不由代理代签；属开发迭代材料，不进入首轮封存输入，不抵扣 80+10 组。
- **G03**：离线样本按原设计标注；服务适配分支保持 `blocked_contract_g03`，不计入通过。

## 6. 预算登记（性能预算门材料）

逐事件局部预算见 §1 表；场景草案（协议 §7.1 的 50 ms/节点默认上限内逐项清点，全部待实测）：

| 场景 | 草案 | 状态 |
| --- | --- | --- |
| 确认+结算范围链（7 模型调用 + 5 程序屏障逐项，K=B=1、单机会、D06/D07/D08 与提交门夹具代替） | ≈370 ms | **限定场景估算** |
| 完整单段最小轮（+D08+D06×2+stage/commit+W_r+D07） | ≈630 ms + W_r | **记为超预算（草案）** |
| 完整请求含一次自动后续轮 | ≈1260 ms + 2×W_r | **记为超预算（草案）** |
| 完整请求 500 ms 目标 | — | **未验收**；须按冻结规格实测 ≥20 可比完整观测后判定 |

超预算场景的收敛只允许：实测更紧节点值、协议 §8 条件下的合法合并/批处理、设备真实并行、继续细拆换更小模型；**不得省略任何屏障/等待凑预算**。实测超任一局部/总预算即 `latency_fail` 进入下一轮细拆。

## 7. 准备缺口（六门现状，缺项不得宣称正式筛选通过）

| 门 | 现状 | 需要什么 | 责任方 |
| --- | --- | --- | --- |
| 来源门 | ❌ 80+10 组未创建；B/C 保护源完整去重/语义同源 `unverified` | 创建并冻结来源组；保护源负责人核验 | 本专项 + 协调人 |
| 标注门 | ❌ 标注/复核/裁定角色未落实；42 题待用户本人复核 | 落实角色与盲审排期；用户完成 42 题复核（开发材料） | 协调人 + 用户 |
| 身份门 | ⚠️ M02 已验真；M01 未下载/未验真/无头；依赖锁、设备、导出未定 | 下载验真 M01；生成本机依赖锁；核实设备；登记全部哈希 | 本专项 |
| 输入门 | ❌ 投影器未实现；输入 token 未实测 | 实现并验证投影器；冻结输入编码 | 本专项 |
| 协议门 | ⚠️ 本提案即材料，待独立复核后冻结 | 复审通过 + 冻结 run-manifest 哈希 | D 审查者 |
| 性能预算门 | ⚠️ 预算表已列，规格参数未冻结、无实测 | 冻结 §2 参数；安排计算窗口后实测 | 协调人 |
| 其他 | G03 blocked；恢复指令未下 | A/B 澄清 G03；用户/总指挥恢复指令 | 协调人 / 用户 |

## 8. 提案 JSON 骨架（冻结时实例化并整体哈希）

```json
{
  "schema": "jity-d-run-manifest-v1",
  "batch": "l3-first-d02-d05",
  "sourceHead": "<git sha>",
  "gates": {"source": "unverified", "annotation": "unstaffed", "identity": "partial",
            "input": "unbuilt", "protocol": "proposed", "performanceBudget": "proposed"},
  "models": [{"id": "M02", "revision": "06d379d…", "payloadVerified": true, "loaded": false}],
  "environment": {"machine": "unverified", "dependencyLock": "missing",
                  "precision": null, "threads": 1},
  "workload": {"personOpportunities": null, "frozenSourcesPerRound": null,
               "chainLevels": null, "d06TriggeredStages": null, "autoRounds": null,
               "K": null, "B": null, "attemptsPerSpec": null},
  "events": [{"id": "M-03", "node": "M01.d03.score", "per": "frozen-source",
              "budgetMs": 40, "batches": "1-K"}],
  "waits": [{"id": "P-11", "kind": "narrative_ready", "inRequest": true, "attribution": "external_narration"}],
  "budgets": {"scopeChainDraftMs": 370, "fullSegmentRoundDraftMs": 630,
              "fullRequestOneAutoRoundDraftMs": 1260, "overBudgetDrafts": [630, 1260],
              "target": {"fullRequestMs": 500, "status": "not_accepted_unmeasured"}},
  "gaps": ["source-groups-unbuilt", "protected-sources-unverified", "m01-not-fetched",
           "dependency-lock-missing", "projector-unbuilt", "annotation-roles-unstaffed",
           "42-drafts-pending-user-review", "compute-window-unscheduled", "g03-blocked"]
}
```

## 9. 复审与执行路径

本提案交 D 审查者复审 → 通过后冻结清单哈希（协议门/性能预算门闭合）→ 六门全过 + 用户/总指挥恢复指令 → 按 §2 冻结规格执行首批实测。本批无训练、无推理、无下载；370 ms 为限定场景估算，630/1260 ms 记为超预算，500 ms 目标未验收。
