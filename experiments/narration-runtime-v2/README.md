# 叙事结果块 v2：数据、金标与 HPC 入口

日期：2026-11-10。分支 `goal/local-10-training`。本目录是 10-training 线的独立产物；来源
`experiments/world-components/narration-dataset-v1/**` 只读，未改一行。

## 1. 解决什么问题

旧转换 `yuyan/convert_yuyan.py` 的 `render_row` 已经拿到 `本回合状态`，但只渲染了
`render_state(before)` 和 `render_delta(delta)`，没有渲染 `render_state(after)`。因此 199 行
训练输入全部缺少结果块。旧 `place_line` 读取物品的 `位于`，而物品行实际用 `位置`，物品位置
也没有进入输入。这个目录做三件事：

1. 用同一批 199 行、同一批目标正文、同一份 `splits/v1.json` 重新生成 v2 输入；
2. 保留旧 serializer 的逐字节输出作为兼容对照，旧权重仍可复现旧路径；
3. 导出结构化 golden 向量和 Python 参考实现，供 01（浏览器输入适配）逐字节实现。

v2 的结果块仍然只是“本回合变化实体的变化字段结果”，不是完整 after 快照。没有出现的字段
表示这次结果没有携带它，不表示实体被删除或字段变成 0。

## 2. 版本与身份

| 项目 | 值 |
| --- | --- |
| `dataVersion` | `narration-rows-v2` |
| `projectionVersion` | `narration-result-view-v2` |
| `serializerVersion` | `yuyan-prose-result-v2` |
| 旧 `serializerVersion` | `yuyan-prose-legacy-v1` |
| 旧 `projectionVersion` | `narration-result-view-v1` |
| `modelTemplateVersion` | `yuyan-raw-completion-v1`（YuYan 臂；instruct 臂仍 pending） |
| `tokenizerHash` | `20287a9d1a2ec9d82b2a13f02c10c7b81e8bb015f114134bca6b06e5c8d376b4` |
| tokenizer | YuYan 字符表 `tokenizers/yuyan-v1/dict.txt`，13,668 条，无空格/制表/换行条目 |
| 行数 | 199 = train 139 / dev 40 / test 20 |
| 源数据 LF SHA-256 | `rows-xy.jsonl` `b7cc1c1b…`；`rows-yuyan.jsonl` `645df1b1…` |
| 源转换代码 LF SHA-256 | `convert_yuyan.py` `dd21a2c4…`；`rows_common.py` `cf87c6a7…`；`split_xy.py` `c1160ce7…` |
| split LF SHA-256 | `c6686b4b33196aeffb3875eda08e1e6d894febd9f94130301c12cd5bd262b836` |

完整哈希、比较账本和限制在 `data/manifest.json`。

## 3. 输入格式（实际字节）

标题顺序固定，段落之间没有换行，整段以 `【正文】` 结束：

```text
【视角】<视角，分号后限制语截断>
【地点】<地点句>…
【人物】<人物句>…
【物品】<物品句>…
【变化】时间推进<时间>。<变化句>…（或“这一回合没有结算出变化。”）
【本回合状态】<结果句>…（只在结果非空时出现）
【正文】
```

规则（与 `src/v2_render.py` 一一对应）：

- 地点按名字的 Unicode 码点升序；人物、物品同理。类型块顺序是 地点 → 人物 → 物品。
- 地点行：`名称（在<位于>里）：<外貌>。`；没有上级地点时省 `（在…里）`，外貌为空时省 `：…`。
- 人物行：`名称：在<位置>，精神值<整数>，外貌<列表>，个性<列表>，任务<任务串>。`；缺字段省对应片段。精神值 0 仍然写 `精神值0`。
- 物品行：`名称（位于<位置>）：<外貌>。`。这是 v2 对旧 `place_line` 的修复：物品读 `位置`，不读 `位于`。
- 列表项用 `、` 连接；每项去掉末尾 `。；，`；任务串先大任务、再小任务，每条 `目标（状态）`，用 `；` 连接。
- 变化句：`实体（类型）：移动到…，精神值变成…，去掉外貌…，多出外貌…，去掉个性…，多出个性…，完成…，新任务…。`；只写实际发生的操作。
- 结果句：`实体（类型）：字段短语，…。`；类型顺序同上，类型内按名字码点升序；字段顺序：
  - 人物：`位置`、`精神值`、`外貌`、`个性`、`任务`
  - 地点：`位于`、`外貌`
  - 物品：`位置`、`外貌`
