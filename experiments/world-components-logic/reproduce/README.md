# 组员从零重训（源码与必要资料）

本分支只分发代码、助手编写的合成训练样本、固定划分、模型来源及简要报告。**不包含模型、LoRA、任务头、检查点、优化器状态、模型备份包或新增的大体积原始日志**。各组员在自己的目录下载公开基座并生成自己的训练产物。

这是从当前 `time-choice-v2` 数据重新训练的新候选配方，复用原有任务编码、完整输入、响应区间损失、LoRA 与分类头实现。它不是历史 r4→r5 检查点的逐字节重演：旧 r4 使用迁移前数据，r5 从旧优化器和 RNG 续训；本入口使用当前数据从零开始，并在一个进程内训练。历史原配置和取样序列在 `historical-settings.json`，不冒充新结果。

## 1. 环境与设备

建议 Python **3.12**；本机检查使用 Python 3.12 和 `requirements.txt` 中的核心版本。新建环境，避免影响其他项目：

```sh
python3.12 -m venv .venv-retrain
source .venv-retrain/bin/activate
python -m pip install -r experiments/world-components-logic/reproduce/requirements.txt
```

Windows 可用 `py -3.12 -m venv .venv-retrain`，然后运行 `.venv-retrain\Scripts\Activate.ps1`；后续 Python 命令相同。

