# D / L3 开跑前 run-manifest 提案 v3（首批 D02–D05 范围链）

日期：2026-10-30（Asia/Shanghai）。状态：**仅方案提案，未运行**；L3 继续暂停，诊断运行也尚未安排。v2 按总指挥对 `58ea66b` 的复审意见补齐账本与四段准入；**v3 按总指挥对 `5ba2249` 的四项意见统一修正**：S3 补 P-15 且 P-11 改为每机会结局一次、全员 skip 纯时间路径补齐 U3/U4（U5/U6 条件执行）、M01 双判别头之间的共享单列（M02 生成与 M01 判别不共享前向）、样本清单按四任务维度对齐协议 80＋10＝90 口径并明确组/case 计数。依据：[验证协议](evaluation-plan.md) §1 六门、§2.1 计数口径、§4.1 投影、§7 测量纪律、[候选表](model-selection.md) §8 依赖图、[L1 架构](architecture.md) §3 屏障。本提案是**协议门材料**：经独立复审后冻结为带哈希的 `artifacts/world-components-logic/run-manifest-l3-first.json`；新增实验臂或改门槛须升版。

## 1. 实际调用事件清单（26 事件，含次数公式）

次数变量：`O`=每段人物机会数（含 skip）、`A`=act 数、`skip=O−A`、`S`=冻结源数（行动源 + 反应源）、`R`=已确认关系判定数（逐关系骰点/准入）、`X`=新准入且未行动反应者数、`G`=闭组数、`U`=D06 触发阶段数、`C`=完成点数、`W`=自动后续轮数。

| ID | 类型 | 事件 | 次数公式 | 局部预算草案 |
| --- | --- | --- | --- | --- |
| P-01 | 程序 | 段起始/顺序采纳 | 1/段 | ≤10 ms |
| P-02 | 程序 | 身份分配 / begin / Python 时间预览（时间先行） | 1/段 | ≤10 ms |
| P-03 | 程序 | discover 确认并冻结源行动原文 | 1/act | ≤10 ms |
| P-04 | 程序 | **按源确认完整目标（含空目标源）** | 1/冻结源 S | ≤10 ms |
| P-05 | 程序 | **按关系骰点/准入 roll**（服务端权威，逐 source→target 关系） | 1/已确认关系 R | ≤10 ms |
| P-06 | 程序 | 反应候选原文冻结 | 1/X | ≤10 ms |
| P-07 | 程序 | close_group 闭组 | 1/G（全部来源与威胁处理完） | ≤10 ms |
| P-08 | 程序 | record_skip 合法否定登记 | 1/skip | ≤10 ms |
| P-09 | 程序 | stage_unit 保存完整候选（只提升工作游标） | 1/单元 | ≤10 ms |
| P-10 | 程序 | **六阶段逐阶段 Python preview**（U1→U2 强制先 preview；顺序不变） | 1/U | ≤10 ms |
| P-11 | 程序 | 本段槽位/边界判断（**每机会结局恰好一次**：skip 与单元完成是同一机会的两种结局，不重复计） | 1/机会结局 = O/段 | ≤10 ms |
| P-12 | 程序 | 纯时间任务扫描触发（**仅当本段无行动单元且未完成时间扫描**；触发后必跑 U3 全人物任务扫描与 U4 判断，U5/U6 按条件） | 0–1/段 | ≤10 ms |
| P-13 | 程序 | commit 原子提交（**普通提交携带单元 或 纯时间扫描提交，每点二选一、互斥**） | 1/C | ≤10 ms |
| P-14 | 等待 | 外部只读叙事 ready（W_r，计入请求并注明归属） | 1/C | 实测 |
| P-15 | 程序 | D07 结论原子确认 / continue 后继创建重排 | 1/round 完成 | ≤10 ms |
| P-16 | 探针 | 取消/迟到/恢复隔离路径 | 按协议 §6 | 单列 |
| M-01 | M01 | D02 act/skip 判别 | O | ≤40 ms/批 |
| M-02 | M02 | D02 行动正文 | 0–1/act | ≤50 ms |
| M-03 | M01 | D03 关系打分（**每个冻结源各 1–K 批，含空目标源；反应源同计**） | S × (1–K) | ≤40 ms/批 |
| M-04 | M02 | D04 反应候选 | 1/X | ≤50 ms |
| M-05 | M02 | D05 全组统一后果计划 | 1/G（仅一次） | ≤50 ms |
| M-06 | M02 | D05 成员表达 | 1–B 批/G | ≤50 ms/批 |
| M-07 | M01/M02 | D06 六阶段逐阶段模型调用；纯时间路径**必含 U3 全人物×任务扫描批与 U4 判断批**，U5/U6 按条件触发 | U × (0–K) | ≤50 ms/批 |
| M-08 | M02 | D07 拟行动生成（round 及全部关联段完成后） | 0–1/round | ≤50 ms |
| M-09 | M01 | D07 双条件判别（**仅 M01 的两个判别头共享一次前向**；M02 生成 M-08 与 M01 判别不共享前向） | 0–1/round | ≤50 ms |
| M-10 | M02 | D08 时间/分段提议（段起始适用位置） | 0–1/段 | ≤30 ms |

