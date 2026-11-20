# N4 单事实中文成句（c4）

| 项 | 值 |
|---|---|
| 对应设计 | R11（内容组织与成句交接的下游：单事实成句） |
| ModelTask | narration / N4 |
| 当前档位 | **c4 本阶段诊断完成；T1 失败；独立验收尚未开展。** 原模板 + 贪心为现有基线，束宽 2 仅作诊断实现；17 条独立样本已登记、未运行 |
| 分支 / 工作树 | `exp/c-fact-wording` / `.local/parallel/c-fact-wording`（基线 `6440534`） |
| 独占目录 | `experiments/world-components/parallel/fact_wording/` |
| 本轮做过的事 | 核对 u240 权重身份；清点可用旧归档；按 unitId 整理 cf24 缺陷、覆盖缺口与来源缺口 |

---

## 1. 这一轮要回答的问题

任务说明要求“复用已冻结的 77M/u240 或只读归档”。在动手做失败分类和对照之前，必须先回答两件事：

1. 本地到底有没有 u240 的权重，它是不是报告里说的那一份？
2. 旧记录里哪些数字能写成“u240 的成绩”，哪些只能写成“某个没有记身份的检查点的成绩”？

第 2 问不是文字游戏。`design/world-engine-reports/components/candidate-selection-space-v1.md` 已经写过：贪心／束宽 2 的三份结果**没有记录模型目录或哈希**，而且那轮的贪心臂与常驻服务归档在 50 条真实回合上只有 44/50 逐字相同。如果直接把那张四格表写成 u240 的表现，就是在给一个不认识的检查点记成绩。

---

## 2. 做了什么（谁给了谁什么）

```
.local/models/u240-model.safetensors   ──┐
.local/models/model.safetensors        ──┤ 程序逐个读文件、算 sha256
.local/models/config.json              ──┤ 并从 safetensors 头里数张量/参数量
.local/models/spiece.model             ──┘        │
                                                  ▼
6 份写了“u240 是什么”的记录 ──► 对照：这些记录里写的哈希，和本地算出来的对不对得上
                                                  │
21 份候选证据文件 ───────────► 各自算 sha256，并看文件自己有没有记检查点身份
                                                  │
                                                  ▼
        freeze/u240-identity-v1.json + freeze/evidence-inventory-v1.json
```

程序是 `scripts/inventory_u240.py`。它只读，不加载模型，不生成任何句子；其他工作树只读不写。输出两个 JSON 在 `freeze/`。

复跑：

```bash
cd experiments/world-components/parallel/fact_wording
python -X utf8 scripts/inventory_u240.py --print
```

---

## 3. u240 身份结论

**本地的 u240 是存在的，两份文件字节完全相同，三份归档记录了同一个 64 位哈希。**

| 项 | 实测值（本轮重算，不从报告抄） |
|---|---|
| 权重文件 | `.local/models/u240-model.safetensors` |
| 大小 | 309,783,976 字节 |
| sha256 | `ab8a98264ee6b4f83eba17d624d7b92b23522c8eacef07d07a5be960e390184a` |
| 重复副本 | `.local/models/model.safetensors`，sha256 相同 |
| 结构 | `T5ForConditionalGeneration`，d_model 512，编码器/解码器各 8 层、6 头，d_ff 1024，词表 32,596 |
| 张量 | 190 个，全部 F32 |
| 参数量 | 77,440,384（77.44M，与 `route-split-report-v1.md` 记的每模型参数量一致） |
| config.json | `cd553527a919b8292894d4e8cc043fcb1a45c60586f9dfa4399f7b2b2e657a9e` |
| spiece.model | `c65feffa65ff0378759778193852083d23349cb1b40c906e9463a12f8076ff32` |

记录侧的对照（`freeze/u240-identity-v1.json` 的 `declarations`）：

