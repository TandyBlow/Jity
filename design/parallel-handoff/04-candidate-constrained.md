# C 路线：事实骨架 → 受控正文（04 → 07 成文）

## 这份东西解决什么

一条回合结算完之后，浏览器里躺着一份已经算好的状态：谁从哪走到哪、哪件事做完了、谁的外貌句子被换成新的、谁的精神值掉了多少。但玩家要读的是一段中文，不是这张表。

这条路线做的事只有一件：**把这批已经算好的事实，一段一段地变成可读的中文正文，同时保证正文里没有一件事实是编的。**

它不写世界状态、不改任何点位、不重新掷骰子。输入是只读的已结算状态，输出是文本。

## 一个具体回合从头走完

以真实世界 `dragon-raja-free-day.world.json` 的第 2 个点为例（`scripts/candidate-constrained/run-program.mjs` 里就是这一对真实点位，用页面同一个状态内核 `buildInitialState` + `applyPoint` 算出来的）：

**输入（已结算的改动，节选）**

- 时间：前进 2 分钟
- 诺诺：从「西侧服务巷」→「器材棚」
- 芬格尔：从「器材棚」→「中央庭院」
- 路明非：护目镜移到右手；外貌换了一句新描述；人格换了一句；精神值 43 → 40；完成 `task_lu_goggles`；新增子任务 `task_lu_counter`
- 器材棚：外观换了一句（挂锁打开、担架拖到门口）
- 恺撒（中央庭院）、唐骁（精神值）：视角看不见，标成 hidden，只进证据，不进正文

**程序做了什么**

1. **投影**（`projection.ts`）：先用点位本身校验这条记录是真的——上一个点位对得上、版本号 +1、`initial` 表一个字没动、每条 Δ 和保存下来的状态一致。对不上就抛错，不猜。然后从「保存后的状态」和「两条点位的差」里，把上表每一项翻译成一条带类型的事实，并记下视角人物所在的房间：同一房间的人/物算「场景可见」，其他算「隐藏」。
2. **排段**（`beats.ts`）：把事实排成顺序固定的几段——开场（时间/地点）→ 视角自己的移动 → 其他人的移动 → 这个人的事件（外貌→任务→子任务→人格→精神）→ 结算结果原话 → 场景细节 → 收尾。每段写明：必须表达哪几条事实、可以用哪些已登记的细节、必须出现哪些人名、长度范围、一个固定随机种子。
3. **成文**（`realize.ts` 程序版 / `compose.ts` 模型版 / 07 的 composer）：只写这一段。程序版只用事实里的词和状态里已经存在的描述，外加「把视线收回来」这类细微动作；模型版一次调用写一段，提示词里只有这一段允许用的事实、人名、地点、物品和细节。
4. **验段**（`verify.ts`）：这一段写完立刻查——事实是否落地、方向对不对、有没有出现没登记的人名/数字/事件、有没有把「已知物品」写成「第一次看见」、有没有写别人心里想什么。不合格就重写这一段；模型重写一次仍不合格，就换程序版写**同一段**（不是退回事实清单，也不是换整段重来）。
5. **合段再验**：全文再查一遍所有必写事实、重复句、与上一回合的重合度、长度。

**输出（程序版，实际跑出来的原文）**

```
两分钟过去了。

路明非站在器材棚。

诺诺离开西侧服务巷，走进器材棚。

芬格尔从器材棚进入中央庭院。

路明非身上，护目镜已经推到额头上，镜带压住一撮头发，右手还搭在颈后的镜带上。

器材笼的挂锁已经打开，锁舌挂在笼门上，笼里那副折叠担架被拖到了门口。

路明非把「把胸前护目镜戴好并确认镜片没有裂纹」这件事做完了。

路明非还有下一件事要做：向秦越报明护目镜已经领到手，再问清担架放在哪一侧。

诺诺完成了「问清路明非的参赛意愿并说明三条接近钟楼的路线」。

路明非身上多了一点变化：开口还是先绕一句玩笑，但已经把护目镜当成要用的东西，不再只是挂在胸前给别人看。

路明非喉咙紧了一下。

路明非把护目镜推到额头上，问秦越担架放在哪一侧；秦越说担架已经在器材笼门口，先报用途再登记。

开盖演习弹药箱在器材棚，箱内两只已装填的通用短枪弹匣各有8发弗里嘉演习弹。

路明非在原地站了一会儿。
```

（最后一段是调用方传进来的「结算结果原话」，程序只做长度截断和逐字校验，不重写；`resultsText`。）

同一份代码在 09 的浏览器驱动给的真实「公开短场景」三个点上也跑通了：起点、一人移动、空改动 + 2 分钟。空改动那个点只写时间、房间和已在场的东西，不硬凑长度。

## 调用方式

