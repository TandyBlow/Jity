# 主树集成记录：从模块到真实页面闭环（2026-11-10 第二批）

本文件记录主集成工作树 `world-narration-worktree` / `world-narration-model` 在本轮的实际状态。
所有数字来自真实浏览器（headless Edge + WebGPU + wllama）跑出的 JSON，归档在
`artifacts/local-game/`。没有一项是"模块完成即产品完成"。

## 1. 已合入的分线提交（真实 merge，不是 cherry-pick 覆盖）

| 分线 | 提交 | 合入内容 |
|---|---|---|
| 05-kernel | `933dd65a` | 静态世界校验、`world-loader`、状态内核差分用例 |
| 01-input | `b9f2bce9` | `projectNarrationInput` / legacy 与 result-v2 序列化、码点与长度策略 |
| 02-narration | `15367421` | `generateCommittedNarration`：事实账本、校验、有界重试、流式状态 |
| 03-actions | `7bf860ea` | 自主行动 / 指代目标 / 被迫反应三个处理器与守卫 |
| 04-settlement | `16e60cfd` | 共同结果、六阶段更新、继续判断 |
| 07-sync | `bca80dc9` | 归档式进度存储、CAS、分叉、离线补写（尚未接入页面） |
| 08-runtime | `f902395b` | 硬停止取消、真实流式证据、队列取消 |
| 09-ui | `955dbfa0` | 阅读/历史/状态/控制四类组件（尚未接入页面） |
| 10-training | `8f22a086` | v2 数据与 HPC 入口、结果块模板 |

合入后修正了四条分线测试与真实内核不一致的地方（槽位声明、`point.sequence`/`kind`、
空初始外貌、纯删除校验路径），改的是测试装置与 `projectStage` 的瞬时点构造，没有放宽产品断言。

## 2. 主树的接线

`frontend/src/lib/world-engine/local/game-model.ts`：

- `action` / `targets` / `reaction` → 03 线 `createActionHandlers`，删除了旧的"点名+动词表"门。
  只保留一个场景预算：未被玩家点名的同场 NPC 本回合不另开冻结组（`maxAutonomousActors`），
  反应仍由受威胁目标触发。
- `results` / `updates` / `continuation` → 04 线 `createSettlementHandlers`，删除旧的
  `program_single_member` 单人捷径、`parseLineChanges` 文本行解析、`programMovementChanges`
  关键词移动兜底和 `autoContinuations < 1` 上限。继续判断在"每回合交还"配置下不再调用模型
  （没有可推进的自动回合，这不是模型判断），其余情况仍走 04 线策略。
- 六阶段改为**场景范围**判定（主角 + 同地点人物 + 携带物 + 房内物品），地点表保持完整以便
  位置引用合法。理由：14 人 73 任务的全世界提示词在 0.6B 上超过上下文并导致 60 秒超时，
  而单点结算只需对玩家可见场景负责。范围写进 evidence，不是静默裁剪。
- `updates` 返回前做一次**结构化移动判断**并合并进 position 阶段：玩家句子确实走向相邻地点、
  而六阶段没有给出主角位移时，用"从候选地点里选一个"的 JSON 问题补上。这是让"走到某处"
  真的改变世界状态的最小闭环，不替换模型对其它字段的判断。
- 继续判断失败不再把整轮变成 `settlement_failed`；模型输出里的未知候选人物按姓名映射或丢弃。

`frontend/src/app/world-local/page.tsx`：

- 两个 GGUF（语义 Qwen3-0.6B、叙事 Qwen2.5-1.5B + LoRA）全部本地加载；`resilientEngine`
  在 wllama 硬停止导致模型卸载后自动重载一次，长会话不会因为一次超时永久失效。
- 语义引擎上下文 8192，叙事 3072；叙事走 ChatML + `<|im_end|>` 停止符。
- localStorage 存档只在没有半结算点时写入，刷新恢复；`run-page-play.mjs` 额外做了刷新恢复检查。

## 3. 真实页面证据（本轮）

| 归档 | 输入 | 结果 |
|---|---|---|
| `page-play-scene-scope.json` | 走向西回廊 | 134.6s；results 13.4s、updates 64.8s、narration 48.1s；正文为草稿（`low_support`） |
| `page-play-move-injected.json` | 走向西回廊 | 112.4s；位移被写入状态（正文在西回廊）；narration 23.0s；`low_support` |
| `page-play-support12.json` | 蹲下问伤势 | 113.4s；模型原稿 164 字被接受过滤，末句宣称完成任务被 `task_claimed_without_fact` 拦下，最终回退草稿 |
| `page-play-final2.json` | 蹲下问伤势 | 159.1s；updates 74.8s 失败（模型把字面量 `id` 当实体），narration 62.4s（两次尝试）后回退草稿 |
| `page-play-final-check.json` | 两回合连续 | 129.6s / 141.4s；两回合都完成并刷新恢复；正文仍是草稿为主的降级文本 |

结论：**闭环成立，正文不达标**。行动、牵连、反应、共同结果、六阶段状态、交还、存档恢复都在真实
页面跑通；正文在多数回合因为模型原稿无法全部落到已结算事实上而回退到程序草稿，草稿是事实正确
的流水句，不是训练材料水平的叙事。单回合 110–160 秒，首段可读文本在提交后约 75–140 秒出现，
**没有达到一分钟内出现可读正文**。

## 4. 仍然失败的具体点

1. **正文接受率低**：Qwen2.5-1.5B + 389 行 LoRA 能写出通顺中文，但经常新增动作、对白、往事或
   把别人的伤势写到主角身上；逐句支持过滤后常不足 80 字，回退草稿。最近四轮全部 `low_support`。
2. **结算模型弱**：0.6B 在 `results` 里给物品写 effects、在 `updates` 里把 `id` 当实体、
   任务覆盖不全。已放宽"未判定任务保持原状"和"过滤未声明 effects"，但仍有整阶段失败。
3. **耗时**：六阶段串行 + 叙事两次尝试使单回合经常超过两分钟；updates 单阶段 60 秒超时会触发
   wllama 硬停止（已用重载兜底，但该回合已失败）。
4. **未接入**：07 的进度服务器、09 的阅读/历史组件、01 的 result-v2 序列化（模型没有 v2 权重，
   接上只会制造第二套格式）、08 的取消按钮和诊断面板。

## 5. 下一步（按证据）

- 把 `results` 的事实改成"每条行动一句可直接引用的结果"，并让叙事只允许引用该结果 + 状态差值，
  从数据侧减少可编造空间（10 线正在做 result-block 数据）。
- 给 1.5B 的 LoRA 补"同事实多写法"样本，目标不是 dev loss，而是页面 `supported` 长度。
- 六阶段合并为一次调用（位置+外貌 / 任务+子任务 / 个性+理智），把 65 秒压到 25 秒以内，
  再谈一分钟首段。
