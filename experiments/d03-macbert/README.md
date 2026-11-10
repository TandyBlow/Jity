# D03 MacBERT 基线实验

第三轮入口：`prepare_r3.py`、`train_r3.py`、`report_r3.py`；[协议](../../docs/research/d03-macbert/r3/protocol.md)。保持2–3人，加入关系对照与表达改写。从第二轮选中的模型继续训练；192训练实例中96为旧train复习，不使用旧开发/测试训练。新测试及旧回归都在选择完成后评测。

```sh
.local/d03-macbert/venv/bin/python experiments/d03-macbert/train_r3.py --run macbert-r3 --device mps
.local/d03-macbert/venv/bin/python experiments/d03-macbert/report_r3.py
```

第三轮需要本地R2父模型及其SHA身份，不是从公开底座直接从零训练的独立配方；R2可通过上述第二轮入口重训，但跨设备或重新训练的模型SHA可能不同，应另登记实验，不能绕过父模型身份校验。

第二轮入口：`prepare_r2.py`、`train_r2.py`、`report_r2.py`。新数据与协议位于 [r2](../../docs/research/d03-macbert/r2/protocol.md)，总共2–3个角色（含行动者），从原始基座重新训练，旧轮次保持不变。

```sh
.local/d03-macbert/venv/bin/python experiments/d03-macbert/train_r2.py --run macbert-r2 --device mps
.local/d03-macbert/venv/bin/python experiments/d03-macbert/report_r2.py
```

第二轮已冻结数据不必重新生成；144个实例来自24个动作机制组，全部助手合成、未经人审。环境沿用独立 D03 环境，完整依赖锁定清单在 `docs/research/d03-macbert/environment-lock.txt`。

在完整、自足的中文短场景中，对当前冻结行动与名册中每个角色进行二分类，再汇总完整目标集。全部编码器参数参与微调。

先读 [预登记协议](../../docs/research/d03-macbert/protocol.md) 和 [数据身份](../../docs/research/d03-macbert/data-manifest.json)。所有数据为助手合成草稿，未经人工审核。这里不是生产输入适配器，不自动写入世界状态，也不表示浏览器部署或完整 500ms 目标已通过。

## 运行

建议在独立 Python 3.12 环境安装 requirements.txt。下面命令从仓库根目录执行。

```sh
python -m venv .local/d03-macbert/venv
.local/d03-macbert/venv/bin/python -m pip install -r experiments/d03-macbert/requirements.txt
.local/d03-macbert/venv/bin/python experiments/d03-macbert/fetch_model.py
.local/d03-macbert/venv/bin/python -m unittest discover -s experiments/d03-macbert -p 'test_*.py'
.local/d03-macbert/venv/bin/python experiments/d03-macbert/train.py --run macbert-r1 --device mps
```

MacBERT 固定 revision，模型文件 SHA-256 记录在 `.local/d03-macbert/base/manifest.json`，训练时逐项重验。模型加载不执行远端代码。数据已交付，无需重建；如需核验生成过程可运行 `prepare_data.py`，它会重写本实验的 scenes.jsonl 与 data-manifest.json。

训练只读取本机已有的底座。输出目录必须不存在，失败记录保留；不要覆盖运行或依据测试结果反复调整。其他设备可以显式指定 `--device cpu` 或 `--device cuda`，但本次只验证 MPS，跨设备结果和速度没有保证。

## 产物

- `docs/research/d03-macbert/scenes.jsonl`：原始输入、标签、分组、人工审核状态。
- `.local/d03-macbert/runs/<run>/run.json`：固定配置、代码与数据身份、环境版本。
- `events.jsonl`：逐轮训练损失、开发集评分、选择记录及故障信息。
- `development-epoch-*.json`：每轮开发集原始分数。
- `test-predictions.json`：冻结选择后的唯一测试输出；`train-predictions.json` 仅作拟合诊断。
- `summary.json`：完整集合、漏选、误选、空集与耗时，以及停止/后续验证决定。
- `model/`：保存重载验证的模型、分词器；`best.pt` 是本地检查点。

所有权重和完整运行日志保存在被 Git 忽略的 `.local/` 中。源码目录 `experiments/` 也继承仓库忽略规则；如果之后明确需要提交，应只对这些源码路径显式添加，不能提交模型或使用全仓添加。本次没有提交、推送或改动线上模型。
