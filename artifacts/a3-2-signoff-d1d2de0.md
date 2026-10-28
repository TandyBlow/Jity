# A3-2 关闭签字：固定组合 `d1d2de0`

日期：2026-10-28。签字：用户复核后同意关闭 A3-2，并冻结本轮约定的 H2 验收范围。

实现组合：A=`1ef34e7`（`3734a52` + 联合验收记录）＋ B=`21a95f0`（`552148c` +
两处 H2 harness 修复），merge **`d1d2de0cf2805d0f3ce1d182cde57821800d3bef`**，
验收树 **`6f16783c834b758d4f8a907f7a972e1836e0ed16`**，契约摘要
`902918016f2bf7eff4cd1afd52da4ca96defdb5ee4082f171fda987de86680c2`。

**最终签字：通过。A3-2「HTTP 刷新与接管联调」在本组合上关闭；本轮约定的
H2 验收范围冻结，冻结对象为该组合、归档提交 `a41a9d4` 及其 manifest。**

## 一、用户独立核对项

- 归档哈希：`manifest.json` 的 14 个文件哈希与入库字节一致，manifest 自身
  SHA-256 为 `1a92a165740a861cf8a8b89504bd54a730bdc9d27dfbe5a3de8ed64b64efe21d`；
- 源码身份：运行前后一致，`source_unchanged_during_run.matchesBaseline=true`；
- 10 个 phase 的状态与报告一致，8 组启动/停止配对；
- 四个数据库（`positive`/`missing`/`corrupt`/`group`）的提交去重、副本与摘要证据；
- 35 条冻结行中仅 `corrupt.db/world_1` 的 1 条按设计不匹配，其余 34 条
  `sha256(action_bytes)` 与 accepted 哈希相等；6 条候选与 3 个 settled 单元
  摘要全部重算一致；
- 远程 CI run `40649575022` 绑定 `a41a9d4`，backend / frontend / world-interface
  三作业全部 success。

## 二、关闭依据（对照 A3-2 关闭标准）

关闭标准：**指定 A/B 提交组合完成 H2，保留请求绑定、原文字节/候选哈希和
迟到围栏证据。**

| 条件 | 证据 |
| --- | --- |
| 指定 A/B 提交组合 | 固定 `d1d2de0`，单 checkout 同时跑 harness 与服务，源码身份运行前后一致 |
| 完成 H2 | main（多源 DFS 恢复 + 保存骰点 + 1 次提交）／接管（`claim_fenced`×2、`stale_epoch`×1、epoch 1→2→3、1 次副本+restore+提交）／successor（两点各一次提交、原始 Δ 顺序完整）／post-restart（同库、栈与骰点身份存活）／三种损坏按声明码停止 |
| 请求绑定 | 每世界 `commit_point` 数 = 非根提交数（1/1、1/1、2/2、0/0），`requestId` 唯一，幂等表无 `inputText`/`claimToken` |
| 原文字节/候选哈希 | 34/35 冻结行字节哈希相等，唯一不匹配是刻意注入；候选与 settled 摘要全部一致 |
| 迟到围栏 | 旧 claim 提交/续期被拒，旧租约迟到写入 `stale_epoch`，新持有者取得新 claim 与新 epoch |

证据目录：[artifacts/h2-integration-d1d2de0](../../artifacts/h2-integration-d1d2de0/README.md)；
冻结记录：[artifacts/h2-freeze-d1d2de0.json](../../artifacts/h2-freeze-d1d2de0.json)。

## 三、冻结范围与边界

冻结范围：**本轮约定的 H2 验收矩阵**，即上述固定组合下的刷新、接管、围栏、
后继接续、重启持久化与三种损坏检查。

不含（不由本次冻结扩张）：

- 120 秒 TTL 自然到期后的接管时序——本矩阵用 release/acquire 的 epoch 交接；
- 真实浏览器页面、B3 全量评估、真实模型整链；
- 旧冻结记录 `artifacts/h2-freeze-6b809dc-0cb1951.json` 保留其原有范围，不被
  本次替换或扩大；接口基线 `e3b197a`/`480d950c…` 同样独立。

## 四、签名边界

本次签字只确认 A3-2 关闭与上述 H2 范围冻结，不代表：

- 世界内核正确性、A3-1 既有验收范围的重新判定；
- 任何后续提交自动属于冻结对象——冻结以 `d1d2de0`（实现）与 `a41a9d4`
  （归档）为准，之后的文档提交不改变冻结内容；
- 后续若修改 A3-2 涉及的产品源码、契约或 harness 断言，需重新固定组合并重跑。
