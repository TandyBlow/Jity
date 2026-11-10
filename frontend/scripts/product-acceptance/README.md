# 09 独立产品验收（真实 `/world-local`）

角色来源：`tasks/product-09-acceptance.md`（sha256 `093694e7a91015366eba7915b17d4cf28c4e8de790b80f2ff55b8adcdb3e9ad8`）。
本目录只做**只读验收**与本地 GPU 排队，不改产品逻辑、不改 06 的树、不用临时页面或 stub 充当产品。

## 边界

- 唯一被测产品：06 的产品树 `worktrees/06-recovery`，路径 `/world-local`，URL/提交/模型/启动命令以 `results/product/integration.json` 为准。
- 驱动只操作页面可见控件（`textarea` + 「行动」按钮），不注入状态、不算结算、不选候选；页面显示什么就记什么。
- COOP/COEP 是产品要求，不是测试便利：默认按产品实际响应测，`--header-shim` 只用于区分“驱动问题”与“产品问题”，并在证据里标 `shimmed`。
- 单次 `accepted=true`、`issues=[]`、3 条样本都不是质量通过；正文逐句与跨回合表达由 01 独立复核，09 只核查玩法、来源、时序、后端、降级与未验证项。
- 记录里区分：AI 复核（09/01 阅读）、自动化检查（脚本断言）、真人/用户试玩（目前没有，不得代签）。

## 先决条件

```bash
node scripts/product-acceptance/check-integration.mjs
# exit 2 表示 06 还没发布可运行产品记录，后续命令不启动浏览器
```

`integration.json` 至少需要：`product.worktree/branch/head/url`、`startup.command/port`、每个模型的 served path + sha256 + bytes、`crossOriginIsolated` 实测值、持久化键或存储说明。

## 十回合真实游玩

```bash
node scripts/product-acceptance/accept-world-local.mjs \
  --base http://127.0.0.1:3177 \
  --turns scripts/product-acceptance/turns-10.json \
  --out ../../../results/product/evidence/09-acceptance-<UTC>-.json \
  --intent 10-turn
```

`turns-10.json` 覆盖：读场景/不移动、移动到器材棚、与林亦舟对话、与诺诺共同移动到西回廊、等待与时间推进、结算中途刷新（`refreshMidSettleMs`）、进入钟楼门厅、上二层平台、问清红蓝局势（任务达成）、长时间等待与状态核对。

每回合记录：输入、提交→首个阶段→首个可读正文→完成的时间、阶段序列、页面正文、降级标注、侧栏状态（精神值/地点/附近/任务）、历史次数、存档长度、控制台模型/GPU 行；回合结束自动落盘。最后做刷新恢复核对与取消控件检查。

## 预检（不跑整局）

```bash
node scripts/product-acceptance/accept-world-local.mjs --preflight --base <url> --out <path>
```

记录 ready 时间、`crossOriginIsolated`、WebGPU adapter、`/models/*.gguf` 请求状态。

## 本地 GPU 队列

其他 lane 在 `results/product/browser-requests/<lane>-<id>.json` 提交请求；09 维护 `results/product/browser-queue.json`：

```bash
node scripts/product-acceptance/browser-queue.mjs --sync
node scripts/product-acceptance/browser-queue.mjs --next
node scripts/product-acceptance/browser-queue.mjs --claim <itemId> --pid $$
node scripts/product-acceptance/browser-queue.mjs --finish <itemId> --status completed --evidence <path>
```

优先级：产品阻断/取消恢复 > 十/二十回合回归 > 已有候选针对性修复 > 新候选首验；同优先级先到先处理。`resource_lease.py` 仍是兼容锁，执行前获取、`finally` 释放；等锁期间继续写代码和证据，不空转。
