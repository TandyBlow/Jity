# R1 复核探针重跑说明

本目录归档 H2 读取契约 R1 复核（2026-10-27）的独立探针脚本与结果，被
[h2-r1-review-4739ae4.md](../h2-r1-review-4739ae4.md)、
[h2-r1-review-fafc859.md](../h2-r1-review-fafc859.md)、
[h2-r1-signoff-812e721.md](../h2-r1-signoff-812e721.md) 引用。
脚本原以绝对本地路径运行，入库时改为环境变量可覆盖的相对默认值。

## 探针与提交对应

| 脚本 → 结果 | 轮次 | A 侧检出 | BROOT 语义 | 历史结果 |
|---|---|---|---|---|
| `probes.py` → `probes.json` | 首轮复核 | `4739ae4` | 旧 B schema（响应版本仍为 1，`8b08057` 时代） | 12/12；顶层 `schemaVersion: 1` 是被测实现当时的值 |
| `version_alias_probe.py` → `version-alias-probe.json` | 首轮复核 | `4739ae4` | 不使用 BROOT | 全过（版本别名共享的模拟，佐证 P1 修复必须拆轴） |
| `fafc859_probes.py` → `fafc859_probes.json` | 修复轮 → 被签字轮覆盖 | `fafc859` → `812e721` | 旧 B schema | **当前内容 15/15 是 `812e721` 轮重跑的输出**；`fafc859` 轮原始输出（13 项符合预期 + 2 项 P2 复现失败）已被同名覆盖、未保留——即下文注意事项 1 的实际先例 |
| `fafc859_probes.py`（改名副本）→ `812e721_probes.json` | 最终签字 | `812e721` | 旧 B schema | 15/15 |
| `fafc859_ts_probe.py` → `fafc859_ts_probe.json` / `.log` | TS 归因 | `fafc859` | 不使用 BROOT（在 worktree frontend 下建临时消费者副本改守卫） | 103/103 |

## 重跑命令与环境变量

脚本默认相对路径按 `.local/` 布局写；在本目录（`artifacts/r1-review/`）下运行**必须**显式指定两个变量：

```bash
WORLD_SERVER_WORKTREE=<A 侧 worktree 根，检出对应提交> \
JITY_REPO_ROOT=<B 仓库根，schemaVersion=1 时代的检出> \
python fafc859_probes.py
```

`probes.py` 与 `version_alias_probe.py` 同理；`fafc859_ts_probe.py` 只用
`WORLD_SERVER_WORKTREE`。依赖 A 侧 backend 运行环境（jsonschema、pydantic、
fastapi 及 `backend/tests` 的夹具辅助函数）。

## 注意事项

1. **必须复制整个目录到临时位置后运行**：结果脚本把输出写到脚本自己同目录
   （`Path(__file__).with_name(...)` / `with_suffix('.json')`），在本目录直接运行会
   覆盖上表已归档的历史结果文件。`fafc859_probes.json` 已经这样被覆盖过一次（见上表）。
2. **失败不改变退出码**：全部脚本恒 exit 0。验收必须读取输出 JSON 的
   `passed` 计数与 `failed` 数组，不能以退出码判定通过。
3. **BROOT 必须指向响应版本仍为 1 的 B 检出**（`8b08057` 及之前）。指向
   `88311b2`（B 已同步响应版本 2）之后的检出时，
   `old_B_rejects_ordinary_first_response_version` 必然失败——2026-10-27 实跑确认
   得 14/15。这不是被测实现的回归，而是探针前提（旧 B 拒绝新版响应）已随 B 同步而失效。
4. `probes.py` 的损坏注入组（`stack_nested_object` 等）直接改写运行时 SQLite 的
   `world_group_progress` 行，只应在临时副本的临时目录数据库上进行。
