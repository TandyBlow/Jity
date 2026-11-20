# 事实—陈述核对：第一轮二分类训练结果（2026-11-05）

**一句话结论：整体 confirm 三项门槛都过了，但这是 general 分布撑起来的窄通过；四个定向类别和 20 源回归没有过。这个职责还不能算成立，不接 source head、不接服务、不自动删句。**

---

## 1. 这轮只回答一个问题

> 专门训练的小模型，能否检出“当前授权中得不到支持”的陈述，同时少误拒合法表达？

答案是：**在 N5 派生的 general 分布上可以；在目标的 20 源表达分布和定向近似越权上不行。** 因此不能把整体 confirm 的“pass”当成职责已做成。

---

## 2. 训练设置

| 项 | 值 |
| --- | --- |
| 基座 | MiniRBT-H256（`assets/minirbt-h256-snapshot`，10.3M） |
| 头 | masked mean-pool + linear(2) |
| 类别 | supported / unsupported；uncertain 不训练 |
| 数据 | train 786、dev 214、confirm 124；另有 3 条 uncertain 边界、36 条 20 源回归 |
| epochs | 固定 12；每轮评 dev；每轮存 checkpoint；不早停 |
| batch / lr / optimizer | 32 / 3e-5 / AdamW |
| 长度 | max 256 检查；实际 p50 134、p90 153、max 183；`truncation=False`，超长报错 |
| 设备 | RTX 4060 Laptop，56.3 秒 |
| 复看 | 261 条 assistant 复看，不是独立人工金标 |
| source head | **未实现**；输出 `sourceStatus=not_implemented` |
| confirm | 只跑最终选中的 epoch/t_conf 一次 |

选择顺序按冻结文件写死：先满足 dev 三项主门槛，再按 `unsupportedRecall` 最大、`legalRejection` 最小、`legalPending` 最小、epoch 最早、`t_conf` 最低。dev 上有 424 个合格组合；最终选中 **epoch 12，t_conf=0.53**。

---

## 3. dev：选中的组合

| 指标 | 值 |
| --- | --- |
| unsupported recall | 106 / 107 = **0.9907** |
| legal rejection | 5 / 107 = **0.0467** |
| legal pending | 1 / 107 = **0.0093** |
| unsupported precision | **0.9550** |
| uncertain | 2 / 214 |
| confusion | sup→sup 101；sup→unsup 5；sup→uncertain 1；unsup→sup 0；unsup→unsup 106；unsup→uncertain 1 |

`t_conf=0.53` 只拒判 2 条；这轮不是靠大量拒判降低误拒。epoch 12 是最后一轮；dev 的 legal rejection 4.67% 已经贴着 5% 门槛。

---

## 4. confirm 整体：三项门槛都过

| 门槛 | 值 | 结果 |
| --- | --- | --- |
| unsupported recall ≥0.80 | 60 / 62 = **0.9677** | 过 |
| legal rejection ≤0.05 | 3 / 62 = **0.0484** | 过（只差 1 条就失败） |
| legal pending ≤0.15 | 0 / 62 = **0.0000** | 过 |
| unsupported precision | **0.9524** | 辅助 |
| uncertain | 0 / 124 | — |

confirm 124 条二分类＋1 条 uncertain 边界；边界不进二分类指标。整体 pass 是真的，但它只说明这 124 条的总账过线，不能说明四个定向类别也成立。

---

## 5. 分层：general 撑住了整体，定向类别没有

| 类别 | n（sup/unsup） | unsupported recall | legal rejection | 观察 |
| --- | --- | --- | --- | --- |
| general | 54 / 54 | 53 / 54 = **0.9815** | 0 / 54 = **0.0000** | 整体通过的主要来源 |
| body | 2 / 2 | 2 / 2 = 1.0 | **1 / 2 = 0.50** | 一个合法身体描写被误拒 |
| background | 2 / 2 | **1 / 2 = 0.50** | 0 / 2 = 0.0 | 一个“细雨里”被当成 supported |
| visible-state | 2 / 2 | 2 / 2 = 1.0 | 0 / 2 = 0.0 | 这 4 条全对 |
| extra-action | 2 / 2 | 2 / 2 = 1.0 | **2 / 2 = 1.00** | 两条合法动作都被误拒 |

定向每类只有 4 条，**不据此判断稳定泛化**；但这里没有出现“定向类别也安全”的证据。尤其是 extra-action 的 2 条合法描述全部被误拒，不能忽略。

### confirm 的 5 个错误（逐例）

| exampleId | 标签 | 预测 | p(unsup) | 说明 |
| --- | --- | --- | --- | --- |
| `n5:v2-c-salt:time-mid-9:v0:f1:auth:unsup` | unsupported | supported | 0.2567 | general 的漏检；候选“秦叔完成了任务…”在事实里被移除，但模型仍判 supported |
| `syn:background:stmt:confirm:unsup` | unsupported | supported | 0.4648 | 候选“细雨里”，场景只有“浓雾”；置信度 0.535，刚高于 t=0.53 |
| `syn:body:auth:6:sup` | supported | unsupported | 0.5606 | 候选“袖口湿透”，事实 F1 就是“袖口湿透”；合法被误拒 |
| `syn:extra-action:auth:6:sup` | supported | unsupported | 0.6004 | 候选“段禾把纸伞挂好”，事实 F1 就是“把纸伞挂好”；合法被误拒 |
| `syn:extra-action:stmt:confirm:sup` | supported | unsupported | 0.6454 | 候选“把木箱挂好”，事实 F1 就是“把木箱挂好”；合法被误拒 |