```ts
import { generateCandidate } from './narration-candidates/constrained';

const result = await generateCandidate({
  engine,                    // 现有 InferenceEngine；program 模式不需要模型
  committed: {               // 已结算点的只读读法
    anchor: { worldId, pointId, version, stateDigest, previousPointId },
    state,                   // 保存下来的 after 状态
    beforeState,             // 上一个点位的状态（根点为 null）
    timeAdvance, entityDeltas,
    facts: [],               // 没有完整状态时可直接给 facts
  },
  inputText,                 // 01 的输入投影（只作为许可材料，不当状态用）
  priorText,                 // 上一回合被接受的正文
  signal, onProgress,
  policy: {
    mode: 'program' | 'model' | 'auto',   // 默认 program：不显式要模型就不调用模型
    sanityStyle: 'direction' | 'number',   // 页面若仍要过旧门禁，用 number
    knowledge: { discoveredItemIds, visitedLocationIds, metCharacterIds },
    resultsText,                            // 本回合结算结果原话
    composer,                               // 07 的 BeatComposer，可选
    model: { maxTokensPerBeat, temperature, timeoutMs, maxAttempts },
    minChars, maxChars, maxBeats, seed, avoidOpenings,
  },
});
```

返回 `{text, accepted, rawAttempts, issues, timings, strategyVersion, status, verification, skeleton, plan, composers, basePacket, display}`。

- `rawAttempts` 每段一条：谁写的（`program`/`model`/`external`/`fallback`）、原文、模型原始输出、耗时、这一段的全部问题。
- `verification`：每条必写事实是否表达、隐藏事实列表、未验证句、与上一回合的重合度。
- `basePacket`：只含位置/任务/人格事实的旧式事实包，方便页面继续跑既有 `alignNarration` 门禁。
- `accepted === false` 必须原样到达页面，不能当成功文案。

## 已验证 / 未验证

已跑（本线可复跑）：

- `node frontend/scripts/candidate-constrained/run-program.mjs`：真实世界点位全部 `accepted:true`——公开短场景 3 个点、自由一日起点/器材棚（6 类事实同时发生，另有 2 条视角外改动）、以及 09 在真实浏览器里跑过的 `root_free_day` 起点；程序模式单点耗时约 3–60 ms（本机，无模型）。
- `node frontend/scripts/candidate-constrained/run-sweep.mjs`：自由一日世界 12 个连续点位（移动、任务完成、子任务、人格、精神、外貌、物品易手、房间变化、纯隐藏改动、纯时间、纯结算原话），12/12 `accepted`。
- 把 07 的语言层注入同一个入口（`--composer <07 的 prose-composer/index.ts>`）：上述 6 个场景与 12 个点位同样全部 `accepted`，07 写的段直接通过本线的分段门禁；07 尚未实现 `kind:'result'` 段（结算原话）时，该段由本线程序写，不丢内容。
- 连续回合（短场景起点→移动→时间流逝）：没有逐字重复的句子；`repetitionVsPrior` 在 40–50 字短回合为 0.56/0.34，在长回合为 0.10/0.18。
- 真实浏览器程序模式（09 的 runner + 07 的 stub 装载器，Edge，无模型）：公开短场景 3 个点、自由一日 3 个点全部 `accepted`，页面内 8–20 ms / 首段可读 8–20 ms。
- `npx vitest run src/lib/world-engine/local/narration-candidates/constrained --maxWorkers=1`：26 个测试，含真实状态内核点位、方向反写、没登记的人名、已知物品再发现、模型失败换程序写同一段、07 composer 注入，以及 06 适配器的整条调用形状（事实包 + `policy.scene` + `resultsText`）。
- `npx tsc -p tsconfig.world-contract.json --noEmit` 与 eslint 无错误。

真实浏览器（09 的共用入口，程序模式，无模型）：公开短场景 3 个点 + 自由一日 3 个点（起点 / 移动 / 任务达成+人格+精神）6/6 `accepted`，页面内整回合 8–20 ms、首段可读 8–20 ms（模块内部首段 2–10 ms），`strategyVersion=constrained-candidate-v1.3`。用 07 的 stub 装载器占住引擎槽，证据里明确标注「program-only stub, no model」，不是模型运行，也不占共享推理租约。

真实浏览器证据（09 的共用入口，05:43Z，qwen2.5-1.5b-instruct，CPU）：

- 09 在本线早期版本上跑过 `root_free_day` 起点：真实引擎加载 35.9 s，程序模式生成 43.8 ms，首段 32 ms；但整段被判 `rejected`，原因是「诺诺也在服务巷」被旧对齐器误判成把路明非的站位改到了诺诺头上（同一地点的在场句与视角站位事实共用同一签名）。这轮真实运行暴露的正是这类错误：已在本线用「该人物自己有同地点的已结算站位」规则修掉，并用同一 `root_free_day` 输入重跑为 `accepted`（全文 173 字，规则牌描述不再被分号截断）。

未验证 / 已知限制：

