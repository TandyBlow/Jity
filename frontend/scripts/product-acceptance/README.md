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

## 指定叙事分支（arm）跑一回合

```bash
node scripts/product-acceptance/accept-world-local.mjs   --base http://127.0.0.1:3241   --turns ../../../results/product/evidence/09-turns-01-legal.json   --query 'narrationModel=qwen3-1.7b&narrationCandidate=constrained&narrationMode=beats'   --expect-page-sha <served-page-sha> --fresh   --out ../../../results/product/evidence/09-<name>.json
```

`--query` 让页面按该候选/模式运行，`__worldArm` 会原样记入证据；`--expect-page-sha` 在 06 中途重建时直接中止（记 INVALID，不算产品结果）；`--fresh` 清空 IndexedDB/Cache/OPFS。驱动在启动浏览器前自动执行 `resource_lease.py acquire`（holderPid=驱动进程），`finally` 清理浏览器后按 token 释放；锁被别人占用时立即退出，不加载模型。

`__worldCandidate` 的每条记录（grade/segments/composers/detail.beats/issues）随回合保存；beats 模式下 `composers` 出现 `program+model-failed` 表示该 beat 的模型调用失败并退回程序成文，`detail.beats` 里有具体失败原因。

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

优先级：产品阻断/取消恢复 > 十/二十回合回归 > 已有候选针对性修复 > 新候选首验；同优先级先到先处理。`resource_lease.py` 是强制独占锁：`acquire` 在模型加载前、`release` 在浏览器清理后，失败即不启动；等锁期间继续写代码和证据，不空转。
