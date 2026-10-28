# 联合接口验收签字：A=`3734a52` ＋ B=`552148c`

日期：2026-10-28。状态：**用户已签字同意，范围仅限本组合的联合接口验收**。
本文件是验收记录的签字页，不改变契约、不冻结基线、不合并开发分支。

## 一、被验收的组合

| 项 | 值 |
|---|---|
| A 输入 | `world-server` @ `3734a52`（`fix(world): keep the replaced round's recorded conclusion`） |
| B 输入 | `world-browser` @ `552148c`（`docs(world): correct the r10 archive wording`） |
| 共同基点 | `79f8120`（`agent`）；双方对 `design/world-protocol/v2` 的字节完全相同（A 的 `812e721..3734a52` 对该目录零 diff，B 镜像同一候选） |
| 组合提交 | `44996f3a5413b0bcd446480e879b1115132816ce`（`git merge --no-ff 552148c`） |
| 验收树 | `f2fbee118fa21f0aaf1f03fa2be7953068d96b64` |
| 签字页所在提交 | `integration/a3734a52-b552148c` 分支头，及 `world-server` 上的同文镜像；以 `git log -1 -- design/world-engine-reports/joint-acceptance-f2fbee11.md` 为准（本表不写死自身哈希，避免自指） |
| 契约摘要 | `902918016f2bf7eff4cd1afd52da4ca96defdb5ee4082f171fda987de86680c2`（manifest 与前端 pin 一致） |
| 环境 | Windows 11 / Python 3.12.3 / Node 22.20.0 / npm 10.9.3，fresh `npm ci`（385 packages） |

组合只存在于临时分支 `integration/a3734a52-b552148c`，按
[分工文档](../browser-world-state-work-split.md) §2.2 建立；`world-server` 与
`world-browser` 开发分支保持各自历史，未合并、未改写。

## 二、冲突裁决（两处，均为契约权威判定）

1. `backend/app/schemas/world/v2/requests.py`：取 A 版——`RollOutcome` 来自
   `judgments`（含 reaction-d20-v1 的 `target=11` 约束），创建模板保留
   `StateSchemaVersion` 轴；B 侧本地 `RollOutcome` 副本与其注释措辞丢弃。
   wire 契约在两侧逐字节相同，因此无消费方可观察的变化。
2. `.gitattributes`：并集——A 的 packaged SQL `eol=lf` 规则 + B 的
   `artifacts/h2-full-6b809dc-0cb1951/**`、`artifacts/b3-short/**`、
   `artifacts/rule-facts/**` 证据字节规则。

## 三、证据

集成树本地实跑（`44996f3`，仅后续文档提交）：

- `python -X utf8 backend/scripts/check_world_interface_baseline.py` → **exit 0**
  - v1、v2 导出 `--check` 均退出 0
  - Python v1 **109 passed**；v2 **376 passed**（77.60s）
  - `typecheck:world` 通过；TS 契约 **38 passed**；轨迹 **65 passed**
  - 4 项变异全部被拒：`generated_crlf`、`response_field`、`dynamic_digest`、
    `gate_handling`；源工件未被修改
- 全量 backend：**1412 passed**（505.35s，0 failed）
- 全量前端：**565/565**；`npm run lint` 0 error；`npm run build` 成功（9 路由）
- `git diff --check` 通过

远程 CI（GitHub Actions）：

| run | head | 结果 |
|---|---|---|
| [`40641906544`](https://github.com/TandyBlow/Jity/actions/runs/40641906544) | `2019f9b`（merge + 验收记录） | backend / frontend / world-interface 全部 success |
| [`40642523016`](https://github.com/TandyBlow/Jity/actions/runs/40642523016) | `5a34e3c`（追加 CI 记录） | backend / frontend / world-interface 全部 success |

这是本组合首次在远端 CI 上闭环：`world-server` 单树（`3734a52`）此前
frontend 与 world-interface 按设计失败（B 的七项版本/pin 同步未合并）。
`world-browser` 单树（`552148c`）仍因 v2 `api-contract.json` 漂移失败
（backend 在 `cabb04c`，A 的 `4739ae4` 未合并）。集成分支是当前唯一三作业
全绿的树。

## 四、签字内容

用户于 2026-10-28 独立核对以下各项后签字同意：

- 合并 `44996f3` 的双亲、验收树 `f2fbee11…` 与通报一致，冲突裁决正确。
- 契约无变化，摘要仍为 `90291801…`；集成树 v1/v2 导出检查通过。
- 远程 CI `40642523016` 确实绑定 `5a34e3c`，三个作业全部成功；日志中的
  **1412、109＋376、38＋65、四项变异拒绝**均吻合。
- 后续提交仅改验收文档；集成分支与远端一致、工作树干净。

## 五、范围边界

**签字范围是 A=`3734a52` ＋ B=`552148c` 的联合接口验收。** 它只宣告：在同一
集成树下，双方契约、Python 内核、TS 消费、轨迹与共同入口一致，且远端 CI
三作业全绿。

不在本次签字范围内（仍待验收，不得据本文件宣称通过）：

- A3-2 整体验收。
- H2 在真实 SQLite 上的刷新/接管、fencing、旧持有者迟到写入拒绝。
- 真实模型整链与叙事质量。
- B 侧浏览器行为的具体签字仍归 B 的批次记录：`world-browser` @ `1dc2272`
  的 `artifacts/world-page/signoff-552148c.md`（该提交在 B=`552148c` 之后仅
  追加签字文档，不在本组合内，故本树无此文件；本树的
  `artifacts/world-page/{README.md,review.json}` 已含该轮 r10 证据）。

本文件不构成冻结。此前的 H2 冻结记录（`artifacts/h2-full-6b809dc-0cb1951/`、
`design/world-engine-reports/h2-recovery*.md`）继续保留各自原有范围，不被
本次验收扩大或改写。`design/world-protocol/v2` 的 A0/B0 基线（`e3b197a`、
摘要 `480d950c…`）同样是独立基线，本文件不改动它。

## 六、下一步

1. **固定该集成组合**，在真实 SQLite 上跑 H2（刷新、接管、fencing、旧持有者
   写入拒绝）与 A3-2。
2. 通过后再决定冻结；只有经过验证的组合才可以成为新基线。
3. 在冻结决定之前不合并开发分支，也不从本组合切出新基线。

## 七、复现

```powershell
git clone https://github.com/TandyBlow/Jity.git jity-integration
cd jity-integration
git checkout integration/a3734a52-b552148c   # 分支头即签字页所在提交
git rev-parse HEAD^{tree}
npm --prefix frontend ci
python -X utf8 backend/scripts/check_world_interface_baseline.py
python -X utf8 -m pytest -q
npm --prefix frontend test
```

签字页所在提交的树比验收树多几处文档记录（merge 之后的 CI 记录、本签字
页、server.md 的引用段）。验收树 `f2fbee11…` 对应提交 `44996f3`，其数字即
第三节所列；该提交未重跑，因为它只增删 Markdown。