- 空列表必须显式表达：`外貌（空）`、`个性（空）`；不能因为 `[]` 是假值就省略。
- 0 必须显式表达：`精神值0`。
- 结果字段值来自行的已结算 after 值（包括列表顺序）；缺失字段才从 `本回合变化` 补齐，并写入 `data/result-fills.jsonl`。199 行本身没有缺字段，所以该文件为空；物品移动、0 值、空列表等形状由 synthetic golden 覆盖。
- 名称、位置、状态等标识类字段拒绝空白；自由文本中的普通空格、制表符、全角空格会被删除并逐条记入 `data/normalization-ledger.jsonl`；CR/LF、NBSP 等其他空白直接拒绝。199 行只有 `时间推进` 里的普通空格，共 199 条记录。
- 未知实体、同名跨类型、未知变化字段、未知结果字段、结果与声明冲突、空视角等稳定报错，错误码见 `src/v2_render.py` 的 `NarrationSerializeError.code`。

## 4. 数据文件

| 文件 | 用途 |
| --- | --- |
| `data/rows-v2.jsonl` | 199 行：`id / x / y / xText / xProse / xProseLegacy / yMarked / 哈希 / 规范化账本 / 结果补齐账本 / 版本` |
| `data/rows-yuyan-v2.jsonl` | 给 YuYan trainer 的五行字段：`id / xProse / yMarked / y / 长度` |
| `data/normalization-ledger.jsonl` | 每个被删除的空白字符及路径 |
| `data/result-fills.jsonl` | 从 delta 补进结果的字段；199 行为空 |
| `data/manifest.json` | 源哈希、行集/目标/split 身份、文件哈希、版本、tokenizer、权重可得性、D 线登记、限制 |

`data/rows-v2.jsonl` 里的 `x` 是规范化并补齐结果后的四字段投影；`xProseLegacy` 是旧
serializer 的逐字节输出，和 `rows-yuyan.jsonl` 的 `xProse` 199/199 相同。

## 5. Golden 向量（01 的接线契约）

- `golden/vectors.jsonl`：49 条，20 条真实行 + 16 条 synthetic + 13 条负例。
- `golden/manifest.json`：版本、tokenizer、覆盖统计、文件哈希、使用说明。

每条成功向量包含：

```json
{
  "caseId": "synthetic-item-move",
  "projection": { "视角": "...", "上回合状态": {...}, "本回合变化": {...}, "本回合状态": {...} },
  "normalization": [...],
  "expected": {
    "status": "ok",
    "text": "【视角】…【正文】",
    "sha256": "...",
    "bytesUtf8Hex": "...",
    "segments": [{"kind": "result", "entity": "铜钥匙", "field": "位置", "charStart": 123, "charEnd": 128}],
    "resultFills": [...]
  }
}
```

失败向量包含 `expected.status = "error"`、`stage`（`normalize` / `build` / `serialize` / `tokenizer`）、`errorCode`、`errorPath`。
`charStart/charEnd` 是 Unicode 码点下标，不是 JS UTF-16 下标；`bytesUtf8Hex` 才是逐字节比较依据。

覆盖：物品位置、物品位置+外貌、精神值 0、人物/物品/地点空列表、大小任务层级、类型顺序、
非 BMP 名称排序（`阿 < ！ < 𠀀`，JS 默认 UTF-16 排序会不同）、无变化回合、普通空格/制表符/
全角空格删除、CR/LF/NBSP 拒绝、OOV 拒绝、未知实体、跨类型同名、未知字段、结果冲突、长输入。

01 的实现要求：

1. 读 `golden/vectors.jsonl`，按 `caseId` 逐条跑自己的 serializer；
2. 成功用例比较 UTF-8 字节（`bytesUtf8Hex`）和 `sha256`，再核对 `segments`；
3. 失败用例在相同 `stage` 返回相同 `errorCode`，不能退回部分文本；
4. 不要从 golden 里找目标正文——向量里没有 `y`；
5. 先实现 `阿 < ！ < 𠀀` 的码点排序，再处理普通中文名字。

## 6. 本地检查命令

```bash
cd experiments/narration-runtime-v2

# 重新生成数据（会先核对源哈希和旧字节）
python -X utf8 src/build_dataset.py

# CPU 小检查：行集/目标/split 不变、旧字节、结果块、物品位置、答案隔离、tokenizer
python -X utf8 src/check_dataset.py

# 重新生成 golden 并自检
python -X utf8 src/build_golden.py
python -X utf8 src/check_golden.py

# 训练前 CPU 预检（不会加载权重）
python -X utf8 train/preflight_v2.py --config configs/yuyan-lora-v2.json
```

