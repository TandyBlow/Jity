# Proposal: goal-ledger-r16

## Why

账本 R16 行仍写「未实现…没有 20 输入真实模型通过记录」，但 G8 的技术证据（`artifacts/goal/acceptance/summary.json`：20/20 首段、全部 <300 s、0 失败；离线 2/2；服务器关闭 2/2；两设备分叉通过）已经存在并归档。账本是 R01–R16 的唯一状态来源，陈旧状态会让读者误判验收进度，也会让 goal 检查反复引用错误行。

## What Changes

- 更新 `design/goal/ledger.md` 的 R16 行：状态改为「技术证据齐（质量线未通过）」；证据列加入 summary、离线、服务器关闭、两设备、移动模拟；缺口列写明 G5/G6 质量线未过、移动档未验收、D-024 早交还仅为评估臂（默认路径仍 64.9–180.7 s）。
- 不改代码、不改验收协议、不改门槛。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

无。纯账本校正；`.openspec.yaml` 设 `skip_specs: true`。

## Impact

- `design/goal/ledger.md`
- 不涉及 `frontend/`、`backend/`、`openspec/specs/`。
