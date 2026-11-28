# P02 实验调度与测量审计：竞态、残留锁、重试与计时口径

**Question.** 两个研究 Agent 共用的实验调度器，能否在并发提交、进程崩溃、超时重试和
重启之后保持账本一致、结果可恢复、测量口径不漂移？

**Setup.** 只读审计 `frontend/scripts/lab/expctl.ps1`（单并发 Job Object 调度器）、
`resource_lease.py`（推理租约）、`frontend/scripts/lab/{load-probe,static-probe}.mjs`
（浏览器探针）、`frontend/scripts/product-acceptance/summarize-timing.mjs`（计时汇总）。
调度器改动在临时队列上冒烟：提交一个 `exit 0` 任务、跑完、再跑一次、伪造一个死 PID 的
`run.lock` 验证回收；没有触碰真实队列中其他 Agent 的任务。

**Findings — 已修（同一提交）.**

1. **提交与运行会互相覆盖账本。** `submit` 与 `run` 都是"整表读-改-写"，一个在跑的任务
   结束时会把期间提交的新任务写没。现在所有队列写回走 `WriteQueue`（`expctl.ps1:71`）：
   命名互斥量内按 id 合并，保留双方记录；`submit` 也在同一互斥量内追加。
2. **崩溃留下的 `run.lock` 会永久阻塞调度。** 原实现只用 `CreateNew`，进程被杀后锁文件
   残留，之后的 `run` 全部报 "another run holds"。现在锁文件写入 pid，获取失败时仅在
   pid 不存在时回收（`expctl.ps1:151-166`）。冒烟：写入 `999999` 后 `run` 正常接管并删除。
3. **`stop` 不落账。** 原来只改 `active.json`，队列里的任务永远停在 `running`。现在同时
   把对应任务标为 `stopped` 并写 `endedAt`（`expctl.ps1:128-139`）。
4. **重试覆盖唯一日志。** `cmd /c ... > log` 每次 attempt 截断同一文件，第一次失败的原因
   在重试后消失。现在日志按 attempt 命名并写回队列（`expctl.ps1:184-190`）；冒烟记录的
   `log` 为 `job-…-133.attempt1.log`，`attempts=1`。

**Findings — 未修（需要设计或跨模块协调）.**

5. **探针无论失败都 exit 0。** `load-probe.mjs`、`static-probe.mjs` 捕获错误后仍
   `process.exit(0)`，调度器记 `done`。应改为只有 `stage === 'done'` 才 0。这两个文件
   当前有另一个 Agent 未提交的修改，故未一并提交，留给负责人。 
6. **超时/内存触底会整单重跑。** `expctl.ps1:268` 对 `timeout` 与 `reserve-floor` 最多重试
   5 次；每次都是同一条命令从头跑，没有恢复令牌或状态一致性校验。对已提交行动的验收
   回合，这就是"因恢复机制重复执行已提交行动"，目标明确禁止。日志现在保住了，但
   账本仍会显示多次 attempt。建议：默认不自动重试，或只允许带 resume 检查的任务重试。
7. **推理租约的 TTL 对活着的 holder 不生效。** `resource_lease.py:94-96`：只要记录的
   `holderPid` 还活着就返回"不 stale"，不检查年龄，也没有心跳；进程挂死时租约永不释放。
   需要心跳字段或最大持有时间，同时保留"不杀用户浏览器"的约束。
8. **调度器与租约是两套互不联动的门。** `expctl.ps1` 只看空闲物理内存/提交上限，
   完全不 acquire `resource_lease.py`；另一个 lane 持有租约时，lab 仍可能放行浏览器任务。
   目标要求"避免多个重型实验无协调地同时运行"，这需要统一的准入门。
9. **只治理内存，不治理 GPU/CPU。** 队列记录 `budgetMB`/`peakTreeMB`，没有 GPU 显存、
   利用率或 CPU 亲和性；WebGPU 实验的显存冲突不会被发现。
10. **计时口径的三个缺口。**
    - `peakMemoryMB` 取 `turn.jsHeap.usedJSHeapSize`（`summarize-timing.mjs:101`），只是
      JS 堆，不是页面/进程峰值；模型权重与 wasm 堆不在内。
    - `longestStreamGapMs` 对所有 generation 取最大（`:29-33`），语义调用与叙事流式的空档
      会混在一起。
    - `pointTextFinishedAtMs` 取 `pointNarration` 的最大完成时钟，却减去同一个
      `pointCommittedAtMs`（`:64-69`）；多 point 回合里两个时钟是否属于同一 point 需要
      驱动侧确认，否则 300 秒口径会被高估或低估。
    - 缺"控制权交还"的显式时钟、长期内存漂移（结束 − 峰值）、GPU 归属和冷启动的
      模型加载分解（现在只有 `readyMs`）。

**Conditions.** 冒烟只覆盖 submit/run/stop 的基本路径，没有在真实并发压力下跑；队列互斥量
是会话内命名互斥量，多用户同时调度不适用。未运行任何模型或浏览器。

**Next.** 与 runner/perf 研究 Agent 对齐后：统一租约与调度器入口；把重试改为显式 resume；
把 `peakMemoryMB` 拆成 JS 堆 / wasm / 页面 RSS；在计时汇总里加控制权交还与漂移字段。

**Artifacts.** `frontend/scripts/lab/expctl.ps1`（合并写、锁回收、stop 落账、attempt 日志）、
本页。P02。探针退出码未改（见第 5 条）。
