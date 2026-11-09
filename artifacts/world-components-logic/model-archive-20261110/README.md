# D 线训练成果备份（2026-11-10）

按用户要求保存当前训练成果。此归档不是模型质量、转换、浏览器部署或生产接入的验收；原始失败结论和 `browserProvider=null` 保持不变。

## 包含内容

- `worktree-local/`：原工作目录中的 MiniRBT / 燃灯 / Qwen 基座及分词器、早期任务头与适配层、WebGPU 基座模型。燃灯仅为历史证据，不是活动后端。
- `task-cache/encoder/`：当前与历史判别头、模型说明及相关基座。
- `task-cache/qwen/runs/`：Qwen r4/r5 全部已存在的训练检查点、优化器恢复状态、合并权重和分词器。
- `task-cache/qwen/source/` 和 `task-cache/webgpu/models/`：原始基座与浏览器基座，用于保留依赖身份。
- `manifest.json`：每个归档文件的原路径、归档相对路径、字节数和 SHA-256。
- `excluded-diagnostics.json`：按用户选择不上传的转换导出和诊断中间缓存（包括失败导出、重复模型及中间张量）的清单与 SHA-256；原文件仍留在本机。

代码、训练数据和原始实验报告位于同一分支的 `experiments/world-components-logic/`、`design/world-engine-reports/components-logic/` 和本归档的父目录。环境、依赖缓存、密钥及运行数据库不属于训练成果归档。

## 下载和校验

本分支的大型记录及二进制模型已无损压缩，分卷通过 Git LFS 保存。检出分支后运行 `git lfs pull`，并先按相邻的 `large-file-backup-20261110/README.md` 运行还原工具，再执行：

```sh
python3 artifacts/world-components-logic/model-archive-20261110/verify_archive.py
```

校验脚本只读文件并验证字节数和 SHA-256。模型档案与实验记录中的原绝对路径未改写，以保留证据身份；`manifest.json` 提供其归档位置映射。在另一台机器运行实验时，需要按实际目录配置路径。备份不会自动启用任何未通过转换的模型。
