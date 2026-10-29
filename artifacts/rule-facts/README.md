# 事实与规则边界、确定性提交及输入裁剪

日期：2026-10-27。实现提交 `2a6eff2654de81b45c07afe01ea47f8aa63b82ca`。
服务端仍为 `0cb1951`，共享摘要仍为 `90291801…`，未改 A/B 冻结契约。

**受支持命令已打通规则判定→Δ→现有提交链→已提交事实→模板叙事。**
真实 HTTP/SQLite 十个场景通过；输入裁剪显著降低本机两组可完整计量的 prefill 成本。
模型润色未放行：完整输入超时，裁剪输入重复表达，均未进入状态或替换模板。
本批不接最小页面，不宣称完整 B3/完整模型链通过。

## 1. 事实来源与允许结果

| 层次 | 来源与身份 | 允许用途 |
| --- | --- | --- |
| 行动提议 | 与服务端 pending inputId/advanceId 绑定的原始玩家命令；或另行比较的模型建议 | 请求执行，不证明事件已经发生 |
| 执行判定 | 程序安装的规则＋服务端 preview 状态、点位时间及既有任务；RuleAuthority 签发进程内 receipt | 生成待提交的确定性 effects/Δ，仍不等于已保存状态 |
| 已提交事实 | commit 成功后按 pointId 重新 get_state，读取保存的原始 Δ 与前后状态 | 模板叙事及受约束润色的唯一事实依据 |

receipt 用 WeakMap 识别真实签发对象，绑定 world/advance/input/round/point、基线版本/摘要和
lease epoch；JSON 副本、结果文本或 `{outcome:"allowed"}` 不能重建它。inspect 只返回副本。
results 描述由规则判定生成；updates 必须持有同组 receipt，并核对描述没有被换掉，
但描述相同本身也不构成执行授权。

用户已明确选择沿用现有“任务达成→人格变化→理智重算”联动，不开放独立 sanitySet。
因此数字案例预先在初始世界中放入真实待完成任务；不在 stage 时补造任务或人格变化。

| 支持命令 | 前置条件与判定依据 | 允许结果 |
| --- | --- | --- |
| `走到门厅` / `走到<已知地点名或ID>` | 主角、pending 输入、位置可解析为地点；程序登记的有向路线；走廊→门厅要求理智≥5 | 原地点→目标地点；slotId/relativeTo=null。已在目标、无路线、门槛不足则无人物 Δ |
| `完成压力试验` | 既有 task_pressure 属于主角，目标文字匹配且 pending；人在走廊；preview 时间比已提交基线推进至少1秒；结果在0–10 | 达成该任务＋规则规定的“经历压力试验后更谨慎”人格变化＋理智减2，三者一起提交 |
| `完成恢复练习` | 同上，匹配 task_recover；规则规定的恢复练习与1秒执行周期 | 任务达成＋“完成恢复练习后更善于自我调节”＋理智加1；超过10则整项拒绝，不截断数值 |
| 自然语言声称“已经到门厅/已经变成8” | 不属于受支持命令，也不是执行凭据 | 不产生 receipt/effects；该示例处理机会以跳过/空点结束 |

这是显式登记的游戏模拟规则，不是对任意动作或自然语言结果的自动解释器。
一次尝试占用一个1秒 normal 点；拒绝或不支持时无人物/数值变化，但时间与输入处理机会
仍会提交一次。每个示例以新世界、新控制器执行一个单主体命令，不提供通用多组规则授权。

进程内 receipt 是可信应用边界，未新增服务端认证协议。底层通用 ControllerDriver＋任意
WorldModelPort 仍可用于旧实验；本批事实保障来自新的 createRuleController 组合入口。
未宣称任意恶意客户端提交都由这套客户端规则拦截。

## 2. 确定性 Δ 与真实提交

复用既有 ControllerDriver：服务端分配 advance/input/round/point/group → 开点及基线 preview →
规则判定 → 确定性 updates → 候选身份分配 → stage → 封点后的候选 preview → commit。
移动只生成 positionSet；数值案例生成 tasksAchieved/personalityChanges/sanitySet 的合法联动。
人格变化草稿 ID 经原 ensureCandidateIdentities 分配/改写；不写入模型自选的永久身份。
没有修改共享 schema、导出物、错误表、服务端校验或旧冻结基线。

[http.json](http.json) 保存逐场景源提交/源码摘要、输入命令、规则判定、原始状态/Δ、
调用顺序、保存锚点、模板文本和重放裁决。
[database-evidence.json](database-evidence.json) 是停服后只读 SQLite 核对：
10 个世界各恰好一个成功 commit；输入均 consumed/ended；point/change ID 均有分配行；
服务端保存的叙事逐字匹配模板，共20条根点＋正常点叙事。
不归档数据库、租约或原始服务日志，不新增长期行动历史表。

十个场景：移动成功、移动门槛不足、数值下降成功、下界拒绝、恢复成功、上界拒绝、
任务缺失、执行时间不足、自由文本不是事实、提交成功但响应丢失。
每场景另测同 requestId 重放、换 requestId 重交旧点及消费后的执行判定拒绝。
丢回执场景两次线上 commit 交换使用同 ID/载荷，数据库仅一条成功提交和一次数值变化。

