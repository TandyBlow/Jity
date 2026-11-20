# 运行目录事后说明（r1）

本目录是 cf24 诊断第一轮的原始运行目录。以下两点是事后补记，不改变 `raw.jsonl`、`order.jsonl`、`failures.jsonl` 的原始字节：

1. **`env.json` 是事后重建的。** 运行开始约 30 秒后，我误用 `rm -rf` 清理“空目录”，删除了当时已生成且未被进程占用的 `env.json` 与 `run.json`。`env.json` 由 `run.json.env` 重建（206 字节，sha256 `44bd4629c909eaf1…`）；原始文件未留存，无法证明字节相同。
2. **`run.json` 由进程在结束时重新写出。** 其 `run_meta` 在模型加载前构建并保存在内存中，结束时写入磁盘；删除发生在写入之前，因此内容取自同一进程，`startedAt` 等字段未被修改。
3. **执行版本与当前脚本不同。** 执行版本 sha256 `9b4b3946…`，源码快照见 `scripts/snapshots/run_diagnostic-9b4b3946.py`；当前 `scripts/run_diagnostic.py`（`007999eb…`）多了未使用的断点续跑分支。

封存哈希与审计细节见 `results/diagnostic-r1-audit-v1.md`。
