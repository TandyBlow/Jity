# C 独立复审：N3 runner 148f412

日期：2026-10-29。审查者：C 工作树审查者。
对象：`148f412ebf9c920335d6f027347a75fb50dc4b55`，父提交 `ff6d40c27d1533bfe9c89a1ce0716563bab4ce8c`。

**结论：暂不通过，不能钉为 EXECUTABLE。** 发现 4 项 P1、4 项 P2。以下行号均针对本次提交的 `experiments/world-components/n2_selection/run_n3_arm.py`，属性问题另列。

全程只使用冻结输出罐头及合成对象。对真实后端控制流的探针通过内存中的假 `torch` / `transformers` 模块提供合成 tokenizer、权重加载器与输出；没有导入真实模型包、下载权重或执行真实模型推理。批准/钉值的变体仅写入审查临时目录，正式冻结记录未修改。

## 需要修复的发现

### R1 / P1：CLI 覆盖值绕过冻结 gold 钉值（283–285、547–548）

`args.expect_gold_sha256 or freeze["evaluation"]["gold"]["sha256"]` 使调用者提供的哈希成为替代权威。给冻结 gold JSONL 末尾追加一个换行，将它的新 SHA-256 传给该参数，runner 即 exit 0、8/8、`gate=true/pass=true`；归档仍引用正式冻结记录的哈希。未传覆盖值时同一替换文件会正确返回 2。

复现中的替换文件 SHA-256：`5f7ceb60c6db35cf1270a91e65e1caaf04d11bf5a6d87c9371efff73927a2690`；正式钉值仍为 `cb86aa46c4328cb971721d4ddce38bb4b0429fdc245e5405f193e0a6a99e9c63`。

修复：gate8 的权威值必须始终来自冻结记录。可移除此 CLI 覆盖能力；若保留参数，参数值还须等于记录钉值，然后再校验实际 gold。仅验证“文件等于调用者自报值”不满足已签认的接线。

### R2 / P1：`--items` 可缩小正式门的分母（276、294、334）

runner 不验证消费的 items 与已登记能力集的字节/条目集合一致。将 `d2_capability_items.jsonl` 仅保留第一行，经 `--items` 传入，仍使用完整冻结 gold 和对应罐头输出，得到 `items=1`、H1/H2 `1/1`、`gate=true/pass=true`。这把正式 8 项门改成了任意子集门。

修复：gate8 开跑前校验实际 items 字节等于预登记的能力集哈希，并核对条目唯一性、完整 ID 集合和 8 项分母；拒绝子集、重复 ID、内容漂移。diagnostic16 同样绑定其登记输入并保证 16 项口径，继续独立归档。

### R3 / P1：真实后端缺少 `dtype`，完成调用后归档必崩溃（172–175、354）

`TransformersBackend` 只设置 `self.dtype_name`，归档却读取 `backend.dtype`。用实际类配合合成 torch/transformers，模拟三门已满足并提供合成 `modelId` 后，8 次合成调用全部完成，随后抛出：

```text
AttributeError: 'TransformersBackend' object has no attribute 'dtype'
```

此时 `--out` 尚未写入，所有逐调用记录均仅在内存中。当前 pending 冻结记录可阻止进入该路径，但在未来批准并钉定后，这个错误会影响每一次正常完成的真实后端运行。

修复：统一后端的日志字段接口；用假模型包走过实际 `TransformersBackend.__init__`、`call` 和最终归档，验证完整输出，而不只验证 StubBackend。

### R4 / P1：CPU 臂仍被判为正式 gate（169–175、330–334）

`auto` 在无 CUDA 时选择 CPU，显式 `--device cpu` 也被接受；随后一律调用 `dm.evaluate(..., diagnostic=False)`，导致 CPU 臂 `gate=true`，并可 `verdict.pass=true`。dtype 中的“non-gate”说明不会改变判定。

本项独立探针仅在审查内存子类中补齐 R3 缺失的 `dtype`，其余实际后端及判定代码不变，合成复现得到 `device=cpu`、`dtype=float32 (non-gate arm, reported separately)`，同时 `gate=true/pass=true`。这是被 R3 暂时遮住的第二个问题。

修复：按冻结记录保证 CUDA bf16 是唯一正式门。CPU 可拒绝进入该门，也可按已登记规则单列为非门臂，但最终门结论必须显式为 false，不能把 CPU 的指标通过报告为 D2 门通过。

### R5 / P2：runner 未钉换行属性，新鲜 Windows 检出的自哈希改变

`experiments/world-components/n2_selection/.gitattributes` 没有 `run_n3_arm.py` 规则，`git check-attr text eol` 两项均为 `unspecified`。在新建且配置 `core.autocrlf=true` 的本地克隆中：