## 2. 纯时间与普通提交的互斥条件

1. P-12 仅当**本段无行动单元且未完成时间扫描**时触发；有行动单元的段走 P-09→P-13 普通提交路径。
2. P-13 每完成点**二选一**：普通提交（携带 P-09 单元结果）或纯时间扫描提交（P-12 之后）；同一提交点不得重复提交，二者互斥。
3. 全员 skip 的段（S0 场景）没有单元，只有纯时间扫描提交——skip 不终止段处理，经 P-11 汇入后仍抵达 P-12/P-13/P-14 及 round 级 D07。
4. 纯时间扫描若触发 U3/U4/U5/U6 联动，其模型批计入 M-07 并同样受逐阶段 preview（P-10）与全覆盖对账约束。
5. **纯时间路径的阶段构成**：U3 全人物（含场外）全部当前任务扫描与 U4 新任务判断**必跑**；U5 仅当 U3 发现新达成（全人物个性检查），U6 仅当个性变化（相应人物理智重算）；无触发即合法空 Δ，不固定 no-op、不省略扫描。

## 3. 事件—场景—次数账本（逐场景清点；全部待实测）

**S1 · 确认+结算范围链**（O=1, A=1, S=2, R=1, X=1, G=1；D06/D07/D08、段起始与提交门由夹具代替——L3 首批范围定义）：

| 事件 | 次数 | 预算 | 小计 |
| --- | --- | --- | --- |
| M-01 D02 判别 | 1 | 40 | 40 |
| M-02 D02 行动正文 | 1 | 50 | 50 |
| M-03 D03 打分（发起者源 1 + 反应者源 1） | 2 | 40 | 80 |
| M-04 D04 反应候选 | 1 | 50 | 50 |
| M-05 D05 计划 | 1 | 50 | 50 |
| M-06 D05 表达 | 1 | 50 | 50 |
| P-03 冻结源行动 | 1 | 10 | 10 |
| P-04 按源确认目标 | 2 | 10 | 20 |
| P-05 按关系骰点/准入 | 1 | 10 | 10 |
| P-06 反应冻结 | 1 | 10 | 10 |
| P-07 close_group | 1 | 10 | 10 |
| **合计（7 模型调用 + 6 程序屏障）** | | | **≈380 ms** |

**S2 · 连锁扩张每级增量**（每级新增 1 个准入未行动反应者作为新源，其目标分析含空目标）：M-03 40 + M-04 50 + P-04 10 + P-05 10 + P-06 10 = **≈+120 ms/级**（不含 D05，不重复结算）。

