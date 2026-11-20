# C 独立复审：N3 runner cf22a65

日期：2026-10-29。审查者：C 工作树审查者。
对象：`cf22a6510ecdc5c43c335fa73f16e10066dd4462`。

**结论：暂不通过，不签认 runner，不翻 EXECUTABLE。** R1/R2/R3/R5/R6/R7/R8 通过复验；R4 的 CPU summary 通过问题已挡住，但保留一项 P2 字段矛盾。本笔修改真实后端时另引入一项 P1 和一项 P2，详见下文。

## CF1 / P1：解码整段生成序列，输入 prompt 混入输出（run_n3_arm.py:291）

原提交先对 `out[0]` 按输入 token 数切片，只解码新增部分。本笔改成 `tokenizer.decode(out[0], ...)`，对 decoder-only causal LM 会把输入前缀与新增 token 一起解码。Hugging Face 的 [Transformers 4.57.3 官方示例](https://huggingface.co/docs/transformers/v4.57.3/en/main_classes/text_generation#transformers.GenerationMixin.compute_transition_scores)同样按输入长度切出 decoder-only 模型的新增 token。

独立探针使用可逆的合成 tokenizer：tokenize 把文本分块，generate 返回“输入 token + 合法 gold JSON token”，decode 严格按收到的 token 解码，不读取外部 canned answer。对实际 `TransformersBackend` 跑完 8 项：

```text
items=8 ok=0 failed=8 classes={'parse': 8}
calls=16
rawOutputStartsWithPrompt=true
validGeneratedSuffix=true
firstOutcome=parse: invalid JSON: Expecting value: line 9 column 59 (char 365)
```

每次新增的回答均为合法且匹配本项的 gold JSON；失败来自输入 prompt 中 R6 的说明性花括号片段先被解析，而非模型输出错误。原始输出归档也因此不再代表模型新增回答。

修复：恢复只解码输入长度之后的 token，outputTokens 与该新增片段保持一致。测试同时断言 decoder 实际收到新增 token 切片、rawOutput 不含输入前缀、合法新增计划能通过。

现有 selftest 的 FakeTokenizer.decode（676–679 行）忽略 `ids`，直接从 last_prompt 选取 gold 返回，导致不论解码全序列还是切片都通过；须用尊重 token 输入的假 decoder 覆盖该差异。

## CF2 / P2：Deadline 触发后仍恒报非超时（278–294 行）

Deadline 仅返回时间判断，不保存是否实际触发；返回值的 `timed_out` 被写死为 False，短于 maxNewTokens 的停止统一报 `finish_reason=stop`。这回退了 148f412 中曾保留的超时触发标志。

独立探针以可控时钟驱动实际 Deadline：budget=1 秒、时钟推进到 2 秒，假 generate 调用 stopping criteria，确认其返回 True，然后停止并返回 1 个新增 token。实际 `call()` 结果：

```json
{"deadlineTriggered":true,"finish_reason":"stop","timed_out":false,"output_tokens":1,"wall":2.0}
```

因此 runner 的 timeout 分类分支在真实后端路径不可达；这类调用会被当作正常停止，再归 parse/structural，甚至在输出恰好完整时被接受。StubBackend 能记录 timeout 不覆盖本问题。

修复：保存 stopping criterion 实际触发原因并传回 call 日志，触发 Deadline 时必须归 timeout，继续与 maxNewTokens 的 length/truncated 分开。使用可控时钟验证实际后端，不通过真实等待或真实模型验证。

## CF3 / P2（R4 残留）：CPU 的 report.gate 与 summary.gate 相反（415–421 行）

本笔已将 CPU 的 `report.summary.gate` 与 `report.summary.verdict.pass` 强制为 false，但 `dm.evaluate()` 返回的根字段 `report.gate` 仍为 true。独立 CPU 合成运行的同一归档中：

```json
{"nonGateArm":true,"report.gate":true,"report.summary.gate":false,"report.summary.verdict.pass":false}
```

R4 原先的 CPU 正式通过问题已被 summary 修复；然而消费 `report.gate` 的下游仍会把该报告识别为门臂，无法保持记录中的“CPU 单列非门”一致性。

修复：在 runner 形成最终报告时统一更新所有门标记；CPU 的根字段、summary 字段与 verdict 应一致为非门/不通过。无需修改已签认指标工具。补充对 `report.gate` 的断言，保留 CUDA 正式门和 diagnostic16 非门的对照。

## R1–R8 复验

| 项 | 结论 | 独立结果 |
| --- | --- | --- |
| R1 gold 权威钉值 | 关闭 | 覆盖参数已移除；冻结 gold 追加换行的副本 exit 2；正式钉值始终来自冻结记录 |
| R2 输入与分母 | 关闭 | gate8 子集、重复行均 exit 2；登记的 8 项与 16 项分别通过；诊断输入字节等于新增登记哈希 |
| R3 dtype/归档 | 关闭 | 实际 TransformersBackend 的 CUDA/CPU 合成路径均生成完整归档，无 dtype 属性异常；新输出解码问题另列 CF1 |
| R4 CPU 非门 | 部分关闭 | summary gate/pass 均 false；根 report.gate 仍 true，见 CF3 |
| R5 换行属性 | 关闭 | runner text eol=lf；实现者工作区、HEAD blob、core.autocrlf=true 新克隆三方 SHA-256 一致 |
| R6 指标工具绑定 | 关闭 | 正确实际工具哈希归档；将实际模块路径指向字节漂移副本时 exit 3 |
| R7 输出 itemId | 关闭 | 缺失与错误 ID 首次均触发重试；第二次正确时恢复，8 项共 16 次调用 |
| R8 顶层数组 | 关闭 | 数组包裹计划被拒；8 项共 16 次调用，failureClasses.parse=8 |

另独立确认：

- runner、指标工具、一致度工具自检全部 PASS；runner 自检的真实适配模拟存在 CF1 所述覆盖盲点。
- 正常 StubBackend 重放：gate8 H1/H2 8/8、pass=true；diagnostic16 H1/H2 16/16，根 gate 与 summary gate 均 false、pass=false。
- 当前正式记录下真实后端请求 exit 3；逐个隔离 approval/status/sha 三门时也均 exit 3，后端构造次数为 0。
- prompt、指标工具、一致度工具、冻结记录、rubric、标签、gold 与原签认文件相对 ff6d40c 无改动。
- 预登记修订记录本笔仅新增 diagnostic16Input；移除该新增段后与 ff6d40c 的 JSON 内容完全相同。它是新版本记录，下表单独列其哈希；原签认仍指向当时版本。

## 复核字节与证据

| 制品 | SHA-256 |
| --- | --- |
| runner（三方一致） | `e21a84f2d499044d9929194b1a7452f830ec8931406bf3b5db5bf880968749ec` |
| 正式冻结记录（未变） | `77b37b43989b52325aa2605878c6d967cd5260c5aa020196040f8230434fbfe1` |
| 本笔预登记修订记录 | `0afb78af21ce149841531b94076a980d7759435b2bda9aaab7df861c49186934` |
| diagnostic16 工作区输入 | `c574d44ebc48a254942fff276cffd18d8607281b6e3617299c1cc0e35cc947fa` |

主工作区保留新鲜克隆 `.local/c-review-cf22a65/clone`，HEAD 为本报告完整提交，core.autocrlf=true，探针运行后工作区无改动。独立复现命令：

```powershell
python .local/c-review-cf22a65/probe.py
```

结果保存在 `.local/c-review-cf22a65/evidence/results.json`，整段输出污染与 CPU 归档分别为 `full-sequence.json`、`cpu.json`。本地脚本断言的是当前缺陷复现及已关闭项的实际行为，执行完成不表示 runner 获准。报告正文已记下必要构造和结果。

所有模型接口均由内存假模块实现，Deadline 由可控时钟触发；没有下载/加载真实权重，没有真实推理，没有修改正式批准状态或冻结钉值。

请只修复 CF1–CF3 并加入对应的有效反例，保留已签认制品字节后提交复审。通过后再独立钉定 runner；本轮不出 signoff。此前 prompt/passLine/evaluation 签认保持有效。