| 记录 | 记录内容 | 完整哈希 | 8 位前缀 |
|---|---|---|---|
| `artifacts/three-arm-r1/three-arm-freeze.json` | 起点权重 u240 | 命中 1 次 | 命中 |
| `artifacts/next-acceptance/cf24-u240-baseline/index.json` | 本轮的 u240 基线运行 | 命中 1 次 | 命中 |
| `artifacts/next-acceptance/target-revision-r1/index.json` | `base.modelSha256` | 命中 1 次 | 命中 |
| `design/.../three-arm-plan-2026-11-05.md` | `~/n4uni/ckpt-u240`，标注与本地逐字节相同 | 0（只写前缀） | 命中（权重／config／tokenizer 各 1） |
| `design/.../cf24-baseline-2026-11-05.md` | 权重 sha 前 8 位 + 与 `u240-model.safetensors` 同 sha | 0（只写前缀） | 命中 |
| `design/.../eval-r1-2026-11-05.md` | u240 权重前缀 | 0（只写前缀） | 命中 |

三份 JSON 里有完整 64 位并和本地重算结果一致；三份文档只写 8 位前缀，前缀也一致。

**明确没验的部分**：HPC 上 `~/n4uni/ckpt-u240` 只在 `three-arm-plan-2026-11-05.md` 里被写成“与本地逐字节相同”，本轮没有连 HPC 重算它的哈希，也没有找训练日志把这个权重绑到某个代码提交上。所以身份证据是“四处记录 + 本地两份副本指向同一个哈希”，不是“从训练到部署的完整链”。

---

## 4. 可用证据清单

判定规则：文件本身，或拥有它的索引，写了上面那个 64 位 sha256，才算 u240 证据。结果写在 `freeze/evidence-inventory-v1.json`。

### 4.1 能标成 u240（证据里带身份）

| 文件 | 内容 | 大小 / sha256 前 16 位 |
|---|---|---|
| `next/artifacts/next-acceptance/cf24-u240-baseline/cf24-u240-baseline/cf24-baseline.json` | 85 条 cf24 单元的贪心原文（CPU，中位 1.25 s/条） | 137,379 / `cb153939fc58feb9` |
| `…/cf24-mechanical.json` | 同一批的机械 S/O/C/A 判定 | 19,648 / `7e2bca51eadf43ad` |
| `…/cf24-overlap.json` | 85 条与训练集的签名级重叠 | 20,213 / `51dedce5047c4f13` |
| `…/cf24-review.json` | 24 个源的归档判读（`reviewer` 为 assistant，不是真人签字） | 21,891 / `79c9908dd8a3726a` |
| `…/cf24-u240-moved-rule/cf24-baseline.json` | 加了一句输入提示后的第二次 85 条原文（输入侧修复失败的证据） | 138,226 / `b276cfd62eb4499b` |
| `next/…/target-revision-r1/val-u240/val-baseline.json` | u240 在 final24 验证集上的原文 | 114,808 / `2f9a2d088c386c5c` |
| `next/…/syntax-gap-r1/probe-u240/probe-baseline.json` | u240 在冻结最小对照探针上的原文（CUDA） | 27,753 / `f3675a90457c7c12` |

这些文件由三个索引认领：`cf24-u240-baseline/index.json`、`target-revision-r1/index.json`。cf24 索引给 9 个子文件写了 sha256，本轮逐个重算，**9/9 一致**。

### 4.2 不能标成 u240（没有身份，只能当诊断）

| 文件 | 内容 | 为什么不能算 u240 |
|---|---|---|
| `wc/artifacts/decode-compare/arm-ab.json` | 90 条小回归的贪心／束宽 2 原文与耗时 | 文件、脚本、日志都没记模型目录或哈希 |
| `wc/artifacts/decode-compare/diag215-ab.json` | 215 条诊断集同上 | 同上 |
| `wc/artifacts/decode-compare/confirm40-ab.json` | 40 条确认集同上 | 同上 |
| `wc/artifacts/world-components/decode-beam-review-v1.md` | 32 条两臂差异的逐条复核 | 复核质量可用，但被复核的句子身份未知 |

这四份文件的 sha256 与 `candidate-selection-space-v1.md` §8 表里写的 16 位前缀逐个对得上（4/4），说明**文件没被改过**——但这只证明“是当时那份文件”，不证明“是 u240 生成的”。两者是不同的问题。