## 7. HPC 入口

配置：`configs/yuyan-lora-v2.json`（已绑定实际 YuYan 基座、tokenizer、数据、split、seed）。
基座和 adapter 只在集群，仓库里只登记哈希：

| 资产 | 来源 | SHA-256 |
| --- | --- | --- |
| `checkpoint_best.pt` | `hpc:~/narr_rows/checkpoint_best.pt` | `674b897a969f7dbcc11cc7b660bba54c6800d894acab150323eadb1c0c456106` |
| 旧 LoRA adapter | `hpc:~/narr_rows/yu-split-6ep/lora_adapter.pt` | `e80c479e690c4128e8f8a4006417ea4f4df13a641b057fbcee3efa807de62c1d` |
| `dict.txt` | `hpc:~/narr_rows/dict.txt` | `20287a9d1a2ec9d82b2a13f02c10c7b81e8bb015f114134bca6b06e5c8d376b4` |

提交：

```bash
python -X utf8 train/hpc_client.py deploy
python -X utf8 train/hpc_client.py submit
python -X utf8 train/hpc_client.py poll <jobId>
python -X utf8 train/hpc_client.py fetch <jobId>
```

`train/train_yuyan_v2.py` 和 `train/train_hf_instruct.py` 都做：

- 固定基座/tokenizer/数据/split 身份并核对哈希；
- 固定 seed；
- `prompt = xProse`（YuYan）或 chat template（instruct），`target = yMarked`（YuYan）或 `y`（instruct）；
- `labels` 只在目标 token + EOS 上，prompt token 全部 `-100`；
- 训练前检查目标正文（含 40 字连续片段）不在输入里；
- 每 epoch 保存 `resume.pt`（adapter + optimizer + epoch + RNG + best），`--resume auto` 续跑；
- dev 选模型，test 只在最后评估一次；
- 报告记录实际数据/基座/tokenizer/config 哈希、train/dev/test id 哈希、长度、截断数、响应 mask、逐轮 loss 和生成样本。

YuYan 诊断臂与旧 `report-250409.json` 使用同一基座、同一 199 行、同一 split、同一 seed、
同一 LoRA rank/alpha、同一 lr 和 epoch 数；唯一有意的差异是 serializer（旧臂无结果块，新臂有）。
旧臂 `max_len=2048` 会静默截断 `row-0002`；v2 臂用 `max_len=2560` 装下全部 2382 token，
该差异记录在配置的 `comparison.maxLenNote` 里，不能把两臂当成完全同条件。

实际运行：

| 作业 | 状态 | 结果 |
| --- | --- | --- |
| 251205 | FAILED，1:18 | 训练前 `print()` 参数错误；无权重 |
| 251206 | COMPLETED，6:30 | best dev 1.4106 @ epoch 3；test 1.4241；train 1.0582 |

对照旧臂 dev 1.4096 / test 1.423，dev +0.0010、test +0.0011，基本不变。样本仍以
`stopReason=length` 结束、4-gram 最高重复 6–16，`row-0006` sampled 出现输入中不存在的
`程雪峰`。因此本目录只声明“数据/输入路径修复并完成受控诊断”，不声明模型质量改善或语义通过。
完整清单：`hpc/runs/251206/run-manifest.json`；失败记录：`hpc/runs/251205/README.md`。

instruct 入口的配置 `configs/hf-instruct.template.json` 仍是 `status=pending`：没有选定 instruct
基座/tokenizer，不能编造哈希，也不能声称已训练。填好身份并通过 preflight 后才能提交
`run_instruct.sh`。

## 8. D 线 4,750 行

`origin/codex/d-training-source-20261110` 提交 `51bd76e9…` 的 4,750 行是短语义监督
（train 3,204 / dev 693 / test 853），不是叙事结果块数据。本目录没有把它混入叙事训练，也没有
把它的 test 当独立终验；它仍可在单独质量检查后用于非叙事训练/开发。登记在 `data/manifest.json`
的 `dLine`。

## 9. 限制

- 199 行是 v1 的冻结场景行，不是独立终验集；目标正文是 v1 目标，没有人工复核元数据。
- 199 行没有真实的物品移动、精神值 0；这些形状只由 synthetic golden 覆盖，不能把它们当作训练行。
- 结果块是部分变化视图，不是完整 after 快照。
- YuYan tokenizer 已绑定；instruct tokenizer 仍 pending。
- HPC 实际运行记录见 `hpc/runs/` 和 `design/parallel-handoff/10-training.md`；未运行前不得写成模型质量已改善。
