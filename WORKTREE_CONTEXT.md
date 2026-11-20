# world-components-next

本分支独立推进叙事组件开发，原分支继续提交，没有冻结或清理。

- `714f171`：给来自 `f725d12` 的未提交方向修正建立字节保真的快照基线。
- `3fe0647`：输入 pin、路径隔离、显式模型配置和 CPU 运行验收。
- 当前输入：`artifacts/next-inputs/pin.json`；历史副本不可更新，读取时校验一致性。
- 运行输出：`artifacts/next-runs/`，默认留本地；手工选中的记录进入 `artifacts/next-acceptance/`。

操作与合并前置检查见 [开发说明](design/world-engine-reports/components/next-worktree.md)。
首次合回原工作树前要备份并核对未跟踪实验副本，不能仅按 git status 判断现场。
当前只验证 CPU 运行链路，GPU 和叙事质量提升尚未验证。