另有 `next/artifacts/next-inputs/world-components/n4-cf24-scoring-v2.json`：它是 base／arm1／arm2／422／431 五臂的 cf24 判分，没有 u240 臂，也没有哈希。旧记录里的 u240 数字（85·24·23）在 cf24 基线报告里已被判定与本次口径不可比，本轮同样不采用。

### 4.3 输入集（数据，不需要身份）

| 文件 | 内容 | 校验 |
|---|---|---|
| `artifacts/world-components/n4-cf24-contract.jsonl`（本树） | 85 条单事实单元 / 24 个源：结果 43、外貌 30、移动 10、理智 2 | sha256 `a94f7a13eb61…`，与 cf24 基线报告写的 12 位前缀一致，行数 85 |
| `wc/artifacts/decode-compare/{cases,diag215-cases,confirm40-cases}.json` | 90 / 215 / 40 条旧案例的输入 | 哈希在清单里；`cases.json` 的 16 位前缀与文档一致 |

---

## 5. 失败与缺口（如实列出）

1. **身份链不完整**：没有训练日志把 `ab8a9826…` 绑到一个代码提交；HPC 副本没复算哈希。现在能说“四处记录指向同一份本地权重”，不能说“这条权重从哪次训练、哪一行代码来”。
2. **贪心／束宽 2 的旧对照不能用**：身份缺失已确认（不是本轮新发现，是被本轮复核证实）。所以“束宽 2 比贪心好 24 条”只能写成一个未知检查点的候选空间结论。
3. **旧 u240 数字口径不可比**：`85·24·23` 与 cf24 基线的 `85·15·21` 判定标准不同（是否把尾句算新增、CPU/GPU 差异），旧数字里连逐事实标签都没留。本轮不引用。
4. **本轮没有跑推理**：只算了哈希和结构，没有加载模型、没有生成。所以下文的耗时预算全部来自旧记录，不是本轮实测。
5. **设备不一致**：cf24 基线在 CPU（4 线程、fp32）跑，syntax-gap 探针在 CUDA 跑。同一份权重，不同设备，速度不能混着比。

---

## 6. 第 2 步：失败分类（已完成归档整理，待真人核验）

`scripts/classify_cf24.py` 连接 85 条原文、旧判读、机械判分、训练重叠和 pin 中登记的夹具；先核对来源哈希、逐条事实和原文一致性，再重算旧 summary。详细结论见 [分类报告](results/failure-report-v1.md)。旧判读的 `reviewer` 明确写了 assistant；本文此前称“人工判读”的地方均指这份旧记录，不代表真人签字。

归档将核心事实全部标为支持，明确缺陷为 **6 条新增动作或状态、2 条复述、3 条语病**，共 11 条。五类分类不应把它们硬改成事实错误：

- 主体：2 条新增尾句把“鞋底”当作站住的主语，不等于核心事实里的人物互换。
- 方向：2 条 `方向=平` 写“上来”，只登记措辞风险，不改判起终点事实矛盾；关系双方互换和高低方向对照未覆盖。
- 理智：仅 2 条 12→9，实际输入隐去了数字，只给“发紧”；数值保真无法判断。
- 位置：2 条新增“在石阶边/木桩旁站住或停留”；可见清单授权物件存在，不授权停留。
- 额外动作或状态：6 条，完整保留归档的新增片段和原因。复述与语病另列，不混作归属或方向失败。

主体、位置、新增类别有交集，不能把类别数量相加当成失败条数。15 条待核验候选拆成固定编号的两批（10 + 5），当前均为 `pending-human-review`。

| 文件 | 内容 |
|---|---|
| `freeze/failure-taxonomy-v1.json` | 分类规则、归档标签与本轮分类的界限 |
| `freeze/failure-classification-v1.json` | 来源哈希、脚本哈希、提交、重算统计、输出文件哈希 |
| `results/cf24-catalog-v1.json` | 全部 85 条的事实、实际输入、输出原文、原标签、来源指针、token 与旧耗时 |
| `results/cf24-moved-rule-pairs-v1.json` | 10 条移动的旧基线/提示变体配对；变化文本不继承旧片段判读 |
| `results/failure-report-v1.md` | 已证明 / 已失败 / 无法判断、限制与下一步 |
| `review/batch-01.json`、`review/batch-02.json` | 10 条与 5 条待真人核验清单；没有填造人类结论 |

