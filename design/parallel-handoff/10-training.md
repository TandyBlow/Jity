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

### 8.4.1 产品世界的 78 条手工短目标

199 行冻结数据是“图书馆世界”，老师数据也常写成套话；而页面实际叙述的是《龙族·自由一日》
世界，此前**一条人工短目标都没有**。`src/build_world_targets.py` 为该世界的 78 个拍逐条写了
20–70 字的目标（移动 15 / 任务 28 / 个性 14 / 精神 14 / 纯时间 7），`authoredBy="lane-10"`，
用同一套逐拍检查跑过，0 条失败。目标文件：`data/world-targets-v1.jsonl` SHA-256
`837f60b1…`。它们是我写的监督，不是 01/05 的手写正文。

### 8.5 已登记候选与已知失败

- `qwen05b-scene-v1`（HPC 251222，3 epoch）：只在 199 条长场景上训练，本地探针能写出通顺段落，
  但会编对白和新事实（`row-0017` 编出“总工程师”对话）。状态 `ready_for_browser`，
  `qualityStatus=not_met`。它是可加载基线，不是质量候选。
- `qwen05b-mix-v1`（HPC 251232，3 epoch，199 长场景 + 21 手写短场景×6）：短模式输出已经接近
  “两句 + 时间”，但仍会凭空写出“手机”“手电”等物；长场景模式照样编对白。
- 拍数据（8.3）已生成并筛选；通过筛选的 98 条与 21 条手写短场景一起训练了
  `qwen15b-beat-v2`（HPC 251254）。本地 20 个 dev 拍探针在 temp 0.4 下 10/20 通过严格事实
  检查，任务拍常只写动作、不写任务本身；仍是失败，不是达标。
- `qwen15b-beat-v3`（HPC 251274）加入 8.4.1 的 78 条产品世界目标，正在排队。

### 8.6 02 接线（拍路线）

1. 拍提示词直接用 8.2 的原文，不要再自己拼一版；`candidates-10.json` 里的 `template` 字段是唯一
   权威。
2. 每拍单独调用模型，`maxTokens` 60–96，`temperature 0.5–0.7`，句子出来先过事实检查，再按
   拍顺序拼接；不要把多拍塞进一次调用。
3. 模型输出为空、超长或主语不对时，按 02 既有策略记账并回退；不要用模板句冒充模型输出。
4. 真实浏览器文本由 09 跑、用户看。10 线只登记权重和模板，不签质量结论。

#### 8.6.1 真实浏览器首跑（2026-11-10 17:25，09 共用执行器）

命令（10 线自己调用 09 的入口，结果只写到自己目录，不碰 `results/quality/browser-09.json`）：

```bash
node scripts/quality-candidates/run-browser-candidates.mjs   --candidate 10-beat=<lane10>/browser/candidate.ts   --candidate-model 10-beat=/models/model-Q4_K_M.gguf   --model-dir <qwen15b-beat-v2 导出目录> --set free-day --only free-day-move   --threads 8 --hard-timeout-ms 900000
```

实际正文（Edge + wllama CPU，载入 29.9 s，整轮 269.8 s，96 字，`accepted=false`）：

```text
路明非紧握着林亦舟放下的演习枪，从西侧服务巷走向西回廊。每一步都显得格外谨慎，空气中弥漫着紧张的气息。

诺诺踩着吱吱作响的石板街，从西侧服务巷走向西回廊。

1分钟过去，屋子里没有别的声音。
```

读法：三条拍里前两条移动的主语和起终点都对（路明非、诺诺，服务巷→西回廊），但都带了“空气
里弥漫着紧张”这类空话；第三条是模板回退——模型其实写了“一分钟过去”，检查器只认阿拉伯数字
把她判错了。检查器已改成同时认“一/两/三…”，并在时间拍的检查里不再要求出现视角人名。第三段
回退句原来写“屋子里”，现在按场景地点写。

这不是合格正文，只是一次真实调用与真实失败；没有写进 09 的共享文件。

## 8.7 限制

