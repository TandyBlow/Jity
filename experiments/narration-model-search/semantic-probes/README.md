# 结构化语义探针（11 线）

这组探针回答一个和“小说写得好不好”分开的问题：模型能否按 04 修正后的协议，输出**引用有效、覆盖完整、任务判断正确**的结构化结果。它不评价文风，也不构成产品验收。

## 09 的真实失败与 04 的修正

09 暴露过四类错误：

1. `results`：effect 指向未声明的 target（`rules`）。
2. `updates`：实体位置写成字面量 `id`（占位符）。
3. `updates`：旧的逐任务 echo 契约只写了 12/73；改成每个有任务的人物一条决定后，又出现过只回答 1/14 人物。
4. `continuation`：用显示名 `路明非` 代替角色 id，且主角不应作为续写候选。

04 已提交两层修正：

- `ad90cfba`：任务提示词为每个 required 人物放一条**可抄的空决定行**，抄示例也会得到全人物覆盖；
- `117befcf`：ledger 记录 `achievedByCharacter` / `emptyCharacters`，区分“抄了空骨架”和“真的判断过”。

本仓库的 frozen pack 固定使用 `117befcf` 的提示词。它仍是探索性探针：positive case 的 expected 是 11 线提出的，不是 03/04 的最终质量结论。

## 两个真实状态案例

`evidence/semantic-cases/`：

- `tasks-free-day-real-73-no-change.json`
  - 来自 06 的真实 turn-15 状态；14 人物、73 任务。
  - 提示词 **6,650 字符**；结算结果只是“向西回廊移动”，expected 为 14 条空决定。
  - 测覆盖和“不编造达成”。
- `tasks-free-day-real-73-one-achieved.json`
  - 同一真实状态；把结算结果写成“戴上护目镜并确认镜片没有裂纹”，明确对应 `task_lu_goggles`。
  - 提示词 **6,664 字符**；expected 只给 `lu: [task_lu_goggles]`，其余 13 人空。
  - 测模型会不会真的填一个达成任务；**照抄全空骨架会被 `--expected` 判错**。
  - 这条 settled result 是构造的（`constructedResult: true`），不是原始模型输出；它不是产品事实。

按 09 实测的 0.51–0.65 token/字符比例，两条提示词约 **3.4–4.4k token**；页面语义模型加载的上下文是 **12,288**。这只是估算，不是 tokenizer 实测；上下文截断不是 1/14 或 12/73 的显然原因。

## 校验和打分

`../src/semantic_validate.py` 默认只做结构校验：

- `tasks`：每个 required 人物一条决定；`achieved` 只能含该人物自己的、未完成的任务 id；
- `results`：effect 的 `targetId` 必须在 `declaredTargetIds`；
- `continuation`：角色有效、不是主角、正文非空、数量不超限；
- `updates`：递归检查 id 字段，拒绝 `id`、`人物id`、`<...>` 等占位符。

加 `--expected` 时，还会把 `tasks` 决定和 pack 里的 `expected` 比较，报告漏标/多标。这是语义正确性检查，不是文风评分。positive case 的“全空骨架”因此会被拒绝，报 `expected task task_lu_goggles not marked achieved for lu`。

## 冻结的提示词

`semantic-probes/tasks-73-release.pack.jsonl` 是两例的 release pack，`correctedContract: true`、`contractCommit: 117befcf…`。已冻结到：

`evidence/semantic-prompts-v2/{prompts.jsonl,prompts.manifest.json}`

manifest 记录 `frozen: true`、`promptCount: 2`、contract commit、pack sha256 和每例 prompt sha256。冻结器仍会在缺 `correctedContract`/`contractCommit` 时拒绝；draft pack 保持 `false`，用于对照。

## 运行

10 用冻结提示词跑 `screen.py`，输出每例 JSON；11 用：

```bash
python -X utf8 src/semantic_validate.py \
  --pack semantic-probes/tasks-73-release.pack.jsonl \
  --run-dir <run-dir> --out <report.json> --expected
```

候选的语义输出只通过 10 的 HPC 批量生成；11 不在本地占用 GPU，也不把语义通过当成叙事质量通过。没有模型跑过这组 release pack 时，报告必须写 `not run`，不能用 expected 文件冒充模型输出。

## 文件

- `fixtures/free-day-73-tasks.json`：14 人物/73 任务紧凑夹具（source sha256 在文件内），自检用 14/14 和 12/14 两种输出验证覆盖尺度。
- `preregistration.v1.json`：两例、六个模型（0.6B + 五个候选）、采样、评分和“不是质量门”的声明。
- `../src/build_semantic_case_from_state.py`：从真实状态重建提示词和 expected；`--achieved` 只允许该人物自己的未完成任务。
- `../src/selftest.py`：17/17，包括真实 73 任务案例、positive/copy 的 `--expected` 负例。
