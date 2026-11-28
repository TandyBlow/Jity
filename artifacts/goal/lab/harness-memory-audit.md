# 09 验收脚本（accept-world-local.mjs）20 回合内存累积审计

只读审计。没有改代码、没有起服务/浏览器/模型、没用 git、没用网络。
证据来源：`frontend/scripts/product-acceptance/accept-world-local.mjs`（1402 行）与
`results/product/evidence/09-turns20-ctx8192-gpu.json`（3 回合的部分证据，6,734,998 B）。

---

## 0. 一句话结论

脚本把**每一个回合的全部现场**（含一份 ~0.9MB 的世界快照、一份 ~172KB 的模型调用记录、
一份 ~26KB 的页面全局 generations）原样塞进同一个内存对象 `evidence`，并且每回合把这个
对象**整体**序列化一次写盘。

- 实测每回合新增：**0.85MB（第 1 回合）→ 1.19MB（第 3 回合）**紧凑 JSON 字节；第 3 回合后
  斜率是快照 **+12.6KB/回合**、整条 turn entry **+22.4KB/回合**（快照里已封顶的缓存占大头）。
- 20 回合外推：内存里的 `evidence` ≈ **26MB** 紧凑 JSON 等价；写出的证据文件（2 空格缩进）
  ≈ **53MB**；`save()` 累计写盘 ≈ **530MB**；单次 `save()` 的峰值字符串 ≈ **53MB**。
- 增长曲线是 **O(N)**（每回合存一份完整快照），其中 `microStatsAll`、`before/after`
  是 **O(N²)**（会话累计数组被复制进每一回合）。
- 另外实测：每份快照里约 **297KB（33%）是字节相同的重复**——54KB 的世界定义出现 4 次，
  head 状态与当前状态各一份（详见第 1 节末）。

---

## 1. 机制：一回合里脚本往内存里放了什么

每回合（`for` 循环，576 行建 `entry`）走完后，`entry` 被 `evidence.turns.push(entry)`
（1113 行）再 `save()`（1114 行）。`entry` 里这些字段是"这个回合现场的原样副本"：

1. `snapshotAfterTurn`（1024 行）：在页面里执行 `__worldSnapshot()`，返回整个 transport
   （点、点位状态、幂等缓存、初始状态、世界状态、叙事、分配、掷骰、任务账本）。**整份**。
2. `product`（886 行）：从 `__worldTurns.at(-1)` 读回本回合记录，包括
   `semanticCalls`、`semanticPrompts`、`submission.calls`（含 coverage/stages/raw）、
   `actions`、`microStats`、**`microStatsAll`（会话累计数组）**、`semanticLog`（会话累计）。
3. `actions`（1028 行）：本回合 actions 整表（和 `product.semanticCalls` 大面积重叠）。
4. `generations`（1040 行）：`__worldGenerations.slice(-200)`，即页面全局的最近 200 条。
5. `live`（1036 行）：`__worldLive`，里面又有一份 `generations`。
6. `console`（1015 行）：`environment.ggmlConsole.slice(consoleStart)`，本回合新增的页面日志。
7. `before` / `after`（515 行的 `snapshot()`）：只读数，但其中的 `transportPoints`（538 行）
   是**到目前为止所有点**的标量表，所以它随回合线性变长。
8. 其余小项：`stages`（758 行）、`text`/`proseIdentity`（858 行，同一段正文存两份）、
   `timings`、`offscreenJudge`（992 行，含完整 decision 行）。

另有三个跨回合容器常驻：

- `evidence.environment.ggmlConsole`（230 行 push）：**无上限**，每回合 +~9.5KB。
- `evidence.modelRequests`（237 行 push）：每条命中 `/models/*.gguf` 或 `/api/*(progress|save|session)`
  的响应一条记录。本次证据只有 1 条（模型 GET）。
- `evidence.failures`（165 行）：每次失败 push，`detail` 可能带大对象（见 P9）。

### 一个回合的具体例子（第 2 回合 → 第 3 回合）

第 3 回合的 `entry` 紧凑 UTF-8 是 **1,189,727 B**，构成：

