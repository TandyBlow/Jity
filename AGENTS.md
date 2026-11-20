# 仓库协作说明

本仓库只有单一工作树，所有开发在 `agent` 分支进行。原 A/B/C/D 与 `goal/local-*` 线已合并回 `agent`（2026-11-20），不再按线分分支或新开工作树。

- goal 入口：`design/goal/goal.md`；能力账本：`design/goal/ledger.md`；决策：`design/goal/decisions.md`。
- 运行期权威：浏览器 TypeScript 内核独占 apply/merge/commit/replay；Python v2 只作差分预言机、金标向量与迁移参考。
- 产品路径：`/world-local` 唯一交付；`/world` 规则页与 Python 服务不投入新玩法。
- 性能：正常提交到可读流式正文 ≤60 秒；单点完成 ≤300 秒；500 ms 仅局部诊断参考。
- 叙事：按 2026-11-11 决定，运行期原样显示非空模型正文；不检查、不裁改、不程序补写。
- 语义判断不能靠固定规则或缩减原功能冒充完成；固定输出/模板只作对照臂。
- 不因整理工作树重新打开已冻结的 H2/A3-2 验收；离线验证、浏览器验证、生产接线分别报告。
- 提交按明确文件路径，不使用全仓 `git add .`；大文件、权重、缓存与本地依赖不入库。
- `experiments/` 被 `.gitignore` 忽略；本地实验产物与备份留在 `.local/`；验收证据放 `artifacts/goal/`。
