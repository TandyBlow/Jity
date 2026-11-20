# Tasks

## 1. AGENTS.md 重写

- [ ] 1.1 用单一工作树/`agent` 分支版本替换 `AGENTS.md` 全文，保留状态权威、整链 500ms、语义判断、冻结验收、按路径提交、忽略目录六条约束；验证：`git grep -n -E "D 工作树|world-components-logic|world-components-next" -- AGENTS.md` 无输出，且六条约束仍能在新文中找到。
- [ ] 1.2 核对新说明与物理状态一致；验证：`git worktree list` 只有 `D:/others/Jity`、分支 `agent` 一条。

## 2. WORKTREE_CONTEXT.md 收敛

- [ ] 2.1 将 `WORKTREE_CONTEXT.md` 替换为三行指针（标题、单一工作树/`agent`、指向 `AGENTS.md`）；验证：文件仅三行，`git grep -n "world-components-next" -- WORKTREE_CONTEXT.md` 无输出。

## 3. 本地 CLAUDE.md 对齐

- [ ] 3.1 把 `CLAUDE.md` 中 "Latest component assignment"、"User branch constraint" 及旧 heads 段落替换为单一工作树/`agent` 分支说明，保留产品约束（状态权威、协议基线、sanity 规则、H2 冻结范围）；验证：重读 "Active project" 一节，工作方式只剩单一工作树表述，产品约束段落未删。

## 4. 一致性检查与提交

- [ ] 4.1 检查其余当前状态文档不再误述工作树结构；验证：`git grep -n -E "D 工作树|world-components-next|按线分支" -- '*.md' ':!artifacts/**'` 只命中历史记录或本 change 自身。
- [ ] 4.2 校验 change 产物；验证：`openspec validate align-worktree-docs` 通过。
- [ ] 4.3 按路径暂存并提交 `AGENTS.md`、`WORKTREE_CONTEXT.md`（`CLAUDE.md` 被忽略，不提交）；验证：`git status --short` 不再列出这两个文件，`git show --stat HEAD` 仅含这两个文件。

## Workflow follow-up

- 评审通过后用 archive 流程归档本 change。
- 远端旧分支与 `.local/` 退役备份不在本次范围，需要清理时另开提案。
