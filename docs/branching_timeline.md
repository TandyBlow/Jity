# 分支剧情时间线与跨幕上下文

本文档描述剧情树快照、历史节点恢复、后续分叉以及 Campaign 跨幕上下文的当前实现。开发日志记录版本变化；本文档作为维护这些能力时的长期技术入口。

## 目标与边界

每次成功生成都会形成一个不可变的 `story_turns` 节点。节点保存玩家行动、结构化剧情输出、完整游戏状态、Campaign 进度、模型和来源。`game_sessions.active_turn_id` 指向当前剧情头。

恢复历史节点不会删除原后代。恢复后提交的新行动以该节点为父节点，因此与原后代形成兄弟分支。当前只支持同一会话内恢复，不允许跨会话激活节点。

## 数据模型

主要字段：

- `story_turns.id`：节点主键。
- `session_id`：所属游戏会话。
- `parent_turn_id`：父节点；根节点为 `NULL`。
- `depth`：从根节点开始的深度。
- `player_action`、`output_json`：本回合输入和结构化输出。
- `state_json`：该节点完成后的完整游戏状态，包括服务器内部记忆快照。
- `campaign_progress_json`：Arc、Session、幕内回合、锚点、recap、NPC 关系和存档槽信息。
- `model`、`source`、`model_output_id`：生成来源和审计关联。
- `game_sessions.active_turn_id`：当前激活节点。

数据库初始化会为旧会话补建根节点。新会话由 `GameStateManager.create_session()` 立即创建根节点。

## 生成与提交顺序

`ScenarioGenerator.generate()` 对同一 `session_id` 使用会话级异步锁，并读取当前 `active_turn_id` 作为 `expected_parent_id`。请求若携带 `timeline_node_id`，它必须与当前节点一致，否则返回并发修改错误。

普通 LLM 回合与固定开场均遵循同一提交原则：

1. 读取当前节点、游戏状态和 Campaign 管理器。
2. 构建提示词并生成 `StoryOutput`，或生成固定开场输出。
3. 在内存中应用状态、记忆和 Campaign 推进。
4. 调用 `commit_story_turn()`，在一个数据库事务中插入子节点、写入本分支消息、更新会话状态并移动 `active_turn_id`。
5. 只有 `expected_parent_id` 仍为当前头节点时事务才成功，防止并发请求覆盖另一条分支。

模型请求失败不会创建剧情节点；错误详情仍写入 `model_outputs` 供诊断。

## 恢复与继续分叉

后端端点：

- `GET /sessions/{session_id}/timeline` 返回节点摘要、父子关系、当前节点和当前祖先路径。
- `GET /sessions/{session_id}/timeline/{node_id}` 返回完整剧情输出、公开状态与 Campaign 快照。
- `POST /sessions/{session_id}/timeline/{node_id}/activate` 原子恢复节点状态和 Campaign 进度，然后失效 Campaign Manager 与 Memory Controller 缓存。

消息历史查询通过递归 CTE 只选择当前节点的祖先链。被放弃分支的消息仍保留在数据库中，但不会进入当前分支的历史、提示词或 recap。

前端 `/timeline` 将节点渲染成树。选择节点可查看当时剧情、地点、数值、物品、NPC、任务和世界事实；点击“从此处继续”后回到游戏控制台，下一次行动建立新分支。

## Campaign 跨幕上下文

跨幕连续性使用两层隔离：

1. Narrator 的最近原始消息限定为当前 `campaign_session_index`。上一幕原始对话不会与新幕开场竞争；跨幕因果通过 recap 保留。
2. Director 明确接收当前地点、当前幕固定开场和当前幕最近记录。上一幕 recap 标注为背景，不能作为当前场景继续。

纯续写动作（例如“继续”“继续剧情”“接着”）不依赖物品或在场 NPC，因此确定性判为可行，避免开场人物尚未写入结构化 `entry_state` 时被 Examiner 错误阻止。更具体的交互、移动和物品行动仍进入 Examiner 规则判定。

## 回归测试

后端自动测试：

```bash
cd backend
python -m pytest -q
```

重点用例：

- `backend/tests/test_branching_timeline.py`：兄弟分支、祖先链消息隔离、精确状态恢复、过期父节点和跨会话拒绝。
- `backend/tests/test_campaign_openings.py`：四战役开场、跨幕固定开场、当前幕提示隔离和“继续”不被误拦截。
- `backend/tests/test_api.py`：根节点与时间线 API 会话边界。

真实 LLM 跨幕冒烟：

```bash
python scripts/campaign_transition_smoke.py \
  --base-url http://127.0.0.1:8000
```

脚本对四个内置 Campaign 创建临时副本，把每幕限制为两回合，通过生产 HTTP 路径执行：

```text
固定开场 → 真实 LLM 继续 → 下一幕固定开场 → 真实 LLM 继续
```

Markdown 报告适合人工检查剧情，JSON 报告适合保存检查结果。测试必须确认：

- 非默认战役没有混入“入学调查”专属内容。
- 固定开场没有重复。
- 下一幕地点和开场与 Campaign JSON 一致。
- 下一幕后的 Narrator 输出承接新地点和新人物，而不是回到上一幕。
- 持久化的输入提示词与实际四步输入一致。

真实 LLM 测试会消耗额度，不应放入默认 CI；发布前或修改 Campaign 上下文、Director、Examiner、消息查询、recap 和时间线恢复逻辑后手动执行。

## 已知限制

- 会话级锁是进程内锁；多进程部署主要依赖 `expected_parent_id` 的数据库并发保护。
- 时间线节点保存完整 JSON 快照，长战役会增加 SQLite 体积，尚未实现压缩或归档。
- 后台记忆维护不是持久任务队列；进程退出可能中断尚未完成的维护任务。
- `artifacts/smoke/` 中的报告是回归证据，不是稳定测试夹具；新的正式结果应使用带时间戳文件，开发日志只链接最终通过的报告。
