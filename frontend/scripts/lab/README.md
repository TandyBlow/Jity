# 实验室工具（lab）说明

本目录放的是"跑重活时的限流与取证"工具，不是产品代码。三个脚本分工：

| 文件 | 干什么 |
| --- | --- |
| `expctl.ps1` | 排队 + 逐个跑 + 内存/时间兜底 + 杀干净。所有重活都从它走。 |
| `monitor.ps1` | 每秒记一行资源账（进程内存、系统内存、显卡显存）。 |
| `diag-oneturn.ps1` | 把"监控 + 起产品服务 + 跑一轮浏览器对话"打包成**一个** job。 |

核心机制只有一条：**`expctl.ps1 run` 把重活放进一个 Windows Job Object（作业对象），这个对象带"提交内存上限"和"关门即杀"，所以活干完或进程树跑飞，里面的东西一起死。**

---

## 一、先看一次真实跑完的流程

下面是 `artifacts/goal/lab/queue.json` 里真实存在的一条记录（2026-11-28 那次单轮诊断）：

**第 1 步，投递。** 有人执行：

```powershell
powershell -File frontend/scripts/lab/expctl.ps1 -Action submit `
  -Name diag-oneturn `
  -Command "powershell -NoProfile -ExecutionPolicy Bypass -File frontend\scripts\lab\diag-oneturn.ps1" `
  -BudgetMB 7000 -TimeoutSec 600
