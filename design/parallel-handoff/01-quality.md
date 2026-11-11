# 01 独立叙事质量：检查器、复核结果、开发包（2026-11-10）

本文件是给 06（集成）和 02（生成）的可核查交接。所有结论是 AI 逐条复核，`reviewKind=independent_agent`；没有真人签字，也没有产品通过声明。

## 1. 交付物

| 内容 | 路径 | 状态 |
|---|---|---|
| 独立检查器模块 | `frontend/src/lib/world-engine/local/narration-quality/`（`review.ts`、`scene.ts`、`lexicon.ts`、`types.ts`） | 8 passed / 1 skipped（`--maxWorkers=1`），tsc/eslint 干净 |
| 正反例校准 | `experiments/narration-quality/review/anchors.json`（17 例）+ `anchors.test.ts` | 全绿；每个反例都对应真实运行里的失败文本 |
| 逐句复核记录 | `experiments/narration-quality/review/findings-2026-11-10.md` | 08/02/04/旧 199 行 |
| 公开开发包 | `experiments/narration-quality/dev-package-v1/`，共享副本 `results/quality/dev-package-v1/` | 15 例，输入/参考/包哈希冻结 |
| rubric + 晋级门 | 包内 `RUBRIC.md` | 在看 11/12 输出前写定 |
| 独立验收登记 | `results/product/independent-acceptance/registry.json` + `gate-report.json` | `not_ready`，14 条真实原因 |

## 2. 检查器判什么

**硬错误**（`fact.*`）：时间未表达/数字错、移动方向反转或漏述、任务完成/漏述、精神值数字错、个性/外貌与结算不符、物品被写到错误的人手里（含"手里空着"矛盾）、无据事件/声音/往事/承诺/结果、无据人物物品、视角内心越界、性别代词错。

**文风失败**（`style.*`）：状态面板、字段句、名单播报、复述前文、重复结尾/开头、同词循环、重复标点、截断、元叙述。

**只标待复核**（`review.*`）：细微动作、情绪反应、指代可解性、同义改写是否表达必述事实。`pending` 不自动通过。

## 3. 真实失败（详见 findings 文件）

1. **08 的 1.7B accepted 文本**：性别/指代（周宁被写成"他"，08 已记录）、无据脚步声（续写点无人移动）、无据物体细节（"灰粒"）、任务/个性字段成句、地图标签复述、跨回合开头逐字重复。技术速度保留，`met` 不成立。
2. **02 的 accepted 102 字文本**：0 事实错误，但五句全是字段播报；根因是提示把字段句当【前一句】，并逐 beat 拼接。
3. **04 程序成文**：事实骨架正确，但把未结算的"担架被拖到门口"写进正文，并把任务/个性写成清单句。程序模式不是事实自动安全。
4. **旧 199 行监督**：198/199 行不写时间推进；17 行漏移动；8 行无据脚步声；5 行无据往事；2 行视角越界。旧行不能当时间/移动覆盖的正例。
5. **05 的 3 行连续片段**：`tide-duty-t1` 有一句无依据脚步声（该回合无人移动），已发 05。

## 4. 误报与修正（保留记录，证明不是靠放宽通过）

- 物品随人搬移（`tide t3` 潮位计 仪器间→值班室，罗平同向移动）：原先误报"物品在场景却被写成抱着"，已修为合法。
- "她以前……"与已结算外貌变化对比：从硬错误降为复核。
- "合上簿子/拿起杯子"这类日常道具动作：降为复核（用户允许的细微动作）。
- "松了口气"是可见反应，不算视角越界。
- 单字/双字姓名包含关系（`天台` ⊂ `天台楼梯间`）：改为最长匹配 + 位置归属校验。

同一批输入前后的误报没减少语义要求：71 行人写目标仍是 **0 条事实错误**，风格标记从 31 条保持不变；旧 199 行的事实标记总数 232（时间缺失 198 为主）。

## 5. 给 06 的集成方式

- 新模块只依赖自身，不 import 产品页/runtime；接线由 06 决定。
- 建议入口：`reviewNarration({id, input, text, options})`；`options` 可传 `genders`、`priorTexts`、`mustNotReveal`、`licensedEntities`。页面集成时可只用 `counts`+`findings` 做门，`review/pending` 不拦生成、只记录。
- 批跑：见 `dev-package-v1/README.md`。
- 不要用它替代 02 现有的 `verify.ts`；两者可并存，由 06 决定哪个做产品门。`verify.ts` 归 01 的写权请求在 `results/product/ownership-requests/01-narration-quality-verify.json`。

## 6. 未做的

- 没有独立终验批次（现有 15 例全是公开开发材料，01/05 都写过其中一部分，不能当盲测）。
- 没有真人读评；没有 10/20 回合完整正文的跨回合复核（等 09 的真实运行）。
- 没有宣布任何产品通过。

---

# v2：充值恢复后的状态（2026-11-10 晚）

## 已完成

| 项 | 位置 | 状态 |
|---|---|---|
| 独立检查器（审读/门/跨回合/性别登记） | `frontend/src/lib/world-engine/local/narration-quality/` | 提交 `99d85f19`，38 条锚点、29 测试全绿 |
| 开发回归包（给 11/12） | `results/quality/dev-package-v1/` | 15 例 + RUBRIC 已发布，标注"公开开发回归、永不终验" |
| 独立终验批次 v1 | `results/product/independent-acceptance/final-batch-v1/` | 6 例在看任何候选输出前冻结；01 回避；05→03 评审（等声明） |
| 独立验收登记 | `results/product/independent-acceptance/registry.json` | `not_ready`，含 checkerDrift 说明；工具不替人判正文 |
| 真实输出复核 | `results/quality/findings-*.md` | Qwen3 三臂 ×2 轮、clean 轮、LoRA 臂、0.5B smoke、10 回合程序成文、K1 失败回合 |

## 本轮新增的硬错误类别（都由真实输出驱动）

`fact.time_added`（没结算时间却写"一分钟过去"）、`fact.trait_as_event`（条件句变当前事件）、`fact.object_speaks`（静物发声）、`fact.state_contradiction`（枪口朝向/身体痕迹左右）、`fact.body_mark_added`（结算里没有的伤）、`fact.wrong_place`（人物写到结算地点之外/外侧）、`fact.past_added` 扩展（弹片刮过）、`style.placeholder`（只显示省略号）、`style.meta` 扩展（本组结算/程序成文/降级）。

同时**放宽**了两类曾被误判为事实错误的允许润色：场景物品被短暂拿起/放下、无引号对白与手中持有物——都降为待复核，避免把手写正文删空。71 条人写目标仍 0 事实错误。

## 页面证据现状

- `09-product-10turn.json`（旧）：回合 1 是程序成文（108 字），回合 2 只有"…"；四层只存了计数，第 2 回合计数还是第 1 回合带来的。已在 `requests-01-to-06-real-turn.md` 逐句记录。
- `09-one-legal-turn.json`（K1 后）：页面不再显示"…"、不写历史、给出可恢复提示（改善）；但回合从不发出"结束"信号，驱动等满 330s，且失败提示带着成功路径的标签"正文已按已结算事实修正"。
- 驱动侧 done 条件只认 `本轮完成|本轮已交还|本轮停止`；建议改读 `__worldTurns[last].done/failed`。

## 仍未完成

1. 09 的真实十/二十回合完整正文（跨回合检查代码已就绪并在这两回合证据上跑通）。
2. 终验批次的 05/03 评审声明（登记保持 `frozen_pending_reviewer`）。
3. 用户实际阅读试玩；在此之前不宣布任何产品通过。

## v1.1（2026-11-11）

- 开发包重建为 `narration-dev-package-v1.1`：三例旧 delta 形状规范化（`任务` 快照→`完成任务`、裸 `外貌`→`新增外貌`、字符串→数组），时间串去空格；facts 未变，`v2_render` 15/15 可序列化。11 的 12/15 子集声明应撤回。
- 晋级门有批跑命令：`frontend/src/lib/world-engine/local/narration-quality/gate-batch.test.ts`，三种结果 `accept_as_model_prose` / `hold_for_review` / `regenerate`；示例在 `experiments/narration-quality/gate/`。
- 检查器新增：护目镜"挂在胸前 vs 戴在眼前"、专属饰物归属（发圈/识别带）、同一处细节换物质、性别代词绑定、声音去重。48 条锚点，31 测试全绿。
- 页面身份检查有 2.4 秒时序竞争（`__worldTurns` 在 mount effect 里），已同时报 09/06；09 已改名 16:42 那次为 `-wrong-globals`，16:46 重跑。

## 2026-11-11 01:30（按 QUALITY-PRIORITY-20261111 执行）

**17:01 真实页面回合已按点/调用拆开**（`results/quality/findings-09-1701-turn.md`）：

- updates 142159 ms 是六阶段总耗时；第一点叙事 57519 ms 被 `wrong_person,low_support` 拒绝；随后 continuation 11982 ms、time_scan updates 64321 ms、第二点叙事无候选；整轮 330131 ms 超时，`historyDelta 0`，显示 0 字。
- `firstReadableMs 173686` 对应的是**程序成文**，不是模型正文；`acceptedMs null`、`source draft`。不能再把"160 秒无正文"当成实际调用链。
- 最终存下的 49 字草稿 0 fact、2 条 review（细微动作、视角心理）；被拒候选原文没存，所以守卫对错无法判定，只能判定"证据不足"。
- 程序成文自身有 `time_added`（该点无时间）与验收口吻"符合行动要求"；第一段可读文字是它。

