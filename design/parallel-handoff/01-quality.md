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
