> 当前 D 线权威流程与新运行端口见 [D_LINE_AUTHORITY.md](D_LINE_AUTHORITY.md)。下文原 API→目标 API→影子模型入口保留为历史实验，不代表当前两次 API 结算流程。

# Windows 开发交接：API + 唯一 D03 小模型

## 当前版本与范围

以 D 的干净源码提交 `51bd76e97a8892a6ff012a2ebea57476deb22d4b` 为基础，合入 D03 第三轮及前置 R2，以及从 R3 继续训练的真实游戏剧情首轮源码、冻结数据和结果。没有合入撤回的模型归档提交、LFS 指针或 D02 小模型方案。

| 职责 | 当前方案 |
|---|---|
| 开局、行动、反应、共同结果、其他语义更新、继续判断、时间建议、叙事 | API |
| D03：冻结行动影响哪些角色 | MacBERT 小模型研究候选；尚未质量验收，实验中与 API 对照 |
| ID、骰点、资格/准入、冻结、状态写入、持久化 | 确定性程序 |

完整 API + D03 生产链尚未接线。本分支提供一个可运行的独立实验入口：API 提出行动 → 原文冻结 → API 目标建议 → 可选 D03 对同一输入作影子判断。候选结果落到本地 JSON，**不写入游戏世界**。这不是浏览器完整交互产品。

仓库继承的旧 MiniRBT、Qwen 和其他模型实验只是历史资料；它们不是当前方案的运行依赖，不需要下载或重训。不要运行旧的一键全模型训练命令来启动本方案。

## 环境

推荐 Windows 10/11、Python **3.12**（64位）。只做 API 演示或数据审计可以不安装模型库。训练建议预留至少数GB磁盘，CPU可能较慢。PowerShell 从仓库根目录操作，无需修改执行策略或激活环境：

```powershell
py -3.12 -m venv .venv-d03
.\.venv-d03\Scripts\python.exe -m pip install -r experiments/d03-macbert/requirements.txt
.\.venv-d03\Scripts\python.exe -X utf8 experiments/d03-macbert/portable_train.py --stage r2 --audit
.\.venv-d03\Scripts\python.exe -X utf8 experiments/d03-macbert/portable_train.py --stage r3 --audit
.\.venv-d03\Scripts\python.exe -X utf8 experiments/d03-macbert/portable_train.py --stage gameplay --audit
```

路径含空格时用引号。仓库用 `.gitattributes` 固定冻结文件的 LF；不要自行用记事本换编码、换行或改标签。脚本使用 UTF-8。无需 Mac 的 MPS、Conda、bash 或作者绝对目录。

## 组员自行获得小模型

**仓库没有权重。** 第一次下载固定版本公开 MacBERT，之后所有训练与模型加载都从本机目录进行。

```powershell
.\.venv-d03\Scripts\python.exe -X utf8 experiments/d03-macbert/fetch_model.py
.\.venv-d03\Scripts\python.exe -X utf8 experiments/d03-macbert/portable_train.py --stage r2 --run my-r2 --device cpu
.\.venv-d03\Scripts\python.exe -X utf8 experiments/d03-macbert/portable_train.py --stage r3 --run my-r3 --parent-run .local/d03-macbert/runs/my-r2 --device cpu
.\.venv-d03\Scripts\python.exe -X utf8 experiments/d03-macbert/portable_train.py --stage gameplay --run my-gameplay-v1 --parent-run .local/d03-macbert/runs/my-r3 --device cpu
```

依次执行。最新游戏剧情阶段名为 `gameplay`，使用已完成的本机 R3；允许继续研究尚未通过质量门的 R3，不表示质量验收。详见 [游戏剧情训练说明](docs/research/d03-gameplay-dataset-20261110-v1/PORTABLE.md)。

