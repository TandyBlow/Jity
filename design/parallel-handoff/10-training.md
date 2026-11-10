# 10-training handoff：结果块 v2、golden 与 HPC 入口

日期：2026-11-10。分支 `goal/local-10-training`。来源数据只读，未改
`experiments/world-components/narration-dataset-v1/**`。

## 1. 问题

旧 `yuyan/convert_yuyan.py` 的 `render_row` 没有渲染 `本回合状态`，199 行训练输入全部缺少
结果块；旧 `place_line` 读取物品的 `位于`，而物品行用 `位置`，物品位置没有进入输入。旧
serializer 的逐字节输出必须保留给旧权重；新格式另立版本。

## 2. 已交付

| 路径 | 内容 |
| --- | --- |
| `experiments/narration-runtime-v2/data/rows-v2.jsonl` | 199 行结构化投影 + v2 `xProse` + 旧 `xProseLegacy` + 目标 + 账本 |
| `experiments/narration-runtime-v2/data/rows-yuyan-v2.jsonl` | YuYan trainer 五行字段 |
| `experiments/narration-runtime-v2/data/manifest.json` | 源/行集/目标/split 身份、文件哈希、版本、tokenizer、权重可得性、限制 |
| `experiments/narration-runtime-v2/src/v2_render.py` | Python 参考 serializer + `build_result` + 稳定错误码 |
| `experiments/narration-runtime-v2/src/projection_v2.py` | 字段感知规范化（空格删除账本、标识拒绝） |
| `experiments/narration-runtime-v2/src/legacy_compat.py` | 导入冻结 v1 转换器并逐字节对照 |
| `experiments/narration-runtime-v2/src/check_legacy_rules.py` | 直接执行 `split_xy`/`rows_common`：x/xText 199/199、人物结果字段 386/386、物品位置旧缺口 |
| `experiments/narration-runtime-v2/golden/vectors.jsonl` | 49 条 golden（20 真实 + 16 synthetic + 13 负例） |
| `experiments/narration-runtime-v2/golden/manifest.json` | 覆盖统计、版本、tokenizer、使用说明 |
| `experiments/narration-runtime-v2/configs/yuyan-lora-v2.json` | 已绑定实际基座/tokenizer/数据/split/seed 的 YuYan 诊断臂 |
| `experiments/narration-runtime-v2/configs/hf-instruct.template.json` | instruct 入口模板；`status=pending`，未选基座 |
| `experiments/narration-runtime-v2/train/` | YuYan/Instruct trainer、preflight、sbatch、HPC client |
| `experiments/narration-runtime-v2/README.md` | 完整格式、命令、限制 |

## 3. 01 接线（最重要）

01 不需要读本目录的 Python 代码。直接读：

- `experiments/narration-runtime-v2/golden/vectors.jsonl`
- `experiments/narration-runtime-v2/golden/manifest.json`

每条成功向量有 `projection` 和 `expected.bytesUtf8Hex / sha256 / segments`。这里的
`projection` 是源 X 的四字段（`视角/上回合状态/本回合变化/本回合状态`），不是 01 运行时的
`beforeState/delta/resultState` 包装；01 要么直接调用 Python 参考，要么先做字段映射再比字节。
浏览器 serializer 必须比较 UTF-8 字节，失败用例在相同 `stage` 返回相同 `errorCode`。向量里没有
目标正文，不要从 golden 找 `y`。

实际句式摘要：

```text
【视角】…【地点】…【人物】…【物品】…【变化】时间推进…。…【本回合状态】…【正文】
```

- 物品状态行：`名称（位于<位置>）：<外貌>。`
- 结果块只在非空时出现；实体类型顺序 地点→人物→物品；类型内名字 Unicode 码点升序。
- 结果字段顺序：人物 `位置/精神值/外貌/个性/任务`；地点 `位于/外貌`；物品 `位置/外貌`。
- 0 写 `精神值0`；空列表写 `外貌（空）` / `个性（空）`。
- 普通空格/制表/全角空格删除并记账；CR/LF/NBSP 等拒绝；OOV 拒绝。
- 非 BMP 排序金标：`阿 < ！ < 𠀀`；JS 默认 UTF-16 排序会不同。

## 3.1 与 01 当前 result-v2 草稿的差异（必须先和解）

01 工作树已经有一份独立实现的 `result-samples-v1.json`（30 行），不是本目录
`golden/vectors.jsonl` 的副本。两边对同一 30 行的结果：

