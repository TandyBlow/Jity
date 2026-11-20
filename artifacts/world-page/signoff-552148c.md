# B 端世界页 SPA 进入隔离轮最终复验

日期：2026-10-28。复核：用户独立验收；记录：B 端验收任务。
签字提交：`552148c`（轮次提交 `74ce5df` 红探针 → `bf3d92f` 修复 → `62e9f2d`
lint → `26963c8` 归档 → `552148c` 措辞修正）。
绑定报告：[review.json](review.json)（`PASS_WORLD_PAGE`，13 步，
`recordedAt=2026-10-28T05:06:31.151Z`，记录时 head `2e5f177`、脏树摘要与本提交一致）。

**最终签字：本批通过。上一轮两项 P2 关闭，B 批次可确认通过；整体 CI 尚未闭环。**

## 关闭的两项 P2

1. **SPA 进入 `/world` 不隔离**：从 `/`（无 COOP/COEP 头）经客户端路由进入时，
   既有文档不会因 `/world` 的响应头获得隔离。修复=挂载自检失败整页重载一次
   （`sessionStorage` 护栏防循环；`StrictMode` 二次挂载不再起会话）。复核实测：
   软导航后自动重载，隔离生效，护栏清除。
2. **缺响应头时降级静默**：原实现把降级提示写进 `note`，而 boot 成功会清空
   `note`，用户看不到降级事实。修复=独立 `isoWarning` 状态，持续显示。复核实测：
   缺头环境只重载一次，降级告警持续可见。

## 复核方独立实跑

- SPA 进入后自动重载：`crossOriginIsolated=true`、`navigationType=reload`、护栏清除。
- 缺响应头环境：仅一次重载，降级告警不被 boot 清空。
- 15 个源码摘要全部与签字树匹配（`review.json:browserSource.sha256`；本地
  `sha256` 复核无差异）。
- 前端 565/565、双 tsc、`npm run lint` 通过（lint 仍有 warning，无 error）。
- `world-browser` 与 `origin/world-browser` 一致，工作树干净；复核用服务已停止。

## CI 归因与下一步

B 单树（`552148c`）：

- `python -X utf8 backend/scripts/check_world_interface_baseline.py` 在
  `export_world_protocol.py --version v2 --check` 处以
  `generated artifact drift: api-contract.json` 退出 1。差异集中在 `get_context`：
  已提交契约含 `frozen_work_missing` / `frozen_work_corrupt` 与对应 notes，
  本树生成器不产出。
- `python -X utf8 -m pytest -q`（backend）：848 passed / 75 failed，失败全部在
  `test_world_protocol_v2_{contract,revision,export}`。
- 根因：B 在 `88311b2` 镜像了 A 的 R1 候选契约，但 `world-browser` 的
  `backend/app/schemas/world/v2` 仍停在 `cabb04c`，未含 A 的 `4739ae4`。
  A worktree（`world-server`）同命令 `--version v2 --check` 退出 0。
- 前端作业：565 + lint + build 在本树通过（lint 债已在 `62e9f2d` 清除）。

按分工约定 §2.2，下一步由 A 在临时集成 checkout 组合
**A=`3734a52` ＋ B=`552148c`**，收绿 `backend` 与 `world-interface`；无需提前合并
开发分支。整体 CI 在集成验收前不闭环。

## 签字边界

签字范围仅为 B 端世界页批次（含 SPA 进入隔离轮与前端 lint 清理）。不含：

- A 端 Python 契约与 `world-server` 实现；
- 双方共同摘要冻结（本轮无契约变更，`contract-digest.json` 未动）；
- H2 在真实 SQLite 上的刷新/接管、fencing 与旧持有者写拒绝（仍未运行）；
- A3 整体验收与最终整链真实模型验收。
