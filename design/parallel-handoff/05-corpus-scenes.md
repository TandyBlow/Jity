# 05 线交接：完整场景与连续回合正文（第一批）

状态：首批可直接消费的材料已完成，分支 `goal/local-05-kernel`，工作树 `D:/others/Jity/.local/parallel-local-game/worktrees/05-kernel`。本批只新增写作材料，不改内核、页面、模型或冻结数据。

## 交付物

| 路径 | 内容 |
|---|---|
| `experiments/narration-quality/corpus-scenes/README.md` | 字段、序列、事实纪律、消费方式、限制 |
| `experiments/narration-quality/corpus-scenes/build_corpus.py` | 应用变化 + 事实检查 + 生成消费文件 |
| `experiments/narration-quality/corpus-scenes/world/tide-watch.json` | 自带开发世界和三条分支起始快照 |
| `experiments/narration-quality/corpus-scenes/sequences/*.json` | 三条连续序列的逐回合源稿 |
| `experiments/narration-quality/corpus-scenes/generated/rows.jsonl` | 主材料：11 行，含 `input`、`targetText`、`priorText`、`requiredFacts` 等 |
| `experiments/narration-quality/corpus-scenes/generated/rows-xy.jsonl` | 轻量 `x`/`y`，供训练管线 |
| `experiments/narration-quality/corpus-scenes/generated/splits.json` | 8 train / 3 dev，按序列分 |
| `experiments/narration-quality/corpus-scenes/generated/manifest.json` | 源/生成物哈希、统计、事实检查和外部校验结果 |
| `experiments/narration-quality/corpus-scenes/generated/preview.md` | 逐回合人工阅读稿 |
| `results/quality/team-05-kernel.json` | 给 10/02/03/04 的共享登记 |

本批 3 条序列：值班室 5 回合、栈桥 3 回合、电报间 3 回合（dev）。正文 168–296 字，平均约 240 字。

## 这份材料是什么，不是什么

是：作者新写的开发世界完整场景，每回合有完整五键输入（视角/上回合状态/本回合变化/本回合状态）、合法上一回合正文、必须落实的结算事实、允许的细节、视角边界和禁止补写项。覆盖多角色同场、同一场不同任务、任务完成后的个性/情绪变化、物品转移与外貌增删、离场人物回来、连续回合不重复发现。

不是：模型、权重、评测分数、浏览器页面记录、独立终验集。三条分支的首回合从作者设定的起始快照开始（`branches.*.premise`），不是页面已经发生的历史；不能把手写快照冒充浏览器记录。

旧 199 行、旧 splits、冻结数据都没有修改。`sourceRowId` 为 `authored:...`，表示本批是新写；如果后续改写旧行目标，必须保留 `row-XXXX` 作 `sourceRowId` 并原样保留旧输入。

## 给 10（训练）

- 直接消费 `generated/rows-xy.jsonl` 的 `x` + `y`；需要 `priorText` 时从 `rows.jsonl` 取。
- 连续回合必须按 `sequenceId` + `turnIndex` 顺序使用，不能打乱；同一序列内后一回合不能重新发现前一回合已经发生的事。
- 不要把 `requiredFacts`、`licensedDetails`、`knowledgeBoundary`、`forbiddenInventions` 拼进 prompt 或参考答案。
- 需要 beat 目标时，从 `requiredFacts` 选事实另写文本，不要机械切分整段 `targetText`。
- `tide-watch-radio` 是 dev，不进入训练。
- 这不是候选模型输出，不能拿它当模型质量证据。

## 给 02（浏览器叙事）

- 用这批材料检查多角色/连续回合/任务后情绪三类真实缺口；允许同义改写，但任务目标、新增个性、外貌增删这些冻结文本必须逐字出现（当前对齐器约束）。
- 对齐器的已知识边界（写作时已绕开，供复核）：任务/个性句必须本句出现人物名；任务目标不要含地点名（会被其他在场人物的 `at` 事实误判）；个性文本不要含另一个人物名（会被判 actor swap）；物品转移句避免“到+地点”的移动句式（对齐器没有物品事实）。
- 真实模型失败时回传原始输入、生成文本和错误类型，不要用规则模板替换失败场景后声明通过。

## 给 03/04（本地指令模型 / 事实骨架）

- 可把这 11 行当作“事实已结算、正文已落实”的完整场景对照，检查候选输出是否漏事实、加事件、换人物、反方向、漏时间。
- `requiredFacts` 是人工指定的最小事实集；`licensedDetails` 是允许但不强制的细节；`forbiddenInventions` 是本回合明确禁止的补写。不要把这些字段当模型输入。
- 候选模型若只能写逐事实短句，可先用这批材料判断它是否具备多角色同场和连续回合能力，再决定是否投入更长场景。

## 校验

1. 重建：`python -X utf8 experiments/narration-quality/corpus-scenes/build_corpus.py`，11 行，事实检查全部通过。
2. 本线测试：`cd frontend && npx vitest run src/lib/world-engine/local/state.test.ts src/lib/world-engine/local/canonical.test.ts src/lib/world-engine/local/world-loader.test.ts src/lib/world-engine/local/local-transport.test.ts --maxWorkers=1`，内核/transport/loader 不受本批影响。
3. 外部校验：用 02 线提交 `211fd463` 的 `verifyNarration` 临时拷贝逐行跑，11/11 无 hard issue，23/23 强制事实落实，无重复句/小句，无上一回合回声（bigram 0.08–0.14）。拷贝跑完删除，未改 02 工作树。
4. 类型检查：`cd frontend && npx tsc --noEmit -p tsconfig.world-contract.json` 与 `npx tsc --noEmit -p tsconfig.json`。

## 限制与下一步

- 正文 168–296 字，比旧长行短；下一批补更长的多拍场景。
- 本批不写精神值变化：当前对齐器要求 from/to 数字，会把正文变成状态复述；情绪由个性文本承担。
- 没有物品整体出现/消失，只有转移和外貌增删。
- 没有真实模型、浏览器 GPU 或页面 E2E；页面接线仍由主 agent 负责。
- 下一批按 02/10 的真实失败补：三人以上同场、同回合两件任务、物品出现/消失、旧行忠实改写（登记原 `sourceRowId`）。