| 部分 | 字节 | 里面是什么 |
|---|---:|---|
| `snapshotAfterTurn` | 912,270 | 见下表 |
| `product` | 171,963 | semanticCalls 44,234 / semanticPrompts 57,162 / submission 18,343 / actions 16,356 / pointPrompts 10,454 / microStatsAll 13,972 / microStats 4,647 / narration 3,986 / engines 1,788 |
| `generations` | 25,931 | 49 条 × 529 B |
| `actions`（顶层副本） | 16,356 | 与 product.actions 同源 |
| **`submission`（顶层再存一份）** | 18,343 | 与 product.submission 是同一对象，JSON 里出现两次 |
| `console` | 9,064 | 本回合页面日志 |
| `offscreenJudge` | 6,133 | 判决行汇总 |
| `stages` | 6,221 | 阶段时间线 |
| `proseIdentity` + `text` | 8,908 | 正文存了两份（articleText + recordText） |
| `before` + `after` | 6,786 | 面板读数 + 全量 transportPoints |
| `live` | 2,264 | 含一份 generations |
| 其它（stageSequence/timings/jsHeap/inputLine…） | 5,488 | 含键名与括号的开销 |

`snapshotAfterTurn` 内部（第 3 回合）：

| 子项 | 字节 | 第 2→3 回合增量 | 说明 |
|---|---:|---:|---|
| `transport.idempotency` | 565,687 | +5,050 | 200 条封顶（条目 99→198→200，最大序号已到 413，说明按条数淘汰）。每条 `{hash,response}` 约 2.8KB |
| `transport.pointStates` | 164,259 | +485 | root 81,357 + head 81,508 各带一份全量 `state`；其余 11 个点各 **94 B**（只有 digest）。这个版本已经压缩过，不像 E40 记录的老构建那样每点一份 65KB 状态 |
| `transport.state` | 81,404 | 0 | 当前世界状态（其中 `state.initial` 54,073 + characters 16,149 + items 9,659） |
| `transport.initial` | 54,073 | 0 | 世界初始定义，与 `state.initial` **字节相同** |
| `transport.narrations` | 12,558 | +3,939 | 每回合新增约 4 段正文（中文 3 字节/字） |
| `transport.points` | 4,582 | +1,468 | 每回合 +4 个点 |
| `transport.allocations` / `rolls` | 2,267 / 2,284 | +698 / +657 | 每回合累积 |
| `taskLedger` | 23,351 | +73 | 基本不涨 |
| 其余（commands / narrationSources / commandPointIds） | 926 | +284 | |

（上表是各值之和；`JSON.stringify(snapshot)` 还有 79 B 的键名与括号。）

所以第 3 回合快照 = **566KB 已封顶的幂等缓存 + ~400KB 世界本体（initial+state+点位 digest+账本）
+ 12.6KB/回合 的线性增长**。换句话说：这份证据里快照贵在"常数"，不是贵在"越玩越大"。

### 快照里有约 1/3 是同一份数据的重复副本（实测）

对第 3 回合快照做 sha256 比对：

| 内容 | 出现次数 | 每次字节 | 合计 |
|---|---:|---:|---:|
| 世界定义 `initial` | **4 次**：`transport.initial`、`transport.state.initial`、`pointStates[root].state.initial`、`pointStates[head].state.initial` | 54,073 | 216,292（4 份 sha 完全相同） |
| 当前世界状态 | **2 次**：`transport.state` 与 `pointStates[head].state`（sha 相同） | 81,404 | 162,808 |

即 912KB 的快照里约 **297KB（33%）是字节相同的重复**。这是产品侧 `__worldSnapshot()` 的形状，
脚本只是原样搬进内存、每回合再序列化一遍，所以这笔冗余在证据文件里会被乘上回合数。

---

## 2. 每回合增长的结构清单（按体积排序）

字节为紧凑 UTF-8 实测（t3 = 第 3 回合），"封顶"指该结构在第 20 回合还会不会继续变大。

