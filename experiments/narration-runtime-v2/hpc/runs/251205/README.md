# Job 251205: failed pre-training smoke

- 提交：2026-11-10T11:24:24 +08:00
- 开始：2026-11-10T11:24:24 +08:00
- 结束：2026-11-10T11:25:42 +08:00
- 耗时：00:01:18
- 状态：FAILED，exit 1:0
- 节点/显卡：hpcgpu10 / RTX 4090 D
- 配置：`configs/yuyan-lora-v2.json`（当时 maxLen 2560）
- 数据/基座/tokenizer 身份：与 251206 相同；preflight 和 base SHA-256 检查均通过

## 失败原因

`train/train_yuyan_v2.py` 在打印第一行训练摘要时把 `ensure_ascii=False` 传给了
`print()`，而不是 `json.dumps()`：

```text
TypeError: 'ensure_ascii' is an invalid keyword argument for print()
```

这是脚本错误，不是数据、基座或模型质量问题。失败发生在训练开始前，没有生成
adapter、checkpoint 或质量样本。

## 修复与后续

- 把 `ensure_ascii=False` 移入 `json.dumps`；
- 增加 `--device cpu` 的微型模型 smoke 路径，在本地用随机 1 层模型跑完 1 个 epoch、
  dev/test 评估、resume 文件和样本生成；
- 重新部署并以 251206 重跑。

保留本目录的 `job.out` / `job.err` 作为失败证据；不把失败改写成通过。
