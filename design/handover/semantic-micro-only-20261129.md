# 语义 micro-only 交付说明（2026-11-29）

分支：`semantic-micro-only`（已推送 origin）。工作树：`D:\others\Jity-semantic`。

## 怎么跑

```
# 页面：不加载 0.6B 的语义配置；叙事仍用 1.7B
http://<host>/world-local?semanticArm=micro-only
```

组合臂（等价，显式写各端口）：

```
?semanticArm=micro-only
# 等价于：taskStage=goal & subtasks=program & action=template & targets=rule
```

验收驱动示例：

```
node scripts/product-acceptance/accept-world-local.mjs \
  --base http://127.0.0.1:3178 --query "semanticArm=micro-only" \
  --turns ../artifacts/goal/semantic-micro/turns-frozen-8.json \
  --header-shim --allow-page-sha-mismatch --allow-unknown-page \
  --out ../results/product/evidence/<name>.json
```

## 已验证

| 夹具 | 结果 | 证据 |
|---|---|---|
| 冻结八场景 | 8/8 COMPLETED、0 failures、16.5–37.8 s；仅 1.7B 请求，0.6B 0 次；位置与混合臂 0 差异；任务仅少严格标准下误判的 `lu_kit` | `smoke-micro-only-frozen8-20261129.json` |
| 冻结二十输入 | 20/20、0 failures、18.6–43.3 s；刷新恢复 20→20、pageSaysRestored=true；仅 1.7B 请求；位置 0 差异；3 条 NPC 任务严格 pending | `smoke-micro-only-turns20-20261129.json` |
| 离线两回合 | 运行中，见 `smoke-micro-only-offline-20261129.json` | — |

## 端口与代码

- `local/micro/goal-verifier.ts`：条件台账 + 累计证据（`strictConditionHits`），最终可选模型/程序裁决；`exportLedger/importLedger` 随 `LocalGameSnapshot.goalTaskLedger` 持久化。
- `local/micro/subtasks.ts`：程序子任务（结构化事实标记；删除了父任务复述模板）。
- `local/semantics/actions/index.ts`：`templateOnly`、`targetsNoLlm`、`microOnly` 反应模板。
- `local/semantics/settlement/{results,updates,continuation}.ts`：`microOnly` 保守答案（results no-change、position/appearance/personality 无变化、sanity 保持、continuation handback）。
- `page.tsx`：`semanticArm=micro-only` 不创建 0.6B 引擎，narration 固定 1.7B；`__worldArm.semanticEngine='absent'`。
- `local/structured-events.ts`：只读事件适配器（S07，尚未接入叙事）。

## 已知缺口

1. 任务最终裁决仍是行为克隆 10M 模型（S01 control）；严格多事实金标模型未训练。程序裁决臂（S08）已设计，未实现。
2. NPC 行动全部来自模板闭集；targets 弃权空目标；合法变化被保守跳过的数量尚未逐条读评。
3. 台账随 head 保存；历史只读不回滚；若将来从历史分叉需要重建台账。
4. 移动端未测；叙事仍 1.7B（S06 范围）。
5. 结构化事件适配器未接入任务/叙事，只读测试通过。

## 关键文档

`design/research/S01`–`S09`；历史审计 `E54`–`E57`。金标 `artifacts/goal/semantic-micro/bench-v1.jsonl`（平台 P05 已独立复核 114/114 一致）。
