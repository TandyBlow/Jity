# 合并前组合验收：A=`9321409` + B=`cd077a2`（2026-10-29）

独立 detached 集成检出（不提前合入开发分支），合并提交 `9892089`，
tree `28d75e154c0ef6ac9677f23f0264b7172b966f8e`。冲突三处均按目录归属解决：

| 文件 | 解决 |
|---|---|
| `.gitattributes` | 并集（A 的 storage SQL/H2 归档规则 + B 的 b3-short/rule-facts 规则） |
| `backend/app/schemas/world/v2/requests.py` | 取 A 侧（backend 归 A；两侧行为代码相同，仅注释措辞差异） |
| `design/browser-world-state-workflow.md` | B 的开发方向更新引用 + A 的 v0.4.2 版本头 |

## 检查结果（全部 PASS）

| 检查 | 结果 |
|---|---|
| 后端全量 pytest | 1412 passed（354s） |
| `npm ci`（干净安装） | 成功 |
| `npm test` | 34 文件 603 项全过 |
| `npm run lint` / `npm run build` | 通过（既有 warning，见下） |
| 统一入口 `check_world_interface_baseline.py` | PASS：TS 契约 38 项、TS 轨迹 65 项、四类破坏探针全部拒绝（CRLF/响应字段/动态摘要/gate 处理） |
| A4 固定场景执行器 | PASS：T01×2 + T03×2 真实 HTTP/SQLite、2 次重启回读、12 条已登记漂移照旧 |
| B transport 检查（aPath=集成树） | PASS：A=B=`9892089`、CORS 精确 origin、2 浏览器 root flow、h2-history 6 点 6 读、rawDeltas 匹配独立期望、源码运行前后不变 |

**关键确认：A 分支单独运行时 TS 契约红 35 项（旧 B 消费守卫钉信封
schemaVersion=1）在本组合树消失**——B 的新消费层（`88311b2` 起的版本同步）
接入后守卫已是 `schemaVersion !== 2`，与契约产物一致。契约摘要不变：
`902918016f2bf7…`，前端 pin 与生成物一致。

## 覆盖矩阵（共同轨迹 T01–T09）

| 层 | 覆盖 | 证据 |
|---|---|---|
| 离线轨迹核对（模板/捕获/断言/独立摘要） | 全部 11 份（T01–T09 含 T02-empty、T03-collapse）×2 样本 | 统一入口 Python 426 项 + TS 契约 38 + 轨迹 65 |
| 真实 HTTP 固定输出整链 | T01×2、T03×2（SQLite 持久 + 重启回读）；T01 场景完整 roster 六点历史链 | 执行器报告 + transport 报告 history 子检查 |
| 浏览器内 B 未改 transport/控制器 | T01 root flows ×2（claim 回执三元组、fresh requestIds、根 gate 清理、读稳定） | transport 报告 rootFlows |
| 真实 TTL 到期 | world-server `d4e0dd3` 批次（A 侧独立，三重复×三路径） | artifacts/world-ttl-realtime.json |
| H2 完整恢复验收（刷新/接管/围栏/损坏注入） | 冻结于组合 `d1d2de0`（A=`1ef34e7`+B=`21a95f0`），**本组合未重跑** | artifacts/h2-integration-d1d2de0/ |

**缺口（非本组合新增，历史如此，不阻断组合验收）**：T02/T04–T09 无真实
HTTP 固定输出整链（运行时路径由单元测试与离线轨迹覆盖）；完整 H2 与真实
模型整链按原计划另行验收。

## 阻断清单

无阻断项。非阻断登记三项：

1. `t03.scenario.ts:487` unused `candidates` 与既有 `useBrowserAutoPlay`
   hook warning——均在 B 基线 `641380a` 前已存在，非本组合引入；
2. T01 s1–s4 断言漂移 12 条仍按登记豁免，刷新属接口基线修订待双方；
3. H2 完整验收绑定旧组合 `d1d2de0`；若其后任一侧产品源码/契约/harness
   断言变更，须按冻结记录重固定组合重跑。

## 可复跑命令（在集成检出根目录）

```sh
python -X utf8 -m pytest -q            # 在 backend/
npm --prefix frontend test
npm --prefix frontend run lint
npm --prefix frontend run build
python -X utf8 backend/scripts/check_world_interface_baseline.py
python -X utf8 backend/scripts/check_world_http_scenarios.py
node frontend/scripts/review-world-a4-transport.mjs . artifacts/world-integration-a9321409-cd077a2/transport-report.json
```

本目录两份 JSON 为集成树实跑产物（executor-report 的 A 身份即合并提交
`9892089`；transport-report 的 A/B 均为 `9892089`，其 A.status 字段如实
记录了执行器先行重跑导致的 `artifacts/world-http-scenarios.json` 变更——
运行器自身产物，不在源码身份清单内）。