**检查器新增/修正**（50 锚点，31 测试）：

- `style.state_recital`：有移动/任务变化的点写成状态清单 → 判 regenerate；82 字清单会触发，71 条人工短场景 0 误伤，无变化安静段不触发。
- `路明非的护目镜` 这类"物品名包含人名"仍算点名了本人；`她手里的短枪` 按性别/上一句点名绑定；身体痕迹按**所在分句**定归属；`从胸前摘下` 不算"戴着"。
- 回归：human-71 0 fact、终验参考 0 fact、开发包 v1.1 仅 2 条已知参考缺陷、browser09 17/52。

**篇幅契约测量**（`results/quality/length-contract-01.md`）：页面 140–220/160–240、采用门槛 ≥100；01 短语料中位 97、10 的 82 条中位 94、开发包参考 98、终验参考 56–86；只有 05 的 11 条中位 248 符合长契约。等 06 定一个数。

**12 字重合**（`results/quality/overlap-12char-01.md`）：82 条自身 59 个共享窗口里 54 个是通用句法，content 仅 3 个；199 条里 1514 个共享窗口，content 仅 1 个；10 的 10 份 LoRA 采样 content 为 0。要求 10 落盘 5 条 dev 原文再复核"4/5 开头相同"。

**04 的真实候选正文复核**（`results/quality/findings-04-candidates-01.md`）：两条 `grade: program` 的 adopted 文本都含 `路明非：无判定。` 占位结果、环境字段句（"推拉门可回服务巷"）和物品/外貌清单；第二条模型尝试 179.5 s 失败后程序补上，总耗时仍 3 分钟。这些是玩家会看到的草稿文字，需 04/06 修；不冒充模型正文。

**17:37 回合（0b69aaa8）**：`results/quality/findings-09-1737-turn.md`。updates 133.6 s（position 11.7 / appearance 27.8 / tasks 40.5 / subtasks 18.9 / personality 34.6）；narration 56.9 s 被拒；**程序兜底自己被拒**（`fact_time_wrong×2 + too_long`）；玩家看到的 568 字草稿后半段是 14 个角色逐条"完成了「任务目标」"——来源是 `game-model.ts` 的 `factualNarration` 遍历全部 `entityDeltas`，没有按视角/在场过滤。action nono 三连 `action_is_task_goal` 修复失败。已写进给 04/06 的请求（追加七）。

**10 回合暂不接受（2026-11-11）**：17:37 回合（0b69aaa8）超时 330 s、无合格正文，但重载后 `committedEntries=1`、`headPointId=point_round_3_1`、historyCount 0→1、任务列表少了一条——结算点被提交、正文没有。08 的复核请求成立。已发 `results/product/browser-requests/01-input-ten-turn-hold.json`：10 回合验收在 06 证明每轮提交载荷（pointId/digest/实体变化/history 条目/textSource/acceptedMs 或"无正文"标记/回滚状态）之前不予接受。

**06 provenance / 篇幅契约（2026-11-11）**：`results/quality/review-06-20261111-provenance.md`。c02f527a 的 draft/program 标注与 17:37 证据一致；但 02 的 `7f8e102f` 无变化回合提示 84～120 字，06 接受门槛仍是 140 字（`game-model.ts:416/511`），prose-facts 路径下无变化回合必被拒。需要 06 把门槛写进 policy、02 从 policy 派生，不能两边硬编码。04/03 的修复只能由真实回合验证。

**更正 + 性别表（2026-11-11）**：17:37 证据里 `turns[0]` 前后任务列表其实完全相同，"任务少一条"是 `refreshRestore` 面板窗口差异，已在 `findings-09-1737-turn.md` 与 ten-turn-hold 里显式更正（提交点仍由 committedEntries/headPointId/historyCount 支撑，但载荷未证明）。检查器采用 05 的 `character-gender-evidence.md`：路明非/诺诺/楚子航/林亦舟/沈澄 五人带引文来源，周宁仍按 08 的人工记录；q3 里 10 句"周宁…他"变成硬错误，"诺诺的发圈…他没说话"保持歧义（男性视角在场）。锚点 56。

**开场 wrong_person（2026-11-11）**：cf3d027e 的开场 88.6 s 后被 `wrong_person` 拒绝 → 程序兜底。原因是提示词只写"X 视角"、没写第三人称，而 `narration-alignment.ts:331` 只收第三人称（引号外出现"我"即拒）。已写 `requests-01-to-06-real-turn.md` 追加八：建议 02 在提示词明确第三人称；否则 06 的对齐器要接受"我=视角人物"。被拒原文仍未存，无法进一步判断。

**cf3d027e 合法回合（2026-11-11）**：`results/quality/findings-09-cf3d-turn.md`。开场 88.6 s 被 `wrong_person`/`repetition` 拒；玩家回合 303.5 s，narration 58 s 被拒 `added_event,ungrounded,low_support`，提交程序文本（`textSource: program`，`firstReadableMs null`）。程序文本以**凯撒**开头（玩家是路明非），并有"诺诺：未成功触发…"的内部判定句；最可能是 `game-model.ts:742-750` 把整段 `resultsText` 逐句拼进正文，只去掉了视角人物的名字前缀（results raw 未存，属推断）。03 的 action 修复见效（无 `action_is_task_goal`）；04 无任务点名册但两次自动轮仍各 76 s。10 回合仍不接受。

**02 accepted 的 unseen 189 字含未结算裁纸刀（2026-11-11）**：`results/quality/findings-02-unseen-01.md`。02 标 accepted 的稿子里"黎含章的裁纸刀在桌角…"不在结算输入（只有三本登记簿、算盘），是 `fact.object_added`；同一稿"三分钟过去"重复两次（`style.punctuation`）。检查器工具规则已扩展到"出现且未结算即判"，锚点 60（`neg/unseen-accepted-knife`）；human-71/final-v1 仍 0 事实。

**状态（2026-11-11 02:28Z）**：06 冻结 `2324cde1`（page `7bfcdb99`），新增完整 committed snapshot + narration sources 供状态复核；尚未包含 resultsText/开场第三人称的正文修复。09 在 2cc873e4 上试的 joint-group（`09-joint-group-cf3d-invalid.json`）因页面 sha 不匹配 + Qwen3-0.6B 分片 fetch 失败判 INVALID，不是产品正文证据。等 09 在 2324cde1 上的合法回合；本轮检查器已到 60 锚点，human-71/final-v1 仍 0 事实。

**新链入口（2026-11-11）**：06 页面 `2324cde1` 已支持 `?narrationModel=qwen3-1.7b&narrationCandidate=trained&narrationMode=scene&narrationShape=prose-facts`，并记录 `__worldArm`（含模型文件 sha256）。但 09 驱动 `accept-world-local.mjs:210` 是 `goto(${base}/)`：把 query 放进 `--base` 会被追加 `/` 弄坏最后一个参数，传纯 base 则 candidate=auto（02 报告 auto 选不到 productDefault → 不调模型）。已发 `results/product/browser-requests/01-input-arm-url-needs-driver-query.json`：09 需要 --query/--url，06 需确认入口或设默认；否则唯一优先链跑不起来。按用户 02:30 指示，140 字硬门槛不再作为拒绝理由，06 修订契约。

**新链真实回合（2026-11-11）**：`results/quality/findings-09-new-chain-2324.md`。2324cde1 上 arm 身份核对通过（qwen3-1.7b，b139949c…，trained/scene/prose-facts）。开场 60.8 s 模型正文 fallback=false，但 01 判 4 条 state_contradiction（红发垂落、左臂红痕、识别带挪发圈、胸袋弹匣）。玩家回合 narration 124 字 0 violation，被 `time_missing` + `low_support`（124<140）拒掉 → 程序兜底（仍以凯撒为主角、含内部判定句）；330 s，historyDelta 0。已发 `requests-01-to-06-new-chain-2324.md`：06 去掉 140、决定时间要求、把 gate 接开场/玩家点；02 修四句。

**新链复核补充（2026-11-11）**：开场 207 字模型正文存在 `transport.narrations`，但页面只渲染 `entries`（只含 player 点），玩家看到的是"等待输入…"，这段唯一模型正文不可见。玩家回合 124 字 0 violation 被 `time_missing`+`low_support`(124<140) 拒；06 `f15d7a98` 已去掉 140（minChars 20）、提示改为按内容定长，时间门槛未定。刷新 `narrationSources: null`、historyCount 0→1、驱动判 state changed。已发 `requests-01-to-06-new-chain-2324.md`（含请 09 记录 `__worldTurns` 的 rawAttempts）。

