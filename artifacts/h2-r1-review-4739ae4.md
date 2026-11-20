# A 端 R1 候选独立复核

日期：2026-10-27。复核者：当前 B 验收任务。

后续状态：本报告的版本 P1 已在 fafc859 修复并经独立复验关闭。
修复轮结果见 [复验报告](h2-r1-review-fafc859.md)，最新结论见
[最终签字](h2-r1-signoff-812e721.md)；本文件保留首次复核的历史结果。

复核实现：`4739ae4dbce284c7c73a5ca5efeebf35217a4f9c`，候选父提交 `3c81ad6`。
检出包含其文档提交 `0042528ba3ce5e33bee836e9ecf37ef8d818cc32`，与本次拉取的
`origin/world-server` 一致。B 保持 `8b08057`，未更新消费代码或摘要 pin。

**结论：不按此前锁定的 (a) 要求签字通过。** 恢复事实与事务实现的已检查路径未发现
新的功能阻断；有一项必须修复的版本问题，并且实际交付范围与原候选约定不同。
本次没有宣布共同基线冻结、A3 或完整 H2 关闭。

## P1：破坏性恢复响应仍使用旧 schemaVersion，未执行已锁定的 1→2

位置：A 工作树 `backend/app/schemas/world/v2/base.py:18`、`:23`，
`backend/app/services/world/control.py:62`；新必填字段在
`backend/app/schemas/world/v2/work.py:181` 起定义。

候选新增必填 rolls/progress，但 Envelope 及实际响应仍为 schemaVersion=1。
以真实 SQLite 服务产生响应、用 B 当前导入的旧 ContextResponse schema 验证：普通
context 被接受，带新冻结恢复载荷的 context 才被拒绝。这不是约定中的首响应版本
拒绝；构建/轨迹摘要 pin 也没有替代线上版本字段的这一行为。

修复必须包含：

- Envelope 常量和 Literal 同步为 2，运行时响应组装引用同一来源，避免独立 SCHEMA=1。
- 拆开版本别名的现有复用：`requests.py:84` 的 WorldInitialTemplate.schemaVersion
  与 `trace.py:86` 的 traceFormatVersion 当前都使用响应 SchemaVersion。
  模拟只将共享别名改为 Literal[2] 时，模板填 1 被字段拒绝，填 2 又被
  WorldInitialState 的状态版本 1 校验拒绝；traceFormatVersion=1 也被拒绝。
- 状态模型与创建模板保持版本 1，轨迹格式保持版本 1；响应版本为 2。
- 同步受影响响应夹具、测试、导出物和新摘要；不得全局替换 schemaVersion。
- 报告明确旧 B 拒绝新版响应，不将“不宣称兼容”代替具体版本策略。

原始独立证据（已归档入仓）：[r1-review/probes.json](r1-review/probes.json)、
[r1-review/version-alias-probe.json](r1-review/version-alias-probe.json)，
生成脚本为同目录的 `probes.py`、`version_alias_probe.py`。

## 交付范围差异：实际候选包含运行时事务与消费 pin

相对 `3c81ad6`，候选为 40 文件、2496 增行/111 删行。除契约/夹具/导出外，还新增
world_progress_repository.py、services/world/progress.py，并修改存储、控制服务、
judgment 服务与应用入口；同时更新了 frontend 的 contract-digest.json。
因此不能将其描述为原约定的纯契约 (a)，也不能要求该实际提交的 --check 只在 pin
层红。本次已实际审查这些事务路径并运行相关测试，但原范围与本次扩展交付必须在
交付记录中明确对齐，不能以测试通过代替范围确认。

按指定名字搜索，app 内 FrozenGroupView(/PointRecoveryView( 仍仅有类定义；真实
恢复组经已有字典投影和 RecoveryView 校验形成。本次没有以这个 grep 结果代替对
进度读取及写入路径的审查。

## 实际验证

- 聚焦新增恢复契约、进度、HTTP 测试：91 passed，33.40 秒。
- 从 A/backend 执行 `python -X utf8 -m pytest -q`：1406 passed、1 failed，324.29 秒。
  唯一失败是 test_packaged_schema_matches_frozen_specification，原因见下一节。
- 共同入口 `python -X utf8 backend/scripts/check_world_interface_baseline.py`：PASS。
  包含 v1/v2 导出、Python 契约 109/373、TS 类型、契约 38、轨迹 65，四类破坏探针
  均被拒绝。未把这个入口的通过写成服务/H2 通过。
- A v2 导出 --check：退出 0。漂移、manifest/artifact 哈希和 A 候选自身 pin 一致。
- `git diff --check 3c81ad6 4739ae4`：通过。
- 独立探针 12 项全部符合预期：旧 B 接受普通响应但拒绝新恢复载荷、四种非法三态
  组合在 Python 与 JSON Schema 均拒绝、T07 stack=[person_f,person_e] 且
  frontier=[person_f]、missing/corrupt 夹具走操作声明表、四种恶意进度形状均返回
  frozen_work_corrupt/409 且不重掷。
- 额外版本耦合模拟复现创建模板和轨迹格式误升级风险；未修改候选模型来执行模拟。

代码审查核对了必填性、roll/threat 双向唯一绑定、出向 rollRefs、created 接受树、
reused 不翻转原 admitted、有序 DFS 与 frontier、closed/staged 拒绝，以及同事务
保存目标/roll/行动原文/进度、接管保留事实、恢复缺损拒绝及终结清理的路径。

## 全量测试唯一失败的归因：既有 Windows SQL 检出换行

`backend/app/database/world_storage_v2.sql` 是 i/lf、w/crlf；共享 storage-contract.sql
有 text eol=lf 规则。前者缺少该规则。两份 Git HEAD 原始 blob 逐字节相同，且与
be87679 的 packaged SQL 相同；候选没有改动这些文件。

本机 packaged SQL 有 250 个 CRLF，归一化后与 Git blob 完全相同；Git blob SHA256：
`041bf83d4b7683c68ae5877f8c0ab9992bcb33399bd5a431655b0b19935a8831`。
临时用 Git 原始 LF 字节运行失败单测：1 passed，1.83 秒。随后恢复最初 Windows
工作副本字节，A tracked 工作树重新干净，仅保留原有 `_proj_create.json`。

这是既有跨平台检出问题，不记作 4739ae4 引入的功能回归。若要求 Windows 干净检出
全量一次全绿，应给 packaged SQL 添加精确的 text eol=lf 规则。没有声称本轮同一次
全量已得到 1407 passed。

## 摘要及后续边界

候选摘要：`bff913209dc3c91084912542b5ac7af8927b3e46f530ed162d2b759faf5d5afe`。
B 当前旧摘要：`abda455597e743f63da1c205ca7bc68044728c5f92a3cb7ae920440ef324eedd`。
修复响应版本后应重新计算候选摘要，再供 B 成套消费，不能提前冻结当前值。

B 后续需要同步共享物、恢复业务类型与 rolls/progress 消费、DFS/三态调度，并将
正式规则切到 reaction-d20-v1/target=11。七项版本/pin 同步不是完整消费任务。
之后固定新 A/B 提交，再运行新版 B 控制器对真实 SQLite 的完整 H2 刷新、接管、
当前与后继接续、多源/环/批量和缺损/迁移反例。

本次复核未运行完整 H2，未修改候选业务源码，未合并或提交 B 消费改动。
