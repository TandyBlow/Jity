# C 审查签认：N3 runner 实现

日期：2026-10-29。审查者：C 工作树审查者。
签认对象：`f9c119087b895b27f410fd30c15afadb403d5b96`（`world-components`）。

**结论：runner 实现审查通过。** `review-148f412.md` 的 R1–R8 和 `review-cf22a65.md` 的 CF1–CF3 均关闭，本轮无未关闭的审查发现。可以按既定流程另做 runner 钉定提交，将下列已审查字节的 SHA-256 写入正式冻结记录，并更新 runner 状态；这不代替老板对解码配置的批准。

## 签认范围与字节

对象为 `experiments/world-components/n2_selection/run_n3_arm.py`：冻结 prompt 装配、首个顶层 JSON 对象解析、输出结构/itemId 校验、至多一次重试、失败分类、逐调用归档、gold/items/实际指标工具的字节绑定，以及真实推理的批准/状态/自哈希三道前置检查。

| 制品 | SHA-256 |
| --- | --- |
| 本次 runner | `7189e233d93c870e459696ca609e04e9f26d8730a52400231e12123ee8bac0a2` |
| 本次审查所用正式冻结记录 | `77b37b43989b52325aa2605878c6d967cd5260c5aa020196040f8230434fbfe1` |
| 本次预登记修订记录（含 diagnostic16Input） | `0afb78af21ce149841531b94076a980d7759435b2bda9aaab7df861c49186934` |
| prompt v2 | `a7697894d54f0afbf07ccd79b2e1a8db40a0e07f4a0156b221812ac088199bea` |
| 实际指标工具 | `a3a349b908edd92a126f34fc530f6ce25a62b5f15283bacf7a16733adc00131c` |
| 一致度工具 | `1c8c6233b542d422f234e6c320090afa7500c8bcc40fd9077d5e519394c5752d` |
| gate8 gold JSONL | `cb86aa46c4328cb971721d4ddce38bb4b0429fdc245e5405f193e0a6a99e9c63` |
| gold 冻结记录 JSON | `8026434e9c7f705ed3ba13ff5e339a69bf54b27cba79019747b3812e085d5f4a` |
| diagnostic16 输入（登记的 CRLF 工作区字节） | `c574d44ebc48a254942fff276cffd18d8607281b6e3617299c1cc0e35cc947fa` |

runner 的实现者工作区、提交 blob、配置 `core.autocrlf=true` 的独立新鲜克隆三方字节哈希一致；`text eol=lf` 属性已生效。prompt、指标工具、一致度工具、rubric、双 AI 标签、gold、正式冻结记录和原 `signoff-d5ca042.md` 的提交字节相对基线 `ff6d40c` 未变。原签认 Markdown 的字节依据为提交 blob；其普通 Markdown 检出换行不作为运行输入验证。

## 独立复验结果

在 `--no-hardlinks --no-checkout` 新克隆配置 `core.autocrlf=true` 后检出上述完整提交。后端测试注入内存假 torch/transformers；合成 tokenizer 可逆，decode 只解码实际收到的 token，generate 返回输入前缀加新增 token。批准状态、runner 钉值和 modelId 的测试变体只写入本地审查目录，正式记录未改动。

| 项 | 实测结果 |
| --- | --- |
| CF1：只解码新增 token | 实际 TransformersBackend 的 CUDA 合成路径 8 次调用、8/8 ok、pass=true；逐项 rawOutput 等于本项 gold JSON，不含输入前缀；outputTokens 等于新增 token 数 |
| CF2：真实后端 Deadline | 可控时钟从调用起点推进 2 秒、预算为正数 1 秒，实际 Deadline 返回 true；call.timed_out=true；端到端 8 项均归 timeout，逐调用 timedOut=true、pass=false |
| length 与 timeout 分开 | 合成返回 512 个新增 token，8 项均归 truncated，逐调用 finishReason=length、timedOut=false、pass=false |
| CF3/R4：CPU 非门 | CPU 合成路径完成归档；nonGateArm=true，report.gate=false、summary.gate=false、verdict.pass=false；CUDA 对照两个 gate 字段与通过结论均为 true |
| R1：gold 强制绑定 | 覆盖 CLI 已移除；冻结 gold 追加换行的副本 exit 2；正常归档使用冻结记录中的权威钉值 |
| R2：登记输入/分母 | gate8 子集和重复行均 exit 2；正式 8 项、登记的 16 项输入分别接受 |
| R3/R5：后端归档与字节 | CUDA/CPU 实际类的合成调用均完整归档，无 dtype 属性错误；新鲜检出自哈希与已审查字节一致 |
| R6：实际指标工具 | 正确实际工具哈希入归档；模块路径指向字节漂移副本时 exit 3 |
| R7：输出 itemId | 错误与缺失 ID 的首次输出均进入重试，第二次正确输出恢复；各场景 8 项共 16 次调用 |
| R8：数组包裹拒绝 | 每项两次数组包裹输出均拒绝；8 项共 16 次调用，failureClasses.parse=8 |
| 两种 scope | 正常桩 gate8 H1/H2 8/8、pass=true；diagnostic16 H1/H2 16/16，根 gate/summary gate 均 false、pass=false，独立归档 |
| 三道真实开跑门 | 当前正式记录 exit 3；分别仅使 approval、runner.status 或 runner.sha256 一门不满足时也均 exit 3；后端构造次数为 0 |
| 自检 | runner、指标工具、一致度工具的 --selftest 全部 PASS、exit 0 |

## 复现材料

主工作区保留 `.local/c-review-f9c1190/clone`，HEAD 为本签认完整提交，探针后克隆无工作区改动。独立探针沿用前轮的可逆 tokenizer 与可控时钟，改为验证修复后的正确行为；未复制实现者的假后端测试。

```powershell
python .local/c-review-f9c1190/probe.py
```

辅助证据：`.local/c-review-f9c1190/evidence/results.json`、`selftests.json`，以及同目录的 CUDA、CPU、timeout、truncated、8/16 项与拒绝场景归档。上述本地文件用于复核；本签认以指定提交、完整哈希表和正文中的实测结果为依据。

## 后续钉定与开跑条件

本轮正式冻结记录仍为 `runner.status=NOT-IMPLEMENTED`、`runner.sha256=null`，解码配置仍待老板批准。本签认满足“runner 已经审查”的条件，支持后续独立提交钉入本表 runner 哈希并将 runner.status 更新为 EXECUTABLE；钉定提交的记录差异仍应复核。

真实开跑继续按既定顺序满足解码配置批准和正式字节钉定，保留当前拒绝检查。runner 字节若再改变，本签认不自动覆盖新版本，须重新审查并钉定。

本轮没有真实模型推理，未证明模型质量或 D2 门通过，也未验收浏览器或生产接线。此前 prompt/passLine/evaluation 的签认继续有效。