- 拍数据的老师是 7B 模型，句子是机器写的，不是人工金标；通过筛选只说明它守住了这一条事实。
- 21 条短场景来自 train 行，是开发材料，不是独立终验集。
- 05 的整场语料（`corpus-scenes`）目前**没有并入训练**：它的“本回合变化”把 `解除个性` 写成
  字符串，和 v2 内核的数组形状不一致，硬接等于训练产品页面不会产生的输入。等 05 的行能过
  内核序列化器再接。
- 0.5B 在长场景上的 loss 与正文质量没有对应关系；目前唯一的质量证据是真实浏览器文本。


## 9. 页面草稿臂：按 06 自己那条提示词训练（2026-11-10 晚）

06 的树里已经有两步确定性文本：`game-model.ts` 的 `factualNarration` 把已结算事实写成
“草稿段”，`prompt.ts` 的 `instructNarrationInput(..., draft)` 再把草稿变成给模型的指令。
这两步都在页面里，不在我这边；我原来自己造的 `【事实草稿】…【正文】` 模板和它对不上，
按那个模板训练等于训练一个页面不会发出的输入。

现在的做法：

| 项 | 内容 |
| --- | --- |
| `src/build_page_pairs.py` | 把上面两段 TS 的字符串与拼装顺序逐字搬到 Python；页面模板一变，必须重新生成数据，不能在推理时临时改提示词 |
| `data/train-page-v1.jsonl` | 71 条人工短行（01 的 20 条龙族世界行 + 51 条图书馆行），每条 = 页面式提示词 + 人工正文；sha256 `6df3a8c7…` |
| `data/splits-page-v1.json` | 199 行冻结 split 不动；01 的 71 行按 `worldFamily#lineage` 整组划分，同一来源的所有变体只在同一侧；组清单连同哈希一起存 |
| `configs/qwen15b-page-v1.json` | 1.5B + LoRA r16/a32，3 epoch，lr 1.5e-4，maxLen 1280 |
| HPC `251495` | CPU 分区 16 核，输出目录 `~/beats_v1/runs/qwen15b-page-v1`，独占写入 |
| `browser/draft-candidate.ts` | 与训练同一条提示词；页面把草稿传进来就用页面的，页面没传才用本文件的降级拼法；输出先过草稿事实覆盖/凭空数字/空话/新增对白检查，未通过才回退草稿 |
| `src/eval_draft.py` | 离线筛查导出后的 GGUF；已用 71 条人工正文校准：71/71 全过，说明它不会把人工写法判死 |
| `hpc/batch_screen.py` | 给 11/12 的批量服务：一个 GGUF、一份冻结 case 文件、N 个 seed，输出原始正文 + 时间 + 便宜的事实检查；不做质量判定 |
| `hpc/gpu_probe.py` | 在真实 V100 上量 fp16 推理是否可跑、单实例 tokens/s；训练 bf16 的限制不能直接推到推理 |

两条要说清的落差：

1. 页面要求 160–240 字，01 的人工正文只有 61–158 字（中位 97）。用这批数据训出来的模型会
   写得更短。这是数据事实，先报给 06，不靠改提示词掩盖。
2. 199 行冻结场景没有进这一臂：它们的正文有对白、也没逐条覆盖草稿事实，混进来会教模型
   “不用管草稿”。它们仍留在场景臂和冻结 split 里。

## 9.1 设备实测与训练精度

- `hpc/gpu_probe.py` 在真实分配到的卡上量：卡型号/显存/驱动、`torch.cuda.is_bf16_supported()`、
  fp16 前向是否可用、单实例 tokens/s、显存占用。训练用 bf16 的限制**不能**直接推到推理上：
  V100（sm_70）没有 bf16 张量核，但 fp16 有；所以推理与训练都要各自实测，不能靠名字推断。
- `train/train_beats.py` 新增 `--precision auto|bf16|fp16|fp32`。fp16 时 LoRA 主权重留 fp32，
  前后向走 autocast + GradScaler，报里记 `precision/ampEnabled/device`。这样 V100 也能训练，
  不必把 1.5B 塞进 CPU 队列几小时。
