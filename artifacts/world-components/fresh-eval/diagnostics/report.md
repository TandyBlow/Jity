# 六条诊断夹具核验报告（自动生成，勿手改）

工作树 HEAD：`01e0a92fd88a`；脚本 `tools/build_diagnostics.py`。

**定位**：六条诊断夹具、零条正式独立评测题、未冻结。内核通过只说明增量被接受，不说明该点已提交，也不说明它未参与训练或调参。

绑定来源：`design/world-protocol/v1/fixtures/school.initial-state.json`（sha256 `285468a395bde87e…`），根点摘要 `9301b7992248a972…`，与已提交根点一致：是。（这只证明初始状态一致，不证明点位身份或独立性。）

| 编号 | 内容 | 模块 | 类型 | 内核 | 投影 | v1 | v2 | 变化签名 |
|---|---|---|---|---|---|---|---|---|
| `c8d01` | 单人移动 + 其余五人现状陈述 | 页面已提交叙事路径（committed-narration） | 覆盖诊断 | accepted by apply_point | 全部支持 | source-bound | source-bound | c8d01_p1: `moved*1|1|180s` |
| `c8d02` | 三人三地同时变化（含跨父地点） | 页面已提交叙事路径 | 覆盖诊断 | accepted by apply_point | 全部支持 | source-bound | source-bound | c8d02_p1: `moved*3|3|90s` |
| `c8d03` | 视角外的人移动（N2 视角诊断） | C 侧 N2 视角规则臂（narration_pipeline.select_facts） | 视角诊断 | accepted by apply_point | 全部支持 | source-bound | source-bound | c8d03_p1: `moved*1|1|50s` |
| `c8d04` | 任务达成 + 人格变化 + 理智下降（回归诊断） | 页面已提交叙事路径 | 回归诊断（针对已确认的‘下降写成上升’错误） | accepted by apply_point | 全部支持 | rejected | source-bound | c8d04_p1: `personality_changed*1+sanity_changed*1+task_achieved*1|1|120s` |
| `c8d05` | 空增量点（只有时间流逝） | 页面已提交叙事路径 | 覆盖诊断 | accepted by apply_point | 全部支持 | source-bound | source-bound | c8d05_p1: `none|0|40s` |
| `c8d06` | 三点链：移动 → 空点 → 父任务达成＋人格＋理智 | 页面已提交叙事路径 | 覆盖诊断（含任务树边界） | accepted by apply_point | 全部支持 | source-bound；rejected；source-bound | source-bound；rejected；source-bound | c8d06_p1: `moved*1|1|4s`；c8d06_p2: `none|0|120s`；c8d06_p3: `personality_changed*1+sanity_changed*1+task_achieved*1|1|180s` |

## 三个状态分别记录

### `c8d01`

- 来源绑定：registered-fixture design/world-protocol/v1/fixtures/school.initial-state.json sha256 285468a395bde87e… state root_0 digest 9301b7992248a972…
- 内核校验：accepted by apply_point
- 提交状态：not-committed: hypothetical point, no round/group/settle/points record
- 独立性：undetermined: fixture vocabulary appears in corpora and archives; no evidence shows these points were excluded from training or tuning

### `c8d02`

- 来源绑定：registered-fixture design/world-protocol/v1/fixtures/school.initial-state.json sha256 285468a395bde87e… state root_0 digest 9301b7992248a972…
- 内核校验：accepted by apply_point
- 提交状态：not-committed: hypothetical point, no round/group/settle/points record
- 独立性：undetermined: fixture vocabulary appears in corpora and archives; no evidence shows these points were excluded from training or tuning

### `c8d03`

- 来源绑定：registered-fixture design/world-protocol/v1/fixtures/school.initial-state.json sha256 285468a395bde87e… state root_0 digest 9301b7992248a972…
- 内核校验：accepted by apply_point
- 提交状态：not-committed: hypothetical point, no round/group/settle/points record
- 独立性：undetermined: fixture vocabulary appears in corpora and archives; no evidence shows these points were excluded from training or tuning

### `c8d04`

- 来源绑定：registered-fixture design/world-protocol/v1/fixtures/school.initial-state.json sha256 285468a395bde87e… state root_0 digest 9301b7992248a972…
- 内核校验：accepted by apply_point
- 提交状态：not-committed: hypothetical point, no round/group/settle/points record
- 独立性：undetermined: fixture vocabulary appears in corpora and archives; no evidence shows these points were excluded from training or tuning

### `c8d05`

- 来源绑定：registered-fixture design/world-protocol/v1/fixtures/school.initial-state.json sha256 285468a395bde87e… state root_0 digest 9301b7992248a972…
- 内核校验：accepted by apply_point
- 提交状态：not-committed: hypothetical point, no round/group/settle/points record
- 独立性：undetermined: fixture vocabulary appears in corpora and archives; no evidence shows these points were excluded from training or tuning

### `c8d06`

- 来源绑定：registered-fixture design/world-protocol/v1/fixtures/school.initial-state.json sha256 285468a395bde87e… state root_0 digest 9301b7992248a972…
- 内核校验：accepted by apply_point
- 提交状态：not-committed: hypothetical point, no round/group/settle/points record
- 独立性：undetermined: fixture vocabulary appears in corpora and archives; no evidence shows these points were excluded from training or tuning

## 人工指定的参数

- `c8d01`：时长 3 分钟（本轮人工指定）；目的地 corridor（夹具既有地点）
- `c8d02`：时长 90 秒（本轮人工指定）；三条目的地均为夹具既有地点
- `c8d03`：时长 50 秒（本轮人工指定）；视角取夹具主角 person_c
- `c8d04`：时长 2 分钟（本轮人工指定）；理智 30→26（本轮人工指定；夹具 time-only 用的是 35）；人格文本＝夹具原文
- `c8d05`：时长 40 秒（本轮人工指定）
- `c8d06`：三段时长 4 秒 / 2 分钟 / 3 分钟（本轮人工指定）；理智 30→28（本轮人工指定）；人格文本＝夹具原文

## 签名口径

- 采用：change-only：只统计本点原始 Δ 产生的事实；现状读数不进签名
- 时间：时长折算秒数后比较（保留）

- **旧题内部同形**（变化口径无法区分）：
    - `none|0|300s` ← nv-empty-1, nv-cont-3
- **诊断夹具与旧题同形（口径同形，不写作派生）**：
    - `c8d06` / `c8d06_p2` 的 `none|0|120s` 等于 `nv-cont-2`（旧题变化依据 undetermined）

## 边界

- 叙事事实是按 TS 规则在 Python 里重写的镜像，不是执行 TS；投影是否真的接受仍需在该路径上跑一次。
- 本批全部为假设点，没有提交记录；不得用于任何独立性与能力结论。
- 未冻结；未做人工核验（表见 `review-table.md`，逐条材料见 `review-packets.md`）。
- 旧题的变化事实依据全部 `undetermined`（见 `sources/three-arm-provenance.md`）：签名相同只说明“按当前转换口径同形”。
- 预期复核见 `expectation-review.md`：两条预期目前只能人工判定。
- `nv-task-only-1` 是手写包与生产投影的输入契约不一致（`gaps.md` g05），其失败不能算模型失败。
