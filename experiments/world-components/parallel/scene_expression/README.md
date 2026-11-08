# c6 · 授权场景素材对叙事生成的三臂实验（u240 / Randeng-T5-77M）

| 项 | 值 |
|---|---|
| 分支 | `exp/c-scene-expression` |
| 父分支 | `world-components` @ `64405346fe63c2f05cf067f3b328893fa9e0d381` |
| 任务书 | 工作树根 `TASK.md`（未跟踪）；实验方案见根目录 `SCENE-CONTEXT-ABLATION-v3.md` |
| 对应 R | R11（叙事选择/组织/生成）／R03（人物与世界变化） |
| 当前档位 | **本轮收口：生成与执行方初审完成，整批文案验收不合格；自然度评审停止，转入段落生成路线方案** |
| 独占目录 | `experiments/world-components/parallel/scene_expression/` |

## 目录差异（必须写清）

v3 方案正文写的工作目录是 `experiments/world-components/parallel/c-context-ablation/`；本分支的任务书与并行分支编号表登记的是 `experiments/world-components/parallel/scene_expression/`。**本分支产物统一放在后者**，前者不存在；这是路径登记差异，不是两份实验。

## 要回答什么

同一批已提交事实，补上当前有效、主角视角可见的世界素材后，同一个 77M 模型在**逐事实生成流程**里能否写得更自然，同时不增加事实遗漏、错误或未授权行动。

结论边界：只描述 u240 逐事实生成＋程序拼接的效果；整回合单次调用只作为兼容性诊断（`step1/step1-verify.json`），不是正式路线；不训练、不改共享契约、不接产品。

## 文件

| 文件 | 作用 |
|---|---|
| `freeze-protocol.md` | 冻结协议：模型身份、样本、责任分配、素材来源、三臂提示、调用与拼接、解码、程序句、判分、人工核验、门槛、限制 |
| `frozen/manifest.json` | 冻结清单：样本导出、素材、输入、构建脚本的 SHA-256 与冻结时提交 |
| `frozen/materials.json` | 每题素材池（`entityId` / `fieldPath` / 来源 ID / 可见性 / 生效点）与三臂场景头 |
| `frozen/inputs.json` | 每题每个必述槽位：模型槽的完整 prompt（A/B/C 各一份），程序槽的固定句 |
| `frozen/prompt-tokens.json` | 十题每条输入的实际 token 长度（A 114–125、B 136–160、C 168–197；共 8 条 × 3 臂） |
| `build_inputs.py` | 生成上面两份冻结 JSON；改脚本等于改协议，需重跑并更新 manifest |
| `measure_inputs.py` | 只量 token，不生成 |
| `step1_verify.py`、`step1/step1-verify.json` | 第 1 步：权重大小/SHA、加载、旧模板兼容、贪心可复现 |
| `step1_token_probe.py`、`step1/step1-token-probe.json` | 第 1 步：训练输入长度分布、十题所需事实能否落进旧契约 |
| `step1/narration-split-samples.export.json` | 从 TS 导出的冻结样本（源文件 SHA-256 记录在内） |
| `export_samples.mjs` | 上述导出的可复现脚本 |
| `probe_sentences.mjs` | 冻结前诊断：程序句送进冻结判分器的必述与残差结果 |
| `run_frozen.py`、`step3/` | 24 条调用与 30 份初稿（`calls.jsonl`、`drafts.jsonl`、`run.json`、`preflight.json`） |
| `score_drafts.mjs`、`step4/scores.json` | 冻结判分器自检＋评分，含共享授权词表残差 |
| `step4/ballot/` | 遮蔽映射 `order.json` 与空选票 `ballot.json` |
| `step4/run-report.md` | 生成／评分／评审材料报告（含第 5 步更正） |
| `adjudicate.py`、`step5/clauses.jsonl`、`step5/adjudication.json` | 72 条分句的逐句核验（执行方 pre-check，待独立人工确认） |
| `build_packet.py`、`step5/review-packet.md` | 盲评包：已提交事实背景＋甲/乙/丙，无臂名无评分 |
| `step5/summary.md` | 人工核验与程序评分对照、责任划分、待定项 |
| `step5/material-use-evidence.md` | 逐项核对增补素材是否真的进了正文（区分共用事实行） |
| `step5/final-comparison.md` | 按样本列出三臂的遗漏／事实错误／未授权动作（不跨口径相加） |
| `step5/independent-review/` | 独立评审记录位置：`clause-review.jsonl`、`naturalness-return.json`、改判说明；不覆盖初审 |
| `build_independent_review.py`、`reveal_naturalness.py` | 生成独立评审模板；选票收齐后揭示映射并统计（当前已停止评审，模板留空） |
| `step6/verdict-stop-naturalness.md` | 失败结论与评审停止记录 |
| `step6/references/` | 三题参照段落（人工写作，非模型输出）＋逐句来源表 |
| `build_references.py` | 参照来源表的生成与路径校验 |
| `step6/references/reference-paragraphs-v2.md` | 参照 v2：正文＋面板＋来源；删除语义越界，数值移入面板（仍为草稿，未作标尺） |
| `step6/route-plan.md` | 段落生成路线方案：验收标准、A/B/C 路线、数据、排期、未决问题 |

