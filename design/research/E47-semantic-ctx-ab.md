# E47 语义上下文 A/B：12288 → 8192 实测省 278MB，与 KV 账一致

**Question.** 把语义模型上下文从 12288 降到 8192，页面归属内存实际降多少？
是否与 E42 的 KV 估算（q8 每 token 59.5KiB）对得上？

**Setup.** 同一个重建后的产品页（`next start -p 3177`），无头 Edge（`headless`），
`?narrationModel=semantic&cpu=1`，每次全新浏览器配置（空 IndexedDB，从 S0 开局），
提交同一条夹具输入（s01 移动），`memory-baseline.mjs` 每 60s 调一次
`measureUserAgentSpecificMemory`；两臂只差 `semanticCtx=12288` / `8192`。
进程 RSS 由 `sample-process-memory.ps1` 每 2s 采样（含用户自己的 Edge）。

**Results.**
- 加载期（S0 校验、模型未加载）：两臂都是 **147.6MB**。
- 回合后峰值（页面归属）：12288 = **2,342.7MB**，8192 = **2,064.3MB**，
  差 **278.4MB**；KV 理论差 249.6MB（749 → 499）。
- 两臂在回合结束后约 2 分钟都跌到 **178–179MB**，说明模型 worker 被整体释放
  （页面仍 ready；两臂一致，不是某一配置的伪影）。释放的触发未确认：候选是
  隐藏标签页的 `visibilitychange` 释放或一次硬停终止；需要单独实验。
- RSS 峰值按时间窗切分是 3,604MB（臂 1）与 4,093MB（臂 2），窗口有重叠且含
  用户自己的 Edge，不能用于比较；UAA 才是可归因的指标。

**Implication.** 上下文确实是一个真实的 ~250MB 级杠杆，且方向与 KV 账一致；
8192 在 64,423 次真实调用里 0 次越界（E42），没有证据支持保留 12288。
峰值指标下，回合后的常驻内存会随回合结束回落，因此"峰值"必须与"空闲"分开报。

**Caveats.** 每臂一次运行、单回合；无头 CPU 臂，GPU 臂的峰值构成可能不同；
UAA 单次约 25s，采样稀疏；worker 释放的触发原因未定；RSS 无法按臂归因。

**Artifacts.** `ab-ctx12288.jsonl`、`ab-ctx8192.jsonl`、`ctx_ab_report.py`、
`ab-process-memory.csv`、`ab2-process-memory.csv`。E47。