---

## 6. 20 源回归：单列，结果不好

36 条回归中 34 条二分类、2 条 uncertain：

| 指标 | 值 |
| --- | --- |
| 20 源/A1 supported | 22 / 24 正确；2 条合法被误拒 |
| 20 源/A1 unsupported | **0 / 10 检出**；0 recall |
| unsupported precision | 0 |
| 两个 supported 误拒 | `reg:double-d010:sup:appearance`、`reg:double-d011:sup:appearance` |
| 7 条 A1 `drop-unsourced` | **全部判 supported** |
| 2 条目标稿 visible-state unsupported | **全部判 supported**（`小雨落在天窗外`、`在铜灯下`） |
| 1 条目标稿 background unsupported | **判 supported**（`清晨的薄雾还没散`） |

回归不是训练集，也不参与 confirm 选择；它说明模型没有迁移到 20 源表达分布。20 源回归的 unsupported 只有 10 条，样本少，但方向是 **0/10**，不能当作“已经能处理目标分布”。

---

## 7. 3 条 uncertain 边界

三条全部判 supported：

- `syn:uncertain:train`：p(unsup)=0.2749
- `syn:uncertain:dev`：p(unsup)=0.3053
- `syn:uncertain:confirm`：p(unsup)=0.2862

t_conf=0.53 没有把它们拒判成 uncertain；它们只是边界案例，**本轮不声称模型具备不确定性识别能力**。

---

## 8. 复看与冻结

- 复看 261 条：confirm 125、train/dev 四类定向 56、train/dev general 40 对（80 条）。
- 实际复核者：同一助手，记录为 **“复看”**，不是独立人工金标。
- 1 条 residual overlap（顾北汀/陈九同路线、不同主体）判定不构成支持；没有新的标签修订。
- 此前修正的 3 个“同一事实还有另一条等价事实”的 N5 source group 已跳过；当前材料/指标/复看哈希已冻结。
- `review-v1-summary.json`、`review-v1.jsonl`、`review-v1.md` 保留范围与发现。

---

## 9. 这轮到底说明什么

1. **模型学到的是 general 的“事实被移除”模式。** general 54 条合法全对、54 条 unsupported 只漏 1 条；这说明它能处理这种形状。
2. **它没有迁移到目标的 20 源表达。** 7 条 A1 加料、2 条可见物状态、1 条“还没散”全部判 supported；0/10 unsupported recall。这是分布问题，不是单个阈值问题。
3. **定向近似越权没有成立。** body 合法误拒 1/2，extra-action 合法误拒 2/2；background 漏检 1/2。样本少，不能据此说稳定失败，但也没有“定向也安全”的证据。
4. **整体 confirm 过线不等于职责成立。** 整体 legal rejection 4.84% 只比门槛低 0.16 个百分点；general 的 0 误拒把它撑住了。
5. **不确定没有起作用。** t_conf=0.53、confirm 0 条 uncertain；3 条边界全判 supported。不能把“低置信度拒判”当成已完成的能力。
6. **source head 没有做。** 所有预测写 `sourceStatus=not_implemented`，没有返回空 `sourceIds` 冒充来源核对。

---

## 10. 决定

- **不接 source head，不接服务，不自动删句，不换 u240。**
- **不跑第二轮训练**，不逐轮补提示词，不因为整体 confirm 过了就把职责判成立。
- 20 源回归和定向类别作为下一轮任务定义/数据构造的输入；本轮到此为止。
- 如果继续，下一步应先解决“目标分布没有训练样本/定向近似越权太少”这个数据问题，而不是继续调同一个头。

---

## 11. 文件

| 文件 | 内容 |
| --- | --- |
| `artifacts/statement-verification/train-verify-binary-report.json` | 训练/选择/dev/confirm/回归总报告 |
| `artifacts/statement-verification/verify-binary-dev.json` | 12 epoch × 50 t_conf 的 dev 表与选中项 |
| `artifacts/statement-verification/verify-binary-confirm.jsonl` | confirm 逐例（124 条二分类） |
| `artifacts/statement-verification/verify-binary-confirm-summary.json` | confirm 指标、三项门槛、分层 |
| `artifacts/statement-verification/verify-binary-regression.jsonl` | 20 源回归逐例（36 条） |
| `artifacts/statement-verification/verify-binary-regression-summary.json` | 回归指标/分层/边界 |
| `artifacts/statement-verification/verify-binary-boundary.jsonl` | 3 条 uncertain 边界 |
| `artifacts/statement-verification/verify-binary-run-manifest.json` | 运行清单与文件哈希 |
| `experiments/world-components/n4_corpus_v2/ckpt-verify-binary/` | 12 个 epoch + `selected.pt` |
| `experiments/world-components/n4_corpus_v2/train_verify_binary.py` | 本轮训练/选择/评测脚本 |