| 结构 | 代码行 | t1 | t2 | t3 | t2→t3 | 封顶 | 备注 |
|---|---|---:|---:|---:|---:|---|---|
| `turns[].snapshotAfterTurn` | 1024 | 607,738 | 899,645 | 912,270 | +12,625 | 否（线性） | 幂等缓存封顶 566KB；points/narrations/allocations/rolls 每回合 +6.8KB |
| `turns[].product` | 886 | 160,370 | 171,878 | 171,963 | +85 | 部分 | `microStatsAll` 是会话累计数组：4,656→9,326→13,972（+4,646/回合，O(N²)） |
| `turns[].generations` | 1040 | 8,475 | 16,917 | 25,931 | +9,014 | 是（`slice(-200)` ≈ 106KB） | 每回合 +17 条，第 12–13 回合触顶 |
| `turns[].actions` | 1028 | 16,433 | 16,430 | 16,356 | −74 | 是 | 与 product.semanticCalls / submission 重叠 |
| `turns[].submission` | 924（product 内） | 18,196 | 19,393 | 18,343 | −1,050 | 是 | 每回合 63 条 call，raw 截 4000 字符/条 |
| `turns[].console` | 1015 | 9,533 | 9,624 | 9,064 | −560 | 是 | 同时还有一份在 `environment.ggmlConsole` |
| `environment.ggmlConsole` | 230 | — | — | 28,704（累计） | +9,500 | **否** | 600 字符/条截断，条数不封顶（3 回合 340 条） |
| `turns[].before/after.transportPoints` | 515/538 | 2,449 | 4,613 | 6,786 | +2,173 | 否（线性 ×2） | 全量点表存两次，+1,085/回合/份 |
| `turns[].offscreenJudge` | 992 | 6,176 | 6,175 | 6,133 | −42 | 是 | |
| `turns[].stages` | 758 | 5,031 | 6,337 | 6,221 | −116 | 是（阶段数固定） | |
| `turns[].text + proseIdentity` | 853/858 | 8,479 | 8,536 | 8,908 | +372 | 是 | 同一段正文两个字段 |
| `turns[].live` | 1036 | 2,266 | 2,264 | 2,264 | 0 | 是 | 内含一份 generations |
| `modelRequests` | 237 | 1 条 | — | — | ~0 | 视页面而定 | 若产品每回合 POST `/api/save`，每回合 +~200B |
| `failures` | 165 | 0 | 0 | 0 | 0 | 否 | `detail` 可能带大对象（P9） |
| **整条 turn entry** | 1113 | 849,809 | 1,167,323 | 1,189,727 | +22,404 | 否 | |

---

## 3. 20 回合外推

模型：t3 实测值 + 线性斜率（快照 +12.4KB/回合，microStatsAll +4.65KB/回合，pointStates +0.5KB/回合，
before/after 各 +1.09KB/回合），generations 按 529B/条在 200 条处封顶。
第 1–3 回合用实测、第 4 回合起用上述斜率。

| 回合 | 该回合新增（紧凑） | 累计 `evidence` | 写出的证据文件（2 空格缩进 ≈ ×2.02） |
|---:|---:|---:|---:|
| 1 | 0.85MB | 0.85MB | 1.7MB |
| 3 | 1.19MB | 3.21MB | 6.7MB（与实测文件 6,734,998 B 吻合） |
| 5 | 1.19MB | 5.7MB | 11.5MB |
| 10 | 1.32MB | 12.0MB | 24.3MB |
| 15 | 1.43MB | 19.0MB | 38.3MB |
| 20 | 1.52MB | **26.4MB** | **53.4MB** |

`save()` 的代价（146–161 行）：每次调用都 `JSON.stringify(evidence, null, 2)` 整份序列化，
写 `*.tmp-<pid>` 再 rename。第 k 回合一次 `save()` 要生成约"累计 pretty 体积"的字符串并写同量字节。

- 20 回合内至少 20 次 `save()`（每回合 1 次 + 取消/刷新/失败/收尾各若干次），
  累计写盘 ≈ **530MB**，单次峰值字符串 ≈ **53MB**（中文在 V8 里是双字节，实际堆上可能 ≈ 字符串字节数 2×）。
- 磁盘峰值 = 证据文件 + tmp 副本 ≈ **106MB**。
- 这些是"序列化字节"，不等于 V8 堆占用；`evidence` 对象本身还有嵌套对象头开销，
  按经验再加 20%–60%（本次没有实跑堆采样，属估计）。

