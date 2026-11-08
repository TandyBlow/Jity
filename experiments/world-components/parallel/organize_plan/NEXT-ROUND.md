# 下一轮：可用检查点与新留出（本轮不启动训练）

日期：2026-11-08。基线提交：`8a93f45`（v2 检查器）＋本轮复核应用。
状态：**只做清点与门槛定义，没有训练、没有申请 GPU、没有调用模型、没有生成新世界回合。**

本文回答两件事：**拿什么权重跑**、**拿什么材料当留出**。两件都还没有落实，因此“模型能否执行计划”仍然无法判断。

## 1. 检查点：本地 30 个权重目录，没有一个有“读过计划”的证据

`inventory_checkpoints.py` 只读扫描 7 个根目录，读 `config.json` 与 `model.safetensors` 的字节，**不加载模型**。结果在 `freeze/checkpoint-inventory.json`。

| 项 | 数字 |
| --- | --- |
| 找到的权重目录 | 30 |
| 完成 sha256 的 | 29（跳过一个 942 MB 的 Qwen GGUF，超过 500 MB 上限） |
| 记录里能对上哈希的 | **1**：Randeng-T5-77M 基座 `5cdc572109cf…`，出现在 `controllability-freeze-v1.json` 的 `base_hashes` 里 |
| 有“训练时消费过计划块”证据的 | **0** |

为什么 0：旧 controllability 的冻结记录里，`base_hashes` 只钉了**基座**的哈希；它的训练产物在报告里写明**没有保存**（`controllability-report-v1.md`：「权重未提交」；`README` 记的 `ckpt-group` 只有 `~/n4group_run/ckpt-group` 这种路径，没有文件哈希，且当时 HPC 公钥登录被拒）。

本地这 29 个有权重的目录分别是什么（摘自清点结果）：

| 目录 | 大小 | 是什么 |
| --- | --- | --- |
| `.local/models` | 295 MB | u240 成句检查点（`ab8a9826…`；`.local/models/u240-model.safetensors` 是同目录的另一份拷贝） |
| `.local/demo-n1n4/ckpt-{asm,rewrite,rw60,rw100}` | 295 MB × 4 | 早期 n1→n4 演示的装配/改写臂 |
| `.local/world-components-worktree/.../n4-finetune/*` | 295 MB × 14 | N4 单句/方向/路由臂 |
| `.local/.../n4_corpus_v2/ckpt-{v2,v3,v3a,n5,extractor-v1}` | 295 MB × 4 + 39 MB × 1 | N4 语料 v2/v3、N5 抽取 |
| `.local/world-components-next-worktree/artifacts/next-runs/*` | 295 MB × 2 | cf24 对照/处理臂 |
| `.local/world-components-worktree/ckpt-scenevb` | 295 MB | 场景词表臂 |
| `.local/demo-n1n4/.qwen05` | 942 MB | Qwen2.5-0.5B 的 GGUF/权重副本，超过 500 MB 上限，未算哈希 |
| `.local/mockremote/base` | 295 MB | 测试桩（与 `n4_corpus_v2/ckpt-v2` 同哈希 `e89739ec…`） |

这些权重**都不是**在“事实 + 计划块”的输入上训练的。拿它们跑 18 条计划提示，得到的只能是“零样本/其它训练任务的行为”，不能回答计划执行问题——和本轮 `model_smoke.py` 的基线 smoke（0/4）同一类证据。

### 1.1 要落实检查点，只有三条路，各有代价

| 路线 | 具体做法 | 代价 / 风险 | 是否满足“可归因” |
| --- | --- | --- | --- |
| A. 找回旧检查点 | 按记录里的 `~/n4group_run/ckpt-group` 去 HPC 找；找到后必须核出 `model.safetensors` 的 sha256，并与任何记录对上 | 该路径的历史记录没有哈希，找到也无法证明就是当时那个；公钥登录此前被拒 | 只有拿到哈希且能对上记录才算 |
| B. 重训一次可控性臂 | 复现 `controllability-v1` 的冻结配置（77M、120 更新、20/6/10 划分） | **需要 GPU，本任务禁止**；且旧材料本身有“B 全是同一形状”的缺陷，重训也只能在同一批材料上回答 | 是（配方+哈希齐全） |
| C. 换一个已发布的中文 instruction 模型零样本测试 | 例如 0.5B–1B 档的通用模型，直接读计划提示 | 不是“计划训练”，只能测“提示里写了计划，通用模型会不会照做”；不能替代计划执行能力结论 | 是，但结论范围要改写 |