## 3. 已提交事实叙事

projectCommittedNarration 读取保存点和紧邻前驱，核对 point/version/world、原始 Δ、
当前位置与数值，以及任务和人格因果记录。人格记录必须来自该提交点及其 sequence。
未声明的状态变化、不完整的数值因果、未知字段或不一致读取均停止，不猜测缺失事实。

基线模板选择少量“当前人物位置/数值＋本点移动/数值及其任务人格依据”，不读取行动提议
或 results 文本重建事件。例：`周宁的精神值从10变为8。周宁完成了任务「完成压力试验」。`

润色只允许每条事实的两个明确短句变体，可换顺序，每项一次。
未知合句、错误人物/地点/数值、增加事件、遗漏或重复都拒绝并退回模板。
这是有限表达语言的完整匹配，不冒称通用自然语言语义检测器。

## 4. 按任务裁剪与本机成本

RuntimeWorldModelPort 新增显式 inputMode=focused，默认仍 full：
action 保留当次人物、命令/消费状态、本人任务/个性/当前数值、地点和附近实体；
updates 位置/理智阶段只保留相关当前字段、描述与规则判定副本（仅作候选比较）；
narration 只传经保存读取核对的事实及短句，不再重复 initial/live 的完整前后状态。
其他任务/阶段不擅自裁剪；无保存读取凭据的叙事保留完整输入，错误绑定直接拒绝。

真实 Edge、Qwen3-0.6B-Q4_K_M、CPU 4线程、n_ctx4096、temperature0、seed42。
两个 arm 的输出要求与 token 上限相同；cache_prompt=false，完成的五次调用实际 cache_n=0。
叙事两边都有同一事实短句及表达要求；full 额外携带 before/Δ/after 一次，未双传 get_state 对象。

| 任务 | full prefill | focused prefill | 本次观测 |
| --- | ---: | ---: | --- |
| action | 79.1秒 / 907 tokens | 28.3秒 / 469 tokens | prefill 约减64.3% |
| updates/sanity | 69.1秒 / 1092 tokens | 25.5秒 / 431 tokens | prefill 约减63.0% |
| narration | 120秒限额内未正常结束；无最终计数 | 18.4秒 | 完整输入已有部分输出；不能把120.3秒墙钟填成 prefill |

每任务仅一对，非统计结论；恢复断点导致两个浏览器会话，设备/配置/权重与运行时代码相同。
五次已完成调用的缓存计数为0；超时调用计数缺失，未伪报为0。
行动 full 还附加了未请求的压力试验，自动关键词判据曾误放行；focused 移动提议正确。
两次数值阶段候选正确为8，仍无权自行形成提交事实。
focused 叙事约26.3秒，但逐条重复两个短句变体，虽位置/数值正确，仍被拒绝并使用模板。

## 5. 原始证据、断点恢复与复跑

[latency-first.json](latency-first.json) 保留前五条实际调用，包括完整叙事的超时/部分输出。
初版 runner 误要求超时调用也有 cache_n，因此中断；其精确源码快照为
[runner-first.txt](runner-first.txt)，不作为执行入口。
[latency.json](latency.json) 从原报告续跑，仅新增最后一条 focused 叙事，没有重付前四条成功调用。
resume 校验参数、事实源、资产和除 runner 外的运行时摘要一致；前五行保持原样。
[review.json](review.json) 分开记录规则/模板验收、模型内容问题与处理耗时。
[polish-selection.json](polish-selection.json) 以同一已保存事实和原始裁剪候选实际调用
selectFactNarration：拒绝重复润色，选中的模板与已保存文本逐字一致，未新增模型调用或覆盖叙事。

```powershell
# B/frontend；A checkout 由 --server-checkout 必填指定（旧默认路径已退役），端口18784必须空闲
node scripts/review-world-rule-facts.mjs --server-checkout <服务检出> --out .local/rule-facts-replay.json
node scripts/run-b3-focused.mjs --http-report .local/rule-facts-replay.json --out .local/focused-replay.json
# 中断后保留所有已付调用（失败也不自动重试），只补剩余项
node scripts/run-b3-focused.mjs --http-report .local/rule-facts-replay.json --resume .local/focused-replay.json --out .local/focused-resumed.json
```

HTTP 脚本先确认端口空闲，新建隔离 SQLite，隐藏启动持久化 app，finally 停服；
浏览器脚本对 HTML 显式设 COOP/COEP，120秒原生生成期限＋140秒外层 watchdog，finally 关闭
浏览器/Vite。需本地模型/wasm 和 Python/前端依赖；未下载新权重。
仓库根目录可运行 `node artifacts/rule-facts/verify.mjs` 核对清单与来源。

验证：前端 **553/553**，双 tsc 通过，真实 SQLite **10/10**，归档源码绑定/哈希通过。
实现与评测均发生在 `9905209` 上的变更工作区；清单绑定到 `2a6eff2`，保留真实 head/status。
初版 runner 的唯一源码差异由精确快照单独绑定，未把恢复后的源码冒充首次测时源码。
本批交付待复核通过后，再接少量支持指令的最小交互页面。
