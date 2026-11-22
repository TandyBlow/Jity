# Design: 组件设计评审（2026-11-22）

## 组件地图与依赖方向

```
                    ┌─────────────────────────────┐
玩家输入 → page.tsx │ LocalGameSession (组合根, 706)│ 持久化 + 租约 + checkpoint
                    └───────┬─────────────┬───────┘
                            │             │
              ControllerDriver (1233)  CheckpointingTransport
                            │             │
                    schedule.ts (纯决策,1155)  LocalWorldTransport (1024, 31 ops)
                            │             │
                            └──────► state.ts (apply/merge/commit/replay)
模型端口:
  LocalGameModel (1242) ─► action / targets / results / updates / continuation
                        └► point-narration → narration-generation
其他:
  persistence/ (IndexedDB, 租约)   progress-sync/ (离线队列, CAS, 分叉)   backend/ (差分预言机 + A2/A3 服务)
```

依赖无环：`schedule ← controller ← session`，`state ← transport ← session`。四层切分（纯决策 / 纯状态 / 编排 / 组合）本身就是正确缝线。

## 每个组件的结论

| 组件 | 行数 | 结论 | 热点 |
|---|---|---|---|
| controller.ts | 1233 | 合理；adoptSuccess 264 行、六阶段顺序散在 4 个 case | 每 step 一次模型调用，墙钟由它决定 |
| schedule.ts | 1155 | 合理；纯函数，类型中枢 | 决策树 659 行；六阶段顺序两处编码 |
| local/transport.ts | 1024 | 合理；draft→commit 原子写 | 每次写 clone 全 record 两次 + 405 KB 快照落盘 |
| local/session.ts | 706 | 合理；「先存盘再消费」是架构不变量 | 写路径串行等 IndexedDB |
| game-model + semantics | 约 6.6k（非测试） | 任务分 lane 合理 | results 每组 1 次（×3 重试）、scene 每组 1 次、verifier 每点 1 次 |
| 叙事管线 + page.tsx | 1825（页面） | 接口分层合理；默认 auto 落回单次 instruct 写作 | 页面 23 个 state/16 个 ref；流式每 chunk 重建列表 |
| persistence + progress-sync | 880 + 1602 | 边界干净、可独立测试 | 持久化写放大；队列存整份快照（5 MB 配额）；IndexedDB 无单测 |
| Python | — | 文档与代码分叉 | 冻结的 11 模块 fixture 与可运行 A2/A3 服务是两套东西，architecture.md 只写前者 |

## 瓶颈归因（实测）

1. **回合 250–300 秒**：`timing-baseline` 15 个点共 139 次结算调用；updates 69 次合计 921 s（中位 11 s，最大 41.5 s），正常回合 108–178 s 中结算调用占 72–82%。D-018 把任务阶段从每组改为按点一次，方向正确。
2. **写放大**：每次 transport 写都全量 clone record（transport.ts:889）、clone 响应进幂等表（:918）、onPersist 再 clone（:921），session 等 IndexedDB 落盘后才让 driver 继续；单快照约 405 KB。比模型调用小，但在关键路径上。
3. **叙事质量**：不是组件问题。1.7B 基线五题里回声/凭空细节占主导（事实 1.4、风格 1.8、回声 2.2、完成度 1.6）。
4. **小模型组合对照**（同栈，5 题 × 3 次）：

| 臂 | 总时长 | 平均/次 | 平均 token | 备注 |
|---|---|---|---|---|
| 0.6B 单次 | 25.7 s | 1.7 s | 106 | 质量明显弱于 1.7B |
| 0.6B 草稿 + 0.6B 润色 | 56.4 s | 3.8 s | 209 | 比 1.7B 单次慢 42%，润色常原样复制草稿 |
| 1.7B 单次（交付基线） | 39.8 s | 2.7 s | 124 | 质量仍不达标但强于 0.6B |

结论：小模型层层润色不是免费的提速；两次 0.6B 调用已经比一次 1.7B 慢，五层更慢。8 GB 显存与仓库的「不并发解码」契约也排除了并行多模型。

## 拆分判断

**不能靠拆分解决的**：回合延迟（串行调用数 × 单次耗时）、叙事质量（模型能力）、泛句事实（模型能力）。per-stage executor 会把 schedule 已有的阶段顺序复制到更多文件，耦合不减。

**能靠拆分/修复解决的**：
1. 写放大：draft 直传 onPersist、只 clone 一次、IndexedDB 移出同步关键路径（需保「先存盘再消费」语义，改为异步 drain + 可观测）。
2. 死代码：`action-execution/port.ts` 只有测试 import，删除或接线。
3. 文档纠偏：architecture.md 的 Python 段改为「冻结 fixture + A2/A3 服务」两套；补依赖图。
4. 测试缺口：IndexedDB 后端无 Vitest 覆盖（无 fake-indexeddb）；持久化 880 行只有约 57 行直接用例。
5. 可维护性拆分（不改行为）：controller 六阶段抽 point-updates.ts、transport 按协议域拆 handler、schedule 按职责拆文件、session 抽 ProgressWriter、page 拆 hooks/组件。

## Risks / Trade-offs

- 大拆分与 G8 封存证据：任何行为改动都要重跑 20 输入；纯结构拆分可保行为但 review 面变大。
- 写放大修复会影响 checkpoint 不变量；必须先补 IndexedDB 测试再动。
- 60/300 门槛不改（D-014/D-016/D-017）；延迟改进只能来自调用数、提示大小、模型速度。

## NOT in scope

- 并行组结算（需要第二个引擎/权重，8 GB 不允许）。
- 五个 50M 模型分层叙事（对照已给出反例；50M 中文 GGUF 当前不可得）。
- 换模型/微调（D-020 的 HPC 对照，Slurm 恢复后再做）。
- 事实门（用户未决定，D-004 保持）。