---

## 4. 修补建议（含行号、省多少、谁会被影响）

### P1. 每回合快照写 sidecar，内存里只留摘要（1024–1027 行）

做法：读出 `snapshotAfterTurn` 后立刻写 `<out>.snapshots/<id>.json`，`entry` 里只留
`{ path, bytes, sha256, headPointId, version, pointCount, narrationCount }`。

- 省：每回合 **912KB**（占该回合紧凑字节的 77%）；20 回合累计快照 19.2MB，
  文件从 53MB（缩进）降到约 **14MB**，内存峰值 26MB → 约 **7MB**。
- 风险：
  - `frontend/scripts/verify-point-replay.ts:8` 直接读 `evidence.turns.at(-1).snapshotAfterTurn` → 会崩，必须改成按 ref 读文件。
  - `frontend/src/lib/world-engine/local/state-invariants/verify-09-evidence.test.ts:124-137` 把每回合
    `snapshotAfterTurn` 收进 forward chain。它的 `filesAt()` 只列同目录 `.json`，所以 sidecar **必须放子目录**，
    否则会被当成证据文件逐个跑校验；该测试还要改成按 ref 加载。
  - 单文件自包含的交付方式被破坏：证据归档/评审要连 sidecar 目录一起拷。
  - 只留 digest 不能回放（digest 只证明字节一致），所以 digest 必须和 sidecar 成对存在。
  - 顺序必须是"先写 sidecar，再 `save()`"，否则崩溃会留下指向不存在文件的 ref；
    `--resume`/复核时应把缺失 sidecar 当失败。

### P1b. 存进证据前把快照里的重复副本去重（1024–1027 行，配合 P1）

做法：写 sidecar 之前做一次纯拷贝压缩：`transport.initial` 留一份，
`state.initial` 与 `pointStates[root/head].state.initial` 换成 `{"$ref":"transport.initial"}`；
`pointStates[head].state` 与 `transport.state` 相同时去掉一份，换 `{"$ref":"transport.state"}`。
原始快照的 sha256 单独存在 ref 里，能证明"没丢字节"。

- 省：每回合 **约 297KB**（快照 912KB → 约 615KB）；20 回合 sidecar 总量 19.2MB → **11.7MB**。
  如果不走 sidecar、直接在根 JSON 里去重，则文件再减约 7.5MB。
- 风险：`verifySessionSnapshot` / `verifySnapshotSequence`（`verify-09-evidence.test.ts:124-140`、
  `verify-point-replay.ts`）要的是真正可用于回放的状态，`$ref` 会让它们读不到 `state.initial` → 要么在
  sidecar 里写原始形状（压缩只作用于内存摘要，不适用于 sidecar），要么在校验前做一次 deref。
  建议：sidecar 写原始快照，内存与根 JSON 只存压缩后的摘要 + 原始 sha256。

### P2. 会话累计数组改成增量（913 行 `microStatsAll`、915 行 `semanticLog`）

做法：每回合只存"上次之后新增"的切片 + `fromIndex`；完整数组放顶层 `evidence.microStats`，
只存一次（结束时写）。

- 省：`microStatsAll` 每回合 +4.6KB 且被复制 N 份，20 回合约 **0.98MB**；`semanticLog` 在当前构建是 null，
  但页面一旦启用就是同型 O(N²) 结构。
- 风险：如果将来有人按回合读 `microStatsAll` 求和，会把增量当全量 → 必须同时写 `fromIndex`，
  并在文档里说明"这是增量"。当前仓库里没有任何脚本读 `microStatsAll`（`rg` 只命中本脚本 913 行），风险低。

### P3. 控制台日志：环形缓冲 + 每回合只留白名单（230、1015–1021 行）

做法：(a) `ggmlConsole` 改环形缓冲（例如保留最后 2000 条）+ 总数计数；
(b) `entry.console` 只保留 `[world-local refusal]` 与 `[narration] … rejected` 两类行（其余存条数 + sha256）。