- **model 模式（真实模型逐段写）尚未在浏览器里跑完**：共享推理租约从 05:59Z 起由 06-recovery 持有，且其会话仍在执行一个 25 分钟上限的真实回合，不是残留锁；本线按公约不删别线的锁。model 模式目前只有脚本引擎测试证明「每段一次调用、失败重写同一段、超出回合预算就换程序写」的流程成立。
- 模型每回合最多 6 段顺序调用（`maxBeats` 默认在 model 模式取 6、程序模式取 10）；0.5B 模型在 CPU 上的实际首段/整段耗时必须等真实运行才能给数，不能拿本文的毫秒数代替。`turnTimeoutMs`（默认 180 s）用完后剩余段由程序写，不会把整回合拖过等待上限。
- 程序版句子模板有限，同一段连续多回合会换说法但不是无限多样；`avoidOpenings` 只能避开重复开头。
- 人格/外貌的「撤销」事实（`removed`）只用被替换的旧句说明，没有独立的否认证词。
- 事实包模式（没有完整状态）只能靠调用方给的 `policy.scene` 补地点/在场人物/物件细节；不给这些提示时正文会明显更薄。本线已按 06 的形状测过：给了 `placeNote`/`presentNotes`/`objectNotes` 就能写出完整场景，`resultsText` 也会变成必需的结算原话。
- 本线程序版对同一房间的物件句仍可能连续以「中央庭院里，…」开头；连续回合的逐字重复已被门禁挡下，但句式变化有限，这正是 07 语言层要接的部分。

## 自然度修复（2026-11-10，v1.4）

真实程序正文里出现的"说明腔"和连续回合复读已经按以下方式修掉，门禁不变：

- **任务达成**不再写"X 完成了「目标」"这一种报表句。现在有三套框架轮换：
  `「目标」这件事，X 办完了`、`「目标」有了结果，X 这边也算办完了`、`X 完成了「目标」`。
  目标原文和完成动词都必须保留——旧对齐器正是靠这两者绑定 `task_achieved`，
  省掉目标等于抹掉事实。
- **个性变化**不再写"X 的性子变了一点：…"或"X 身上多了一点变化：…"，
  直接以人物名接已结算的个性句（如"路明非开口还是先绕一句玩笑，…"）。
- **新增小任务**不再写"给自己记下一条"，改成"还有一件事没完：…"。
- **跨回合开头与结尾**：上一回合每句话的前 6 个字自动进入本回合的避让集合，
  同一开头不再连着重开；开场/收尾这种不承载事实的句子还会避开上一回合出现过的整句，
  不会每回合都用"X 没有马上再动"收尾；逐字重复仍由全文门禁硬拒。
- **逐段来源**：`CandidateResult` 新增
  `segments:[{beatId,kind,source,text}]`、`beatCounts:{model,program,external,fallback}`、
  `mixed`。程序写的段落就是 `source='program'`，模型写的段落是 `model`，
  重写失败退回程序是 `fallback`；页面可以逐段标降级，`accepted` 只表示
  事实门禁通过，不代表整段是模型小说正文。

模型模式（v1.4 追加）：

- 提示词里的事实说明句改成叙事口吻（"「目标」这件事，X 已经办完了"而不是
  "X 完成了一项任务"），并明确禁止"完成了一项任务/个性发生了变化/新增一条待办"
  这类状态说明。小模型会照抄提示词句式，提示词本身是报告腔时正文必然是报告腔。
- 重试反馈按失败项给具体指令：漏时间说"必须写出已经过去的时间"，方向反了说
  "方向不能反"，凭空加动作说"不要补写没有结算的新动作、新对话或新事件"，
  开头重复说"换一个开头"，不再只说"事实或措辞不合要求"。
- 被否掉的草稿不再丢弃：`BeatEvidence.rejected[]` 保留每一稿的原文和问题，
  审计时能看到模型实际写了什么、哪一稿被门禁拒绝。
- 跨回合开头重复（前 6 字相同）是 soft 问题：给一次带指令的重写机会，
  第二稿仍重复则接受，不因文风问题把整回合判死。
- 新增 4 个模型模式测试：凭空动作被拒并重写、漏时间被指出并重写、
  开头重复触发重写、方向反了退回程序；共 32 个单测通过。

验证：33 个单测通过；12 个连续真实点位 12/12 通过，跨点逐字重复 0 句。

## 与 07 / 09 / 06 的接口

- **07**：实现 `BeatComposer`（`(request, options) => {text, raw?, source:'model'|'external', ms?, attempts?}`），放进 `policy.composer` 即可；不需要 import 本线代码。规则：只写这一段、只用 `scene.licensed` 里的材料、必须表达 `beat.factIds`、流式必须是真的增量。
- **09**：见 `results/quality/team-04-settlement.json` 的 `runEntry`，直接把它们已有的 `run-browser-candidates.mjs` 指向本模块、导出名 `generateCandidate`。
- **06**：薄适配，把 `committed`（含 state/beforeState/timeAdvance/entityDeltas，或只有 facts + `policy.scene`）、`inputText`、`priorText`、`policy` 传进来；页面可继续把 `basePacket` 交给 `alignNarration`，但 sanity 用 `policy.sanityStyle:'number'` 或从包中剔除。06 目前把可用提交钉在 `b18d36d7`，应改为本线 HEAD `4e0f5d26`：事实包 + 场景提示、切句授权、上一回合描写不复用、`resultsText` 成段，都是在其适配器形状上验证的。
