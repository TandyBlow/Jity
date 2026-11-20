# C 审查签认：D2 prompt、通过线与 evaluation 冻结

日期：2026-10-29。审查者：C 工作树审查者。
签认对象：`d5ca04211876cb1dda656aa3f255da81352a6be9`（`world-components`）。

结论：**本轮审查通过**。P1 字节复现问题及两条 P3 措辞问题关闭；新增的评分时 gold 哈希校验经独立正反探针验证。对下表所钉定冻结记录中的 **prompt、8 项能力集 passLine、evaluation 段**给予正式签认，替代其中 round-25 的条件性字节确认。

## 签认范围

- Prompt v2：模板、固定重试后缀、条目 ID 与 viewpoint/facts 装配规则，完整文件哈希见下表。prompt、rubric、双 AI 标签及 gold 在本笔提交中均未改动。
- 8 项能力集的门：H1/H2 全项通过、G1 F1 ≥ 0.80、G2 accuracy ≥ 0.80、pronounProduction ≥ 0.50、G3 ≥ 0.75；G4 仅报告。沿用记录中的 pooled 口径、失败即归档及本批不调参约束。
- H2 只判本句组内的实体锚定与登记名；G2 按 comparable groups 的位置配对计分，pronoun-site production 保留全部 gold sites 分母。
- evaluation 绑定下表指标工具及 AI gold。16 项按冻结记录中的 `diagnostic16` 单列，`gate=false`、`verdict.pass` 不为 true，不与 8 项合并分母。该降为诊断集的范围决策按修订记录归属于总指挥，本签认确认实现与记录相符。

## 独立复核

从本地仓库新建 `--no-hardlinks --no-checkout` 克隆，在克隆配置 `core.autocrlf=true` 后检出上述完整提交；不是复用实现者工作区运行。检出前后均核实 HEAD；测试结束时克隆无工作区改动。审查过程未运行模型推理。

| 复核项 | 实测结果 |
| --- | --- |
| 五条 `-text` 属性 | `git check-attr text` 对五份制品均返回 `unset` |
| 五份制品与 prompt/两工具 | 新克隆、HEAD blob、实现者工作区三方 SHA-256 一致，冻结与修订记录引用值一致 |
| gold 冻结重放 | exit 0；重建的 JSON 与 JSONL 均与归档逐字节相同 |
| `d2_metrics.py --selftest` | PASS，exit 0 |
| `d2_labels_agreement.py --selftest` | PASS，exit 0，含冻结入口替换/篡改拒绝探针 |
| 错钉 `--expect-gold-sha256 deadbeef` | 打印实际 gold 哈希与 expected 不符，exit 2，未评分 |
| 从冻结记录读取正确 gold 钉值 | exit 0；gold-vs-gold H1/H2 均 8/8，G1/G2/production/G3/G4 均 1.0，`verdict.pass=true` |
| 两处 P3 | rationale 统一为实测 321–386 token、1.3–1.6×；CPU float32 明确为单列非门臂，与 CUDA bf16 唯一门一致 |

关键复现命令（在新克隆根目录执行，输出目录预先建立）：

```powershell
python experiments/world-components/n2_selection/d2_metrics.py --selftest
python experiments/world-components/n2_selection/d2_labels_agreement.py --selftest
python experiments/world-components/n2_selection/d2_labels_agreement.py --labels-a experiments/world-components/n2_selection/annotation/labels-d2-ai-a.jsonl --labels-b experiments/world-components/n2_selection/annotation/labels-d2-ai-b.jsonl --out <审查输出目录>/n2-labels-d2-gold.json
python experiments/world-components/n2_selection/d2_metrics.py --gold artifacts/world-components/n2-labels-d2-gold.jsonl --plan artifacts/world-components/n2-labels-d2-gold.jsonl --expect-gold-sha256 deadbeef
python experiments/world-components/n2_selection/d2_metrics.py --gold artifacts/world-components/n2-labels-d2-gold.jsonl --plan artifacts/world-components/n2-labels-d2-gold.jsonl --expect-gold-sha256 cb86aa46c4328cb971721d4ddce38bb4b0429fdc245e5405f193e0a6a99e9c63
```

审查脚本及完整命令输出保留于主工作区 `.local/c-review-d5ca042/verify.py`、`.local/c-review-d5ca042/evidence/commands.json`；这些是本地辅助证据，签认的提交与字节依据为下表。

## SHA-256（完整文件字节）

| 文件 | SHA-256 |
| --- | --- |
| `artifacts/world-components/d2-n3-prompt-freeze.json` | `77b37b43989b52325aa2605878c6d967cd5260c5aa020196040f8230434fbfe1` |
| `artifacts/world-components/d2-preregistration-revision.json` | `ef977a5041efce47fa11707c0004c41532cd192f10ed0ebae37dd5845ab0ae0e` |
| `artifacts/world-components/d2-metrics-preregistration.json` | `95a945797c2fde6641e99e3f5749cfdeee87179ef7544f9d9d3229ec55d67c9a` |
| `artifacts/world-components/n2-labels-d2-gold.jsonl` | `cb86aa46c4328cb971721d4ddce38bb4b0429fdc245e5405f193e0a6a99e9c63` |
| `artifacts/world-components/n2-labels-d2-gold.json` | `8026434e9c7f705ed3ba13ff5e339a69bf54b27cba79019747b3812e085d5f4a` |
| `experiments/world-components/n2_selection/d2-n3-prompt-draft.md` | `a7697894d54f0afbf07ccd79b2e1a8db40a0e07f4a0156b221812ac088199bea` |
| `experiments/world-components/n2_selection/d2_metrics.py` | `a3a349b908edd92a126f34fc530f6ce25a62b5f15283bacf7a16733adc00131c` |
| `experiments/world-components/n2_selection/d2_labels_agreement.py` | `1c8c6233b542d422f234e6c320090afa7500c8bcc40fd9077d5e519394c5752d` |

## 开跑前仍须满足的已登记条件

冻结记录的 `decodingConfig.approval` 仍为 `PENDING-OWNER-APPROVAL`，`runner.status` 仍为 `NOT-IMPLEMENTED`、哈希为 null。解码配置获老板批准、runner 实现并审查且按记录钉定字节后，才具备开跑前提。

本笔新增的是可调用的 gold 校验能力；CLI 参数目前可选，尚未实现的 runner 仍须把“读取冻结记录 `evaluation.gold.sha256`、强制传给评分 CLI、校验失败即中止”写入契约并落实。该后续接线属于 runner 审查，不影响本轮能力与冻结范围的签认。

本签认不宣告 D2 完成、N3 模型臂通过、浏览器运行时通过或生产接线完成。gold 的性质仍为按归档协议产生的 AI gold。
