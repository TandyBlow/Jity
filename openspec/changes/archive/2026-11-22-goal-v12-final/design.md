# Design: goal-v12-final

## Context

`design/goal/goal.md`（v11）同时承担两个角色：产品终态说明与 G1–G8 执行路线。两者混写后，goal 变成阶段计划，读者无法一眼看到「做完是什么样」。用户要求 goal 只写最终目标。相关的终态约束已在决策里：D-001 运行期权威、D-004 叙事原样输出、D-010 设备、D-019 签字放弃、D-022 叙事质量路线待定、D-023 移动端与分档门槛待定、D-024 延迟口径待定。

## Goals / Non-Goals

- Goals：goal.md 只描述终态（可玩、两档设备、本地推理、延迟、质量、同步、证据），并把未决项以决策编号链接；`CLAUDE.md` 与 `design/README.md` 指向新文本。
- Non-Goals：不改产品代码、验收协议、决策记录与任务账本；不把未决项写成已定结论。

## Decisions

1. **终态与路线分离**：goal 写终态；路线、阶段与能力状态由 `ledger.md`、`decisions.md` 与归档的 OpenSpec changes 承担。替代方案（继续在 goal 里保留 G1–G8）会让 goal 再次退化为施工计划，用户已明确否掉。
2. **未决项用链接而非内联**：D-022/23/24 尚未裁决，goal 只写约束与指向，不复制参数，避免两处漂移。
3. **不新增 spec delta**：产品行为不变，`.openspec.yaml` 设 `skip_specs: true`；规格仍由 `openspec/specs/browser-world-kernel` 与 `product-page` 描述。

## Risks / Trade-offs

- [goal 与账本漂移] → goal 只写终态条件；能力状态一律引用 `ledger.md`。
- [旧读者按 G 编号找路线] → `goal.md` 增加「与 v11 的关系」一节，指向 ledger、归档 change 与 tag。
- [未决项被误读为已定] → 单独「未决项」列表，每项标 `pending-user` 与决策编号。

## Migration Plan

1. 重写 `design/goal/goal.md`；2. 更新 `CLAUDE.md` 与 `design/README.md` 的指向；3. `openspec validate --strict`；4. 归档 change、打 tag `goal-v12-final-20261122`、提交。回滚：恢复 goal.md 的 v11 版本即可，无数据迁移。

## Open Questions

- D-022：叙事质量走定向微调、自修复、换运行时，还是改门槛/收尾。
- D-023：移动档的时间与质量门槛。
- D-024：是否把「再次可行动 ≤60 秒」定为硬门槛，并授权交还时机与调用数的调度改造。
