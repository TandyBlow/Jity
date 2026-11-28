# E48 内存杠杆实测：浏览器 731MB 是底，Next/Blob 无重复，KV 与静态服务可省

**Question.** 产品页 ~3.3GB 的进程树峰值里，哪些是不可避免的，哪些是当前实现的
选择？此前"−30% 不可达"的结论是否过早？

**Setup.** `/lab-static.html`（纯静态服务器，无 Next、无 COI，单线程）+ 调度器
`peakTreeMB`（Job Object 内整棵进程树）；对照 `/world-local`（Next + 探针页）。
所有测试都是无头 Edge、CPU、一次性浏览器。

**Results（进程树峰值，MB）.**

| 配置 | 峰值 |
|---|---|
| 只有浏览器 + Playwright（about:blank） | **731** |
| 空白页 + Next 服务器 | 1000 |
| 静态 init ctx2048 q8 | 2014 |
| 静态 init ctx8192 q8 | 2466 |
| 静态 init ctx8192 q4 KV | 2239 |
| 静态 init ctx4096 q4 KV | **2175** |
| 静态 init ctx8192 q8 + 4000 字提示推理 | 2112 |
| 同上，n_batch=256 / 128 | 2106 / 2084 |
| URL 直接加载（wllama 无缓存 / OPFS） | 2239 / 2260 |

**Findings.**
- **浏览器本体 731MB 是固定成本**；之前说的"空白页 1000MB"里约 270MB 是
  Next 服务器与探针页面，不是浏览器。
- **KB 与 KV 是真实杠杆**：ctx 8192→4096（q4）省 64MB（本轮噪声内，理论 125）；
  q8→q4 在 ctx8192 省 **227MB**（理论 249）；ctx 2048→8192（q8）多 452MB
  （理论 375 + 噪声）。方向与 KV 账一致。
- **URL/OPFS 没有收益**：wllama 无论从页面 Blob 还是 URL 载入，都会把权重
  再拷进 wasm MEMFS，2239/2260 vs 2241，说明"页面侧 Blob 是重复副本"不成立。
- **n_batch 不是杠杆**：真正带 4000 字提示时，nb 2048/256/128 的差异在噪声内
  （2112/2106/2084）。此前 132MB 的差异是 `promptLen` 被 cmd 的 `&` 吃掉造成的假象。
- **首次推理只加约 95MB**，远小于加载与 KV。

**Implication（纠正 E42/E47 的结论）.** 从产品页 ~3.3GB 出发，可省的组合是：
Next 换静态服务（约 270MB）+ ctx 4096（约 250MB）+ q4 KV（约 125MB）≈ 645MB，
落到 ~2.65GB（−20%）；静态 + ctx4096 + q4 的静态实验已经是 2175MB（相对 3.3GB
约 −34%）。所以 **−30% 不是不可达，而是需要"静态化 + 小上下文 + 低精度 KV"三件事
同时做，并过集成门槛与 KV 质量验证**；仅靠 ctx/KV 调参大约 −14% 的说法成立，
但不能外推为"现有架构不可达"。

**Caveats.** 单次运行、CPU 单线程、无 COI；静态实验不含 Next 与产品页的 JS；
KV q4 的质量影响未测；ctx4096 会截断 0.32% 的长语义调用（E42），需要兜底。

**Artifacts.** `frontend/public/lab-static.html`、`frontend/scripts/lab/static-*.ps1|mjs`、
`artifacts/goal/lab/queue.json`（peakTreeMB 原始记录）。E48。