- 251505 第一次探测卡在 `from_pretrained`：没传 `local_files_only=True`，分词器去连外网，集群
  无外网就干等约 5 分钟。已取消重提 251507（带 `local_files_only=True`）。训练脚本早就带了这个
  参数，所以训练作业没有这个毛病。
- `hpc/finalize_run.py`：一条命令走完 取报告+适配器 → 合并 → Q4_K_M → dev 筛查 → 生成候选记录
  （含哈希与“loss 不等于正文质量”的说明）。

## 9.2 HPC 台账与轮询纪律

`results/product/hpc-queue.json` 是唯一台账：作业用途/状态/分区/输出目录/数据哈希/取消原因，
GPU 与吞吐取不到就写 unknown。远程 `sleep` 属于同步等待、会堵住 agent 窗口，已停用；轮询改成
每 ~15 分钟一次短 `squeue`/`tail`，`nextPollAt` 写在台账里，中间做代码/数据/导出/评审工作。

## 9.3 页面臂第一次真实对比（基础模型 vs 微调，同一批 dev 输入）

作业 251513（LoRA 适配器）与 251514（同基座、不挂适配器），模型 Qwen2.5-1.5B-Instruct，
V100 fp16，同一 5 条 dev 输入、同一提示词（页面自己的 `instructNarrationInput`）、温度 0.5、
种子 20261110。原文在 `hpc/runs/qwen15b-page-v1-gpu/probe-dev{,-base}.json`。

| 输入草稿 | 基座（未微调） | 微调 v1（r16、3 epoch） |
| --- | --- | --- |
| 时间 10 分钟 + 顾望舒办完查后门锁 | 写“站在昏暗的屋内…阳光透过窗户”，整段与草稿无关 | 时间与任务都在；但补出“查岗簿、九月撬门锁、十月空格”等草稿没有的细节，且把顾望舒写成“他” |
| 时间 27 分钟 + 秦既明办完查火灾 | 写“暗器、闪电、拔出长刀” | 时间与任务都在；补出“叶浅心里一惊”，同样没有依据 |
| 只有时间 8 分钟 | 写“古塔顶端、破旧斗篷、云层透光” | 保住时间；整段场景是自己加的（岗亭、值班表、顾既明） |
| 只有时间 19 分钟 | 写“山脚下…长剑…远方” | 只写袖口黑印，事实干净，但完全没有草稿以外的信息 |
| 场景草稿（报刊库返潮） | 复述环境后加“抽屉被人翻动、旧杂志裂痕、墙上画” | **开头整段是另一条训练行（short-0098）的句子**，随后又加了“黄黑绳断了、对面没有房子” |

读法：

1. 基座确实在跑题——这正是 06 说的“自由场景下编对白/编动作”。微调把它拉回“守住时间+任务”，
   这是真实收益。
2. v1 仍然在同域内编细节（查岗簿、叶浅、岗亭），并且出现**跨行记忆**：把 short-0098 的开头
   原样搬到 short-0161。devLoss 从 4.09 涨到 4.14 而训练 loss 掉到 0.017，正是记住 52 条提示的
   症状，不是学会了改写。
3. v1 正文长度 62–125 字，页面要求 160–240 字。原因是监督语料本身只有 61–158 字（中位 97）。

## 9.4 因此改了什么

- 新增 `data/train-page-v2.jsonl`：01 的 71 行 + 05 的 11 条 250–280 字连续场景（05 是同一
  序列，全部留在 train，不给 dev）。82 行。
- `configs/qwen15b-page-v2.json`：LoRA r8/alpha16、dropout 0.1、weightDecay 0.01、**1 epoch**，
  减少记住提示的机会。作业 251515。
- 草稿端口修了两处保真问题：场景外貌要从静态世界（`上回合状态` 的地点/人物 `外貌`）取，
  不是从只记变化的 `本回合状态` 取；只有人物才写“没有出声”，物品不写。

## 9.5 更正：页面那段“时间过去/走到走廊/外貌”不是模型写的

