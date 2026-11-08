# 下一轮：检查点取证结果与留出交接（本轮不训练）

日期：2026-11-08。基线：`3431678` 之后的 c3 工作树。
状态：**取证结束（未发现）；留出交接契约与接收工具已就绪（材料未到）；签认表已生成（未签）。没有训练、没有申请 GPU、没有调用模型生成。**

三项决定已定：

| 决定 | 内容 | 本轮状态 |
| --- | --- | --- |
| 1 检查点 | 走 A 取证；找不到就记录缺失并停止，不自动转 B 重训；C 不复跑（零样本 smoke 已有证据） | **已执行，结论：本地未发现可归因检查点** |
| 2 新留出 | 由 A 在 Python 侧生成 ≥10 个新来源；c3 只读接收、核查隔离、构造双计划、推理前冻结 | **契约与工具就绪；材料未到** |
| 3 人工签认 | 由项目负责人逐条核对并另存签认记录；保留 AI 标注；T09 可留 `unsure`；签认前维持 `PROVISIONAL_AI_REVIEW_ONLY` | **签认表已生成，未签** |

---

## 1. 取证（决定 1）

工具：`recover_checkpoint.py`，只读，不加载模型。结果：`freeze/checkpoint-forensics.json`。

### 1.1 已提交脚本没有落盘逻辑

`train_controllability.py` 在**所有已提交版本**（本仓库只有 1 个版本，`80ed473`）里都没有 `save_pretrained`、也没有 `torch.save`。它做的是：

```python
best = {"success": ns, "loss": dl, "epoch": epoch, "updates": update,
        "state": {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}}
...
model.load_state_dict(best["state"])   # 只在内存里恢复，然后直接评估
```

也就是说：最好的一轮状态只存在于进程内存里，选点后立刻 `load_state_dict` 再跑留出，没有落盘这一步。

能说的只有：**这份已提交的脚本跑一遍不会写出权重**，本地扫描也没发现可归因的权重。不能说成“任何地方都不存在过”——未提交的脚本变体、手工导出的副本、别的机器上的临时文件，都不在本次证据范围内。

对照：后来那个 784M 成句脚本（`train_sentence_scale_784.py`）确实有 `model.save_pretrained(...)`，所以那批检查点在本地能找到。

### 1.2 记录里没有可比的哈希

| 检查 | 结果 |
| --- | --- |
| 冻结记录 `controllability-freeze-v1.json` 的字段 | `base_hashes` 只钉基座（`5cdc5721…`）、`base`、`training`、`selection`、`acceptance`、`no`；**没有任何 trained-checkpoint 字段** |
| 运行记录 `controllability-run-v1/results.json` 的字段 | `material`、`material_sha256`、`freeze`、`freeze_sha256`、`config`、`counts`、`history`、`selected`、`holdout`、`holdout_success`；**哈希字段只有材料与冻结记录，没有权重** |
| 运行目录内容 | 只有 `results.json`（40 KB）与 `run.log`（5 KB），没有 `*.safetensors`/`*.bin` |
| `controllability-report-v1.md` | **全文没有出现“权重”二字**，所以它既没声称保存、也没声称丢弃 |

更正一处此前的错误引用：`权重未提交` 这句话出自 `design/world-engine-reports/components/README.md`，说的是 **A/B_h 句组臂**那次 120 次更新的运行，不是 controllability。两者不能混引；已单独记在 `freeze/checkpoint-forensics.json` 的 `claimsInRecords.otherRunStatement` 里。

### 1.3 文件系统：30 个权重目录，0 个可归因

`inventory_checkpoints.py`（只读、只含 `config.json` 与权重字节）扫 7 个根目录：

| 项 | 数字 |
| --- | --- |
| 权重目录 | 30 |
| 完成 sha256 | 29（跳过一个 942 MB 的 Qwen 副本） |
| 记录里能对上哈希 | **1**：基座 `5cdc5721…` |
| 有“训练时消费过计划块”证据 | **0** |

另外，名字里含 `ckpt-group`/`controllab`/`n4group` 的目录有 10 个，**全部是运行记录目录**（`results.json`/`run.log`），没有一个含权重文件。

### 1.4 没检查到的通道

| 通道 | 状态 | 说明 |
| --- | --- | --- |
| HPC `~/n4group_run/ckpt-group` | 未检查 | 本环境无 SSH 凭据；且记录里没有该文件的哈希，即使取回也无法归因 |
| 离线归档/备份 | 未发现 | 搜索范围内没有这类归档；日后若有人提供副本，必须带一个能与记录对上的哈希，否则仍不可归因 |

### 1.5 结论口径

**取证结果：已提交的 controllability 训练脚本没有检查点落盘逻辑，本地未发现可归因于“读过计划块”的检查点。**