- 本目录 golden：`d699a69734127c4ea763c1ba53dca1f8c5669d955887c6830d97aa177a35b2fc`；
- 01 的 `result-samples-v1.json`：`c4a05f7270c90e497e353932f53653fd9e2d9dd395eeea2c4a8937bba206a5a1`；
- 逐字节相同 1/30（只有 `row-0008` 无变化行），其余 29 行不同；
- 两边 projection 版本也不同：本目录 `narration-result-view-v2`，01 的 meta 是
  `narration-projection-v1`。先对齐 projection，再谈 serializer 字节。

具体差异（按影响排序）：

1. **物品状态行**：`row-0002` 的 `报架放大镜` 在 before 里有 `位置=报刊架后`。本目录 v2 输出
   `报架放大镜（位于报刊架后）：…`；01 仍走旧 `placeLine`，只读 `位于`，输出
   `报架放大镜：…`，物品位置丢失。这是本线任务要求修的字段，01 当前草稿需要补。
   修法：给物品单独一个 `itemLine`，读 `entry.位置`，输出 `名称（位于<位置>）：…`；地点继续用
   `placeLine` 的 `（在<位于>里）`，不要把两者混成一个函数。
2. **任务结果句法**：01 用 `大任务《…》（…）`、`小任务《…》（…，属于《…》）`，显式保留父子；
   本目录 v2 用 `任务<目标>（<状态>）`，结构化投影里有父子，但拼出的文本没有“大/小/属于”标签。
   若要求结果块文本显式保留父子，应采纳 01 的标签；这属于结果句法变化，必须另立版本并重建。
3. **列表和字段分隔**：01 用 `外貌[...]`、`个性[...]`，字段之间用 `；`；本目录 v2 用
   `外貌...`、`个性...`，字段之间用 `，`。

在这些差异消除前，不能把两份 `yuyan-prose-result-v2` 当成同一格式，也不能拿本目录 golden 去断言
01 的 serializer 通过。主 agent 必须先选定一套句法，再让 01 和本目录各自重生/重算哈希；若要保留
01 的任务标签，本目录数据应升到新的 `serializerVersion`，不能继续叫同一个 v2。

## 4. 验证（本地 CPU；标注 HPC 登录节点的除外）

实际运行：

```bash
cd experiments/narration-runtime-v2
python -X utf8 src/build_dataset.py
python -X utf8 src/check_dataset.py
python -X utf8 src/check_legacy_rules.py
python -X utf8 src/build_golden.py
python -X utf8 src/check_golden.py
python -X utf8 train/preflight_v2.py --config configs/yuyan-lora-v2.json
```

最后一条 `preflight_v2.py --config configs/yuyan-lora-v2.json` 在 HPC 登录节点运行，
因为基座/tokenizer 在 `~/narr_rows`；它不占 GPU。其余命令本地 CPU 可跑。

结果：

- `rows-xy.jsonl`/`rows-yuyan.jsonl`/转换代码/split 的 LF SHA-256 与登记值一致；
- 旧 serializer 重渲染 199/199 与已存 `xProse` 逐字节相同；
- 行集、id、目标正文、`splits/v1.json` 身份不变；train 139 / dev 40 / test 20；
- v2 199/199 可重渲染且无空白/换行；198 行有结果块，`row-0008` 是无变化行；
- `split_xy.build_x/build_text` 199/199 与存储的 `x/xText` 相同；`rows_common.result_view` 人物字段 386/386 与 v2 结果相同；物品位置旧缺口被实际复现；
- 199 行答案隔离检查通过；199 行 tokenizer 可编码；
- 41 条物品状态行都含 `位于`；
- 49 条 golden 自检通过，覆盖统计见 `golden/manifest.json`；
- 本地 CPU 微型模型 smoke 验证 `resume.pt` 恢复：1 epoch 后 `--epochs 2 --resume auto` 从 epoch 2 继续并完成；
- 199 行中没有真实物品移动或精神值 0；这些由 synthetic golden 覆盖，不是训练行。

## 5. HPC 实际结果

YuYan 诊断臂已实际跑完。配置 `configs/yuyan-lora-v2.json`；基座
`~/narr_rows/checkpoint_best.pt`（`674b897a…`）；tokenizer `~/narr_rows/dict.txt`
（`20287a9d…`）；数据 `~/narr_v2/data/rows-yuyan-v2.jsonl`（`cb6764bf…`）；split
`c6686b4b…`；seed 20261109；LoRA rank 16 / alpha 32；lr 1e-4；6 epochs；maxLen 2560。

| 作业 | 状态 | 说明 |
| --- | --- | --- |
| 251205 | FAILED，1:18 | 训练前 `print()` 误收 `ensure_ascii` 参数；无权重；已修复 |
| 251206 | COMPLETED，6:30 | best dev 1.4106 @ epoch 3；test 1.4241；train 1.0582；峰值 11,089 MiB |