上一节把 09 页面显示的一段正文当成模型输出并据此推断模型在照抄状态——**这个判断撤回**。
代码证据：`worktrees/06-recovery/frontend/src/lib/world-engine/local/game-model.ts` 里
`factualNarration`（当前树 633 行起）依次生成“时间过去了约 N 分钟。”（638）、“X……最后停在 B。”
（643–648）、“<地点>里，<地点外貌>。”（667–671）、在场人物外貌句（673–679，走
`visibleCharacters`）。全是程序拼接，不调用模型。用户引用的 588/598/623 是另一提交快照里的
同一批语句。

那次真实运行的真实归属（`hpc/browser-10.json` run 2）：两拍移动是模型原文并被采用；第三拍
“1分钟过去，屋子里没有别的声音。”是**程序模板回退**，因为三次模型尝试都因 `amount_missing`
被拒（当时检查器只认阿拉伯数字）。三次被拒的模型原句都留在 `attempts` 里。

因此：

- 训练目标只取人工正文（01 的 71 行、05 的 11 条）；程序草稿只出现在提示词一侧，程序回退
  文本不进训练集、也不算“质量好转”的证据。
- 三类文本从此分开记：`programDraft` / `modelRawAttempts` / `acceptedModelText`，程序回退
  单独标出。`results/quality/candidates-10.json` 已按这个结构改写。
- 说明文档：`results/product/evidence/10-narration-provenance.md`。
- 还没证明的：模型在自由提示下会不会照抄状态（目前只有那一次运行的 5 条尝试）；草稿式提示词
  是不是失败主因（仍是假设，09 正在同一冻结输入上做三来源对比）。

## 10. 充值恢复后的第一批真实测量（2026-11-10T15:24Z）

按 `RESTART-AFTER-REVIEW.md`（sha256 `20238282a0069cf34f40e49d8ab1691e2fc35de47faf99a0762a68ff30d016ce`）核对：
我这边所有训练/探针作业都已完成（251511/251513/251514/251515/251516/251547/251553 全部 COMPLETED，
无排队），没有重投同一配置。两次作业的浪费如实记了：251570 FAILED（model_server.py 没进部署清单，
1 秒），251571 TIMEOUT（服务起来了但 50 分钟无人连接，因为客户端还没建）。

### 10.1 四个正文臂在同一批 dev 输入上的完整文本对比

同一份页面提示词、同一 5 条 dev 行、temperature 0.5、seed 20261110、V100 fp16：

| 臂 | 总字数 | 漏草稿条款 | 编造数字 | 新增对白 | 与其它训练行 12 字重合 |
|---|---|---|---|---|---|
| 未训练基座 | 1428 | 7 | 2 | 1 | 0/5 |
| v1 r16 3ep 71 行 | 495 | 0 | 0 | 0 | 4/5 |
| v2 r8 1ep 82 行 | 458 | 3 | 4 | 0 | 2/5 |
| v3 草稿钳制 2ep | 379 | 4 | 0 | 0 | 2/5 |

三个训练臂都用“编造”换了“漏条款 + 变短 + 背训练句”，没有一臂同时过关；v3 的零编造数字
是把草稿给不出的数字句从 target 删掉换来的。结论：这个数据量上加 epoch 只会加重记忆。
明细与复算方式见 `results/product/evidence/10-training-quality-route.md` §1。

### 10.2 可加载候选（质量未通过）

`qwen15b-page-v3`：`D:/others/Jity/.local/models-narration/qwen15b-page-v3/model-Q4_K_M.gguf`，
986,048,064 B，sha256 `a03bcfeaa4837d6754257a5f6e71cd24ac3ebce4bb26ee92fc2280d096c5632f`，
提示词与页面 golden 逐字节一致，GGUF 自带 Qwen 对话模板（必须用对话接口调用，不能用裸补全，
否则模型会续写提示词）。已写进 `results/quality/candidates-10.json`。
离线筛查 6 条 dev：2 条干净、3 条漏时间/任务、1 条新增对白；**没有跑过真实页面**。
06 若要试，需要在 `page.tsx` 的 `NARRATION_MODELS` 里加一个变体并在 `public/models/` 放这份文件
（986 MB，我没有写 06 的树）；09 跑的时候把 `__worldArm` 里的文件与哈希一起记下来。

### 10.3 给 06 的定位：程序兜底被当成小说段落显示

