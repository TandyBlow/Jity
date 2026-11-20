# Proposal: G3 模型资产与时间包线

## Why

`frontend/public/models/` 为空，页面声明的语义/叙事 GGUF 不在仓库；现有 10 轮页面记录未证明 60/300 时间门槛（其中一条 `readyMs=167917`、`turnMs=503844`）。G3 必须先取得产品实际模型并在目标设备实测，未通过不带病进入 G4/G8。

## What Changes

- 新增外部下载脚本 `frontend/scripts/fetch-models.mjs`：按固定 URL/bytes/sha256 取得语义 Qwen3-0.6B 与叙事 Qwen3-1.7B 的 GGUF，逐字节校验后原子落盘；仓库不托管权重（D-010）。
- 产 `artifacts/goal/model-manifest.json`：文件、bytes、sha256、license、获取方式、HF revision。
- 在 RTX 4060 Laptop 8 GB + Edge 上跑 3 次冷启动 + 至少 10 个真实 `/world-local` 输入点，覆盖自动链与一个重负载点。
- 产 `artifacts/goal/timing-baseline.json`：逐点记录 `inputAt`、`pointCommittedAt`、`narrationStartedAt`、`firstReadableAt`、`pointTextFinishedAt`、首 token、最长流式空档、阶段耗时、峰值内存；冷启动独立报告。
- 为单树布局修正验收驱动的仓库根、`integration.json` 与 lease 路径，新增最小 `resource_lease.py`。
- 不达标时登记失败、提出下一候选并复测；不改 60/300 门槛。

## Capabilities

None. 本变更是模型资产、工具与测量，产品运行期行为不变；`.openspec.yaml` 设 `skip_specs: true`，原因记录于此。

## Impact

- 新增：`frontend/scripts/fetch-models.mjs`、`frontend/scripts/product-acceptance/summarize-timing.mjs`、`resource_lease.py`、`results/product/integration.json`。
- 修改：`frontend/scripts/product-acceptance/{accept-world-local.mjs,lease.mjs}` 的路径常量（旧 worktree 布局 → 单树）。
- 资产：`frontend/public/models/*.gguf`（gitignored，约 1.4 GiB）。
- 证据：`artifacts/goal/model-manifest.json`、`artifacts/goal/timing-baseline.json`、逐次运行 JSON。
- 文档：`design/goal/ledger.md`、`design/goal/decisions.md`（D-007 状态与时间结论）。
