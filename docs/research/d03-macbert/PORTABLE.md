# 跨平台重训入口

本分支活动方案：API负责生成及其他语义任务；唯一小模型候选为D03 MacBERT。旧MiniRBT/Qwen实验保留为历史资料，不是本方案的活动后端。

`portable_train.py`沿用冻结R2/R3数据、训练配置、分组、开发选择和测试流程，增加Windows UTF-8文件读写、显式CPU/CUDA/MPS设备、可指定底座与父运行目录。默认CPU。使用Python3.12。

R2从固定公开MacBERT基座训练；R3从组员自己完成且通过探索门的R2运行继续。父模型哈希来自该运行自己的summary并核验，不要求与作者Mac产生相同权重。新运行保存设备、源代码、数据及实际父模型哈希，不冒充历史成绩。历史脚本和报告字节保留，旧报告中的作者路径只是历史证据，不是运行依赖。

Windows PowerShell，从仓库根目录执行：

```powershell
py -3.12 -m venv .venv-d03
.\.venv-d03\Scripts\python.exe -m pip install -r experiments/d03-macbert/requirements.txt
.\.venv-d03\Scripts\python.exe -X utf8 experiments/d03-macbert/fetch_model.py
.\.venv-d03\Scripts\python.exe -X utf8 experiments/d03-macbert/portable_train.py --stage r2 --audit
.\.venv-d03\Scripts\python.exe -X utf8 experiments/d03-macbert/portable_train.py --stage r3 --audit
.\.venv-d03\Scripts\python.exe -X utf8 experiments/d03-macbert/portable_train.py --stage r2 --run my-r2 --device cpu
.\.venv-d03\Scripts\python.exe -X utf8 experiments/d03-macbert/portable_train.py --stage r3 --run my-r3 --parent-run .local/d03-macbert/runs/my-r2 --device cpu
```

不要将两条训练命令同时执行。R2未达到探索门时R3拒绝启动。完整CPU训练可能较慢；有NVIDIA GPU且安装对应PyTorch构建时显式改为`--device cuda`。MPS仅适用于Apple。CUDA硬件、完整Windows训练均不能由Mac结果代替；CI验证范围单独记录。

不必激活虚拟环境，以上直接调用python.exe，避免PowerShell脚本执行策略问题。路径用Path解析，含空格时加引号。`.gitattributes`将冻结数据与代码保持LF，避免Windows自动换行导致SHA失配。不要改训练JSONL的编码、换行或标签来绕过审计。

权重、checkpoint、优化器和日志仅存`.local/`，虚拟环境`.venv-d03/`也忽略。运行目录必须是新的，失败记录不覆盖。原始`train_r2.py`/`train_r3.py`属于历史执行证据，组员使用`portable_train.py`。

新入口仅验证了工程等价/数据和微型CPU梯度流程，不自动声称与Mac历史模型相同，也不表示D03 R3质量通过。各组员新运行以自己生成的summary和原始预测为准。
