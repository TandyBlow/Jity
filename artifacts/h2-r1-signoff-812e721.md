# A 端 R1 候选最终复验

日期：2026-10-27。复核与签字：当前 B 验收任务。
实现提交：`812e721011b606ea01437fe711ebeb33abde0a4f`。
候选实现链：`4739ae4` → `fafc859` → `812e721`；交付记录包含 `ecdb9a9` 及本笔追加说明。

**最终签字：通过。P1/P2 均已关闭，未发现遗留的 A 端候选验收阻断，允许进入 B 消费。**

## 关闭依据

- 响应版本为 2，状态模型/创建模板版本为 1，轨迹格式版本为 1，各自独立。
- TraceFormatVersion 已恢复 Annotated[Literal[1], BeforeValidator(_integer)]。
  布尔 true 在标量、TraceDocument、实际 validate_trace 工具及 JSON Schema 一致拒绝。
  数值为整数的浮点 1.0 在实际轨迹工具及 JSON Schema 仍通过，没有扩大限制。
- 新增专项负例与 bool_trace_version 变异项均实际运行通过。
- 本笔相对 ecdb9a9 仅改版本守卫、负例及交付文档，共 3 文件；导出物和 B 消费代码
  无 diff。实际候选包含前轮已审查的事务进度实现，其范围差异已在交付记录明示。

## 本轮独立实跑

- 聚焦契约、恢复契约与轨迹格式：181 passed，4.54 秒。
- 15 项独立版本断言全部通过，另独立核对浮点 1.0 在工具/JSON Schema 的一致接受。
- v1/v2 导出 --check 均退出 0，确认漂移、manifest/artifact 哈希与 A 自身 pin 一致。
- git diff --check ecdb9a9 812e721 通过。
- 从 A/backend 执行 `python -X utf8 -m pytest -q`：**1410 passed，287.24 秒**。

独立探针证据（已归档入仓）：[r1-review/812e721_probes.json](r1-review/812e721_probes.json)。
测试源码为同目录的 [r1-review/fafc859_probes.py](r1-review/fafc859_probes.py)，
此轮对修复后实现重新运行，15 项全过。

前轮已实际复跑：Python 契约 v1 109/v2 374、tsc 均通过；旧 B 的 TS 契约及轨迹红项
由响应版本守卫导致。在临时消费者副本仅将版本守卫改为 2 后，103/103 通过。
本笔导出物及 TS 消费代码零变更，未重复这些不受本笔影响的检查，也未宣称实际 B
已经消费新版接口。

## 固定摘要与签字边界

候选摘要保持：

```text
902918016f2bf7eff4cd1afd52da4ca96defdb5ee4082f171fda987de86680c2
```

B 仍在 `8b08057`，原摘要 pin 保持 `abda4555…`。本次没有修改 A 或 B 业务实现。

签字范围仅为已复核的 A 端 R1 候选交付。下一步 B 成套消费共享物、七项版本/pin
同步面、完整 rolls/progress、DFS/三态恢复调度及 reaction-d20-v1 正式规则。
此签字不代替 B 消费验收、双方共同摘要冻结、新版 B 控制器的真实 SQLite 完整 H2
联调或 A3-2 整体验收。
