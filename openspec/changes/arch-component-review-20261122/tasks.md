# Tasks: 组件设计评审

## 1. 评审（已完成）

- [x] 1.1 五个 reader 并行读完内核、语义结算、叙事与页面、持久化与同步、Python 预言机；组件地图与依赖方向落 `design.md`。
- [x] 1.2 瓶颈归因：串行模型调用占回合 72–82%；写放大为次要关键路径项；叙事质量属模型能力。
- [x] 1.3 小模型组合对照（同栈）：0.6B 单次 25.7 s / 0.6B 草稿+润色 56.4 s / 1.7B 单次 39.8 s，润色常原样复制草稿。

## 2. 候选修复（未执行，待用户选范围）

- [ ] 2.1 写放大：draft 直传 onPersist、只 clone 一次、IndexedDB 移出同步关键路径；先补 IndexedDB 测试。
- [ ] 2.2 删除死端口 `action-execution/port.ts`（仅测试 import）或接线。
- [ ] 2.3 architecture.md 纠偏：Python 两套语义（冻结 fixture + A2/A3 服务）与依赖图。
- [ ] 2.4 持久化测试：fake-indexeddb 后端用例，覆盖 revision CAS、租约、冲突、恢复。
- [ ] 2.5 可维护性拆分（可选）：controller point-updates、transport 协议域、schedule 分文件、session ProgressWriter、page hooks/组件。

## 3. 收口

- [ ] 3.1 `openspec validate "arch-component-review-20261122" --strict`；按用户选择执行 2.x 后归档。
