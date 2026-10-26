# A 端 R1 修复轮复验

日期：2026-10-27。复核者：当前 B 验收任务。

后续状态：本报告新增的 P2 已在 812e721 修复并经独立复验关闭；
最新结论见 [最终签字](h2-r1-signoff-812e721.md)。本文件保留修复轮的历史结果。
实现：`fafc859bb6ab9f8ccde24e3a7455e52902e54116`；检出包含文档提交
`ecdb9a96ef4cce0fad6cef56b1185b6d609d4c40`，已执行 pull --ff-only 确认与远端一致。
B 仍在 `8b08057`，没有修改其消费代码或 pin。

**结论：前轮 P1 已关闭；新增一处 P2 类型校验回归，修复后再完成候选签字。**
本轮完整后端测试实际得到 1408 passed；不把旧 B 的版本拒绝记作 A 功能失败。

## P2：轨迹格式别名拆分时丢失整数守卫，布尔 true 被接受为版本 1

位置：A 工作树 `backend/app/schemas/world/v2/base.py:30`，消费者为
`backend/app/schemas/world/v2/trace.py:86` 和 `backend/scripts/world_trace_expected.py:116`。

本轮将 traceFormatVersion 从带 BeforeValidator(_integer) 的 SchemaVersion 改为
裸 Literal[1]。Pydantic 的 Literal 比较会接受 True 并归一成整数 1，即使模型启用了
strict=True。Python 轨迹入口首先用 TraceDocument 加载，之后仅校验请求/响应等
内容，不会再用整个 trace.schema.json 拒绝这个格式字段。

独立复现：

```python
data = json.loads(Path('design/world-protocol/v2/traces/T07.json').read_bytes())
data['traceFormatVersion'] = True
TraceDocument.model_validate(data)  # 成功，traceFormatVersion 被变为 1
validate_trace(data)                # 整条轨迹校验也成功
Draft202012Validator(trace_schema).validate(data)  # 拒绝：true 不是整数
```

旧整数守卫对 True 的拒绝也已独立确认。这是该修复提交引入的 Python/导出 schema
一致性回归，不是对浮点 1.0 的新限制；原 _integer 本就允许数值为整数的浮点数。

修复：保持轨迹版本独立，定义为
`TraceFormatVersion = Annotated[Literal[1], BeforeValidator(_integer)]`，并补充布尔 true
在 TraceDocument/validate_trace 与 JSON Schema 两侧均被拒绝的负例。
不需要重做版本轴设计或扩大到 B 业务代码。

证据与可重跑脚本（已归档入仓）：
[r1-review/fafc859_probes.py](r1-review/fafc859_probes.py)、同名 `.json`。
15 个独立断言中 13 个符合预期；另两个断言是上述同一 P2 在标量及实际加载入口的
复现，没有将它们计作两个独立缺陷。

## 前轮问题关闭情况

- 响应常量与 Literal 都为 2，实际运行时出口引用契约常量。实时普通 context 已在
  旧 B schema 的 schemaVersion 路径被拒绝。
- 创建模板和状态模型保持 1：真实 get_state 返回“信封 2、state 1、initial 1”；
  模板 1 可创建、模板 2 明确拒绝。轨迹格式 1 的正常样本可加载。
- 独立遍历 v2 JSON：293 个带 canonicalVersion 的数值版本节点（含 versions.json）
  均为 2，其余 58 个显式数值 schemaVersion 均为 1，未发现跨层误替换。
- SQL 新增精确 text eol=lf 规则，工作副本 i/lf、w/lf；此次全量不再出现前轮失败。
- server.md 已明确记录 4739ae4 实际包含事务运行时及 pin，不再冒称纯契约 (a)。
  前轮对事务路径的审查仍有效，本轮未重新声称交付范围从未扩展。

## 实际验证结果

- 从 A/backend 执行 `python -X utf8 -m pytest -q`：**1408 passed，299.78 秒**。
- v1/v2 导出 --check 均退出 0；漂移、manifest/artifact 哈希、A 自身 pin 一致。
- 共同入口分层：Python v1 **109 passed**、v2 **374 passed**、tsc 通过。
  TS 契约实际为 **35 failed / 3 passed**，入口在此退出；单独运行 TS 轨迹为
  **46 failed / 19 passed**。错误及间接断言失败均归因于旧 protocol.ts:35 拒绝响应版本 2。
- 为独立验证红项归因，在同一导入深度创建消费者临时副本，唯一改动是将
  `v.schemaVersion !== 1` 改为 `!== 2`，契约＋轨迹 **103/103 passed**。
  此探针未修改 A 或 B 源码，不代表 B 真实消费实现已经交付。
- `git diff --check 0042528 fafc859` 通过；A tracked 工作树干净，仅原有
  `_proj_create.json` 未跟踪文件。临时消费者副本已清理。

TS 归因证据：[r1-review/fafc859_ts_probe.py](r1-review/fafc859_ts_probe.py)、同名 `.json/.log`。

## 候选摘要与边界

新摘要：`902918016f2bf7eff4cd1afd52da4ca96defdb5ee4082f171fda987de86680c2`。
原 `bff9132…` 不再是当前候选摘要。

B 仍需成套同步共享物、七项版本/pin 同步面，以及恢复业务类型、完整 rolls、
sourceStack/三态调度和 reaction-d20-v1 正式规则。实际双方共同检查、冻结及新版
B 控制器对真实 SQLite 的完整 H2 仍未完成。

本次没有修改候选实现，没有提交 B 消费代码，没有以现有全量绿色掩盖独立反例。
