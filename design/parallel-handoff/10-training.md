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

每条成功向量有 `projection` 和 `expected.bytesUtf8Hex / sha256 / segments`。浏览器 serializer
必须比较 UTF-8 字节，失败用例在相同 `stage` 返回相同 `errorCode`。向量里没有目标正文，不要
从 golden 找 `y`。

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