**f15d 独立复核（2026-11-11）**：`results/quality/findings-f15d-01.md`。06 `f15d7a98`、qwen3-1.7b `b139949c…`、trained/scene/prose-facts；等待 299.3 s、接受 287.4 s、25 semantic + 3 narration。页面 `turns[0].text` 是**自动轮** `point_round_auto…` 的 185 字，不是玩家点 `point_round_3_1` 的 180 字（玩家点 17.4 s 已生成但被 `updateLast` 覆盖）。硬错误：自动轮"手中护目镜"（结算挂在胸前、右手空着，末句又写手中没有东西）、规则牌声响、"时间已到"；玩家点"胸袋还有一只弹匣"（结算只说能放）、漏"读规则牌"结果；开场左臂红痕、发圈松散、胸袋弹匣。玩家点与自动轮最后一句完全相同。source=model/COMPLETED/violations=[] 不是质量证书；287 s 不是 60 s。已发 `requests-01-to-02-f15d.md`、`requests-01-to-04-f15d-review.md`，并在 `requests-01-to-06-new-chain-2324.md` 追加"自动轮覆盖玩家点正文"。124 字旧回合拒绝原因已更正为未证明。

**程序兜底精确位置（2026-11-11）**：`results/quality/requests-01-to-06-program-projection.md`。06 当前 `game-model.ts:746` 仍把 `resultsText` 按 `；` 拼进正文（凯撒/内部判定句），`783-788` 把所有实体 `tasksAchieved` 写成正文（17:37 的 14 人清单），`765-771` 用 `initialAppearance` 而非当前外貌。f15d 走模型正文未触发，但下一次任何 fallback 会重现。

**下一次 09 run（2026-11-11）**：06 已冻结 `6bd382d0`（build xQg4…, pid 25132，含 02 的 invented-mark/filled-hand/quiet-turn 修复）。`results/product/browser-requests/01-input-to-09-f15d-next-run.json` 请 09 在 6bd382d0 上跑，逐点记录最终原文/attempt/拒绝原因，并确认自动轮不再覆盖玩家点；f15d 的 185 字自动轮不是玩家点正文。

**阻断下一次 09 run 的显示 bug（2026-11-11）**：`results/quality/requests-01-to-06-narration-binding.md`。`page.tsx:639-666` 的 `onNarrationComplete/onNarrationProgress` 仍无条件 `updateLast`，自动轮 narration 会覆盖玩家点 entry；f15d 的 185 字就是这样顶掉 180 字玩家点正文的。在这条修好前，09 的"最终正文"仍不是玩家点的；先修绑定，再跑一回合。

**6bd3 run 两次中止（2026-11-11）**：`09-one-legal-turn-6bd3-lease-aborted.json`（19:17，开场 54.3 s 后）和 `-preprojection.json`（19:21，开场 50.8 s 后）都在玩家回合前停住，没有回合记录；疑似 lease/preprojection。已在 `results/product/browser-requests/01-input-to-09-f15d-next-run.json` 记录，09 需先接管 lease 再提交玩家回合。这两条不是产品证据。

**02 复跑 `quiet-minute-4`（2026-11-11）**：147 字、accepted、24.0 s、首字 8.2 s，在 02 `28f30c7e` 上。01 检查器判 1 条硬事实：`诺诺一步步走近`（无结算 move，`fact.event_added`）；`钟声` 判 review（远处地标氛围，不是事实），`泥土味` review，`用发圈束住红发` review（静态外貌演成动作）。同一输入的三次复跑：-2 时间缺失+脚步声、-3 红发垂落、-4 诺诺走近；各剩 1 条。已发 `results/quality/answers-01-to-02-quiet-minute.md`。06 当前 build 只合到 `beb09bb4`，还没 vendor `1c826929`/`28f30c7e`。

**6bd3 中止的可能原因（2026-11-11）**：09 driver 没有 lease 接管逻辑；页面 `page.tsx:1096-1099` 有「在这个标签页接管」，`takeOverLease()` 会 `store.takeoverLease` 后 reload。6bd3 两次都在开场后、玩家回合前停住，疑似旧 lease 未接管。已写入 `results/product/browser-requests/01-input-to-09-f15d-next-run.json` 的 `leasePointer`；09 应先点接管再提交。

**1562 run（19:38）失败原因不是叙事质量（2026-11-11）**：`09-one-legal-turn-1562.json`（runId 1938-1fdc）开场 narration 899 ms 就 `fallback=true`，页面报 `model shard 1/1 fetch failed (/models/Qwen3-0.6B-Q4_K_M.gguf)`，语义模型没加载 → 结算没完成 → 玩家回合 `submit_refused`，无正文。arm 本身正确（qwen3-1.7b b139949c）。模型文件在 `public/models` 里存在（396 MB），所以这是**静态服务/加载时**问题，不是模型缺失或正文问题。同文件还有 `1562-preflight-invalid`（旧的 build marker 检查），也不是产品回合。06 已冻结 `21c34d67`（page sha 3b33fccb, build wvno…, pid 11316, 19:39），下一次 run 应在这个 build 上；在这之前 1562/6bd3 都不能当产品证据。

**21c3 独立复核（2026-11-11）**：`results/quality/findings-21c3.md`。最终 130 字是程序回退（source=draft），第 3 句 `诺诺：确认任务完成…` 是假任务（4 次 updates `achieved: []`，73 行全 pending）；模型候选 93 supported/0 violations 被 `unprojected_entity:诺诺的红色识别带` 拒（红带是诺诺已结算持有物，投影漏了）+ `loop_repeated_clause`；玩家点 26.9 s 正文没显示，自动轮回退覆盖；snapshot 是根点，history 0→1；首合格 167.5 s。L0 新增 `fact.task_asserted`（21c3 最终正文命中，human-71/final-v1 仍 0），68 锚点、31/4。已发 04 `requests-01-to-04-21c3-projection.md`、06/02/09 追加。

**`3f54eac0` 复核（2026-11-11）**：06 的 binding 修复只保护了 `record.narrations`/`record.source/acceptedMs`，`onNarrationProgress`（page.tsx:640-643）和 `onNarrationComplete`（681-699）仍对任何 point 执行 `updateLast` 改 entry 文本；f15d/21c3 的"自动轮覆盖玩家点"没有修好。已在 `requests-01-to-06-narration-binding.md` 追加最小修法（entry 加 pointId，只允许玩家点更新）。下一条页面 run 前必须补上，否则显示仍是自动轮。

**06 vendor 落后（2026-11-11）**：06 树的 `narration-generation` 还没有 02 的 `1c826929`（时间补句）、`28f30c7e`（远处地标）、`eede2b23`（2x echo 不算 loop）、`16554f55`（filled-hand 句子定位）。21c3 的 `loop_repeated_clause+loop_repeated_clause` 正是 2x echo，旧副本仍 hard 拒。已在 06 request 里列出四个 commit；下一个 build 必须 vendor 到 02 最新。

**b7cd 独立复核（2026-11-11）**：`results/quality/findings-b7cd.md`。页面显示的是 auto-2 程序回退 134 字：凯撒在红方集结点、诺诺"在身边"（假邻近）、"行动成功完成"（4 次 updates `achieved: []`、73 行 pending）；玩家点 110 字（路明非/西侧服务巷，含"诺诺：未成功触发"字段句）被覆盖。snapshot 现在正确（head auto_2、15:23、4 条 narration）、historyDelta 1，`3f54eac0` 的 refresh 生效但 entry 文本仍按任意 point 更新。模型开场 134（"黄黑绳被放下"）和 auto-1 92（逐字重复开场第一句、fallback=false）未被显示。L0 新增 `style.status_panel`（说话人名+冒号结果句）、`task_asserted` 扩展（行动成功完成）、`style.repeated_opening` 锚点；71 锚点、31/4；human-71/final-v1 仍 0。

**真实状态复核测试（2026-11-11）**：`narration-input/review-run.test.ts`（默认跳过）用 b7cd 的 snapshot 构造"before=初始状态、after=逐点状态、时间=1 分钟"的 checker 行（经 `projectNarrationInput` → `renderLegacyInput` → `parseLegacyInput`）。结果：auto-1 的 92 字模型文本 `repeated_opening` + `echo_prior 0.78`（页面却 fallback=false 接受）；auto-2 程序文本 `task_asserted` + `status_panel`；凯撒句只是 `review.tone`（不在投影场景内，需要人工看）。同时修了 `basePlace` 的"地点（槽位）"后缀和同地点槽位变化不算 `move_omitted`；human-71/final-v1 仍 0。

**e9a5 独立复核（2026-11-11）**：`results/quality/findings-e9a5.md`。`e9a51950` 的逐点显示生效：页面显示点 149 + auto-1 125 + auto-2 130，玩家段在前；但 root 123 开场仍不显示；回合级 `textSource: model` 里混着 auto-2 的 program 段。内容：点 149 与 root 首句逐字相同（`repeated_opening`）+ "黄黑绳缓缓放下"（已放下，硬）+ 玩家动作"走进服务巷读规则牌"没写（只在 auto-2 程序段）；auto-1 125 模型"短枪还挂在腰间"（诺诺手里，硬）+ 重复点（echo 0.62）；auto-2 130 程序"诺诺：确认任务完成…行动成功完成"（假任务）+ 字段句；root 123 "枪口微微抬起" + "绳缓缓放下"（2 硬）。301.3 s、首草稿 101.9 s。04：group_12 重复三次、`nono achieved` 未落到 updates（`achieved []`）、`changes nono lane slot_waist` 提议未 apply（state 仍 slot_entry）。L0 新增绳"已放下"重演、手→腰持枪两条硬规则；75 锚点、31/4；human-71/final-v1 仍 0。

