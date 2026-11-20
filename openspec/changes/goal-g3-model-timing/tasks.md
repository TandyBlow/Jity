# Tasks: G3 模型资产与时间包线

## 1. 资产

- [x] 1.1 `frontend/scripts/fetch-models.mjs` 下载 Qwen3-0.6B/1.7B GGUF，验 bytes+sha256，原子落盘；证据：脚本 + `artifacts/goal/model-manifest.json`。
- [x] 1.2 清单含 role/file/url/repo/revision/bytes/sha256/license/tokenizer 说明；权重不在 git。
- [x] 1.3 下载后用 `sha256sum` 独立复核两份文件与清单一致。

## 2. 验收驱动单树适配

- [x] 2.1 `accept-world-local.mjs` 的 `integrationPath`、`rootDir`、默认 worktree 改为仓库根相对路径。
- [x] 2.2 `lease.mjs` 指向 `<repo>/resource_lease.py`；新增最小 `resource_lease.py`；`resources/` 加入 `.gitignore`。
- [x] 2.3 `results/product/integration.json` 记录页面、启动命令、模型清单与哈希。
- [x] 2.4 `--preflight --fresh` 对 `http://127.0.0.1:3177/world-local` 能通过：COOP/COEP 生效、adapter 为 RTX 4060、GGUF 请求 200。

## 3. 冷启动

- [x] 3.1 3 次冷启动（新浏览器进程 + `--fresh`），逐次记录 `readyMs`、isolated、adapter、模型请求、JS heap。
- [x] 3.2 冷启动结果写 `artifacts/goal/timing-baseline.json` 的 `coldStarts`；不混入正常点。

## 4. 真实点

- [x] 4.1 跑 `turns-10.json` 全部 10 个输入，逐回合证据落盘；结果：8 个正常点（t4 结算失败、t6 刷新不计）+ 补测 t12 共 9 点。
- [ ] 4.2 确认至少一次自动链（`continuationDecision=continue`）与一个重负载点；缺失时追加 `turns-extra-2.json`（t11/t12）补足点数。当前 0 次 continue；重负载点已有；还差 1 个正常点。
- [x] 4.3 汇总 `artifacts/goal/timing-baseline.json`：9 点 + 冷启动，字段齐全。
- [x] 4.4 逐点判定：9 点首段 ≤60,000 ms（最差 43,526）、完成−提交 ≤300,000 ms（最差 13,772）；失败/重试/回退全部保留。

## 5. 结论

- [ ] 5.1 达标：G3 记为通过并写证据路径；不达标：登记失败与下一候选决策，复测。当前结论：已测点时间通过；10 点覆盖阻塞于 G2/G4 的结算失败恢复，G3 保持 active。

## Workflow follow-up

- 更新 `design/goal/ledger.md`（G3 行、R06/R10/R14 证据）与 `design/goal/decisions.md`（D-007 状态、时间结论）。
- `openspec validate "goal-g3-model-timing" --strict`，归档，按路径 commit，打 G3 tag。