本轮不做任何一条。**下一步需要用户裁决走哪条**；其中 A 只是取证、B 需要 GPU 批准、C 需要明确接受“零样本”这个范围限定。

## 2. 新留出：现有 9 个来源不能当能力留出

`freeze/sources.json` 的 9 个来源都有完整证据链（`*-authorized.json` + `world_evidence` + `world_points.delta_json` + 授权关系），但：

1. 它们**全部出现在旧材料里**（`controllability-v1.jsonl` 与 `pairs-v2.jsonl`），历史上被用于训练、选点或复核，`fixture-r5`、`train-r4` 还是旧固定留出——按“见过就不能当新留出”的规矩，不能拿来出能力结论。
2. 主工作区 `artifacts/world-provenance/pairs/` 只有这 10 组（`fixture-r1..r5`、`train-r1..r5`），没有第 11 组。
3. 生成新的一组需要**新的世界回合**：提交点、`delta_json`、`world_evidence` 行、`world_point_evidence` 前驱链、`world-relation-validator/1` 的关系授权。这是 Python 侧的权威写入，属 A 的职责范围，不在本分支。

所以新留出目前是**阻塞状态**，不是“还没跑”。一个可用的新留出至少需要：

| 要求 | 为什么 |
| --- | --- |
| ≥10 个来源（含至少 3 个多事实组、2 个带授权 `before` 边） | 成对成功门的 8/10 需要分母 |
| 每源两份合法计划，形状**随源变化**（不能一份永远“全拆”） | 否则固定策略能白拿，旧实验就是这么失败的 |
| 每个事实能追到 `pointId` / `evidenceId` / `delta_json` | 本轮的来源核验链条，缺一不可 |
| 关系授权来自 `world-relation-validator/1` 的 `verdict=pass` | 计划里的边只能搬运授权，不能自造 |
| 从未出现在任何旧训练/选点/复核材料里 | 否则不能称留出 |

## 3. 判据与工具已经就绪，缺的只是权重和材料

| 环节 | 状态 | 文件 |
| --- | --- | --- |
| 计划合法性校验 | 就绪，18/18 + 20 负例 | `plan_contract.py`、`freeze/negative-cases.json` |
| 文本一致性（顺序/关系词作用域/新增内容） | 就绪，11/11 探针 | `text_conformance.py`、`freeze/tamper-probes.json` |
| 验收判据（含两级判据与门线） | 冻结 | `freeze/criteria-v2.json` |
| 人工核验流程 | 就绪，已收到一轮 AI 复核（待人工签认） | `runs/r2/manual-review.json`、`apply_review.py` |
| 下游模拟输入 | 冻结 18 条 | `runs/r2/downstream-inputs.jsonl` |
| 固定策略对照 | 就绪，当前 0 成对 | `runs/r2/controls.json` |
| 可用检查点 | **缺** | `freeze/checkpoint-inventory.json` |
| 新留出材料 | **缺（阻塞，需 Python 侧新回合）** | — |

## 4. 本轮明确没做什么

- 没有训练，没有申请 GPU，没有加载权重跑推理（`inventory_checkpoints.py` 只读 `config.json` 和权重字节）。
- 没有生成新世界回合，没有改任何夹具、没有改计划、没有改判据。
- 没有把 AI 复核当成人工签认：`runs/r2/acceptance.json` 的 `gateStatus` 是 `PROVISIONAL_AI_REVIEW_ONLY`，不是 `OPEN`。
- 没有改写已冻结的 `criteria-v2.json`；`fail` 这个第四个取值单独立了修正记录 `freeze/criteria-v2-amendment-1.json`。

## 5. 需要用户决定的三件事

1. 检查点走 A（取证）、B（重训，需 GPU 批准）还是 C（零样本，需接受范围限定）？
2. 新留出由谁生成：是否把“新世界回合 + 授权关系”排进 A 的排期？
3. 人工签认由谁做、按什么形式留痕（当前 `manual-review.json` 的 `reviewer` 块是 AI 复核，`humanSignoff: pending`）。
