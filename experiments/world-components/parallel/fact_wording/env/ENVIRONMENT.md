# 运行环境记录（c4 / N4 解码对照）

| 项 | 值 |
|---|---|
| 位置 | `experiments/world-components/parallel/fact_wording/env/`（工作树内，`.gitignore` 已忽略 `experiments/`） |
| 解释器 | `env/Scripts/python.exe`，CPython **3.12.3**（`uv python install 3.12.3`，独立于此前的 3.11.15） |
| 建立时间 | 2026-11-08 |
| 建立方式 | `uv venv --python 3.12.3 env` → `uv pip install ...` |
| 依赖锁 | `env/requirements.lock.txt`（26 行，`uv pip freeze` 输出） |

## 与 cf24 基线的版本对照

基线取自 `artifacts/next-acceptance/cf24-u240-baseline/cf24-u240-baseline/cf24-baseline.json` 的 `environment` 字段。

| 项 | 基线要求 | 本环境实测 | 是否一致 |
|---|---|---|---|
| python | 3.12.3 | 3.12.3 | 是 |
| torch | 2.7.0+cu126 | 2.7.0+cu126 | 是 |
| transformers | 4.57.3 | 4.57.3 | 是 |
| sentencepiece | （基线未记） | 0.2.0 | 记录在案 |
| 设备 | cpu | cpu（`torch.cuda.is_available()` 为 True，但运行显式用 CPU） | 按协议 |
| 线程 | 4 | 4（`torch.set_num_threads(4)`、`OMP/MKL_NUM_THREADS=4`） | 是 |

**注意**：版本一致指的是“版本号与基线相同”，不是“同一台机器上装出的同一个环境”。本环境是新装的，wheel 来自公共索引，`requirements.lock.txt` 记录了实际解析到的全部版本。

## 安装来源

| 包 | 索引 | 版本 |
|---|---|---|
| torch | `https://download.pytorch.org/whl/cu126` | 2.7.0+cu126 |
| transformers / tokenizers / safetensors / sentencepiece / numpy 等 | 默认 PyPI 索引 | 见 lock |

安装日志（本地临时文件，未纳入交付）：`/tmp/torch-install.log`、`/tmp/tf-install.log`。

## 复现

```bash
cd experiments/world-components/parallel/fact_wording
uv python install 3.12.3
uv venv --python 3.12.3 env
uv pip install --python env/Scripts/python.exe --index-url https://download.pytorch.org/whl/cu126 "torch==2.7.0"
uv pip install --python env/Scripts/python.exe "transformers==4.57.3" "sentencepiece==0.2.0" "safetensors" "numpy<3"
uv pip freeze --python env/Scripts/python.exe > env/requirements.lock.txt
```

## 未验证

- 没有把本环境的 tokenizer 输出与基线机器逐 token 比对；只验证了权重与 config/tokenizer 文件哈希一致。
- GPU 未用于任何结果；CUDA 可用与否不影响本协议（协议固定 CPU）。
- 环境目录约数 GB（torch cu126），不随仓库分发；重建按上面的命令即可。

## 2026-11-09 追加（真实状态冒烟）

- 为导入 `experiments/world-components/narration_pipeline.py`（需要 pydantic 校验世界契约），通过 `uv pip install` 加入：`pydantic 2.14.3`、`pydantic-core 2.50.4`、`annotated-types 0.8.0`、`typing-inspection 0.4.5`。
- 原 C4 诊断环境不变（torch 2.7.0+cu126、transformers 4.57.3、sentencepiece 0.2.0）；新增包只影响这次的 N3 链路导入。
- 真实状态冒烟使用 `scripts/run_real_state_smoke.py`，模型仍为 u240（sha256 `ab8a9826…`）。