边界：结论只覆盖①这份已提交脚本②本地文件系统。它不能证明“任何机器、任何时间都不曾存在过权重”。这不是“模型能力失败”，也不是“接口无效”——只是没有可用的权重来问这个问题。按决定，到此停止，不自动转 B 重训。

---

## 2. 新留出（决定 2）

契约与接收工具：`HOLDOUT-HANDOFF.md`、`validate_holdout.py`。

A 需要交付：≥10 个新来源，每个来源的提交点、`delta_json`、`world_evidence` 行、前驱链、`world-relation-validator/1` 的授权记录，外加一个 `manifest.json`。

c3 会跑两个自检，证明工具不是“只会通过”也不是“只会拒绝”：

| 自检 | 结果 |
| --- | --- |
| `--self-test`（把现有 9 个来源当成包） | schema/链/证据/授权/计划 **0 错**；隔离把 45 条事实全部判重；来源数 9 未达 10 → `not-admissible` |
| `--unit-test`（两条合成事实） | 全新事实 0 错；把“袖口沾了雨”改成“袖口沾了雨水” → `I-near-duplicate-fact` |

隔离线是 bigram Jaccard ≥ 0.8，只比事实文本、不比姓名，所以“只改人名/地点、事实描述不变”会被抓。

---

## 3. 签认（决定 3）

签认表：`runs/r2/signoff-form.json`（10 行，已把 AI 结论放在 `aiVerdict`/`aiNote`，留出 `humanVerdict`/`humanNote`）。

表里钉了四个哈希，防止“签的时候看的东西”和“跑的时候用的东西”不是一份：判据文件、检查器代码、探针集、人工核验表，外加 `acceptance.json` 的 `identitySha256`。

流程：

1. 负责人逐行填 `humanVerdict`（`paraphrase-ok` / `new-content-fail` / `unsure`）和签名、日期、提交 SHA；
2. `python -X utf8 apply_signoff.py` 生成 `runs/r2/signoff.json`；缺字段或哈希漂移会拒绝；
3. `python -X utf8 apply_review.py` 重算门状态：签认后若没有偏差，`gateStatus` 变 `OPEN`；`unsure` 的行仍记在 `openItems`，**不计通过**。

现在 `apply_signoff.py --show` 的输出是 `status: incomplete`，缺 3 个签名字段和 10 行结论；`acceptance.json` 的 `gateStatus` 保持 `PROVISIONAL_AI_REVIEW_ONLY`。

---

## 4. 本轮明确没做什么

- 没有训练、没有申请 GPU、没有用任何权重生成文本。
- 没有生成新的世界回合、没有改夹具、没有改计划、没有改判据。
- 没有把 AI 复核当成人工签认。
- 没有为了凑数把 `fail` 写进判据：生成器改为对这些行写 `verdict: null` + `alreadyFailedHard: true`，旧值只在 `apply_review` 里做窄口映射并记录偏差。

## 5. 三个独立状态（当前）

`python -X utf8 check_round_ready.py` 输出：

| # | 状态 | 就绪 | 依据 |
| --- | --- | --- | --- |
| 1 | **留出待交付** | NO | `freeze/holdout-v1-freeze.json` 不存在 |
| 2 | 签认完成，门 OPEN | yes | 委托签认：`pi（AI 编码代理）`，2026-11-08，审阅 `4dd9df4`；8 × `new-content-fail`、2 × `unsure`；T09 未通过 |
| 3 | **计划训练检查点缺失** | NO | `freeze/checkpoint-adoption.json` 不存在；取证 `not-found-locally` |

```
模型能力实验：BLOCKED（未就绪：留出待交付、计划训练检查点缺失）
```

**门 OPEN 不等于可以跑模型。** 三项独立判定，缺一即 BLOCKED。

## 6. 下一步

| 等什么 | 谁 | 到货后 c3 的动作 |
| --- | --- | --- |
| 留出包 | A | `validate_holdout.py --package`（含生成过程与人工语义复核两道闸）→ `--freeze` → `render_input.py` → 再冻一份输入 |
| 检查点（若决定走回头） | 用户 / A | 必须先给出 `freeze/checkpoint-adoption.json`：权重 sha256 + 能对上的一份记录；对不上判“不可归因”，不跑 |
| B 重训是否批准 | 用户 | 另行决定；c3 不自动进入，不申请 GPU |

## 7. 本轮之后的禁止项

- 即使留出到货、门 OPEN，只要 `check_round_ready.py` 仍报 BLOCKED，就不启动模型能力实验。
- 不擅自把“门 OPEN”写成“能力已验证”。
- 不用低于 0.8 的 bigram 分数当作留出独立性的证明。
