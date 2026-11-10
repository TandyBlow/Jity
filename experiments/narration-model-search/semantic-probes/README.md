# 结构化语义探针（11 线）

这组探针回答一个和“小说写得好不好”分开的问题：候选模型能否按 03/04 修正后的协议，输出**引用有效、覆盖完整**的结构化结果。它不评价文风，也不构成产品验收。

## 为什么现在只有校验器

09 的真实回合暴露了四类错误：

1. `results`：effect 指向未声明的 target（`rules`）。
2. `updates`：实体位置写成字面量 `id`（占位符）。
3. `updates`：任务覆盖只写了 12/73（旧的逐行 echo 组织）。
4. `continuation`：用显示名 `路明非` 代替角色 id，且主角不应作为续写候选。

其中 2、3、4 首先是提示词/覆盖组织/引用解析缺陷；04 已改成“每个有任务的人物一条决定、唯一全名可解析、占位符拒绝”。在这些修复提交前冻结探针，会把协议缺陷误判成模型能力不足。因此本目录先提供**校验器和冻结格式**，真实案例等 03/04 的修正版提示词/状态/schema。

## 文件

- `../src/semantic_validate.py`：读取 `pack.jsonl` 和 `run-dir/<caseId>.json`，校验 JSON 引用和覆盖；输出逐例 `ok/errors/warnings`，退出码 0（全过）或 2。
- 真实 pack：待 03/04 提供（见 `results/11-model-search/requests/11-to-03-04-semantic-cases-001.json`）。
- 合成自检：在 `src/selftest.py` 里，覆盖四类错误的正/负例；它不是候选结果。
- `fixtures/free-day-73-tasks.json`：从 06 当前 `dragon-raja-free-day.world.json` 的 initial 状态导出的紧凑夹具（14 人物、73 任务、source sha256 在文件内）；自检用 14 人物全覆盖和 12/14 两种输出验证覆盖尺度。
- `evidence/semantic-cases/tasks-free-day-real-73-no-change.json`：从 06 真实 turn-15 状态生成的 73 任务草稿案例。实际提示词 **6109 字符**，14 个有任务人物；结算结果只是“向西回廊移动”，所以提议的 expected 是 14 条空决定。全 14 条通过校验，12/14 被拒（缺 `tomiyama`、`zhou`）。它**不是冻结案例**，`correctedContract` 仍为 false，冻结器会拒绝；等 03/04 确认提示词和期望后再冻结。

## pack 格式（JSONL，每行一例）

```json
{
  "caseId": "updates-...",
  "kind": "tasks|results|continuation|updates",
  "allowedIds": ["char_shen", "loc_hall", "task_watch"],
  "nameToId": {"沈砚": "char_shen"},
  "allowUniqueNames": true,
  "protagonistId": "char_lu",
  "requiredCharacterIds": ["char_shen", "char_lu"],
  "allowedTaskIdsByCharacter": {"char_shen": ["task_watch"]},
  "alreadyAchievedTaskIds": [],
  "declaredTargetIds": ["char_lu"],
  "maxCandidates": 4
}
```

`kind` 检查：

- `tasks`：`decisions` 必须有每个 required 人物一条；`achieved` 只能含该人物自己的、未完成的任务 id；不得重复。
- `results`：`members[].effects[].targetId` 必须在 `declaredTargetIds` 内。
- `continuation`：每个 `candidates[].characterId` 必须有效、不是主角、`text` 非空、数量不超过上限。
- `updates`：递归检查 `entityId/containerId/characterId/targetId/...` 字段，拒绝占位符和未知 id。

所有 kind 都拒绝 `id`、`人物id`、`<...>` 等占位符；`allowUniqueNames` 只允许唯一全名映射到 id，并记录 warning。

## 冻结成 screen.py 可跑的提示词

03/04 的修正版 pack 每例必须带 `system`、`user`、`correctedContract: true`、`contractCommit`，然后：

```bash
python -X utf8 src/prepare_semantic_prompts.py --pack semantic-probes/pack.jsonl   --out-dir evidence/semantic-prompts-v1 --frozen
```

缺 `correctedContract`/`contractCommit` 时脚本拒绝冻结；这是为了防止把旧的 73 行 echo 提示词当成修正契约。冻结后由 10 用 `screen.py` 跑，11 用 `semantic_validate.py` 验。

## 运行

```bash
python -X utf8 src/semantic_validate.py \
  --pack semantic-probes/pack.jsonl \
  --run-dir evidence/runs/semantic/<model> \
  --out evidence/runs/semantic/<model>/semantic-report.json
```

候选的语义输出仍通过 10 的 HPC 批量生成；11 不在本地占用 GPU，也不把语义通过当成叙事质量通过。