依次执行。R2 需通过自己的探索质量门，R3才接受它作为父模型。父模型按本机实际SHA核验，不要求与作者Mac逐字节一致；跨设备重训分数不保证复现。已有CUDA兼容PyTorch及NVIDIA GPU时显式改用`--device cuda`。默认CPU，设备不可用报错，不静默切换。

新产物位于 `.local/d03-macbert/runs/<run>/`，重点查看 `summary.json`、测试预测和 `events.jsonl`。运行目录不能重用。历史 `train_r2.py` / `train_r3.py` 留作证据，不是 Windows 推荐入口。详情见 [跨平台训练说明](docs/research/d03-macbert/PORTABLE.md)。

## API + D03 实验入口

接口兼容 OpenAI Chat Completions 的 JSON 输出。API Key 只从本机环境读取，不放进源码、命令参数或提交文件。请在 PowerShell 本地输入：

```powershell
$env:JITY_API_BASE_URL = 'https://api.deepseek.com/v1'
$env:JITY_API_MODEL = 'deepseek-chat'
$key = Read-Host 'API Key' -AsSecureString
$env:JITY_API_KEY = [System.Net.NetworkCredential]::new('', $key).Password

# 每次演示会真实调用两次 API；不会自动重试。
.\.venv-d03\Scripts\python.exe -X utf8 scripts/hybrid/run.py --input scripts/hybrid/example.json --output .local/hybrid/api-01.json --mode api

# 已自行重训后，加入唯一小模型 D03 的影子对照。
.\.venv-d03\Scripts\python.exe -X utf8 scripts/hybrid/run.py --input scripts/hybrid/example.json --output .local/hybrid/shadow-01.json --mode shadow --model-run .local/d03-macbert/runs/my-r3
```

`apiTargetProposal` 和 `localTargetProposal` 都是建议；API 也不是金标准。`agreement` 只表示二者是否一致。小模型无论置信度多高都不在此脚本内变成权威状态。输入暂限2–3人自足短场景，超过512tokens会明确拒绝，不截断。未知ID、空行动和不完整API响应会报错，不修造答案。

本次打包只做无网络API替身测试，没有使用你的API额度或上传样本。

## 已有结果与验证边界

- R2 简化测试24/24，仅4个机制组及相关改写。
- R3 新难题12/24；父模型在同题上8/24；旧基础题回归24/24。R3仍未通过质量门，不可称为已部署教师。
- R2/R3 合成数据为助手草稿，人工复核数0。见 [R3报告](docs/research/d03-macbert/r3/report.md)。
- 最新游戏剧情阶段：用户接受17条，训练7/开发4/测试6，另7条歧义样本排除。测试5/6（R3父模型同题1/6），旧题回归24/24；仍未通过探索质量门。四份记录来自同一战役，不能当作跨世界泛化验证。见 [训练报告](docs/research/d03-gameplay-dataset-20261110-v1/training-report.md)。
- Windows/Linux CI 检查源码保护、数据分组、UTF-8/跨目录入口、CPU微型模型梯度及保存重载、无网络API编排；**不会下载MacBERT或进行完整重训**。
- 本机检查和GitHub CI结果分别记录在分支发布记录中。没有将Mac结果冒称为完整Windows/CUDA训练结果。

```powershell
.\.venv-d03\Scripts\python.exe -X utf8 -m unittest discover -s experiments/d03-macbert -p 'test_*.py' -v
.\.venv-d03\Scripts\python.exe -X utf8 -m unittest discover -s scripts/hybrid -p 'test_*.py' -v
.\.venv-d03\Scripts\python.exe -X utf8 scripts/hybrid/check_release.py
```

## 提交边界

仅提交源码、小型冻结数据和必要报告。权重、检查点、虚拟环境、缓存、运行日志、`.env`和密钥都留在本地。本分支新增保护规则和CI检查拒绝权重扩展名、LFS指针、大于2MiB的文件及Windows非法路径。请使用明确文件列表暂存，不要强制添加整个`.local/`或整个实验运行目录。