来源限制：每条能追到冻结 `contract` 的行号、`sourceId/factId` 与 `materials-v2` 的 JSON 指针；原夹具没有 `entityId`、`pointId`、世界 `fieldPath`。这些缺失值明确保留，不按姓名补造；本轮只能复核登记夹具，不能称为已提交世界点或新的独立验收。签名级 independent 也不能证明短语级独立。

在本目录复跑：

```powershell
python -X utf8 scripts/classify_cf24.py
python -X utf8 scripts/classify_cf24.py --check
```

`--check` 只读核对来源与产物。生成清单不承载已完成的真人判定，后续真人反馈另存文件。本轮不加载模型、不生成，所有推理耗时来自旧 CPU 记录。

## 7. 下一步（第 3→4 步）

**第 3 步：对照工具就绪、预检通过，完整对照未跑。** 协议 v2 改正了束搜索停止规则（v1 的“两条完成就停”会丢掉分数更高的未完成分支，反例见协议 §1）；独立环境 py3.12.3 / torch 2.7.0+cu126 / transformers 4.57.3；4 个归档脚本只读复制、哈希一致；束宽 2 实现通过 9 组测试（含 300 张随机表穷举对照），P1–P9 全过，5 条预检单元的贪心输出与归档 u240 逐字一致。报告见 `results/preflight-report-v1.md`。独立验收集仍为空，cf24／final24／moved24／探针都只能当诊断。

**第 4 步：交付。** 原始输出、每单元耗时、回退原因、结论分“已证明／已失败／无法判断”三类；人工核验每批 ≤ 10 条、编号固定、可复跑。

---

## 8. 结论（单独可读）

本地确实存在冻结的 u240：`u240-model.safetensors` 与 `model.safetensors` 字节相同（sha256 `ab8a9826…`，309,783,976 字节，77,440,384 参数），三份归档 JSON 记录了同一个完整哈希，三份设计文档记录了同样的 8 位前缀。可用的 u240 证据是 cf24 的 85 条原文＋人工判读、moved-rule 复跑、final24 验证集与 syntax-gap 探针；贪心／束宽 2 的三份 305 条对照**不能**算作 u240 成绩，因为它们从未记录检查点身份。

cf24 的第 2 步分类已整理：85 条原文与旧判读一致，11 条归档缺陷按新增、复述和语病保留，方向与理智数值覆盖不足单列为无法判断。两批共 15 条候选等待真人核验，模型泛化未据此验收；归档夹具缺提交点与实体 ID，不能冒充世界权威记录。

支撑文件：`freeze/u240-identity-v1.json`、`freeze/evidence-inventory-v1.json`、`freeze/failure-classification-v1.json`、`results/failure-report-v1.md` 及两个脚本。

---

## 9. 结项（c4 本阶段）

**最终状态：c4 本阶段诊断完成；T1 失败；独立验收尚未开展。**

| 项目 | 结论 |
|---|---|
| u240 身份与运行链路 | 本地哈希与三份归档一致，P1–P9 预检通过，两次诊断有源码快照与原始记录；`env.json` 事后重建等限制保留 |
| 束宽 2 | cf24 85 条：贪心 70/11/4，束宽 74/7/4；改善 4、退化 0、不变 77、U 4；耗时约 2.7×；改善中 3 条 seen-fact、1 条签名独立；**不足以设为默认** |
| T1 | 准入失败：有效修复 0/6，原通过退化 4 条（t03:f0、t05:f0、t11:f2、t18:f1）；新增 6→8、复述 2→4；**不进入独立验收** |

因果口径更正：撤掉该分句后新增仍存在，**不能否定它是“充分原因”**；本轮直接支持“这一替换未减少新增，并引入四条退化”。见 `results/candidate-t1-result-v1-audit.md`。