- 省：每回合 **~9KB**（3 回合已积 28.7KB，20 回合 ~190KB，且是唯一完全无上限的容器）。
- 风险：`summarize-semantics.mjs:55-58` 专门扫 `turn.console` 找 `[world-local refusal]`；
  `entry.narrationRejections`（1016 行）由 `entry.console` 派生 → 白名单必须覆盖这两类。
  环形缓冲会让 `consoleStart`（590 行）的索引失效（淘汰后位移）→ 必须改用绝对序号，或每回合单独缓冲。

### P4. generations 只留本回合新增（1040–1043 行）

做法：保留"上次之后新增"的条目（~17 条/回合、约 9KB），另外显式保留 narration 引擎那一条；
完整 200 条只在收尾写一次 sidecar。

- 省：第 3 回合 26KB → ~9KB；第 12 回合后每回合 106KB → ~9KB（20 回合累计约省 1.2MB）。
- 风险：`summarize-timing.mjs:25-37` 的 `generationPick(turn)` 从 `turn.generations` 里找 narration 条目、
  并取全表 `maxStreamGapMs`；切片后可能找不到 → 必须显式保留 `generationNarration`，
  或让 summarizer 读 sidecar。
- 附带：`entry.live.generations`（1036–1039 行）是同一份数据的第三份，可一并去掉。

### P5. before/after 只存本回合涉及的点（538–557 行）

做法：与上一回合的 keys 做差，存 `newPointIds` / `changedPointIds` + `pointCount` + `anyAutomatic`。

- 省：每回合 **~2.2KB**（两份合计），20 回合累计 ~0.26MB；量小，但它是 O(N²) 结构，点数多了会放大。
- 风险：`summarize-semantics.mjs:59` 用 `turn.after.transportPoints` 判断是否存在 `trigger === 'automatic'`
  的点 → 保留 `anyAutomatic` 或保留 trigger 字段即可；没有其它脚本读 `transportPoints`。

### P6. `save()` 去掉 pretty 缩进（150 行）

做法：`JSON.stringify(evidence)`（紧凑），或只重写"根索引 + 本回合文件"。

- 省：写盘总量 **530MB → 约 260MB**，峰值字符串 **53MB → 约 26MB**，每次 save 的停顿时长减半。
- 风险：按行读该文件的人/监控（tail、按行 `rg`）会失效；与 `artifacts/` 里已有的 pretty 证据做 diff 会全篇变化。
  所有 `JSON.parse` 消费者不受影响。`--print` 只走 `summary`，不受影响。

### P7. 把 turns 拆成每回合一个文件（1113–1114 行 + 全篇）

做法：`<out>.turns/turn-01.json` …，根 JSON 只留 runId/status/summary/failures 和每回合的摘要；
另提供 `loadEvidence(path)` 把根 + 目录拼回完整结构。

- 省：这是**唯一改变增长曲线**的补丁——内存峰值从 O(N)（26MB）变 O(1)（每回合 ~1.2MB）。
- 风险（改动面最大）：所有遍历 `evidence.turns` 的消费者都要改或走 `loadEvidence`：
  `summarize-acceptance.mjs`、`summarize-timing.mjs`、`summarize-narration.mjs`、`check-prose-facts.mjs`、
  `selftest.mjs:127-133`、`verify-09-evidence.test.ts:95-140`、`verify-point-replay.ts`。
  建议在 P1/P2/P6 之后再做，并且保留 `--evidence-single-file` 开关给旧的归档流程。

### P8. 删掉 `evidence.submissions`（1369 行）

做法：它是 `turn.submission` 的重复数组（内存里同对象引用，文件里第二份，~18KB/回合）；
`summary.submissionCalls`（1380–1385 行）改成直接从 `evidence.turns` 算。

- 省：每回合 **18KB**，20 回合 ~364KB（只省文件，不省内存）。
- 风险：`frontend/scripts/parallel-settlement/check-run.mjs:29` 认识 `input.submissions`，但同一函数
  也认识 `input.turns`（:30），所以删掉后仍能跑；其它脚本不读它。

### P9. `refreshRestore` 里的大对象（1252、1281–1305、1312–1314 行）