与旧臂 `report-250409.json`（dev 1.4096，test 1.423）相比，dev +0.0010、test +0.0011，
基本不变。旧臂 `max_len=2048` 会静默截断 `row-0002`；v2 用 2560 装下 2382 token，差异已登记。

样本观察：v2 greedy 字数普遍比旧臂长（如 row-0006 621 vs 418），但全部仍以
`stopReason=length`（600 token 上限）结束；4-gram 最高重复 6–16；`row-0006` sampled 输出出现
输入中不存在的 `程雪峰`。因此：

- 数据/输入路径修复已完成，受控诊断已跑完；
- **没有模型质量改善或语义通过的证据**，loss 也不是正文质量指标；
- 不把这次训练写成产品验收通过；正文质量仍需独立评估。

完整清单：`experiments/narration-runtime-v2/hpc/runs/251206/run-manifest.json`；
失败记录：`.../hpc/runs/251205/README.md`。代码提交 `a9d6606b` 包含实际部署的 trainer
（SHA-256 `cf84e1e6…`）。之后 trainer 增加了 token 溢出拒绝（tip `6aff0fc1`），只做了本地 CPU
smoke，未重跑 HPC；上表的 HPC 数值仍属于 `a9d6606b`。

## 6. 主 agent 需要做的接线

1. 若要使用结果块路线：让 01 按 golden 实现 serializer，再把页面/`game-model` 的输入投影接到
   `【视角】…【本回合状态】…【正文】`；不要把旧 `xProse` 和新格式混喂同一权重。
2. 若继续使用现有自然语言 instruct prompt（主树 `rows-instruct.jsonl` 路线）：不要把本目录的
   `xProse` 当作那个 prompt；两条路线各自登记 `projectionVersion/serializerVersion/modelTemplateVersion/tokenizerHash`。
3. 需要 instruct HPC 时：填 `configs/hf-instruct.template.json` 的 base/tokenizer 身份和哈希，
   去掉 `status=pending`，跑 preflight，再 `CONFIG=... sbatch run_instruct.sh`。不要编造哈希。

## 7. 限制

- 199 行是 v1 冻结行，不是独立终验；无人工复核元数据。
- 结果块是部分变化视图，不是完整 after 快照。
- 真实 199 行没有物品移动/精神值 0；synthetic golden 只证明格式与拒绝路径，不是人工语义金标。
- golden 文本由参考 serializer 生成并自检；真实行有旧字节核验，但不等于独立读评。
- instruct 基座/tokenizer 未选，不能声称 instruct 臂已训练。
- D 线 4,750 行是短语义监督，未混入叙事训练，也不能作独立终验。

## 8. B 组路线：短拍监督 + 可部署权重（2026-11-10 质量任务）

阶段一的 199 行长正文数据、v2 输入、golden 与 HPC 入口继续有效。质量任务里 10 线只做一件事：
让浏览器里跑起来的权重写出“守住事实、像正文”的句子；不替 02 判定通过。

### 8.1 为什么改成按“拍”写

用产品自己的检查口径（`src/narration_rules.py` 逐行复刻）扫了 199 条人工 `y`：**0/199** 能同时
覆盖本回合所有强制事实。人工正文是文学写法，时间用“十年后”“没过多久”这类说法，任务完成写成
“找到了”，个性和精神值根本不提数字。把 199 条长文当唯一监督，模型学到的是氛围段落，不是
“这一回合结算了什么”。

所以拆成两种监督：

- **拍（beat）**：一条结算事实 = 一次模型调用，1–2 句，主语必须是这条事实的主体。程序把各拍
  按顺序拼成一回合正文。事实由 Python 结算，模型只负责语言。
- **整场（scene）**：199 条人工长文，只用来教句子的密度和节奏，不作为事实覆盖的验收单位。

### 8.2 数据文件（都可复算）

| 文件 | 内容 | SHA-256 |
| --- | --- | --- |
| `data/beats-v1.jsonl` | 368 拍：199 行拆出的移动 44 / 完成任务 133 / 个性 90 / 精神 94 / 纯时间 7；含库世界与产品世界（龙族）两套场景 | 见 `src/build_beats.py` 运行输出 |
| `data/rows-short-v1.jsonl` | 01 的 21 条手写短场景，结构化输入用 v2 参考序列化器重排，逐字节等于冻结行的 `xProse` | 语料 `32234af4…` |
| `data/train-v2.jsonl` | 训练混合：199 条长场景 ×1 + 21 条手写短场景 ×6；`mode` 区分 `scene`/`short` | `b7d36b73…` |
| `hpc/beats-all.jsonl` | 交给 HPC 7B 老师写的拍集合（不含纯时间拍） | 由 `beats-v1.jsonl` 过滤 |

