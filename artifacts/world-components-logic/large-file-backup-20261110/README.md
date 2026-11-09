# 大型训练文件无损归档

按用户选择，将当前快照中的大型模型、检查点和原始实验记录进行无损压缩后上传。87 个大文件原始合计约 11.0 GB（含相同内容的不同路径），压缩为约 2.27 GB。压缩包分为 9 份，每份不超过 256 MiB，使用 Git LFS 保存。代码、训练数据、其余模型配置和实验报告仍按原目录跟踪。

`manifest.json` 记录每个分卷、完整压缩包和每个原始文件的 SHA-256、字节数和还原路径。所有原始大文件仍留在原工作目录；Git 忽略这些已归档的副本，避免再次重复上传。修改它们不会自动更新本次冻结归档。

## 下载和还原

先检出本分支并运行 `git lfs pull`。安装 `zstd`（macOS 可运行 `brew install zstd`），然后在仓库根目录执行：

```sh
python3 artifacts/world-components-logic/large-file-backup-20261110/restore_large_files.py
python3 artifacts/world-components-logic/model-archive-20261110/verify_archive.py
```

还原工具依次核对分卷和整个压缩包，流式解压到原相对路径，并逐文件验证内容。不覆盖内容不同的现有文件；相同内容的文件保留原样。解压需要约 2 GiB 的窗口内存，以及存放缺失原始文件的磁盘空间。

只检查压缩包内所有原始文件而不写出，可运行：

```sh
python3 artifacts/world-components-logic/large-file-backup-20261110/restore_large_files.py --verify-only
```

归档仅用于备份，不代表模型转换、语义质量或生产接入通过。用户指定排除的转换诊断中间缓存未放入压缩包，其清单与校验值见相邻模型归档中的 `excluded-diagnostics.json`。
