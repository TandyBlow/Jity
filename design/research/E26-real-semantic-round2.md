# E26 真实事件采集第二轮：部分成功与重复/失败密度

**Question.** `env_partial` 的可训练样本是 0，`info_repeat`/`info_failure`/
`info_partial` 各只有个位数；用两条新路由把这几类补起来，同时覆盖
"把部分改变做完"的后续状态。

**Setup.** `semantic-scenarios.json` 新增两条 train 路由：
`env-11`（12 回合：5 个部分成功、3 个把部分改变完成到底、失败/移动/转移对照）
与 `info-24`（10 回合：new/repeat/failure/partial，问诺诺、芬格尔、顾岚）。
沿用 `run_semantic_routes.py` 的 micro 验收链路（seed=11），两条路由均
`COMPLETED`。标注走既有 DeepSeek 缓存管线：22 条新回合全部缓存未命中，
21 条完成标注，`sm-e-partial-4` 连续三次 `api-error: Connection error`
（其他行正常），标记为 invalid，证据保留、不进数据集。

**Results.**
- 数据集：260 → 280 原始行，train 245、test 8；validator `pass=true`。
- 字段计数（train）：info 正 57 / 负 106；env 正 55 / 负 165（门槛 50/50）。
- 类别变化：`env_partial` env present 1（此前 0）、insufficient 2、conflict 1；
  `env_failure` env absent 4、conflict 5；`info_repeat` info absent 1、
  insufficient 5；`info_failure` info absent 5；`info_partial` info absent 3。
- 训练门 `train_micro_semantic.py` 通过；gate 测试 21/21。

**Fix set（新暴露）.**
- "把部分改变做完"的 env_success 出现 2 条 conflict（检修盖/长桌补全回合），
  env_failure 5 条 conflict——和 sc06/sc08 同族：部分状态与完成状态之间的
  转移没有被差分记为环境变化。下一轮环境补丁先修这个转移。
- `info_new` 里仍有 2 条 absent：问了人但结算没有产生可支撑的信息事实。

**Conditions.** 单一世界 dragon-raja-free-day（goal.md 非目标禁止新造世界，
与目标文本的"多世界"要求冲突，待用户裁决）；种子 11；每路由一次。

**Principle.** 部分成功事件从此有可训练正例；同时证明"补全部分改变"仍是
环境补丁的缺口，conflict 行正是修复清单，不是负例。

**Artifacts.** `evidence-semantic-env-11.json`、`evidence-semantic-info-24.json`
（本地大文件，不入库）、`semantic-turns-{env-11,info-24}.json`、
`real-semantic.jsonl`、`real-semantic-manifest.json`、D-135。