拍提示词的形状（老师、训练、推理三处必须一字不差）：

```text
【本拍事实】<结算出来的一句话>
【主体】<主语>：这一段的动作属于<主语>，不要换成别人。
【场景】<视角人物>在<地点>　<地点行>…
【在场】<其他人>（只作为在场的人，不写他们的动作和对白）
【示例】事实：<示例事实>。正文：<示例正文>
【写法】一到两句。<按事实类型不同的写法要求>
【正文】
```

早期版本把【场景】放最前、不点名主体，老师写出来的句子主语经常变成视角人物（事实是沈含章
移动，正文写周叙白）。现在的顺序和【主体】行就是针对这个失败改的。

### 8.3 老师数据与筛选

HPC 7B（`~/qwen7b`，Qwen2.5-7B-Instruct）按上面的提示词，每拍采样 2–3 条。`src/check_beats.py`
逐条检查，只有通过的句子才进训练：

- 移动：主体在句子里，起点和终点都出现，有移动动词，方向不能反；
- 完成任务：主体在，有完成动词，任务目标的特征词至少命中两个；
- 个性：主体在，新个性的特征词命中两个；
- 精神：主体在，方向词或变化后的数字出现；
- 通用：不超过 120 字、单段、没有别的角色做出动作。

检查不通过的原句写进 `grade.json` 的 `rejectedExamples`，不静默丢弃。

### 8.4 训练与导出

`train/train_beats.py` 只对 assistant 段算 loss，system 固定一句，用户段是上面的拍提示词或
`train-v2.jsonl` 里的整场输入。超过 `maxLen` 直接报错，不静默截断；目标整段出现在提示词里
也直接报错。HPC 入口：

```bash
python hpc/beats_job.py submit-train --config qwen05b-mix-v1.json --run qwen05b-mix-v1
python hpc/beats_job.py fetch-train <jobId> --run qwen05b-mix-v1
```

本地导出（合并 LoRA → f16 GGUF → Q4_K_M）：

```bash
python hpc/export_candidate.py --adapter <adapter-best.pt>   --base D:/others/Jity/.local/qwen-train/model   --out D:/others/Jity/.local/models-narration/<run> --quant Q4_K_M
```

权重不进 Git。候选登记在 `results/quality/candidates-10.json`，路径、SHA-256、输入样例、
完整模板、分词器哈希都在里面；训练状态与数据缺口在 `results/quality/training.json`。

### 8.5 已登记候选与已知失败

- `qwen05b-scene-v1`（HPC 251222，3 epoch）：只在 199 条长场景上训练，本地探针能写出通顺段落，
  但会编对白和新事实（`row-0017` 编出“总工程师”对话）。状态 `ready_for_browser`，
  `qualityStatus=not_met`。它是可加载基线，不是质量候选。
- `qwen05b-mix-v1`（HPC 251232，3 epoch，199 长场景 + 21 手写短场景×6）：短模式输出已经接近
  “两句 + 时间”，但仍会凭空写出“手机”“手电”等物；长场景模式照样编对白。
- 拍数据（8.3）正在生成、筛选；通过筛选的句子会与 21 条手写短场景一起训练下一版。

### 8.6 02 接线（拍路线）

1. 拍提示词直接用 8.2 的原文，不要再自己拼一版；`candidates-10.json` 里的 `template` 字段是唯一
   权威。
2. 每拍单独调用模型，`maxTokens` 60–96，`temperature 0.5–0.7`，句子出来先过事实检查，再按
   拍顺序拼接；不要把多拍塞进一次调用。
3. 模型输出为空、超长或主语不对时，按 02 既有策略记账并回退；不要用模板句冒充模型输出。
4. 真实浏览器文本由 09 跑、用户看。10 线只登记权重和模板，不签质量结论。

### 8.7 限制

- 拍数据的老师是 7B 模型，句子是机器写的，不是人工金标；通过筛选只说明它守住了这一条事实。
- 21 条短场景来自 train 行，是开发材料，不是独立终验集。
- 05 的整场语料（`corpus-scenes`）目前**没有并入训练**：它的“本回合变化”把 `解除个性` 写成
  字符串，和 v2 内核的数组形状不一致，硬接等于训练产品页面不会产生的输入。等 05 的行能过
  内核序列化器再接。
- 0.5B 在长场景上的 loss 与正文质量没有对应关系；目前唯一的质量证据是真实浏览器文本。