```

`submit` 这一刻**不启动任何东西**。它只做一件事：往 `artifacts/goal/lab/queue.json` 这个 JSON 数组末尾追加一条记录，然后打印 `queued job-... diag-oneturn`，退出。记录长这样：

```json
{
  "id": "job-20261128-154316-156",
  "name": "diag-oneturn",
  "command": "powershell -NoProfile ... diag-oneturn.ps1",
  "cwd": ".",
  "budgetMB": 7000,
  "timeoutSec": 600,
  "killMatch": "",
  "status": "queued",
  "submittedAt": "2026-11-28T15:43:16.3196774+08:00",
  "startedAt": null, "endedAt": null, "pid": null, "peakTreeMB": null,
  "log": "artifacts/goal/lab/job-20261128-154316-156.log"
}
```

`id` 是 `job-年月日-时分秒-三位随机数`。`log` 指向这条活自己的输出文件。

**第 2 步，跑。** 另一个人（或另一个终端）执行 `expctl.ps1 -Action run`。它做四件事：

1. 从 `queue.json` 里挑第一条 `status == "queued"` 的记录。
2. **等内存**：每秒查系统剩余物理内存和提交量，两个条件都满足才放行 —— 剩余物理内存 ≥ `ReserveMB`（默认 6144 MB，即 6 GB），并且"提交上限 − 已提交" ≥ 4096 MB。不满足就打印 `deferred ...` 然后每 15 秒重查一次，同时重读 `queue.json`（这样期间你在别处把这单停掉，它会退出等待）。
3. **起进程**：用 `cmd.exe /c <command> > <log> 2>&1` 在工作目录里静默启动，命令自己的标准输出和标准错误全部写进那条 `log` 文件。
4. **建笼子**：新建一个 Job Object，设两条限制后把这个进程塞进去。

这个笼子的两个关键性质：

- **提交内存上限** = `BudgetMB`，同时设在"单个进程"和"整个 job"两个层级上。里面任何进程想多要内存，到额度就失败，不会把整机拖进换页。
- **关门即杀（kill-on-close）**：控制进程一旦关掉这个笼子的句柄，里面还活着的进程全部被系统杀掉。

**第 3 步，盯着。** 跑的过程中每秒做一次：

- 算这棵进程树（父进程往下递归）的工作集总和，记下峰值 `peakTreeMB`。
- 查系统剩余物理内存，低于 `HardFloorMB`（默认 3072 MB）→ 立刻 `TerminateJobObject`，结束原因记 `hard-floor`。
- 查已跑秒数，超过 `TimeoutSec` → 同样终止，原因记 `timeout`。
- 把当前所有子孙进程的 pid + 创建时间记在一张表里（后面收尸用）。

**第 4 步，收尸。** 主进程退出或被打断后，按顺序扫两遍：

- 如果传了 `KillMatch`：找出**命令行里含这个字符串**、且创建时间不早于本次启动的进程，逐个 `Stop-Process -Force`，打印 `matched-kill <pid>`。这是给"用 ShellExecute 逃出笼子的孙进程"准备的补刀。
- 再按第 3 步记下的 pid + 创建时间表核对：还活着且创建时间一致（说明就是那一个，不是复用了 pid 的新进程）→ 杀掉，打印 `swept <pid>`。
- 最后关句柄（关门即杀兜底）。

**第 5 步，记账。** 回到 `queue.json`，把这条记录的 `status` 改成 `done` / `timeout` / `hard-floor`，填 `endedAt`、`peakTreeMB`、`pid`，删掉 `active.json`，打印 `finished <name> status=... peakTreeMB=...`。真实结果就是：`status: done`、`peakTreeMB: 237`、耗时约 6 分 11 秒。

`artifacts/goal/lab/` 里留下的就是：`queue.json`（账本）、`job-<id>.log`（这条活的输出）。

---

## 二、`expctl.ps1`

### 动作

| Action | 行为 |
| --- | --- |
| `submit` | 只往 `queue.json` 追加一条 `queued` 记录，不启动进程。必须给 `-Name` 和 `-Command`。 |
| `run` | 顺序处理队列：一次只跑一条，跑完再取下一条，队列空了打印 `queue empty` 退出。 |
| `status` | 把 `queue.json` 打成表格（id / name / status / budgetMB / timeoutSec / startedAt / endedAt），若存在 `active.json` 再原样打印其内容。 |
| `stop` | 只对 `active.json` 里记的那个 pid 执行 `taskkill /PID <pid> /T /F`（连子进程一起），把该记录标成 `stopped`。没在跑就打印 `no active job`。 |

`stop` 的作用范围就是这个 pid 树，不会去动别人的进程。

### 参数

| 参数 | 默认 | 含义 |
| --- | --- | --- |
| `-Name` | 空 | 任务名，写进账本，方便人看。 |
| `-Command` | 空 | 实际要执行的命令行，交给 `cmd.exe /c`。 |
| `-Cwd` | `.` | 工作目录，相对路径按仓库根解析。 |
| `-BudgetMB` | `4096` | 这个 job 的提交内存上限（单进程 + 整 job 都设成这个值）。 |
| `-TimeoutSec` | `1800` | 墙钟上限，超了终止整笼。 |
| `-ReserveMB` | `6144` | 放行门槛：开始前系统剩余物理内存必须 ≥ 这个数（6 GB）。 |
| `-HardFloorMB` | `3072` | 运行中红线：剩余物理内存掉到这以下就立刻终止。 |
| `-KillMatch` | 空 | 收尸时用命令行子串匹配的额外补刀（给逃出笼子的进程）。 |
| `-Queue` | `artifacts/goal/lab/queue.json` | 账本文件。 |
| `-Active` | `artifacts/goal/lab/active.json` | "当前在跑哪单"的指针文件。 |

相对路径统一按仓库根（`frontend/scripts/lab/../../..`）解析；目录不存在会自动建。

### 关于 `queue.json`

它是 `submit` 和 `run` 之间**唯一**的交接渠道：两人不通信，只读写这同一个文件。`submit` 写、`run` 读并改写 `status`，文件里数组的顺序就是执行顺序（先进先出）。

写文件时对数组做了逐条序列化再拼 `[...]` 的处理，所以数组不会因为 PowerShell 把单元素数组压扁而写成对象。

---

## 三、`monitor.ps1`

每秒往 CSV 追加一行，`-Out` 默认 `artifacts/goal/lab/monitor.csv`，`-Seconds` 默认 300 秒。

### 列

`t,kind,pid,ppid,name,privateMB,wsMB,freeMB,commitMB,limitMB,pagefileMB,gpuDedicatedMB,gpuSharedMB,cmd`

- `t` 相对开始时刻的秒数。
- `kind` 本行类型：`proc`（普通进程行）或 `gpu`（显卡显存行）。
- `pid` / `ppid` / `name` 进程号、父进程号、进程名。
- `privateMB` 该进程独占的内存（私有提交），`wsMB` 实际驻留物理内存。
- `freeMB` 系统剩余物理内存，`commitMB` 系统已提交，`limitMB` 提交上限，`pagefileMB` 页面文件当前用量。
- `gpuDedicatedMB` / `gpuSharedMB` 该进程的显卡专用显存 / 共享显存。
- `cmd` 命令行（逗号和换行已替换成空格，避免破坏 CSV）。

### 采集规则

- 每秒一次：先取系统四项（剩余物理内存、已提交、提交上限、页面文件），再扫 `msedge / node / python / python3 / chrome / next` 这些进程，各写一行 `kind=proc`。
- 每 `-GpuEvery` 秒（默认 5 秒）：读性能计数器 `\GPU Process Memory(*)\Dedicated Usage` 和 `\GPU Process Memory(*)\Shared Usage`，从计数器实例名里的 `pid_<数字>` 取出进程号，写一行 `kind=gpu`（`privateMB`、`wsMB`、`name`、`cmd` 留空）。
- `-Tag <子串>`：只保留命令行里含该子串的进程行，用来把视线锁在某一次实验上。
- 进程号和命令行每 10 秒刷新一次缓存（`ppid` / `cmd` 最多落后 10 秒）。

写文件方式是**每行立刻追加**（`Export-Csv -Append`），开头只写一次表头。所以哪怕脚本被强杀，已经落盘的行不会丢——这是刻意设计，因为要抓的正是"崩溃/被杀那一刻"的数据。

---

## 四、`diag-oneturn.ps1`

一次受控诊断，**全部子进程都在调用者同一个 Job Object 里**，所以上限、超时、关门即杀都由外层的 `expctl.ps1 run` 统一管。

参数：`-Out`（默认 `artifacts/goal/lab`）、`-Port`（默认 `3177`）、`-TurnSeconds`（默认 `240`）。

执行顺序：

1. 后台起 `monitor.ps1 -Out <Out>/diag-monitor.csv -Seconds 600`，等 1 秒。
2. 在 `frontend/` 里起产品服务：`node frontend/node_modules/next/dist/bin/next -p <Port> start`，输出重定向到 `<Out>/diag-server.log`。
3. 轮询 `http://127.0.0.1:<Port>/world-local`，最多等 120 秒，拿到 200 才算就绪；结果连同等了几秒写进 `<Out>/diag.log`（`server ready=True after N s`）。
4. 就绪后，读同目录的 `diag-turn.txt`（就是那一句要说的话）作为本轮输入，执行：

   ```
   node frontend/scripts/memory-baseline.mjs \
     "http://127.0.0.1:<Port>/world-local?narrationModel=semantic&semanticCtx=8192" \
     diag-oneturn <Out>/diag-browser.jsonl <TurnSeconds> "<那一句话>"
   ```

   `memory-baseline.mjs` 负责开浏览器、提交这一轮、把页面侧的内存时间线按行写进 `diag-browser.jsonl`。退出码记进 `diag.log`。