| 字节来源 | runner SHA-256 |
| --- | --- |
| HEAD blob / 实现者原工作区 | `f8c1b22d42679e7ae9db07c296589b614fae81d07858de3a15040175eb8a6d30` |
| 新克隆工作区 | `a7e06dfae78ccc723d927dc9c4f713bce2b9b51a9eab8607e134ff367dbfbb1e` |

若直接钉报告中的 blob 哈希，默认换行转换环境中的新检出会被 runner 自哈希门拒绝。

修复：对新 runner 增加与现有 D2 工具一致的 `text eol=lf` 属性，重新确认 blob、实现者工作区、`core.autocrlf=true` 新鲜检出三方哈希一致后再提交钉值。

### R6 / P2：未验证实际导入的指标工具等于 evaluation 钉值（38、268–289、334）

runner 直接导入并调用 `d2_metrics`，既不对其实际 `__file__` 校验哈希，也不在归档中记录实际指标工具哈希。对审查目录中的独立工具副本仅追加注释，保留原 runner 字节、原冻结记录、items、gold 和罐头输出，仍 exit 0、8/8、`pass=true`。

冻结钉值为 `a3a349b908edd92a126f34fc530f6ce25a62b5f15283bacf7a16733adc00131c`，消费的工具副本哈希却为 `f5f74febd4fb064cba4f4ca60634eb176e4257fec7c126944ea7d527b09e3fef`。runner 自哈希不能覆盖它导入的外部评分代码。

修复：验证实际导入的指标工具字节等于 `evaluation.metricTool.sha256`，失败时拒绝执行，并在归档记录实际工具哈希。继续保留已签认的指标工具原字节。

### R7 / P2：输出 itemId 错误被静默重写（105–117、325）

结构校验不检查模型输出的 `itemId`，接受后又直接写成当前 `iid`。把 8 个罐头输出中的 `itemId` 全部替换为 `WRONG-ITEM`，其余结构保持不变，runner 仍报告 8/8、无重试、`pass=true`。输出缺少 itemId 同样没有校验入口。

修复：在结构分类阶段要求输出 itemId 与本次条目相等，错误/缺失进入既有一次重试流程；不要通过归档时补写 ID 隐藏输出违规。

### R8 / P2：首个花括号扫描会把数组里的对象当作顶层计划（93–97）

对 `[<合法 gold 对象>]` 调用 `parse_plan`，它从数组内部第一个 `{` 开始解码，返回合法计划；结构校验也返回空问题列表。输入实际为顶层数组，该策略仍接受其内部对象，与“首个顶层 JSON 对象、无修补”的冻结契约不符。

修复：识别 JSON 层级，保证被消费对象处于顶层；保留约定允许的前后文字行为，但不通过跳进数组/其他 JSON 容器提取内部对象来修复不合规输出。补充数组包裹对象的拒绝及重试探针。

## 已通过的独立检查

- 提交仅新增 runner、两份桩归档并修改一处进度说明。签认文件、正式冻结记录、prompt、预登记修订记录、rubric、AI 标签与 gold 相对基线未变。
- 冻结 prompt 文件哈希通过；独立读取模板，以单次正则替换作参照，8 项装配逐字一致，重试后缀一致。
- `run_n3_arm.py --selftest` PASS；独立桩重放得到 8/8 正式指标自检通过、16/16 诊断集 `gate=false/pass=false`。
- 当前正式冻结记录下，真实后端请求 exit 3。分别只让 approval、runner.status、runner.sha256 中的一门不满足，也都 exit 3，后端构造次数为 0。
- 不覆盖钉值时，错 gold 正确 exit 2。
- 合成 parse/structural 首次失败后第二次恢复；最多两次尝试。timeout 与 length 截断在归档中可区分，终态 failureClasses 分别计数。

## 复现与交付

本地主工作区保留独立克隆 `.local/c-review-148f412/clone`，HEAD 为本报告完整提交，`core.autocrlf=true`。核心复现脚本：`.local/c-review-148f412/probe.py`，运行命令：

```powershell
python .local/c-review-148f412/probe.py
```

该脚本的断言验证上述现有行为，包括拒绝路径和缺陷复现；脚本完成不表示 runner 获准。记录见 `.local/c-review-148f412/evidence/results.json`；R6 独立副本探针记录见 `metric-drift-result.json`。这些是本地辅助材料，报告已完整记下输入构造、结果、提交与必要哈希。

请先修复上述发现，保持已签认 prompt、指标工具、rubric、AI 标签、gold 字节不变，重建桩归档后提交复审。新 runner 实现通过复审后，再由后续独立提交更新冻结记录的 runner 钉值和状态；真实推理继续等待老板批准解码配置。

此前 `signoff-d5ca042.md` 对 prompt / passLine / evaluation 记录的签认保持有效；本报告指出新 runner 尚未正确落实该冻结范围。
