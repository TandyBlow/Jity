# 任务达成进入回合事实句（R09 展示侧）

日期：2026-11-06。**不训练、不启用模型句、只读。**补的是[接入报告](integration-r1-2026-11-06.md)列出的第一个缺口：任务变化此前只有一句提示，没有说清谁完成了什么。

**当前档位**：展示侧「有页面验收」。不是产品部署接线（仍需设 `WORLD_FACTS_ADAPTER` / `WORLD_SQLITE_PATH`），也不是完整 R09（真模型的任务扫描、子任务生成仍未发生）。

## 1. 原来的缺口是怎么产生的

一次提交里，任务变化只记一个 ID：`tasksAchieved: ["task_pressure"]`。任务的目标文字（例如「完成压力试验」）不在改动里，只存在提交后的世界状态里。适配器原来没有读这段状态的代码，于是把该实体放进 `notDisplayed`，页面统一印一句“存在尚未展示的任务变化”。所以玩家知道“有任务变了”，但不知道是谁、哪个任务。

## 2. 现在一轮的完整过程

以页面上的正常命令为准，`D:/others/Jity/.local/world-components-next-worktree` 的隔离世界：

1. 玩家在走廊输入「完成压力试验」。
2. 规则会话把结算交给服务端；Python 提交时把该点的改动写成 `{"person_c": {"tasksAchieved": ["task_pressure"], "sanitySet": 8, "personalityChanges": [...]}}`，同时把 `characters.person_c.tasks.task_pressure.status` 从 `pending` 改成 `achieved`，保存点位与检查点。
3. 页面请求 `GET /world/facts/world_1/point_7`。
4. 后端按 `WORLD_FACTS_ADAPTER` 加载适配器；适配器读该点改动，恢复该点的已提交状态（重放，并用检查点摘要互核），在 `characters.person_c.tasks` 里找到 `task_pressure`，核对三件事：属于 `person_c`、状态是 `achieved`、有目标文字；然后原样取出目标「完成压力试验」。
5. 适配器返回事实 `{"kind": "task_achieved", "sentence": "周宁达成任务：完成压力试验。"}`，来源里记下读过的字段 `tasks.task_pressure.goal`、`tasks.task_pressure.status`，以及状态来源 `replay`。
6. 页面把这句话印在回合行下面，不再印“尚未展示”的提示。

页面实际显示（第 1 回合）：

```
周宁的理智下降（10→8）。

周宁：经历压力试验后更谨慎。

周宁达成任务：完成压力试验。
```

刷新后，整页重建对每个点位重新请求同一个接口，第 1 行逐字相同。刷新后再加一回合，更早的行也不变。

## 3. 什么情况下不会出句

句子只在“改动、已提交状态、检查点”三者对得上时产生。对不上就出缺口（页面红字“该点位事实暂无法恢复”），绝不猜：

| 情况 | 结果 |
| --- | --- |
| 改动里的任务 ID 在已提交状态里不存在 | 缺口：`the delta says task X was achieved, but the committed state has no such task` |
| 状态仍是 `pending` | 缺口，并写出实际状态 |
| 任务属于别人 | 缺口，并写出实际所有者 |
| 已提交任务没有目标文字 | 缺口 |
| 改动与已提交状态的目标/上级/所有者不一致（新增小任务） | 缺口 |

新增小任务（`subtasksAdded`）的句子形如 `周宁新增小任务：完成恢复练习（上级：完成压力试验）。` 上级目标同样从已提交状态读取，不从改动里的父 ID 自行推断。

## 4. 验收

| 项目 | 结果 |
| --- | --- |
| 正常命令产生任务达成，页面出现任务句 | 通过：`周宁达成任务：完成压力试验。` |
| 页面出现“尚未展示”提示 | 不再出现（校验脚本把“没有尚未展示”当作每回合必须成立） |
| 刷新前后逐回合文本 | 完全一致，包括任务句 |
| 新增回合后更早的历史行 | 原样不动 |
| 控制台错误 | 无 |
| 核对方式 | `verify_page_facts.py` 从 `world_points` 与检查点里的任务目标自行推出每回合必须出现什么，不调用适配器 |
| 结果 | **6 个回合、24 项检查、0 个问题**（上一轮 18 项，新增任务句与“无未展示提示”两类） |
| 适配器单元测试 | 20 个全过（原 15 个 + 新增 5 个：达成句、待办冒充达成、未知任务、子任务句、子任务目标不一致） |

证据：`artifacts/next-acceptance/task-display-r1/`（`verify.json`、`browser-record.json`、3 张截图、19 条事实请求日志、适配器原始输出、`index.json` 含每个文件的 sha256）。

## 5. 没覆盖的部分

- **新增小任务没有页面级验收**：规则词汇表只产出 `positionSet / sanitySet / tasksAchieved / personalityChanges`，没有命令会写 `subtasksAdded`。子任务句只在单元测试里用“已提交状态夹具”验证过，不能算页面流程通过。
- 只在一个隔离世界、一个任务（`task_pressure`）、走廊一个位置跑过；换世界、换任务文本未验证。
- **外貌变化仍然没有正常操作路径**：与[接入报告](integration-r1-2026-11-06.md) §4 相同，本轮没有改变这一点。
- 句子顺序沿用适配器原来的顺序（位置、理智、外貌、性格、任务），没有按 R09 的应用阶段重排。应用顺序和叙事展示顺序是两件事，本轮只补内容。
- 提示文案从“任务变化目前没有展示形状”改为通用的“存在尚未展示的变化”，原因文字也改为透传适配器的实际原因，不再写死成任务。
- 不声称模型句参与：本轮页面用的是模板叙事，模型句开关未打开。

## 6. 文件

| 部分 | 文件 |
| --- | --- |
| 任务句、缺口、来源 | `experiments/world-components/adapt_facts.py` |
| 单元测试 | `experiments/world-components/test_adapt_facts.py` |
| 页面核对（含任务期望） | `experiments/world-components/verify_page_facts.py` |
| 验收脚本（证据目录可配） | `frontend/scripts/world-facts-acceptance.mjs` |
| 主世界页（提示文案、来源折叠） | `frontend/src/app/world/page.tsx` |
| 预览页（提示文案） | `frontend/src/app/world/preview/page.tsx` |
| 后端接口（未改动，沿用） | `world-server` `005ea5b`：`backend/app/routers/world_facts.py` |

复跑命令（仓库根目录，服务已在 8021/3111）：

```bash
# 后端（.local/ws-facts-005ea5b/backend）
WORLD_SQLITE_PATH=<新的 world.db> \
WORLD_FACTS_ADAPTER=<本仓库>/experiments/world-components/adapt_facts.py \
WORLD_FACTS_BACKEND=<.local/ws-facts-005ea5b/backend> \
WORLD_ALLOWED_ORIGINS=http://127.0.0.1:3111 \
python -X utf8 -m uvicorn app.world_app:create_persistent_world_app --factory --port 8021

# 页面
cd frontend && WORLD_FACTS_OUT=artifacts/next-runs/task-display-r1/browser node scripts/world-facts-acceptance.mjs

# 核对
WORLD_FACTS_RECORD=artifacts/next-runs/task-display-r1/browser/record.json \
WORLD_FACTS_DB=artifacts/next-runs/task-display-r1/world.db \
WORLD_FACTS_VERIFY=artifacts/next-runs/task-display-r1/verify.json \
python -X utf8 experiments/world-components/verify_page_facts.py
```