5. 收尾：`taskkill /PID <server> /T /F` 干掉服务树，强停 monitor，往 `diag.log` 追加 `swept server=... monitor=...`。

关键实现点：所有子进程都用 `UseShellExecute=false` + `CreateNoWindow=true` 启动。`UseShellExecute=false` 意味着新进程直接继承调用者的作业对象，不会另起独立会话——这就是"全都待在一个笼子里"成立的原因。

一次跑完，`artifacts/goal/lab/` 里的取证文件是：

- `diag-monitor.csv` 每秒的资源账（含 GPU 行）
- `diag-server.log` 产品服务自己的输出
- `diag-browser.jsonl` 页面侧每阶段的内存与事件
- `diag.log` 就绪耗时、浏览器退出码、收尾记录
- `job-<id>.log` 外层 `run` 给整单存的控制台输出

---

## 五、典型用法

```powershell
# 投一单
powershell -File frontend/scripts/lab/expctl.ps1 -Action submit `
  -Name diag-oneturn `
  -Command "powershell -NoProfile -ExecutionPolicy Bypass -File frontend\scripts\lab\diag-oneturn.ps1" `
  -BudgetMB 7000 -TimeoutSec 900 -ReserveMB 6144 -HardFloorMB 3072

# 前台跑（会一直处理队列直到空）
powershell -File frontend/scripts/lab/expctl.ps1 -Action run

# 看账本
powershell -File frontend/scripts/lab/expctl.ps1 -Action status