**02/04 已响应（2026-11-11）**：02 `6d4236be` 把"手里 + 挂在腰间"判 `self_contradiction`（e9a5 auto-1 的 125 字），`94d40cdb` 是 prompt/known-defect 批次（160/147/133，不是固定字数）；04 `0394380f` 把 e9a5 的 results 事实清洗成"诺诺：确认并检查故障短讯机状态。"（去掉任务完成/成功执行行动）。06 的下一个 build 必须合 02 的 `6d4236be`，否则 09 的下一次 run 仍会接受枪在腰的模型段；程序层还要去掉 results 的说话人标签，避免 `style.status_panel`。

**95dc 独立复核（2026-11-11）**：`results/quality/findings-95dc.md`。02 `6d4236be` + 04 `0394380f` 已进 build；显示仍为点 130（程序）+ auto-1 101（模型），root 115 不显示；run 因 continuation `settlement_failed` FAILED。点程序把**护目镜**当 actor（「护目镜在原地站了一会儿」；04 的 `changes goggles_lu` 是物品 no-op）；results「诺诺：…为false」整句拼进正文。auto-1 模型动作写出来了（02 prompt 起效），但把诺诺的「袖口红痕」移到路明非（`fact.body_mark_added`）+ 缺一分钟（`time_missing`）；root 编了「这里……没人在。」台词 + 重演束发。04 的 `0394380f` 覆盖「任务完成」但没覆盖 group_10 的「完成任务」，`为false` 也没清洗。L0：袖口加入 body mark，95dc 三锚点；78 锚点、31/4；human-71/final-v1 仍 0。checker 还没有"物品当人 actor"的规则（手工判），64 位不改判。

## 2026-11-11 05:28Z — 415c 独立复核（head 415ccbe0，run 2026-11-10T2055-3e8a）

- 415c：玩家点 121 + 自动点 111 均为程序；开场 131 字模型正文不在最终显示；turn `textSource: program`。首可见草稿 93.2 s 是开场模型；玩家点程序回退是候选验证器 `echo_prior` + in-model `unprojected_entity:诺诺的红色识别带/low_support` 的拒绝级联，`narrationDebug violations=[]` 只是独立闸门对 166 字尝试的摘要，不是采用缺口。
- 点程序错句：`路明非的护目镜在原地站了一会儿`（item actor）、`诺诺：未成功触发骰点，路明非未被阻止或反应`（status panel）；输入里的“往里走/看清规则牌”没有落实。
- 自动点（成员诺诺）逐字重复点的后三行（echo），主语是路明非，没有诺诺行动；状态 15:21→15:22，但两个点各写“一分钟过去”。
- 开场（模型，未显示）：`诺诺的短枪在脚边静静地躺着`（手里的枪）、`昨夜的尘埃`（past）、`暮色`（15:21）、`那场未完成的演习`/`石阶`（review）。
- 结算：group_10「完成任务」+ `achievedByCharacter: []`；continuation 重复候选 stop；04 的 `09eb0331`/04:58 continuation 修复未并入本 build。
- 检查器：81 锚点；human-71 0、final-v1 0；item actor、性别近处绑定、持枪在地、昨夜过去标记。

### 415c 最终状态更正（21:02Z）

- 该 run 不是“捕获时 IN_PROGRESS”就结束：最终 `status: FAILED`；reload 75.7 s 到 `ready`，但 `restored: false`；`failures` 与 `finishes` 均为空；turn 的 problems 全是程序回退（`no_accepted_model_text`、`draft_only_not_accepted`、`program_only_not_model_text`）。正文逐句问题不变，见 `results/quality/findings-415c.md`。
- 06 新 build `6eb46279`（`75b8Fn_WPEskCyw5AK_HO`，pid 30692）已合入 04 `09eb0331`/`ebbd21f5`、02 `6ea8b727`，并新增 `c3dc20b6` 逐段来源标签与调度时钟；下一轮 09 跑这个 build。

### 415c 检查器扩展（11cb8ce3）

- `fact.action_omitted`：输入明确写了「往里走 / 看清规则牌」，正文只有物品「还在」和「站了一会儿」，走/看都不出现，真实状态 review-run 首句报 `fact.action_omitted`。
- `fact.item_actor` 覆盖“已结算配饰”（护目镜挂在胸前），保留“他戴上护目镜站起身”这类 worn/handling 守卫，并排除「伸手够得到」习语（human dr-0012 曾误报）。
- 415c 三个锚点改用真实状态输入/action；81 锚点；human-71 71/0、final-v1 6/0。

### 03ec 与 09 解码对比（2026-11-11 05:29Z）

- 03ec（run 2026-11-10T2125-9cc3，head d1019f09）：结算 `group_10` results 调 `Qwen3-0.6B-Q4_K_M.gguf` 分片失败，页面 0 正文，回合没进正文；reload 停在 `reloading`、`restored: false`。不是质量样本；04 `9cb1110d` 未合入，continuation 未检验。
- 09 解码对比（08 runtime `220dca43`）：CPU 1.49 tok/s（80 tok/52.9 s），GPU 12.38 tok/s（72 tok/5.74 s），8.3x 解码；warm-up 报 IncompleteGenerationError、prompt 已缓存（cache 29/new 1）、冷加载 37/42 s，只能作指示性证据，不能当 100-token 冷 prefill 结论。

- 3-turn d101 第 1 回合（run 2026-11-10T2137-ac7c，build Cmw9eBTeAolws1QtBVTG9）：06 的骰子句已消失；但状态「黄黑绳已放下」正文又「被放下」，输入往里走/看规则牌未叙事，诺诺「站在他身旁」与状态器材棚门外不符，钟声/镜片无裂纹无依据；首可读 127.4 s；continuation `continuation_policy_abstract_task_goal` -> settlement_failed。锚点 `neg/d101-3turn-turn1`，84。

- 02 spine 验收稿复核（root-2 144 / move-2 171，均 accepted）：「黄黑绳被放下」再次与「已放下」冲突；「银质手链」是新增佩戴物（判 `fact.object_added`，回答 02 留的问题）；move 把「演习规则牌」放到诺诺脚边并「指尖轻触」，状态是墙上的赛区路线图；「发圈垂落」改变束在脑后的结算；诺诺在巷口而路明非已到中央庭院。见 `findings-02-spine.md`、`requests-01-to-02-spine-prose.md`。

