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

## 运行

```bash
python -X utf8 src/semantic_validate.py \
  --pack semantic-probes/pack.jsonl \
  --run-dir evidence/runs/semantic/<model> \
  --out evidence/runs/semantic/<model>/semantic-report.json
```

候选的语义输出仍通过 10 的 HPC 批量生成；11 不在本地占用 GPU，也不把语义通过当成叙事质量通过。