Linux/Windows 的 PyTorch 需要选择匹配设备的构建。例如 CPU 可先执行 `python -m pip install torch==2.7.1 --index-url https://download.pytorch.org/whl/cpu`，再安装 requirements。CUDA 用户按 [PyTorch 2.7.1 官方版本安装说明](https://pytorch.org/get-started/previous-versions/#v271) 选择适合驱动的构建，再检查 `torch.cuda.is_available()`。版本清单是已观察环境的直接依赖约束，不是所有平台的完整安装验证或跨平台锁文件。

| 设备 | 入口行为 | 验证边界与资源 |
|---|---|---|
| 普通 CPU | MiniRBT 仅 CPU/FP32；Qwen 可选 CPU/FP32 | 原 MiniRBT 内核有历史 CPU 实验；新 Qwen 入口只做了随机微型模型的真实梯度与重载测试，未跑完整 0.6B CPU 重训。CPU Qwen 可能很慢。 |
| Apple Silicon | Qwen 使用 `--device mps --dtype bfloat16` | 历史旧入口真实跑过 MPS；**新封装的完整 MPS 训练未重跑**。原机器为约 18 GiB 统一内存，原运行单进程内存门约 8 GiB；这不是新封装的内存保证。 |
| NVIDIA CUDA | Qwen 显式选择 `--device cuda`，支持 FP32；设备支持时可选 BF16 | 已提供设备检测与独立 CUDA 同步/缓存路径，**未在真实 CUDA 硬件上验证完整训练**。不同精度、驱动和内核可能产生不同结果。 |

MiniRBT 公开基座约 42 MB，Qwen 源文件约 1.52 GB。为依赖、基座和本地结果预留至少数 GB 磁盘；完整 8192 token 输入下的 RAM/VRAM 峰值依设备而变，目前没有测定通用最低显存。内存不足应停止并记录，不要截断输入或暗中更改划分。新封装没有旧监督器的强制 8 GiB 限额或分进程调度，需自行监控内存。

## 2. 固定数据与分享边界

当前包为 **4,750 条助手合成草稿**：train 3,204，development 693，test 853；分别来自 8、2、2 个来源组。Qwen 文本子集为 train 262 / development 63 / test 65。`splits.json` 固定每条样本的 ID、顺序和来源组，不允许把关联变体拆到不同集合。训练函数只从 `train` 生成取样序列。

文件：`../data/short-semantics/time-choice-v2/supervision.jsonl.gz`。SHA-256：

`8aa0875d0268e921142cfab5c2fe42df049193bca2d70b08358cbe909f4abe16`

该数据来自本项目的助手编写场景和程序派生监督，不包含本次上传的第三方小说语料、私人聊天或基座权重。`author_packet.py`、`abstention_packet.py`、`partial_packet.py`、`project_primitives.py` 保留生成方法。**人工复核数为 0，来源核验仍待完成；这些开发/测试来源已用于先前诊断，不是新封存的独立泛化评测集**。请作为组内研究草稿使用，扩大分发或正式发表前另行完成来源及质量审查。

```sh
python experiments/world-components-logic/reproduce/retrain.py audit
```

审计不下载模型、不训练。历史数据清单中的作者绝对路径是原始证据引用，不是本入口的运行路径；本入口以自身位置定位默认数据，并允许 `--dataset`、`--splits`、`--model-dir`、`--output-dir` 和 `--checkpoint-dir` 显式配置。自定义数据必须同时登记匹配的划分清单，不能绕过原划分检查。

## 3. 下载固定版本的基座

下载会核对注册的文件大小和 SHA-256/Git blob 身份，不执行远端代码，不复用作者的私有缓存。模型目录可以换成自己机器上的任意目录。下载与后续使用须遵守各原始模型的许可；本分支不再分发这些权重。

| 用途 | 官方模型 | 固定 revision |
|---|---|---|
| 14 类文本任务 | [Qwen/Qwen3-0.6B](https://huggingface.co/Qwen/Qwen3-0.6B/tree/c1899de289a04d12100db370d81485cdf75e47ca) | `c1899de289a04d12100db370d81485cdf75e47ca` |
| 分类、引用选择、整数头 | [hfl/minirbt-h256](https://huggingface.co/hfl/minirbt-h256/tree/446e1b4012b10946f479563005700c54c9db3f7c) | `446e1b4012b10946f479563005700c54c9db3f7c` |

```sh
python experiments/world-components-logic/reproduce/retrain.py download --model qwen --model-dir .local/retrain/models/qwen
python experiments/world-components-logic/reproduce/retrain.py download --model encoder --model-dir .local/retrain/models/minirbt
```

模型来源、文件清单和精确身份在 `model-sources.json`。旧燃灯代码仅保留为历史实现，不是此入口的活动生成器。

## 4. 训练与评测

Qwen 新候选：seed 42，112 步，batch 1，冻结基座，q/v 投影 LoRA rank 4 / alpha 8，FP32 适配器，AdamW lr 1e-4 / weight decay 0.01 / clip 1，完整上下文 8192、目标与生成上限各 128。损失只覆盖响应及 EOS。先完整生成 128 条训前输出，再训练，保存/重载适配器，再完整生成同一批 128 条训后输出。只作贪心首发，不重采样；没有自动调参或重启训练。

```sh
python experiments/world-components-logic/reproduce/retrain.py train --model qwen --model-dir .local/retrain/models/qwen --output-dir .local/retrain/runs/qwen-fresh-01 --device mps --dtype bfloat16
python experiments/world-components-logic/reproduce/retrain.py evaluate --model qwen --model-dir .local/retrain/models/qwen --checkpoint-dir .local/retrain/runs/qwen-fresh-01 --output-dir .local/retrain/evaluations/qwen-fresh-01 --device mps --dtype bfloat16
```

CPU 将设备参数换为 `--device cpu --dtype float32`。CUDA 将其换为 `--device cuda --dtype float32`，或在支持 BF16 的设备上用 `--dtype bfloat16`；这些完整硬件路径仍需组员自行实测，不应称为已复现历史分数。

MiniRBT 新候选：取固定基座前两层、禁用池化器，CPU/FP32，seed 42，160 步，batch 2，AdamW lr 0.001 / weight decay 0.01 / clip 1；复用完整事实窗口编码和原有 62 个任务头。这个基础重训不是历史 r6 聚焦头与 r8 时间修复组合，不能直接替代其部署身份。

```sh
python experiments/world-components-logic/reproduce/retrain.py train --model encoder --model-dir .local/retrain/models/minirbt --output-dir .local/retrain/runs/encoder-fresh-01 --device cpu --dtype float32
python experiments/world-components-logic/reproduce/retrain.py evaluate --model encoder --model-dir .local/retrain/models/minirbt --checkpoint-dir .local/retrain/runs/encoder-fresh-01 --output-dir .local/retrain/evaluations/encoder-fresh-01 --device cpu --dtype float32
```

每次输出目录必须是新目录，失败记录保留，不能覆盖同名运行。可以显式传 `--seed` 和 `--steps` 登记新的实验；减少步数可能被任务/标签覆盖校验拒绝。权重、优化器状态和所有运行输出留在 `.local/`，不要提交。

`run.json` 记录数据、基座、配置、依赖和源码身份。Qwen 的 `before.jsonl` / `after.jsonl` 保留原始输出和 token；编码头结果在 `training-summary.json`。`evaluate` 校验训练记录及检查点身份后重新推理；用不同设备/精度评测时会如实记录设置。评测精确匹配只是对助手草稿的匹配率，必须另行逐例检查角色、方向、条件、漏项与不完整输出；它不等于语义通过或全链通过。

## 5. 现有结果与当前验证

历史 r5 在旧 r4 上追加 32 步，累计 144 步。128 条训后输出的助手初审：52 条局部满足、62 条不满足、14 条待审；D02 的 14 条和 D04 的 4 条均有明确问题。时间修复没有改变 8 条时间任务的输出。没有人工签署、独立泛化、转换通过或完整浏览器生产验收。摘要与原报告身份见 `historical-results.json`。

另一工作目录的最后一次 r6 续训/转换诊断仍独立进行，本分支未读取或发布其运行中的权重与日志，也不预报结果。

本次发布验证：固定数据与划分校验；两个公开基座的本机原文件身份校验；CPU 随机微型 Qwen 的真实梯度、冻结基座、适配器保存/重载和生成工程检查。**没有为此次打包重新跑真实 0.6B 全量训练，也没有 CUDA 硬件结果。**

```sh
python -m unittest discover -s experiments/world-components-logic/reproduce -p 'test_*.py'
```

已安装神经依赖时包含微型随机模型测试；未安装时该测试明确跳过。这个测试不代表学习了游戏语义。
