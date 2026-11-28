# E29 内存基线第一轮：单引擎臂（桌面）

**Question.** 产品页加载一份 GGUF 时的真实内存构成是什么？浏览器进程 RSS、
JS heap、页面归属内存（wasm/DOM/JS）各是多少，差距多大？（goal 阶段二）

**Setup.** 桌面（RTX 4060 笔记本，16GB）；Edge；页面
`/world-local?micro=1&microContinuation=heads&microReaction=1&taskProposer=micro&seed=11&narrationModel=semantic`
（单引擎 0.6B 臂）。工具：
`frontend/scripts/memory-baseline.mjs`（页面内：阶段、`performance.memory`
每 2 s；`performance.measureUserAgentSpecificMemory()` 每 30 s——该调用自带
GC，单次约 25 s）与 `artifacts/goal/memory-baseline/sample-process-memory.ps1`
（进程级：所有 msedge 进程 WorkingSet 合计 + 系统空闲内存，每 2 s）。

**Results（一次 120 s 采样、28 个页面样本 + 52 个进程样本）.**
- 阶段：loading 3.8 s → streaming 9.8 s（恢复存档后根正文流式）→ ready 24.3 s。
- JS heap：峰值 **58.0 MB**，结束 17.7 MB。
- 页面归属内存（measureUserAgentSpecificMemory 合计）：加载期 147.6 MB →
  稳态 **724.1 MB**（wasm 堆 + DOM + JS）。
- msedge 进程 RSS 合计：运行期峰值 **4,653 MB**（开机基线约 0.93–1.15 GB，
  用户另有 Edge 实例；页面自身约 +3.5 GB）；系统空闲内存最低 3,699 MB。
- 结论：JS heap 只有 RSS 的 ~1%，页面归属内存约为 RSS 增量的一半——三者
  必须分开记录，正是 goal 要求的"不以 JS Heap 代替全部内存"。

**回合级阶段（同臂，页面亲自打一回合，420 s 采样）.** 阶段时间线：loading 3.8 s → streaming 9.8 s（恢复的根正文）→ 提交 24.3 s → streaming 94.4 s → ready 104.5 s → streaming 208.7 s → ready 274.9 s（回合含自动推进，多个流式段）。页面归属内存：加载 147.6 MB → 就绪 724 MB（上一轮）→ 首段叙事 1,100 MB → 回合中 1,373 MB → 全部点完成后 **1,918 MB**；JS heap 峰值 53.9 MB；msedge RSS 峰值 **5,928 MB**，系统空闲最低 2,448 MB。结论：**回合（KV 缓存与逐点叙事）而非加载是内存峰值来源**，单引擎臂一回合就把页面归属内存抬到约 1.9 GB。

**Caveats.** 单次运行、单配置；进程采样包含用户自己的 Edge 实例（用基线
扣除）；未采到回合级阶段（语义/叙事/回合结束）——下一轮用 harness 跑一回合
补齐；双引擎臂峰值约 8GB，需空闲窗口再测；手机端基线待设备重连。

**Artifacts.** `lean-browser-memory.jsonl`、`lean-process-memory.csv`、
`frontend/scripts/memory-baseline.mjs`、`sample-process-memory.ps1`。E29。

**补记（E42 复核，2026-11-28）.** 5,928MB 是 `Get-Process msedge` 全部进程
WorkingSet 求和，含用户其他 Edge 窗口与共享页重复计数，不能当作本页占用；
页面归属的 1,918MB 也未必包含 mmap 的权重页。KV 账与真实 token 分布见 E42。
