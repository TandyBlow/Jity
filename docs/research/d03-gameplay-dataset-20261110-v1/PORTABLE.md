# 最新游戏剧情阶段：Windows / Linux 重训

这是 R3 之后的继续训练，入口阶段名为 `gameplay`；不覆盖历史 R3。四份原始游戏记录来自同一战役。用户认可17条可用标注，7条歧义候选仍排除。按整局划分：game-01/02训练7条、game-03开发4条、game-04测试6条。

## 组员运行

先按仓库根目录 DEVELOPMENT_WINDOWS.md 安装依赖、下载固定公开底座，并完成自己的 R2 → R3 训练；再从仓库根目录依次执行：

```powershell
.\.venv-d03\Scripts\python.exe -X utf8 experiments/d03-macbert/portable_train.py --stage gameplay --audit
.\.venv-d03\Scripts\python.exe -X utf8 experiments/d03-macbert/portable_train.py --stage gameplay --run my-gameplay-v1 --parent-run .local/d03-macbert/runs/my-r3 --device cpu
```

有兼容 NVIDIA GPU 和 PyTorch 时可显式用 `--device cuda`。结果在 `.local/d03-macbert/runs/my-gameplay-v1/`；运行名必须未被使用。父模型按组员自己的 R3 运行记录和实际权重 SHA 校验，且必须使用本仓库冻结 R3 数据。R3 的探索质量门失败不阻止这轮研究；新旧模型均不因完成训练而得到产品批准。R2 → R3 仍要求 R2 通过探索门。

## 数据及历史证据

- `scenes.jsonl` 和 `data-manifest.json` 是当前冻结训练入口与用户接受范围；原始 `README.md` / `manifest.json` 的 pending 状态是接受前历史。
- `all-candidates.jsonl`、`review-queue.jsonl` 保留候选及排除依据。审计证据和标签不会拼入模型输入；旧记录没有观测到的已行动状态明确显示“未知”。
- 本目录 `build.py`、`train.py`、`report_training.py`、`test_training.py` 及报告保留作者历史执行字节，含作者机器路径；它们不是 Windows 入口。原始完整游戏记录不随本次提交，但冻结样本已含重训所需输入，不依赖作者原始记录目录。
- `run.json`、`summary.json` 和各预测文件属于历史 Mac/MPS 运行；新运行独立记录自己的代码、数据、协议和父模型哈希。跨设备训练不保证复现相同分数或权重。
- GitHub 仅提供数据、代码和报告，不含训练后的模型、优化器、缓存或本机环境；拉取本分支不会直接获得作者的新模型。

## 结果边界

作者历史结果：训练7/7、开发4/4、游戏测试5/6（R3父模型同题1/6）、旧R2回归24/24。仍未通过游戏测试探索门。测试仅6个相关片段且全部阳性目标都是诺诺，不能声称跨故事泛化或多人复杂关系已解决。

新增跨平台工程测试验证冻结数据、逐候选输入与历史脚本一致、错误父阶段拒绝，以及微型随机 CPU 模型的实际8轮训练/保存/重载/父模型不变。它不等于 Windows/CUDA 上完整 MacBERT 重训或语义质量验收。