`results/product/evidence/09-product-10turn.json` 第 1 回合四次模型调用全失败，页面正文是
程序兜底，其中 `路明非：本组结算未能确认新的结果。` 的来源：
`semantics/settlement/results.ts:147` 在模型失败时把这句话当成**每个成员的结果值**返回，
正文层再按“人物：句子”排版，于是内部状态句变成角色台词。另一处 `page.tsx:489` 把
`source === 'program'` 的整段写进 `text`，只把 `ms` 置空加 note，条目仍按正文渲染。
建议：失败兜底显示为可恢复状态 + 错误类别，不进入正文文字流。详见 evidence §5。

### 10.4 给 09 的定位：首段计时把程序兜底算成可读正文

同一份证据第 1 回合 `firstReadableMs = 267`，`firstStageMs = 267`，四次模型调用都失败，
最终文本是程序兜底——说明该字段统计的是“屏幕上有字”。建议拆成 `modelFirstTokenMs` /
`programTextMs` / `firstReadableModelMs`，汇总不把 program 文本计入首段可读。详见 evidence §6。

### 10.5 下一步（10 线自己）

“更多覆盖”只能来自新的、按草稿写的人工正文：两次把 199 行旧池子程序化改造成监督都失败
（二元组重合筛：target 中位数掉到 21 字；事实锚点筛：moved 44 条只中 1 条，task 133 条 0 条，
personality 挑中的是景物句）。`build_page_pairs.py` 已加 `--new-rows`，01/05 交来
`{id,viewpoint,draft,target,worldFamily,lineage}` 就能一条命令生成整组划分的训练集。
11/12 的请求继续由 10 统一走 `hpc/batch_screen.py`；目前队列里没有任何 11/12 请求。

## 11. 短对训练（MiniRBT-H256）已跑：授权臂 20%，机制已量出

任务书 `tasks/product-10-short-pair-training.md` sha256 `95d31f3e…`。数据 295 行 / 325 决策 /
4225 对（300 行减 01 的 5 条标签冲突），冻结哈希全部核对过（04 `b9940084…`、13 `0b7766fa…`、
rows `cb4676b3…`、val `284b5404…`、labels `41372ab4…`、split lists `d385b4ac…`、measurement
`69d032f9…`、基座 `6728ca57…`）。

- 作业 254363（第一次）把训练集当验证集喂进早停，`validDecisions 295`，作废保留；
  254378（修正后）在 `gpu` 分区、1× RTX 4090 D、torch 2.5.1+cu124 上跑完，7 epoch（第 4
  epoch 后早停），训练 wall 21 秒。
- **验证 rowHit 0.200（3/15）**，低于 60% 判据；训练损失 1.285→1.271 基本不动；前 15 条
  margin 0.0001–0.004；预测集中到「身体」9/15。
- 机制：同一决策 13 个候选对只在最后一行 `动作：<组名>` 不同（冻结序列化把候选正文放在
  `droppedSections`），163 token 上用 masked-mean 池化后两两余弦 0.999787（min 0.999659）；
  三种池化（mean / CLS / 末位 token）的线性探针在验证集都是 6.7%，训练集 43.9–44.6%，
  等于多数类占比。结论：这一臂在冻结规则下 13 个候选不可分，不是步数不够。
- 已向 04/13 提两条修订，不自行改冻结：A 用冻结文件里已有的不带梯度编码器臂（lrEncoder
  1e-5，需要新的授权，因为一次 run 已用掉）；B 让候选对带上候选正文（把 `candidateTable(text)`
  放回），序列化与新 pairs 需要重冻结。
- TEST 未跑：01 盲版 `004bd736…` 24 行 / 15 个 TEST 目标，20% 的 checkpoint 没有资格读它；
  任务书里「45 行」与这个 24 行不是同一个统计。objectHit 仍为未测（没有对象输入/输出）。
- 证据：`results/action-short-pairs-20261111/10-training-result.json`、`10-training-report.md`；
  代码 `experiments/action-short-pairs/{run_pairwise295.py,probe_pooling.py,shortpair295.sbatch}`。