**当前配置**：保留原输入模板与贪心作为基线；束宽 2 保留为诊断实现；候选 T1 冻结不采用；独立验收集不运行；两者都没有独立验收通过结论。

**可核查索引**：`freeze/final-index-v2.json`，其 sha256 记在同目录的 `freeze/final-index-v2.sha256`（索引是自指的，值不写在被索引的文件里）；可读表见 `results/final-index-v2.md`（204 个文件、0 缺失）。v1 索引保留在 `freeze/final-index-v1.json` 作为历史。环境目录不打包，保留依赖锁与环境说明。冲突采用规则写在索引与 `results/c4-stage-closure-v1.md`。

**重新开展实验的条件**：需要新的、可检验的机制假设，或授权训练侧工作；不能只换一句提示继续搜索。训练侧改动另立任务，本轮不实施。详见 `results/c4-stage-closure-v1.md`。

## 10. 评审后的修正（2026-11-09）

云端评审的七条代码/评测问题**全部成立**，逐条证据见 `results/review-findings-v1.md`：

| 问题 | 处理 |
|---|---|
| 盲判只打乱编号、同事实相邻；T1 输入泄露提示词 | 撤回“严格盲判”说法；新增 `blind-v2/`（整表洗牌、同事实不相邻、隐藏要求分句），**未判** |
| 验收事实来源错（ac01 用 goal、su01 换主体却标非人工、moved 由地点构造、sa01/02 数值不可核） | 生成 v2 登记（`freeze/acceptance-registration-v2.json`）：改正来源与判据；v1 保留；**仍未运行** |
| 1.72/4.69 s 只是解码耗时 | `results/timing-scope-v1.md`：解码 548.51 s、墙钟 568.1 s，残差 18.77 s（编码+记录） |
| 运行目录可被复用/覆盖、raw 与 order 可不同步 | `run_diagnostic.py`：完成的运行不复用；恢复要求两份记录行数一致；恢复时不重写启动元数据 |
| 提交含两个带本地路径的 `.pyc` | 已从工作区与提交删除；分支提交已重写（旧 SHA 不再被引用） |
| 索引漏了失败分析、人工核验、索引脚本 | v2 索引补齐（198 个文件），并列出有意排除项 |
| 不建议继续改提示词 | 采纳，见 `results/next-steps-after-review-v1.md` |

### 第二轮评审（`9702183` 之后）

| 问题 | 处理 |
|---|---|
| 恢复时收尾仍用本进程 `run_meta` 覆盖 `run.json` | 恢复改为继承原元数据，另记 `resumeCount`/`resumedAt`/`runnerSha256AtResume`；收尾只追加 `finishedAt` |
| po01/po02 来源仍不准 | po01 改 `authored`（afterPosition 只有终点位置）；po02 改 `derived`（放筐的人与动作是推导的）；v2 登记已重生成 |
| 盲判 v2 展示模型看不到的数值 | 理智单元去掉 `from`/`to`；每批加固定 `judgingNotes`；两份包已重生成，仍未判 |

证据：`results/review-findings-v2.md`。

## 11. 真实状态 N3→N4 冒烟（2026-11-09）

只读扫描 178 个真实世界库：107 个有改动的已提交点，72 个能走完 N1→N3（58 单事实、14 双事实），但**没有雾港世界（`w_fog_harbor`）的点**，全是测试世界。去重后只有 7 个不同事实：moved 2、task 2、sanity 3。

u240 适用规则（先冻结）：moved 可用；task_achieved 没有 resultText、sanity 只有数字，均判不适用、不调用模型。实际调用 2 次（两条 moved）：**0 通过 / 2 失败**（一条新增“抬头看”，一条把走廊写成“盒子里”）。

- 报告：`results/real-state-n3n4-smoke-v1.md`
- 运行：`artifacts/fact-wording/real-state-smoke/20261108T180059-realstate/`
- 脚本：`scripts/run_real_state_smoke.py`
- 耗时（含编码）：每条 2.1–3.1 s；模型加载 0.69 s
- 限制：世界与 u240 训练世界不同；覆盖仅 2 条；分组/指代未实现；assistant 单判