做法：`snapshotAfterReload` 按 P1 存 ref + digest；`noteFailure('reload', …, evidence.refreshRestore)`
（1312–1314 行）只传计数与布尔，别把整个对象塞进 `failures.detail`。

- 省：收尾一次约 **0.9MB**，失败路径再省一份重复（同一内容在文件里出现两次）。
- 风险：`verify-09-evidence.test.ts:128-137` 会用 `refreshRestore.snapshotAfterReload` 参与全链校验，需同步改；
  `selftest.mjs:134` 读的是 `evidence.refreshRestore.entriesKept`，而脚本写的是 `entriesRestored`
  （**这条断言现在已经对不上**，改这里时顺手确认，别把它当回归）。

### P10.（可选）semanticPrompts / pointPrompts 存摘要（906–907 行）

`product.semanticPrompts` 每回合 50–61KB、`pointPrompts` 每回合 10.5KB，合计占 product 的 40%。
可以只留 `promptChars` + `sha256`，原文写 sidecar。

- 风险：失去"提示词里不含上一回合正文"的原文证据。当前仓库里没有脚本读 `evidence.turns[].product.semanticPrompts`
  （页面 `phone-evidence.tsx` 读的是 `__worldTurns.semanticCalls`，不是这个字段），但 05/06 的叙事校验可能依赖，
  需先确认。另注：`submit.calls[].prompt` 在这份证据里是空的（prompt 字节数只有 190），别把两处搞混。

### 建议顺序

P2 → P6 → P8（低风险、纯缩水）→ P3/P4/P5（要动 summarizer 字段）→ P1/P1b/P9（要动 2 个校验脚本）
→ P7（要动 6–7 个消费者，收益最大但要单独一轮）。

叠加预估（口径见第 3 节，均为紧凑 UTF-8；缩进后 ×2.02）：

| 做的补丁 | 20 回合证据体积 | `save()` 累计写盘 | 内存峰值（`evidence`） |
|---|---:|---:|---:|
| 现状 | 53.4MB（紧凑 26.4MB） | ~529MB | ~26MB |
| P2+P3+P4+P8（只缩常数） | 47.9MB（紧凑 23.7MB） | ~485MB | ~24MB |
| 再加 P6（紧凑写盘） | 23.7MB | ~240MB | ~24MB |
| 再加 P1（快照外置） | 根 4.6MB + sidecar 17.4MB（原始） | ~64MB | ~5.5MB（根 + 一回合临时快照） |
| 再加 P1b（sidecar 去重） | 根 4.6MB + sidecar 11.7MB | ~58MB | ~5.5MB |
| P7（每回合一文件） | 总量同上 | 同上 | 与回合数无关（~1.2MB/回合临时） |

---

## 5. 顺带发现（不是内存问题，但影响证据可信度）

- `displayedEqualsRaw` / `priorProseLeaks`（1158–1219 行）依赖 `turn.candidate.tail`，而本脚本从不写 `candidate`。
  结果是这两项在这份证据里恒为 `null` / 空数组——看起来"检查通过"，实际**没有检查**。
- `evidence.finishes`（129 行声明）在全篇没有任何 push，永远是空数组。
- `--resume` 只保留浏览器存储（`keepStorage`），不会读回已有 `out` 文件；当 `out` 已存在且带 `--resume` 时，
  `evidenceFile = out`（101–103 行），新对象会**覆盖**旧证据，而不是续写。

---

## 6. 未做 / 未验证

- 没有实跑脚本，没有采 Node 堆（`process.memoryUsage()`）；本文所有字节数都是**序列化后的字节**，
  堆上还要加对象头与 V8 双字节字符串开销（估计 +20%–60%）。
- 20 回合数字是外推（第 1–3 回合实测 + 线性斜率），不是跑出来的。
- 幂等缓存的"200 条上限"是从这份证据的 99→198→200 和最大序号 413 推断的（有淘汰、有封顶），
  没有读产品代码确认常量；如果别的构建把这个上限调大，快照会按"每条 2.8KB × 上限"再涨。
- 页面侧 `__worldTurns` / `__worldGenerations` / `__microStats` 自身的常驻增长不在本次范围
  （那是产品内存；脚本只是把它们的副本搬进 Node）。
