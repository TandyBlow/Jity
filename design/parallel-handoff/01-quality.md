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