**S0 · 全员 skip 段**（O=3 全 skip, A=0, S=0, R=0；纯时间提交；对照场景）：

| 事件 | 次数 | 预算 | 小计 |
| --- | --- | --- | --- |
| M-01 D02 判别 | 3 | 40 | 120 |
| M-10 D08 提议 | 1 | 30 | 30 |
| M-07 U3 全人物任务扫描 + U4 判断 | 2 | 50 | 100 |
| P-01/P-02 段起始 / begin | 2 | 10 | 20 |
| P-08 record_skip | 3 | 10 | 30 |
| P-11 槽位判断（每机会结局一次） | 3 | 10 | 30 |
| P-10 preview（U3, U4） | 2 | 10 | 20 |
| P-12 纯时间触发 | 1 | 10 | 10 |
| P-13 纯时间提交 | 1 | 10 | 10 |
| **合计** | | | **≈370 ms + W_r** |

U5/U6 按条件执行：本场景 U3 无达成 → 0 批；若发现达成则加 U5 全人物个性检查批与相应 U6 理智批，另计。

**S3 · 完整单段最小轮**（S1 事件 + 段起始 + D08 + U=2 触发阶段 + 单元提交 + **D07 及 P-15 原子确认**；O=1, A=1, S=2, R=1, X=1, G=1, 单元=1, C=1）：程序 P-01/P-02/P-03/P-04×2/P-05/P-06/P-07/P-09/P-10×2/**P-11×1（每机会结局一次，消除 v2 的重复计数）**/P-13/**P-15** = 13×10 = 130；模型 M-01 40 + M-02 50 + M-03 80 + M-04 50 + M-05 50 + M-06 50 + M-07×2 100 + M-10 30 + M-08 50 + M-09 50 = 550 → **≈680 ms + W_r**。

**S4 · 完整请求含一次自动后续轮**（continue 后继轮按同图重复，边界按协议 §7.1）：S3 ×2 = **≈1360 ms + 2×W_r**。

细化口径取代历史口径：v1 的 370/630/1260 ms 为粗合并口径（已复审，保留记录）；v2 的 S0=250 **漏计纯时间 U3/U4**、S3=690 **重复计 P-11 且漏 P-15**，均在本版修正为 S0=370、S3=680、S4=1360。**全部口径均为草案待实测，均不改写「S3/S4 超预算、500 ms 未验收」的结论。**

## 4. 重复次数与测量纪律

§1 公式中的变量在清单冻结时逐项写死为整数，`null/unknown = 未定且不得开跑`；测量次数按协议 §7（正式性能比较每个登记规格的微节点与完整请求各 ≥20 个可比完整观测；冷启动 ≥3；探索热任务 ≥5、链级 ≥3；冻结种子交错各臂）。每场景另登记其 S/R/X/U/C 的实际取值，防止只报 anchor 场景。

## 5. 等待项

- **W_r 叙事 ready**（P-14）：计入 t1–t0，归属外部叙事，逐次记录；不得移到表外。
- **加载/切换**：冷加载、任务切换、缓存命中/失效按事件单列；发生在 t0 后必须计入完整请求。
- **重试**：仅解析/结构失败或暂时运行错误，上限 1 次并独立附表；首呼为主成绩。
- **取消/迟到**：P-16 探针与超时保留完整起止时间，计入性能全集、不计完成成功。

## 6. 模型与环境身份（身份门材料）

| 项 | 登记 | 现状 |
| --- | --- | --- |
| M02 | `IDEA-CCNL/Randeng-T5-77M-MultiTask-Chinese` / `06d379d7375245f31cfb87166eff134cfeb5dead`，6 文件 SHA-256 已验真 | ✅ 载荷验真；❌ 加载/推理未验证 |
| M01 | `hfl/minirbt-h256` / `446e1b4012b10946f479563005700c54c9db3f7c` | ❌ 权重未下载、未验真；任务头未训练（随机头不得进语义比较） |
| M03 | `Qwen/Qwen2.5-0.5B-Instruct` / `7ae557604adf67be50417f59c2c2f167def9a775` | ❌ 未下载；对照臂（`baseline_missing` 规则适用），非前置 |
| M04 | `Qwen/Qwen3-0.6B` / `c1899de289a04d12100db370d81485cdf75e47ca` | ❌ 未下载；同上 |
| 分词/导出 | SentencePiece/WordPiece、ONNX 工具链版本 | ❌ 未验证 |
| 依赖锁 | 本机（Windows）独立 venv + 版本/分发哈希 | ❌ 未生成（r2 的 ARM64 锁属原实现者机器，不迁移） |
| 设备 | CPU/内存/GPU/线程/并发 | ❌ 未核实 |
| 代码 | 分支 commit、`lab.py`/适配器源文件哈希 | 冻结时写入 |
| 提示词/输出约束 | 模板来源、240/300/600 汉字与结构 schema 版本 | 冻结时写入 |

## 7. 输入版本（来源门/输入门材料）

- **首轮来源组（与协议 §2.1 的 80＋10＝90 口径对齐）**：任务来源组 80 个——D02/D03/D04/D05 四个任务维度各 10 开发 + 10 封存；短链来源组 10 个——4 开发 + 6 封存；合计 **90 个来源组**。**组数 ≠ case 数 ≠ 调用数**：每组 ≥1 个 anchorCase，派生 case 另计，case 清单与各臂调用图冻结前逐组登记（协议 §2.1）；caseCount 在冻结前为 unknown。❌ 全部未创建。
- **投影器**：协议 §4.1 allowlist 截点投影——❌ 未实现/未验证；D03 前无未来骰点/准入、D02 前无未来行动。
- **42 题开发草稿**（字节已绑定，见 §10 JSON）：保持 `pending`，待**用户本人**逐题复核，不由代理代签；属开发迭代材料，不进入首轮封存输入，不抵扣 80+10 组。
- **骰点夹具**：`reaction-d20-v1` 由程序权威给定，模型不掷骰、不分配 rollId（协议 §3）。
- **G03**：离线样本按原设计标注；服务适配分支保持 `blocked_contract_g03`，不计入通过。

## 8. 预算登记（性能预算门材料）

| 场景 | 细化账本草案 | 状态 |
| --- | --- | --- |
| S0 全员 skip 段（含必跑 U3 扫描 + U4 判断） | ≈370 ms + W_r | 待实测 |
| S1 确认+结算范围链 | ≈380 ms | 限定场景估算，待实测 |
| S2 连锁每级增量 | ≈+120 ms/级 | 待实测 |
| S3 完整单段最小轮（含 P-15，P-11 每机会一次） | ≈680 ms + W_r | **超预算（草案）** |
| S4 完整请求含一次自动后续轮 | ≈1360 ms + 2×W_r | **超预算（草案）** |
| 完整请求 500 ms 目标 | — | **未验收**；须按冻结规格实测 ≥20 可比完整观测后判定 |

超预算收敛只允许：实测更紧节点值、协议 §8 条件下的合法合并/批处理、设备真实并行、继续细拆换更小模型；**不得省略任何屏障/等待凑预算**。实测超任一局部/总预算即 `latency_fail` 进入下一轮细拆。

## 9. 准入顺序（四段；每段有独立进入/退出条件）

**第 1 段 · 文档复审（当前所处段）。** 本提案连同 §10 绑定清单交 D 审查者复审。退出条件：复审通过并记录。**哈希只证明文件身份（字节未变），不构成审批、不构成达标证据**；审批是复审者/协调人/用户的流程行为，达标判定只能来自第 4 段。

**第 2 段 · 运行前配置与预算检查。** 内容：§4 变量冻结为整数；创建并冻结 80+10 来源组与投影器；下载验真 M01；生成本机依赖锁并核实设备；按本提案实例化 JSON、整体哈希、登记 sourceHead；六门逐项独立核验。退出条件：六门全过、全部未知值已解决或逐项列为阻断、预算表按冻结规格重算并复核。本段**不运行任何模型**；此前的所有性能数字保持草案/未知。

**第 3 段 · 获准运行。** 进入条件：用户/总指挥明确恢复指令 + 计算窗口 + 第 2 段冻结清单哈希核验一致。首次运行为**诊断运行**：截至本提案不存在任何 D 实测成绩，诊断运行的全部性能预期为「未知」，其产出是第一批实测数据（细化预算、定位热点），**不得以已有实测通过为前提**；结果标记 `exploratory`，不签任何门、不放行封存筛选（协议 §2.3）。

**第 4 段 · 运行后达标判定。** 质量只按协议 §5.2 预登记门判定；性能只按冻结预算对照 ≥20 个可比完整观测判定；对照臂按 `baseline_missing` 规则报告。哈希依旧只证明身份；达标与否的结论只能由预登记门 + 实测数据产生，不由实现者或任何哈希自签。超预算 → `latency_fail` → 下一轮细拆；改门槛/加臂须升版清单。

## 10. 完整清单绑定（JSON v2；冻结时实例化、整体哈希）

```json
{
  "schema": "jity-d-run-manifest-v3",
  "batch": "l3-first-d02-d05",
  "status": "proposal-awaiting-document-review",
  "admissionStage": "1-document-review",
  "sourceHeadAtProposal": "58ea66b1ba490fe587260f704546f1978f54bb9c",
  "events": [
    {"id": "P-01", "node": "segment-start", "per": "segment", "budgetMs": 10},
    {"id": "P-02", "node": "identity-alloc-begin-time-preview", "per": "segment", "budgetMs": 10},
    {"id": "P-03", "node": "freeze-action-text", "per": "act", "budgetMs": 10},
    {"id": "P-04", "node": "confirm-target-set-per-source", "per": "frozen-source", "budgetMs": 10},
    {"id": "P-05", "node": "dice-admission-per-relation", "per": "confirmed-relation", "budgetMs": 10},
    {"id": "P-06", "node": "freeze-reaction-text", "per": "new-admitted-unacted", "budgetMs": 10},
    {"id": "P-07", "node": "close-group", "per": "closed-group", "budgetMs": 10},
    {"id": "P-08", "node": "record-skip", "per": "legal-skip", "budgetMs": 10},
    {"id": "P-09", "node": "stage-unit", "per": "unit", "budgetMs": 10},
    {"id": "P-10", "node": "per-stage-python-preview", "per": "triggered-stage", "budgetMs": 10, "order": "U1-before-U2-when-position-affects-appearance"},
    {"id": "P-11", "node": "segment-slot-boundary-check", "per": "opportunity-outcome", "budgetMs": 10,
     "note": "exactly once per opportunity; skip and unit completion are the two outcomes of the same opportunity"},
    {"id": "P-12", "node": "pure-time-scan-trigger", "per": "segment", "budgetMs": 10,
     "precondition": "no-action-unit-in-segment AND time-scan-incomplete", "exclusiveWith": "P-09-unit-commit-path",
     "thenRuns": ["U3-all-person-task-scan", "U4-new-task-judgment"],
     "conditional": ["U5-if-new-achievements", "U6-if-personality-changed"]},
    {"id": "P-13", "node": "atomic-commit", "per": "completed-point", "budgetMs": 10,
     "variants": ["normal-with-unit", "pure-time-scan"], "mutuallyExclusivePerPoint": true},
    {"id": "P-14", "node": "narrative-ready-wait", "per": "completed-point", "budgetMs": null,
     "budgetStatus": "unknown-measured-at-run", "inRequest": true, "attribution": "external_narration"},
    {"id": "P-15", "node": "d07-atomic-confirm-and-successor", "per": "completed-round", "budgetMs": 10},
    {"id": "P-16", "node": "cancel-late-recovery-probe", "per": "protocol-6-probe", "budgetMs": null, "budgetStatus": "separate-ledger"},
    {"id": "M-01", "node": "M01.d02.act-skip", "per": "opportunity", "budgetMs": 40},
    {"id": "M-02", "node": "M02.d02.action-body", "per": "act", "budgetMs": 50},
    {"id": "M-03", "node": "M01.d03.relation-score", "per": "frozen-source", "batches": "1-K", "budgetMs": 40,
     "note": "every frozen source including empty-target and reaction sources"},
    {"id": "M-04", "node": "M02.d04.reaction", "per": "new-admitted-unacted", "budgetMs": 50},
    {"id": "M-05", "node": "M02.d05.joint-plan", "per": "closed-group", "budgetMs": 50, "oncePerGroup": true},
    {"id": "M-06", "node": "M02.d05.member-expression", "per": "closed-group", "batches": "1-B", "budgetMs": 50},
    {"id": "M-07", "node": "M01-M02.d06.stages", "per": "triggered-stage", "batches": "0-K", "budgetMs": 50,
     "includes": "pure-time path always runs U3 all-person task-scan batches and U4 judgment; U5/U6 conditional"},
    {"id": "M-08", "node": "M02.d07.candidate", "per": "completed-round", "budgetMs": 50,
     "precondition": "round-and-all-linked-segments-complete"},
    {"id": "M-09", "node": "M01.d07.dual-judgment", "per": "completed-round", "budgetMs": 50,
     "dualHeadsShareForward": true, "sharesForwardWithGeneration": false,
     "note": "sharing only between the two M01 judgment heads; M02 generation (M-08) and M01 judgment never share a forward",
     "precondition": "round-and-all-linked-segments-complete"},
    {"id": "M-10", "node": "M02.d08.proposal", "per": "segment", "budgetMs": 30}
  ],
  "inputs": [
    {"kind": "development-drafts", "path": "experiments/world-components-logic/data/dev-inputs.jsonl",
     "sha256": "5db17d612a02425a00f555c178d74689cd84a7fd745656ce87f0daf7c7b3061e",
     "role": "development-iteration-only", "humanReview": "pending-user", "admissibleForRun": false},
    {"kind": "development-drafts", "path": "experiments/world-components-logic/data/dev-review-drafts.jsonl",
     "sha256": "e5a772691b81c6f6e8281706a75725f8fc33cab1c78e5f010b06ff4fc5d9ea1b",
     "role": "development-iteration-only", "humanReview": "pending-user", "admissibleForRun": false},
    {"kind": "provenance", "path": "experiments/world-components-logic/data/dev-provenance.json",
     "sha256": "d104869ca54b270ab11e8b2206ff3f1932d69eb67799c8bb9cc8416e038c050d"},
    {"kind": "model-source-registry", "path": "artifacts/world-components-logic/l2-model-sources-20261029.json",
     "sha256": "dd674851600bd08c5bad796f122ba4ea7fc50f60243d174f32c86f83555312d4"},
    {"kind": "environment-record", "path": "artifacts/world-components-logic/l3-1-environment.json",
     "sha256": "68b3914d29b88e083bc1a408f9653c36d0de8c7144c48fced63d25ff5f9edf34",
     "note": "macOS probe of the original implementer machine; not migrated"},
    {"kind": "projection-spec", "ref": "evaluation-plan.md §4.1", "version": "L2-r3",
     "implementation": "unbuilt", "admissibleForRun": false},
    {"kind": "first-round-groups", "alignedWith": "evaluation-plan §2.1 counts 80+10=90",
     "taskGroupsByDimension": {"D02": {"dev": 10, "sealed": 10}, "D03": {"dev": 10, "sealed": 10},
                               "D04": {"dev": 10, "sealed": 10}, "D05": {"dev": 10, "sealed": 10}},
     "chainGroups": {"dev": 4, "sealed": 6},
     "counts": {"taskSourceGroups": 80, "chainSourceGroups": 10, "sourceGroupsTotal": 90,
                "cases": null, "casesStatus": "unknown-frozen-before-run",
                "countingRule": "groupCount != caseCount != expectedCallCount; per-group anchorCase plus derived cases registered at freeze"},
     "status": "unbuilt", "admissibleForRun": false},
    {"kind": "dice-fixture", "rule": "reaction-d20-v1", "authority": "program", "modelRolls": false}
  ],
  "models": [
    {"id": "M01", "repo": "hfl/minirbt-h256", "revision": "446e1b4012b10946f479563005700c54c9db3f7c",
     "role": "priority-path-encoder", "payloadFetched": false, "payloadVerified": false,
     "payloadSha256": null, "payloadSha256Status": "unknown-until-fetch-and-verify",
     "taskHeads": "untrained", "admissibleForRun": false},
    {"id": "M02", "repo": "IDEA-CCNL/Randeng-T5-77M-MultiTask-Chinese",
     "revision": "06d379d7375245f31cfb87166eff134cfeb5dead",
     "role": "priority-path-generator", "payloadFetched": true, "payloadVerified": true,
     "payloadSha256Status": "per-file-in-registry", "loaded": false, "admissibleForRun": false},
    {"id": "M03", "repo": "Qwen/Qwen2.5-0.5B-Instruct", "revision": "7ae557604adf67be50417f59c2c2f167def9a775",
     "role": "reference-arm-optional", "payloadFetched": false, "payloadVerified": false,
     "prerequisite": false},
    {"id": "M04", "repo": "Qwen/Qwen3-0.6B", "revision": "c1899de289a04d12100db370d81485cdf75e47ca",
     "role": "reference-arm-optional", "payloadFetched": false, "payloadVerified": false,
     "prerequisite": false}
  ],
  "workload": {"personOpportunities": null, "frozenSourcesPerRound": null, "chainLevels": null,
               "d06TriggeredStages": null, "autoRounds": null, "K": null, "B": null,
               "attemptsPerSpec": null,
               "freezeRule": "integers-before-stage-2-exit; null blocks any run"},
  "budgets": {"refinedLedger": {"S0AllSkipSegmentMs": 370, "S1ScopeChainMs": 380,
               "S2ChainLevelDeltaMs": 120, "S3FullSegmentRoundMs": 680,
               "S4RequestOneAutoRoundMs": 1360, "waits": "W_r measured separately per point"},
              "recordedHistory": {"v1Coarse": {"S1": 370, "S3": 630, "S4": 1260, "note": "coarse barriers, reviewed"},
                                   "v2Corrections": {"S0": 250, "S3": 690, "S4": 1380,
                                   "reason": "superseded: missing pure-time U3/U4 in S0; duplicate P-11 and missing P-15 in S3"}},
              "overBudget": ["S3", "S4"],
              "target": {"fullRequestMs": 500, "status": "not_accepted_unmeasured"}},
  "admissionSequence": ["1-document-review", "2-pre-run-config-and-budget-check",
                        "3-authorized-run-diagnostic-exploratory", "4-post-run-judgment"],
  "gaps": ["source-groups-unbuilt", "protected-sources-unverified", "m01-not-fetched",
           "dependency-lock-missing", "machine-unverified", "projector-unbuilt",
           "annotation-roles-unstaffed", "42-drafts-pending-user-review",
           "compute-window-unscheduled", "g03-blocked", "resume-instruction-not-given"]
}
```

## 11. 复审与执行路径

本提案交 D 审查者复审（第 1 段）→ 通过后进入第 2 段配置与预算检查（不运行）→ 六门全过 + 恢复指令后第 3 段诊断运行（exploratory）→ 第 4 段按预登记门判定。本批无训练、无推理、无下载；细化账本 380 ms 为限定场景估算，690/1380 ms 记为超预算，500 ms 目标未验收。
