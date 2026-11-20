# Proposal

## Why

仓库已收敛为单一工作树，所有开发在 `agent` 分支进行，但面向代理的说明仍停留在旧结构：`AGENTS.md` 声明本树是 D 工作树（`world-components-logic`，从 C 的 `30069354` 创建），`WORKTREE_CONTEXT.md` 指向 `world-components-next` 分支，未跟踪的 `CLAUDE.md` 仍保留 A/B/C/D 分工、三分支约束和旧 heads。下一步开发前若不纠正，人和代理会继续按已不存在的工作树规则行事。

## What Changes

- 重写 `AGENTS.md`：声明单一工作树、`agent` 分支、原各线已合入（`e32f06fd` 起）；保留仍然有效的工程约束（Python 状态权威、整链 500ms 性能口径、语义判断不得用固定规则或缩减功能冒充、H2/A3-2 冻结不因整理重开、按路径提交、大文件不入库）。
- 将 `WORKTREE_CONTEXT.md` 压缩为指向 `AGENTS.md` 的三行说明（保留文件而非删除，git 历史可回溯）。
- 更新本地 `CLAUDE.md`（被 `.gitignore` 忽略、不在仓库内）：把 B/C 分工、分支约束、旧 heads 段落替换为单一工作树/`agent` 分支说明；产品约束（状态权威、协议基线、sanity 规则、H2 冻结范围）原样保留。
- 不在范围内：物理工作树（`git worktree list` 已只有当前一个）、`.local/` 退役备份与 review 克隆、远端旧线分支、历史 `artifacts/` 记录。

## Capabilities

### New Capabilities

无。纯文档纠偏，不改变系统行为；`.openspec.yaml` 已设 `skip_specs: true`。

### Modified Capabilities

无。

## Impact

- 仅文档：`AGENTS.md`、`WORKTREE_CONTEXT.md`（仓库内），`CLAUDE.md`（本地未跟踪）。
- 无代码、API、依赖或运行时行为变化。
- 后续代理会话的行为依据改变：不再按 A/B/C/D 工作树或分线分支协作。