# 掐掉当前这单
powershell -File frontend/scripts/lab/expctl.ps1 -Action stop
```

`run` 是阻塞的：队列没空、或当前这单没结束，它就一直占着这个终端。要并行看状态，另开一个终端跑 `status`。

---

## 六、边界与已知行为

- 浏览器本体（无 Next、无页面）单独测是 **731MB**；空白页 1000MB 里的另 270MB 是 Next 服务器与页面。
- **一次只跑一条。** 没有并发，`run` 是单线程顺序处理。第二个 `run` 同时启动会争抢同一个 `queue.json`，不要这么干。
- **内存门槛是两道。** 开始前看 `ReserveMB`（默认 6 GB 自由物理内存）**和** 4096 MB 提交余量（这个 4096 是写死在 `run` 里的，不是参数）；运行中看 `HardFloorMB`。这是两个不同的数，前者决定"能不能开始"，后者决定"跑着跑着要不要立刻掐"。
- **终止一定是整笼。** 超时和触碰内存红线都走 `TerminateJobObject`，不是只杀主进程。
- **补刀有两种，各管一段。** `KillMatch` 按命令行子串 + 创建时间扫全机（能覆盖逃出 job 的进程，但需要你主动给子串）；`swept` 按记录在案的 pid + 创建时间核对（精确，但只覆盖 job 内观察到的子孙）。
- **`stop` 只认 `active.json`。** 如果 `run` 已经结束、`active.json` 已被删掉，`stop` 会说 `no active job`，不会去猜。
- **`monitor.ps1` 的表头是覆盖写的。** 每次启动都重写文件开头，同名文件会被清空重来；要多次采样请用不同的 `-Out`。
- 这些脚本只读写 `artifacts/goal/lab/` 下的文件，不碰仓库其他内容。

---

## 七、一次受控诊断的实测结果（2026-11-28）

调度器 + 监控 + 产品页一回合，全部在一个 Job 里跑；页面用
`narrationModel=semantic&semanticCtx=8192`，无头 Edge。

| t(s) | 空闲 MB | 提交 MB | 页面文件 MB | 事件 |
|---|---|---|---|---|
| 0 | 6132 | 24135 | 2701 | 启动前 |
| 7 | 4917 | 25691 | 2701 | 浏览器与模型加载中 |
| 9 | 3146 | 27361 | 2701 | 加载完成，回合提交 |
| 29 | 2842 | 27746 | 2703 | 触碰 3GB 硬底线，被 TerminateJobObject 终止 |

同一时刻的私有内存（峰值样本，t=29）：我们的两个 Edge 渲染进程
1,341MB + 1,163MB；用户自己的 Edge 渲染 606MB；一个 Jupyter 内核
2,253MB 私有提交（工作集仅 1MB，处于换出状态）。

结论：
- **掉内存的是模型加载那 9 秒**（−2.99GB），不是回合推理；页面文件全程
  2.7GB 没变，说明还没开始大量换页。
- 守护和硬底线都按设计工作：实验被杀，用户的进程毫发无损。
- 在 16GB、用户日常占用约 9–10GB 的机器上，一次浏览器实验需要约 3GB；
  要在实验期间仍留 6GB 空闲，启动前至少要有 **9GB** 空闲——这只能在用户
  离开机器或占用较低的窗口出现。**不要**为了跑实验要求用户关闭日常应用。
- 因此 20 输入门槛与 8 场景应安排在低占用窗口，或改在第二台机器/服务器上
  跑；调度器会按 `ReserveMB` 自动推迟，不要绕过。

---

## 八、分阶段加载：3GB 到底花在哪（2026-11-28 实测）

方法：`/lab-load` 探针页 + `load-probe.mjs`，每个阶段在新浏览器配置里单独跑一单，
用调度器的 **进程树峰值**（`peakTreeMB`，含 Next 服务器约 150–250MB）记账。
`measureUserAgentSpecificMemory` 在这里不可用：它不统计 wllama worker 的 wasm 与
GGUF Blob（init 阶段只报 2.9MB，而进程树是 2.2GB），只能当参考。

| 阶段 | 树峰值 | 相比上一阶段 |
|---|---|---|
| 空白页面（无模型） | 1000MB | — |
| + 下载 GGUF 到 Blob（397MB） | 1418MB | +418MB |
| + wllama 初始化（ctx 2048，q8 KV） | 2231MB | +813MB |
| + 首次推理（8 token） | 2250MB | +19MB |
| init ctx=8192（默认 batch） | 2591MB | +360MB（=KV 375MB） |
| init ctx=8192 + n_batch=256 | 2590MB | 0（batch 对初始化内存无效） |
| init ctx=2048 + n_batch=256 | 2230MB | 0 |

解读：
- 光是一个无头 Edge + Next 服务器就要约 1GB；这是浏览器实验的固定成本。
- GGUF 的 397MB 在 Blob 里实打实多出约 0.4GB；wllama 初始化再花约 0.8GB
  （权重进 wasm + KV 125MB + 计算缓冲）。
- 首次推理几乎不涨（+19MB），所以"加载那 9 秒" = 浏览器基线 + Blob + 初始化。
- 把 ctx 从 2048 提到 8192/12288，KV 各多 375/625MB，正好对上产品页的 3.1GB。
- 想压峰值，优先顺序是：浏览器基线（1GB）> wllama 初始化缓冲（0.8GB）
  > KV（0.1–0.75GB）> Blob（0.4GB）。

补充结论（2026-11-28）：
- `n_batch` 对初始化内存没有影响（2230 vs 2231、2590 vs 2591）；在**真正带 4000 字提示**的
  静态服务器测试里也没有可测差异（nb=2048/256/128：2112/2106/2084MB）。此前有一次
  132MB 的差异，是 `promptLen` 被 cmd 的 `&` 吃掉、实际跑了短提示导致的假象。
- ctx 的 KV 账在进程树上同样成立：2048→8192 多 360MB，与 q8 KV 375MB 的估算一致。
- 产品页 12288 的树峰值约 3.1GB：浏览器基线 1GB + 初始化 0.8GB +
  KV 0.75GB + Blob/页面其余。**ctx 8192 + q4 KV 大约只能到 2.7GB（约 −14%）**；
  30% 目标（≤2.2GB）在现有浏览器+wasm 架构下不可达，需要换运行时或减模型，
  不能靠调参宣称达成。
