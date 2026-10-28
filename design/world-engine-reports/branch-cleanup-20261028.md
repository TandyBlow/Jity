# 两条开发分支的整理记录（2026-10-28）

用户要求本项目只维护 `world-server` 和 `world-browser` 两条开发分支。

此前执行中额外创建了集成分支和叙事实验分支，并把集成验收记录多次 cherry-pick 回开发分支。同一份工作因此出现多个提交身份；签字页的小修正又被拆成多次提交。这是执行时的分支和提交管理问题。

本次整理按文件职责归位：

- `world-server` 保留 Python 内核、事务服务、协议及服务端交付记录。
- `world-browser` 接收 `48eb3a0..e21ecbb` 的全部叙事成果：11 个前端文件、实验说明及两轮评测归档，合成一个提交；不带入集成树里的服务端实现。
- 集成分支的服务端实现已在 server，浏览器实现已在 browser；原验收材料已经归档在两边。两处集成冲突的裁决仍见 server 上的 `joint-acceptance-f2fbee11.md`，不把裁决误当作新的产品功能。
- 移除本地和远端的 `integration/a3734a52-b552148c`、`world-narration-eval` 分支；已发布的 server/browser 历史保留，不强推改写。

整理前四个分支的完整历史已备份并通过 `git bundle verify`：
`.local/branch-cleanup-20261028/backup.bundle`。其中原 server 为 `9101453`，原 browser 为 `305c04f`，集成为 `48eb3a0`，叙事实验为 `e21ecbb`。备份仅在本机，不创建新的分支或远端引用。归档中的旧分支名、源提交和文件摘要保留为历史证据。

以后服务端工作直接提交到 `world-server`，浏览器及模型实验直接提交到 `world-browser`。联调使用指定的两端提交或 detached checkout，不再自行创建实验/集成分支。联合验收材料维护一份，由另一端引用；仅同步必要的协议和消费变更。原有 `master`、`tian`、`agent` 属于其他工作，本次不删除。

迁移验证：前端全套 34 个文件、601 项测试全部通过，`typecheck:world` 和应用 `tsc --noEmit` 通过。11 个前端文件及两个评测归档目录与原 `e21ecbb` 逐文件无差异；browser 未引入 backend 改动。server 本次只更新开发约定和历史验收的复现方式，产品代码未改。
