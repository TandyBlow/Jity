# 组合 `9892089` 的完整 H2 重跑记录

日期：2026-10-29。验收提交 **`9892089`**（tree
`28d75e154c0ef6ac9677f23f0264b7172b966f8e`），由 A=`9321409`（world-server）与
B=`cd077a2`（world-browser）合并而成；归档 tag
`integration/a9321409-bcd077a2`（tag 对象 `4a428262`，远端已推送）。
两个开发分支保持不动。

**本轮结论：组合检查及已声明链路通过；完整 H2 在该组合上通过**（用户此前的
「无阻断」结论限定于组合检查轮，本批补齐正式落地前的完整 H2 条件）。合并目标
与落地时机另行决定；真实模型整链仍单独验收。

## 一、组合与身份

| 项 | 值 |
|---|---|
| 验收提交 | `9892089f46790c691f0dd07e512c03a04ef36120` |
| 验收树 | `28d75e154c0ef6ac9677f23f0264b7172b966f8e` |
| A 侧 | `9321409`（world-server，A4 关闭记录） |
| B 侧 | `cd077a2`（world-browser，harness 夹具修复＋A4 transport 检查） |
| 归档 tag | `integration/a9321409-bcd077a2` → `9892089` |
| 契约摘要 | `902918016f2bf7eff4cd1afd52da4ca96defdb5ee4082f171fda987de86680c2`（未改，149 生成物） |
| 服务 | `app.world_app:create_persistent_world_app`，`--workers 1` |
| 数据库 | 四个新建隔离 SQLite：`positive.db`、`missing.db`、`corrupt.db`、`group.db` |

源码身份（完整哈希见 [manifest.json](manifest.json).sourceSha256）与
d1d2de0 轮一致（A 侧产品文件在两组合之间未变）；运行前后
`sourceUnchangedDuringRun=true`，工作树全程干净。

## 二、Phase 结果（10 调用、8 启停配对）

| Phase | 结果 |
|---|---|
| main（world A+D：多源组 DFS 恢复、提交、叙事、continuation；claim/stale 围栏；跨 epoch 接管并提交封存未提交点） | PASS_MAIN |
| successor（world B：封存点＋预约后继双基线恢复、两点各提交一次、无重复消费） | PASS_SUCCESSOR |
| build-frozen-case（world C：保存骰点的组中状态） | BUILT_FROZEN_CASE |
| post-restart（world C 服务重启：持久租约仍可续、恢复读取同事实） | PASS_POST_RESTART |
| frozen-missing / frozen-corrupt / frozen-group（行删除 / 行动字节损坏 / 活动组文本损坏各 1 行，恢复必须 STOP 于 frozen_work_*） | PASS_FROZEN_MISSING / PASS_FROZEN_CORRUPT / PASS_FROZEN_CORRUPT |

骰点为服务端真实 `reaction-d20-v1`，分支由服务端结果决定并如实记录；模型为
固定回答（transport fixture，非真实模型验收）。每个 phase 的 browser/server
head 均为 `9892089`（报告内断言钉定）。

## 三、数据库证据

[database-evidence.json](database-evidence.json)：4 库 10 世界只读核对——
每世界 `commit_point` 数＝非根提交数、`requestId` 无重复、幂等表无
`inputText`/`claimToken` 私有载荷、冻结工作 `sha256(action_bytes)`＝accepted
`actionContentHash`、候选规范摘要＝accepted `candidatesContentHash`、settled
单元哈希重算一致；重启前 `positive.db` 字节哈希与重启后同文件继续使用
（generation 6→7）。

## 四、与 d1d2de0 冻结记录的关系

[旧组合归档](../../artifacts/h2-integration-d1d2de0/README.md)（A=`1ef34e7`＋
B=`21a95f0`）保留原样、不被替换或扩大；本目录是**新组合**的完整 H2 证据。
两轮的 A 侧产品源码哈希相同，差异来自 B 侧消费层/harness 演进与本轮合并提交。
若此后任一侧产品源码、契约或 H2 harness 断言变更，须重新固定组合重跑。

## 五、复跑

编排器按 d1d2de0 轮同一脚本适配（仅改 pin 与输出目录），随本目录归档为
[run-integration-h2-d1d2de0-base.py](run-integration-h2-d1d2de0-base.py)；
在检出 `9892089`（或重建该合并）后放于 `<checkout>/.local/run_integration_h2.py`：

```sh
python -X utf8 <checkout>/.local/run_integration_h2.py
```

前置：工作树干净、`frontend` 依赖已安装（`npm ci`）。phase 报告、启停日志与
损坏注入记录的完整副本在本地 `.local/h2-integration-9892089-run/`（不入库）；
本目录文件按 [manifest.json](manifest.json) 的最终字节哈希绑定。