## 复现

```bash
# 仓库根；需要 torch/transformers 的解释器（本机用 envs/nndl_proj）
PY=/d/software/Anaconda/envs/nndl_proj/python.exe
$PY -X utf8 experiments/world-components/parallel/scene_expression/step1_verify.py
$PY -X utf8 experiments/world-components/parallel/scene_expression/build_inputs.py
$PY -X utf8 experiments/world-components/parallel/scene_expression/measure_inputs.py
```

`step1_verify.py` 会在主工作树 `.local/models/` 找权重（`git rev-parse --git-common-dir` 定位），不要求当前工作树有副本。

## 已知限制（详见冻结协议第 14 节）

- 十题中 4 题（`ns-task-1`、`ns-task-time-1`、`ns-empty-1`、`ns-cont-3`）没有任何 u240 能表达的事实，整篇只有程序句，不能用来证明素材改善模型叙事；因此有效配对照计划是 6 题，本轮自然度门槛按任务书记 `not_evaluable`。
- 旧契约没有时间、任务、理智数值事实行；这些由固定程序句承担，三臂同文同位置。
- C 臂的“上一段叙事”在数据集里不存在，如实登记为缺口，不补造。
- B 臂的素材包含本轮外貌事实原文，C 臂包含个性变化原文；对相应样本存在“把答案写进提示”的混杂，解释时保留。

## 冻结清单与 README 的哈希差异（留档，不更新旧清单）

`frozen/manifest.json` 里 `docs.README.md = 0e8d9efca55c72ef0dd07c4f141f0d55816535fbb3df1d48210b89962a473197`，对应冻结提交时的 README（当时只有第 1–2 步的文件表）。此后 README 为补充第 3–5 步文件表被多次追加，**当前文件的 SHA-256 已不等于清单值**（自指哈希无法在文件内写死，请用 `sha256sum README.md` 自行核对）。

按协议“冻结文件保持原字节”，**不修改 `frozen/manifest.json` 去追平**；冻结证据以清单记录的版本为准，README 的后续增补不在冻结范围内。

## 当前结论

- 背景对照（A/B/C）：三臂均出现未授权动作（各 2 处，均为移动钥匙）；B、C 各新增两处目的地遗漏，A 无遗漏但以同一句钥匙动作构成事实错误；增补素材未显示叙事收益，自然度门槛 `not_evaluable`。
- **整批文案验收：不合格**（产品负责人判定）。u240 逐事实生成＋直接拼接交不出合格段落；本轮不比较自然度，转入“能否生成合格段落”的路线方案（`step6/route-plan.md`）。

## 仓库约定

仓库 `.gitignore` 忽略 `experiments/`，本目录文件用 `git add -f` 强制加入（与既有 `experiments/` 产物一致）。目录内 `.gitattributes` 设为 `* -text`，禁止换行转换，保证 checkout 后的字节与 `frozen/manifest.json` 里的 SHA-256 一致。

工作树根的 `TASK.md` 与 `SCENE-CONTEXT-ABLATION-v3.md` 是任务方提供的说明，保持未跟踪，不在本分支提交。