- 3-turn d101 第 2 回合：输入「我向诺诺问：现在红蓝两方各在哪，我能不能先保持中立？」；submission 170 ms、results/updates/continuation 调用全 0、decision null，随后 330 s 超时、no_entry_added、history_delta_0、textSource program；显示文本与第 1 回合模型正文逐字相同（不是本轮回退）。06 不得用上回合正文冒充本轮；0 调用提交需单独追因。
- 3-turn d101 结束 **FAILED**（21:48:06Z），只有 2 回合；第 2 回合 0 调用 170 ms 提交 + 330 s 超时 + 显示第 1 回合正文；不是完成的 3 回合证据。
- 02 `418e83df`：dense-point-4 的水声/没有声音矛盾已由 `hard:self_contradiction` 覆盖（测试逐字用原文）；但雨和「他没有移动」仍未覆盖，01 的 rain/move 判据保留。
- 04 `ab242e32`/`6afa8e39`：结算正文剥离骰点/骰子/判定/布尔值，机制-only 事实中止；源修复，但不在 3-turn 的 `5d4c26f6`。06 `58beddad` 已合 02 `418e83df` 与 04 `aa9622a3`，`ab242e32` 待合。
- 06 将 `09-product-03turn-d101.json` 标为 invalid（21:47Z 重启时第 2 回合仍在跑；第 2 回合此前已 330 s 超时）；3-turn 不作为产品证据。06 新构建 `101bb3d2` ready。
- 06 `101bb3d2` 修失败命令历史槽位（`commandPointIds`，对应 3-turn 第 2 回合显示第 1 回合正文的类），`26035d97` 取消失败后的残留 advance；待下一次 09 验证。
- 2603（run 2026-11-10T2155-228b，head 26035d97）：第 1 回合 0 字、`submit_refused`/`settlement_failed_recoverable`；results 1 次调用被 04 `ab242e32` 的「fact only asserted completion」中止。拒绝假完成任务是对的，但整回合中止太大；04 应丢事实/重试，06 应区分结算失败与无正文回合。见 `findings-09-2603.md`。
- 02 `6bc2a3e6`+`c0d0ad7d`/`eff602f2`：已完成的绳再演一遍记 unlicensed_action（测试是 `缓缓放下`）；场景提示带玩家声明的行动，漏写记 note。04 `1f65b0b2` 去掉 results 提示里的 pending task goals。均未进 06 构建；3-turn 原文 `望着…被放下` 需在下个构建复核。
- 校准：`allowedEvents` 是策略（`licensedEvents`），`[]` 不是禁单；已存在的发圈整理/绳子垂着晃动是 review，只有明确的「被放下」再演是硬矛盾。01 修正 spine：`演习规则牌` 在 `可用名字`/`licensedEntities`，问题是位置（review）；`银质手链` 才是新物件。prompt 冲突（细微动作 vs 禁蹲下/坐/靠/站；2 段 vs 1 段；代词规则重复）已交 02 做 composer 定点修正。
- 02 `c5fa1823`/当前 `scene-prompt.ts`：姿势禁单与 2 段/1 段冲突已修；声明行动不再预置手部动作；代词规则仍推两遍（223/231）。`演习规则牌` 是 licensed、`银质手链` 不是，两个检查要分开。
- dfde（run 2026-11-10T2210-414a，head dfdedb18，build PR70dLlINuWjz8cXgKyoV）重复 2603：第 1 回合 0 字，results 被 `fact only asserted completion` 中止；构建不含 04 `1f65b0b2`。两次独立真实运行，非偶发。
- 04 `b2e1dab2`/`c2c8484b`：results 提示加具体走/看行动例；repair 错误带冻结成员行动并要求直接可见结果。repair 改善，但 mixed 答案 drop/retry 仍未实现，06 未构建。
- dfde 结束 **FAILED**（22:13:55Z），1 回合 0 字；06 `12175c21`（加载时补完未 ready 的 head narration）是页面修复，不解决 results 中止。下个构建需含 04 `1f65b0b2`/`b2e1dab2`/`c2c8484b` 与 drop/retry。
- prompt-route hour 独立复核（7 case）：全部有硬/重大无据错误（路明非红发×2、诺诺束发变散×3、无据风声/声音×5、新/移动物件×4、状态清单），6/7 自动 accepted 不是质量；71 字两例也因事实失败。**建议 no-go**：当前 prompt 不作为主路线，停止串行 prompt 补丁，保留 7 例作回归，转向已结算事实结构+模型正文。见 `decision.md`/`review/`。
- 102f（run 2026-11-10T2230-7ddd，head 102fdf1a，build 9B4it4o6pdxfJIWYX5UiH）**FAILED**：page `0d72d63d` ≠ frozen `07690eb4`；0.6B shard fetch 失败（4-12 ms）；0 字/749 ms，未进正文。03ec 同类 setup 失败；06/09 修页面冻结与 0.6B shard，不当作正文样本。
- a178（run 2026-11-10T2236-fb80，head a178ef78，build dT9HKlAA54xSfOhfsk1nS）第 1 回合：95 字 model、129.3 s；首次把走/看规则牌写进正文，绳保持已放下；但时间缺失、加阳光、袖口负细节、墙面/弹痕位置泛化。不是质量通过。
- a178 结束 **COMPLETED**（22:41:10Z）但仅 1 回合；1 回合完成不等于 3/10/20 验收或产品通过。
- 3-turn a178（run 2026-11-10T2241-5ac2，head a178ef78）第 1 回合：**program** 128 字/140.5 s，无模型正文；状态面板、护目镜当行动者、输入走/看被写成未看到。不是模型正文通过。
- 3-turn a178 第 2 回合（问诺诺红蓝/中立）：**program** 113 字/128.2 s；问题未答、无对白，状态面板+清单。
- 3-turn a178 第 3 回合：**program** 132 字/163 s；护目镜三次当主语、引路无回答；run 22:51:34Z **FAILED**，3 回合全 program。
- a178 候选：两次 `echo_prior+unlicensed_sense` 拒绝，第三次 95 字 accepted 仍含「阳光下微光」（同类未拦住）；continuation `abstract_task_goal` 后 settlement_failed/policy_stop。
- 02 `ea30ada8`（source，未进 06 build）：hair owner/state、worn goggles、`time_duplicate`、scene `inventory` 校验，测试用 route 原句；覆盖四类，风/声/新物件/规则牌移位/物品当行动者/停水仍除外。源修复，非通过。
- 09 run-request：a178 两跑都是 prose-facts 臂，不是 constrained beats；constrained 的 run 尚未产出。a178 结论只对 prose-facts 成立。
- 02 `audit-frozen-text.mjs` replay：四绑定全中（root 3/quiet 2/move 2/dense 护目镜/continuation 束发/unseen 重复时间）；风/声/新物件/停水/绳被吹起/位置仍未拦。验证器增益真实，覆盖不全。
- constrained beats 首跑（run 2026-11-10T2306-8c5e，arm=constrained/beats）：第 1 回合 **program** 206 字/169 s；规则牌/路线图整段背诵、状态面板、走/看写成没有动。臂身份正确，无模型正文。
- constrained beats 首跑 23:11:44Z **FAILED**，仅 1 program 回合；仍无模型正文样本。
- constrained 第二跑（2026-11-10T2313-21c6，head 897885dd）：仍 program 217 字/183 s，状态面板+错误结果；连续两跑无模型正文。
- constrained 第二跑 23:19:00Z **FAILED**，同样 1 program 回合；连续两跑无模型正文。
- 02 `205fd1f0` 复跑：停水水花、诺诺身后已拦；规则牌 `在脚下` 因 `placed` 只认 `(墙上)` 仍漏；风/钟/影子/落叶/算盘/刀刃/雨仍未拦。
- 01 checker repair：补 7 类 route 事实（发型归属/束发变散、护目镜胸前 vs 镜片后、停水水花、绳再升起、身后、物品当行动者），新增 7 个 `neg/route/*` 锚点（共 91）；human-71/final-v1 仍 0；风/钟/影子、落叶、算盘/刀刃仍未覆盖。
- constrained 第三跑（2026-11-10T2328-da9c，head 897885dd）：**program** 201 字/187 s，规则牌/路线图整段 + `未被允许反应` 面板；23:34:05Z **FAILED**。三次 constrained 均无模型正文。
- constrained 448e（2026-11-10T2341-711c，head 448e1dd0）：首次 model 正文 485 字/249.5 s；整段状态复述+重复、规则牌在地面、护目镜当行动者、`未看到规则牌` 面板。模型文本，非通过。
- 01 checker 第二遍：`neg/route/448e-recital`（92 锚点）；修 `发圈…识别带`、`而非戴在眼前` 两处误报；全套/human-71/final-v1 全绿。
- 448e 出处更正：09 index 记 2/4 beats model + 2/4 program fallback = **mixed**，不是 source=model；整段不可记 model。
- 448e per-beat：open model / scene program / result program（缺 result fact）/ close model = 2/4+2/4；`beatCounts` 写 model:1/program:0 自相矛盾；result 的 program 文本是 `诺诺：…未看到规则牌…` 面板。
- 01 checker 第三遍：`风声/雨声/钟鸣` + `风穿过…声音`；无来源的风=tone，`远处钟鸣`=氛围，`风铃`=sound_added；92 锚点。
- 01 checker 第四遍：`落叶/枯叶/叶子` 入可新造物；新叶子=review.object_added。
- constrained 05e7（2026-11-11T0002-6075，head 05e7f4ce）：mixed 出处已诚实（2 model+2 program）；`no_accepted_model_text`；323 字状态复述+`路明非也没有动`+状态面板。非通过。
- 05e7 per-beat：open+scene model，result（缺 result fact）+ close（跨 beat 重复）program = 2/4+2/4；`路明非也没有动` 与 `诺诺：因此未被阻止或达成目标。` 属 fallback。
- 01 checker 第五遍：`影子/身影` 入可新造物；`红方集结点影子`=review.object_added。
- 05e7 锚点（93 总数）：`neg/route/05e7-mixed-recital`；`action_omitted` 仍命中。
- 10 dev 双臂（f2135824）独立复核：0/8×2；page-v3 加人/物/伤/往事，shipped 整段自造对白+假完成面板；harness 未计契约禁止项。
- registry 复核：3 个 dev 样本用当前 checker 重读同批冻结文本；hash/binding 漂移清零，剩余阻断项均为实情（dev 分区、未预冻结、维度 fail、findings、无 goal/user 签字）；`quality_acceptance.py` 输出存 `results/quality/registry-check-2026-11-11.json`。
- 跨回合分析（两个 3-turn 真实页运行）：玩家动作/问题/路线请求均未落地；状态面板三回合退化；护目镜连续当行动者；d101 第 2 回合=第 1 回合逐字，`history_delta_0`。见 `results/quality/cross-turn-3turn.md`。
- constrained 6e3a（head 6e3ac5e0）：第 1 回合程序 112 字；`too_long`（480-token 预算 vs 170 字默认 beatMaxChars）+ `ungrounded,low_support`；状态面板第三种措辞；FAILED 1 回合。请求见 `results/quality/requests-01-to-06-6e3a-too-long.md`。
- 01 checker 第六遍：`name：` 面板规则补 `未被/未获得/未达成/阻止/达成目标`；448e/05e7/6e3a 三处真实面板判 `style.status_panel`；新增 6e3a 锚点（94 总数）。
- constrained 6565（head 6565dc0f）：首次 `mixed` 502 字（部分句子按已结算事实），但无 accepted model text；走/看未落地、裸状态列表、面板、规则牌同文两处。checker 补：面板词表、同物两处 `review.self_contradiction`、`诺诺红发` 合词不误判（95 锚点）。
- human-71 复核：71 条人写行仍 0 fact，`review.self_contradiction` 0，style/review 计数与旧报告一致（31/105），新增规则未污染人工材料。
- 6565 逐 beat：`3/4 beats model`，只剩 result beat `fact_missing result:facts:result`；程序兜底即 `诺诺：…` 面板。请求 04 结果事实自然句 + 02 表达接受（`results/quality/requests-01-to-04-02-result-beat.md`）。
- cf3d（head cf3d027e，program 122 字）：checker 命中 `action_omitted` + `status_panel`；视点/地点错（凯撒/红方集结点）因 凯撒 不在投影内未自动判，记为已知限制（07 同结论，归 06/04 组装）。锚点 96。
- 11a7（head 11a78afb）：视点已回 路明非/西侧服务巷，但 `诺诺红发垂落` 与已结算束发矛盾（fact），面板/物品晃动/走看缺失仍在；已向 06 提 beat prompt 保留已结算外貌（`results/quality/requests-01-to-06-11a7-hair.md`）。
- 11a7 逐 beat（09 index）：`open fact_missing time:facts:time (scoping regression)`、`result fact_missing result:facts:result`，scene/close 为 model——同一处 scoping 同时丢了时间事实与已结算外貌。
- 已向 02 提记录修正（`results/quality/requests-01-to-02-arm-name.md`）：`314d9e03` 把 86 字「accepted model beat」写成 constrained，但该页运行是 prose-facts，且与 a178 正文的实际缺陷（time_missing、无据微光、新增袖口细节）冲突；要求写明 candidate/mode、文件、fixture，并区分 verifier 接受与独立复核。
- 4794（head 479421a5）：open/scene/close 已 model；result beat 仍要求逐字 130 字 `fact.text`（09 index），与 prompt 允许改写冲突；绳再次被放下（fact）、面板、编造演习弹声；06 的 per-beat `rejected` 未进 09 导出（`results/quality/requests-01-to-09-beat-rejects-export.md`）。
- 三个 dev 样本按当前 checker（`f68f9305`，含面板词表/同物两处/束发合词/仅面板视点四条）重放：findings 与上次完全一致（`dev-02-free-day-task` 0 fact/2 style/3 review；`dev-02-short-root` 2 fact；`dev-08-free-day-root` 0 fact/5 review），`parseLegacyInput` 往返 true；registry 已按新字节重绑并记 `checkerDrift`。验收门仍 `not_ready`/`blocked`（dev 分区 + 未冻结 + 维度未全过 + 有未解项 + 缺目标/用户签名）。
- 12 b01 六样本独立复核（`results/quality/review-01-12-b01.md`）：0/6 合格；共性缺口=时间推进、黎知微新个性全缺；s43/s97 已解除外貌复现；s61 个性张冠李戴；s97 第一人称；五份外貌罗列。第一人称守卫可读（`perspective.qualified`）。
- 02 `7922d197`/06 `181c527a` 的 `settledViolationsFromScene` 只有测试调用，beat 路径（`narration-candidates/constrained/verify.ts`）没有接；11a7 `诺诺红发垂落`、4794 `黄黑绳在巷口放下` 都是在 beat 层通过的。已提 `results/quality/requests-01-to-02-06-settled-scene-wiring.md`。
- 代码确认：`constrained/verify.ts` 对 `result` 事实用 `text.includes(fact.text)`（4794 为 130 字），模型句必须逐字含整段结算结果，否则 `fact_missing` → 程序面板；已在 `requests-01-to-04-02-result-beat.md` 附代码与三个选项。
- registry 现索引本线复核过的全部真实页面回合（20 条 page runs + 24 条逐回合 reviewedOutputs + 1 条 12 b01 外部样本集）；基础设施无效/中止（lease、错误服务器、runtime-08、10turn 旧记录）不计产品证据，仍在原文件保留。门仍 `not_ready`/`blocked`。
- 更正：4794 的 `action_omitted` 是本线 checker 误报（对象取成「的墙」），已修并加 `pos/route/4794-action-narrated` 负向锚点（98）；4794 只剩绳子重复放下的两处矛盾。
- 926e（head 926e5c98，02 beat 补丁）：`mixed` 103 字，时间/注视已写、短可读；硬缺陷=胸前护目镜被「摘下」、面板仍在、走只部分（`review.action_partial`）。checker 99 锚点；同时修掉本线三个误报（对象取「墙」、规则牌误当规则豁免、目标词序导致 human-71 误报一行）。
- 5810（head 5810ae87）：判定过滤生效，面板消失、护目镜矛盾不再；但 53 字，规则牌与走都不在正文（`fact.action_omitted`），result beat 仍逐字绑定。
- 02 `3b48fb10`/06 `b44c2397` 再次只接到 scene 路径（`narration-generation/verify.ts:424`）；`constrained/verify.ts` 仍无任何 settled/item 调用，故 926e 的「摘下护目镜」在该 build 仍会通过 beat 校验。已在该请求追加证据。
- 更正（root 复核 5810 raw + 代码后）：11a7/926e 的 `fact_missing time` 属失败模型尝试，最终 fallback coverage 为 `expressed:true`；我此前「scoping 丢了时间事实」的写法撤回。模型为何失败（matcher 拒了合法说法 or 真没写）在 `rejected: []` 下无法判定。result 的逐字 `fact.text` 冲突经 root 确认属实。
- 5810 逐 beat：open=program（两次模型尝试 `fact_missing time`，fallback 写成）、scene 与 close 文本完全相同（`路明非低头检查护目镜的镜片。`），合成后只留一句；`beatCounts` 仍与 `composers` 矛盾。长度不作判据，缺陷是走/规则牌缺失与 close 无新内容。
- 已答 06 §8.4 的感觉句判定（`results/quality/judgement-01-sense-sentences.md`）：「护目镜在风中晃动」允许/复核级（挂在胸前的物件微动），「红发垂落」「护目镜泛着雾气/边缘的雾气」为事实矛盾；「规则牌在门口晃动」复核级。并对 §8 两处措辞提记录修正（`requests-01-to-06-fix-claim.md`）：b44c2397 的摘戴检查未接 beat 路径；5810 的 time 失败属模型尝试、fallback coverage=true。
- root 736a 同输入重测：首跑 `root-constrained-736a.json`（`2026-11-11T0225-c06a`）为基础设施无效——把带 query 的完整 URL 传给了 `--base`，0 回合，**不算产品失败**；重跑 `root-constrained-736a-retry.json`（`2026-11-11T0226-4599`）运行中。已独立核对 page sha：git blob `cc3e8b5f…`（LF，75670 字节）与磁盘 `a4259e74…`（CRLF，76957 字节）在 CRLF→LF 归一化后完全相同；`.next-prod/BUILD_ID` = `CK4qMIz_uyP-SCbCxB-fy`，与发布一致。
- 736a 重测复核（`results/quality/findings-736a-retry.md`）：`model` 71 字、accepted 97.2 s，**不合格**——护目镜沿巷走（item actor ×3）、小句重复 4 次、规则牌缺失；root 已定位投影器缺陷 f4272699（忽略 viewpointId、取首个 at 物品；父 e07d324c），06 待吸收。单段规划有效但不等于正文合格。checker 补 item_actor 移动短语与 clause 级 loop，101 锚点；human-71 仍 0 fact。
- 9623（head d17d6534）：**首份真实模型正文经独立复核 0 fact/0 style/0 review**（69 字，走/时间/看牌/诺诺在场各落地）；仍非产品通过——首读 103.7 s、无结果后果、`program_fallback_labelled` 误标与 `textSource:model` 冲突。`results/quality/review-09-9623.md`。第一稿 `rejected` 含「摘下护目镜」，被打回原因是别的 fact_missing，说明摘戴检查仍未接 beat 路径。
- 已向 09/06 提 provenance 误标：9623 `textSource:model`、`composers:["model"]`，却带 `program_fallback_labelled`（`results/quality/requests-01-to-09-9623-provenance.md`）。
- 3turn 9623（head d17d6534）：turn1 模型 103 字可读（0 fact，2 review=场地注记复述）；turn2 提问回合结算被拒 0 字；turn3 只显示 `…`。1/3 可读、0/3 有结果。归属：04 纯对话结果路径、06/09 失败不得展示占位符、02 场地注记复述降权。`results/quality/review-09-3turn-9623.md`
- 已向 04/06 提「提问回合」请求（`results/quality/requests-01-to-04-06-question-turn.md`）：纯对话行动需要结果路径（能答就给答案事实，不能答也要完成并写「没答」），不能 `submit_refused` 整回合；失败时页面不得把 `…` 当正文。
- root `6c202872`（时间可选，基于 aa30835f，7 个 constrained 文件）已独立核对：两处投影 time `mandatory:false`；`verifyText` 强制 `requireTime=false`，coverage 对 time 永不 hard；写错时长仍由 `alignNarration` 拒。已提 06 吸收 / 09 下次运行需同时含 `6c202872`+`f4272699`+结果契约（`results/quality/requests-01-to-06-absorb-time-optional.md`）。本线 checker 同步：缺时长不判、写错判 `fact.time_wrong`。
- aa30 三回合按新边界独立阅读（`results/quality/review-09-aa30.md`）：t1 程序 89 字（候选 `too_short` + 模型稿 `unprojected_entity:诺诺的红色识别带` 被挡，走/看牌都没发生）；t2 提问回合 `missing judgment for lu`（首次有 lu 判定、重试丢失）0 字；t3 仍显示 `…`。结论：不是模型不合格，是候选门槛与结算/展示失败；需 09 在含 6c202872+f4272699+结果契约的 build 重跑。
- 73f3 三回合独立阅读（`results/quality/review-09-73f3.md`）：t1 结算第一次把「走+看牌」判成 achieved（lu 组），但 nono 组两次只写机制事实被 04 拒，整回合 0 字；t2 仍显示 `…`；t3 驱动 30 s 点不到「行动」按钮。结论：挡住玩家的是结果契约与失败恢复，不是叙事模型。需 04/02 把行动结果写进事实、06 修失败后展示/可继续，再同一 build 重跑。
- 已向 04/02 提结果事实形状请求（`results/quality/requests-01-to-04-02-nono-group-fact.md`）：nono 组把好句写在 `reason`、事实仍是「未被判定为反应」；重试重复同一事实。lu 组已是目标形状（`路明非看清了墙上的规则牌`）。
- 按新边界重读并撤回旧意见（`results/quality/reread-9623-under-boundary.md`）：9623 单回合正文（走+看牌+诺诺既有细节）**文字层可给玩家看**，先前「没有结果」是按已删除的 result beat 契约提的；3turn 第一回合可看但后半接近场地清单。剩余问题是时延（103.7 s）、连续回合与产品验收，不是这段文字。
- bed9 三回合按新边界独立阅读（`results/quality/review-09-bed9.md`）：三回合都是 `draft`（06 的保留草稿生效），文字像小说；但 t1/t2 把「诺诺查看伤口」写成正文而结算事实是路明非看牌（actor/目标不符），t2 没答提问，t3 自己走向钟楼还摘护目镜（无据）并把上一回合的问题拖后回答。草稿可看但不得当合格正文/前文。`program_fallback_labelled` 与 `source_draft` 仍冲突。
- 35ad 三回合（`results/quality/review-09-35ad.md`）：**首次出现被接受的模型正文**（t1 59 字 87 s、t3 110 字 116 s）。t1 把「弗里嘉演习弹」放进已结算「右手还空着」的手、把诺诺红带挂到他左臂 → 不合格；t2 草稿复述提问、无回答；t3 有模板残句「方向是从到」和整张路线逐条朗读。checker 修：「摘下…挂在胸前」不再误判，新增空手放物矛盾与饰物否定句遮挡的漏判，锚点 104。
- d531 三回合（`results/quality/review-09-d531.md`）：模板残句与路线朗读已修；t1 仍把弹药塞进「右手还空着」的手；t2 草稿把诺诺红带挂主角左臂、规则牌自己发声，但写明了「她没有说话」；t3 诺诺完全不在场（玩家请她带路）且念物品说明。checker 新增「请某人做而此人不出现」→`fact.action_omitted`，并把 35ad t3 锚点改判为 neg；锚点 107。
- 08f4 三回合（`results/quality/review-09-08f4.md`）：模板/路线问题已消失；t1（model 70 字）「掏出护目镜戴上」与结算 `goggles keep` 相反 → 改物品状态，不合格；t2（model 63 字）复述提问但无答复也无「没答」；t3 草稿诺诺不在场。checker 补「戴上」判矛盾（此前只认「戴好/戴在」），锚点 110。
- **运行时改为原样显示模型正文**（`NARRATION-RAW-OUTPUT-20261111.md`，2026-11-11）：运行时不校验/不裁句/不替换/不降级，非空即逐字显示；只保留空值与全空白判断，程序不编叙事；删除 priorText/历史正文/摘要进下一次调用的全部通道；正文不参与结算。我的角色收敛为**唯一开发期叙事评审**：读原要求+实际结算+完整正文，连续中文说明差距；不以 PASS、锚点数量或自动检查代替阅读。checker 仅开发回归、不进运行时（已核实运行时代码无 import）。删检查≠质量提升，registry 继续 `not_ready`。记录在 `results/quality/decision-runtime-raw-output.md`。
- 9eae 三回合按新方式读（`results/quality/review-09-9eae.md`）：t1 玩家动作做到但丢了诺诺「查看伤口」的结算动作、加了「演习弹已放在器材棚」、红带无主；t2 结算明确有「诺诺摇头说不知道」但正文没写；t3 结算把同一句挂在两人名下，正文照搬并混入机制句「此行动，且未被阻止。」。按影响排序：t3 属 04，t2 属输入/结果交接，t1 属模型自身偏差。
- 已向 09 提出「分段 vs 单次成篇」对照（`results/quality/requests-01-to-09-single-pass-need.md`）：按 9eae 真实输出，分段结果仍是等长并列短句（每句一个事实、无主从/因果，t3 还出现同模板重复），故需要同一状态输入跑一次成篇方案供我比较；比较只靠阅读，不用时长或自动分数选风格。
- 353f 两回合原样输出（`results/quality/review-09-353f-raw.md`）：删审查后首份真实证据，四段全 model、无拒绝。t1 把「走+看牌」拆成三句同义重复、「手中的规则牌」不成立、诺诺结算动作丢失、加了器材棚嗡鸣；t2 结算「诺诺摇头说不知道」在正文完全没有，两次「踏步入内」。四段 open/close 同义，支持单次成篇对照。证据缺口：完整提示原文与单条原始返回未捕获（`generations` 只有 token/耗时）。
- 1e59 两回合（`results/quality/review-09-1e59.md`）：分段已从四段变为单 result 段，重复问题消失；t1 仅 24 字「走+看清牌」，准确但只是一句确认、丢了诺诺结算动作；t2 结算本身错乱（同一句挂两人、红带在胸前发烫、短讯机、反问），正文忠实复现，玩家的提问仍无答案。证据仍缺提示原文，09 `ff738c8e` 起会保留。
- 1e59 三回合（head 61869637，`results/quality/review-09-1e59-3turn.md`）：t1 24 字准确但薄；t2 问出口无回答；t3 214 字、诺诺只在护目镜反光里出现、结尾又出现陈述式路线朗读。关键：t2/t3 路明非那条事实就是玩家原话（含「我」）却标 `completed`，`421431b2` 守卫未拦住；红带/短讯机错句在三份证据里反复出现。
- 09 `09-frozen-raw-6186.json`（run `2026-11-11T0647-98bb`）是**基础设施无效**：`page_sha_mismatch:28ea13ac5681!=65d4852e`，未产生任何回合，不作质量数据点（已记 registry `artifactsNote.infrastructureInvalid`）。
- 查清「…」来源（`requests-01-to-06-empty-entry-ellipsis.md`）：`page.tsx:1247` `{entry.text || (entry.failed||… ? '' : '…')}` —— 空正文且未标 failed 的条目就显示「…」；9623/aa30/frozen-6186 的 t3 均属此列（t3 167 ms、无模型调用）。属 06 页面空状态缺陷，不是模型输出。
- a38d 首回合（`09-frozen-raw-a38d.json`，head a38d8564）：模型 9.1 s 写出正文，但 `continuation_policy_abstract_task_goal` 被 `unwrap` 当失败抛出（`settlement_failed:continuation:…`），整回合 330 s 超时、正文为 null；页面记录 `acceptedMs 85286` 却没有文本、`firstReadableAtMs` 为 null。已提 06（policy stop 不应致命、空状态要显示说明）与 04（policy_stop 应返回值）。
- b2d4 三回合（`09-frozen-raw-b2d4.json`）**不构成质量证据**：三回合 `source: model`、accepted 74–88 s，但 `text: null`/`shownChars 0`。原因查清：驱动用 `div[style*="pre-wrap"]` 取正文，06 把内联样式改成 CSS module 后正文节点变成 `className={styles.partText}`，选择器取不到 → 记录成空。已提 09 改选择器 / 06 加稳定 `data-*`（`requests-01-to-09-prose-selector.md`）。这条也提醒：不能把 `text: null` 直接当成「模型没写」。
- b2d4-retry 三回合（`results/quality/review-09-b2d4-retry.md`）：删审查后首份三回合都有模型正文的证据；t1 走+看牌+牌面引言可读（多扫图/摸绳、丢诺诺结算动作）；**t2 首次把「诺诺摇头说不知道」写进正文**（「红发」无主语）；t3 不合格：诺诺缺席、路线逐段朗读且有方向错、结算复用「看见了规则牌」而与带路无关。页面标签被一起抓进 text（09 选择器）。
- b2d4-clean 三回合（`results/quality/review-09-b2d4-clean.md`）：同 build 同输入的第二份，t1 可读；t2 **把 retry 已写对的「诺诺摇头说不知道」漏掉**，且把诺诺写成「庭院尽头/发圈松散垂落」（位置与外貌都不对）；t3 51.9 s 首次低于 60 s，但结算再次复用「看见了规则牌」，结尾照搬成牌在钟楼前。对比说明：材料没变，模型这次漏写/臆造；t3 仍是结算问题。
- 十回合（`results/quality/review-09-10turn-7686.md`，head 76867160）：7/10 有正文；t5 结算失败、t6 页面「…」占位、t10 195.8 s。核心新发现：t8–t10 的重复来自**同一回合同一组被重复结算（group_151×2 / group_169×3 / group_188×3）且每个叙述点各写一遍**，与点数/调用次数对得上，不是模型话多。另有 t3「他伸手想拉住路明非」自指（结算「诺诺拉住路明非的手」主语被换）、t2/t7 事实仍是玩家原话（t7 保留「我」）、t1 缺「走进去」。
- 6042 十回合（`results/quality/review-09-6042-10turn.md`，head 60428d22）：**t1 走+看牌成段、t2 问答干净，是迄今最好的开头**；t3 结算复用 t2 事实并把诺诺红带/发圈写到路明非身上；t4 内核 `position_invalid` 失败后页面点不到「行动」，t5–t10 全废（两个「…」占位、四次 30 s 点击超时）。已提 06 恢复态、04 跨回合复用事实与内核冲突。
- **非叙事先行测量（01 金标）**：按 `NON-NARRATIVE-PREFLIGHT-20261111.md` 在模型运行前冻结 73 条任务目标的标签判定——`results/semantic-action-preflight-20261111/gold-01.json`，sha256 `5d4f14b1…`；29 单动作 / 38 复合 / 6 无唯一答案（`task_caesar_win`、`task_doctor_prepare`、`task_fingel_soup`、`task_lu_match`、`task_manstein_order`、`task_tang_pause`）。口径：预测标签 ∈ acceptableLabels 判对；复合目标另报 parts 覆盖；只用标签不进门禁。说明见 `results/quality/preflight-gold-01.md`。
- 预检结果复核（`results/quality/preflight-gold-01-verify.md`）：用 jsonl 重算 cold/warm 均 **16/73**（single 7/29、compound 9/38、ambiguous 0/6，枚举外 0），与 04 报告一致；但 04 的「同组放宽 27/73=37%」我复现不出（同组仅 +2 → 18/73=24.7%，共享字 23/73，primary 同组 22/73），建议只报 16/73 并注明同义词规则待用户指定。金标未改。
- 跨运行统计「结算固定话术」（`results/quality/settlement-recurring-facts.md`）：`掀开路明非的袖口` 出现在 18 份证据（9711 一份 13 次）、`红带在胸前发烫…短讯机` 7 份（1e59 6 次）、`看见了规则牌` 多份、`骰点资格` 几乎每份。它们是被反复提交的结算事实、会原样进正文；已提 04 最小要求（本回合/本执行者、禁机制句、不得换人名挂同一句）。
- 9711 四回合（`results/quality/review-09-9711.md`，head 2ef2921a）：t1 只有「目光落在牌上」、无走进；t2 结算事实是「骰点资格」机制句，正文只能复述问题；t3 又把诺诺红带挂到路明非、回答被换成「漫不经心」；t4 首段可读，第二段把玩家原句+多段固定话术拼在一起，正文 131 s 出现但整回合 330 s 不结束。
- 4b1e 十回合（`results/quality/review-09-4b1e-10turn.md`，head 4b1e060e）：9/10 有正文；t2 合格对话；t1 看的是赛区图不是规则牌、t3 没写「不站队」、t5 要把护目镜戴到眼前却写仍挂胸前、t6 把林亦舟的脚踝肿安到路明非身上、t7–t9 诺诺缺席且「摘镜—走石板—林亦舟」重复 4 次；t10 结算失败。量化：摘镜 7、挂胸前 8、石板 5、林亦舟 4、袖口固定话术每回合 13 次。
- 动作数据集（用户 2026-11-11 指令）：判据哈希已亲自复核（`56092d0c…`，未改字）；目标按角色整体切分并先于任何候选行冻结（TRAIN 48 / VALIDATION 10 / TEST 15，`01-goal-split-v1.json` sha `b4680a9e…`）；私有测试集 15 目标 × 3 情境 = 45 行，Y 在见任何模型输出前写好并冻结（sha `26f1a87d…`）；审查规则 18 条与脚本先冻结（`audit-freeze.json`）。
- 审 13 首批 93 行：**10 pass / 83 fail**。fail 根源是「move + 把任务全标完成」造出的无目标 skip（82 行，88% skip、0 条两步），`刚才` 是引擎日志（`…移动到…`、`任务…已完成`）而非角色可感知情节；来源与结构本身合格（93/93 evidence 哈希一致）。逐行见 `results/action-dataset-20261111/01-audit-v1.jsonl`，要求见 `01-to-13-audit-v1.md`。03 盲审包暂不发（10% 只有 1 行，无意义）。
- 审第二批（0094–0220，127 行）：**122 pass / 5 fail**；合计 220 行 = 132 pass / 88 fail（`01-audit-combined-v1.json`）。新 fail：`0132/0149/0182` 把角色放进锁着的器材笼（位置不成立）、`0172` 与 `0106`、`0186` 与 `0125` 是**同一 X 两个不同金标**。仍缺两步行；skip 82 行全来自「全标完成+传送」配方。已要求 13 先交 20–40 行修订再扩量。
- 03 盲审包 v1 已发（10 行，按步数分层随机：skip 8 + 有步数 2；sha `1d59e400…`），包内无我的结论与理由，等 03 先封存再解盲。用户口径已记录：不设「每行必须有未完成目标」这类统一规则，系统口吻的事实句不单独判无效。
- 03 盲审 v1 已解盲（`01-03-blind-comparison-v1.md`）：10 行里 2 行有步数 **2/2 一致 pass**；8 行 skip 03 判 ambiguous、我判 fail，方向一致（都不该进训练），按用户口径我把这 8 行改记 `ambiguous_not_trainable`，原 fail 保留不删。03 抓到 11 行 provenance 三个 source 字段不一致（我已核实并交 13 修），我的包也漏了 snapshot 指针，下一版补。
- batch1 24 行：**20 pass / 4 fail**（`01-audit-batch1.jsonl`）。fail 全是 skip 用了 X 里没有的事实（喊过话、被火力压回、远端角色位置）。批次缺陷：**rowId 从 0001 重号**，与旧 220 行冲突；已要求改全局唯一 id，先交 20–40 行修订再扩量。这批首次出现真正的两步行（提问→告知）与现场型 skip（15:45 未到、不能离岗）。
- 新 09 单回合（`09-overlap-661ae`，head b3304a4b）：正文 111 字三段，第一段可用，第二段是状态差量句「护目镜从服务巷到器材棚」、第三段重复；**结算仍提交示范句式「林亦舟做了什么/看到什么」**，尽管 `fe9db563` 已是该 head 祖先；另有「取下…并…并取下」病句。等待 303 秒、首读为空。已提 04（`01-to-04-example-fact-still-settled.md`）。
- batch2 32 行 **32 pass**（`01-audit-batch2.jsonl`）：A/B 两类齐、skip 6 行都从 X 推出、两步 2 行（问清→决定、看底座→查白旗）。唯一瑕疵 `b2-0028` 用「观察席看不到旗台」作理由，但面板就在候选里，时间未到那条仍成立。累计已审 276 行。
- batch3/4/5 审完：batch3 30/30（`b3-0017` 已由 13 改对并改判 pass）、batch4 **28 pass/2 fail**（`b4-0021` 目标只需一名在场者同意却离开；`b4-0027` 单子还能写却去取纸）、batch5 **36 pass/4 fail**（`b5-0010/0027/0028/0030` 理由中的关键事实不在 X）。累计已审 376 行：280 pass / 96 fail。
- 交付文件 `train13-full-candidates.jsonl`（300 行）逐行审完：**294 pass / 6 fail**（`train13r-0087/0110/0121/0130`、`b6-0007/0009`，均为理由事实不在 X 或标签与自身 X 矛盾）。九行已修（b1-0015/b1-0022/b3-0017/b4-0021/b4-0027/b5-0010/b5-0027/b5-0028/b5-0030）重新读过全 pass。已建 03 盲审包 v2（30 行随机，sha `f5f579de…`）。
- 读 09 overlap-f489（head 57065d4d，231 秒、48 字、`round_conclusion_cancel`）：正文用「锈迹斑斑的螺丝」回答了玩家问的「箱子里有什么」，结算事实只写「查看了里面的内容」；诺诺站位/发圈/识别带反光均无据。请求见 `results/quality/requests-01-to-04-answer-gap.md`、`requests-01-to-06-round-conclusion.md`；审阅 `review-09-f489-overlap.md`。
- 读 02 b33 两轮（页 chunk 与冻结不符）：第一轮 52 字且第二句病句+罐头，第二轮 138 秒后结算未完成。`review-02-b33-2turn.md`。
- **ACTION-SHORT-PAIRS（新）**：读完任务书与 4290 对渲染，出 `results/action-short-pairs-20261111/01-audit-shortx.jsonl`（4290 行，sha `bd0df903…`）：290 pass / 5 fail / 5 冲突。4 组冲突的完整 X 只差 `place` 里的时间；时间在短格式中整体丢失，5 条 skip 行（`b1-0021/b3-0025/b3-0026/b5-0033/b5-0034`）因此不可判。冲突 5 行（`b2-0010/b2-0030/b2-0027/b2-0028/b2-0029`）建议从短配对集剔除、原行与 Y 不动；保留 `train13r-0003/0004/0006/0009`。另发现：短格式不印随身物品（33 行 Y 对象不可见）、空列表渲染成 `；；`、第二步 `已做：<组名>` 在 8 条同组两步行里泄露答案。真实词表实测加时间+随身仍 max 213 token（512 内）。见 `01-shortx-audit.md`、`01-shortx-conflicts.md`、`01-ack.json`。
- 读 09 recovery-7Gzc：取消后交还输入/保留历史正确；第二轮 257 秒 42 字，动作被替换（看规则牌 vs 合盖抬头）、无据微动作、与 f489 同一句罐头（只换「墙边/巷口」「微光/光」）、连续第三次 `round_conclusion_cancel`。`review-09-recovery-7Gzc.md`。
