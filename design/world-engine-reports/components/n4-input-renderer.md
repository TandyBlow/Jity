# N4 叙事输入渲染器（正式组件 v0.1）

日期：2026-11-02。分支：`world-components`。源码基线：`483259c`。状态：**程序组件已实现并通过回归；未接 B，未训练模型**。

## 编号迁移

自 2026-11-02 起，叙事拆分的当前编号为：

| 新编号 | 组件 | 旧编号 |
| --- | --- | --- |
| N1 | 事实提取（程序） | N1 |
| N2 | 内容选择 | N2 |
| N3 | 组织表达（句组计划） | N3 |
| **N4** | **叙事输入渲染（程序：场景上下文＋模型输入文本）** | 原属 N4 内部步骤 |
| **N5** | **叙事成句（模型）** | **旧 N4** |
| **N6** | **事实核对（程序＋语义复核）** | **旧 N5** |

历史文档、归档证据与已冻结文件名继续使用旧编号，不重命名、不重算哈希。新文档和新代码使用上表编号。

## 1. 职责边界

N4 是**唯一生成 N5 模型输入文本**的程序组件。它把三份上游结果拼成一段确定性文本：

- N1 的事实条目（内容与字段）；
- N2 的已选事实集合（哪些进入输入）；
- N3 的有序句组计划（分组、顺序、时间归属、称谓授权）；
- N4.1 从权威状态与显式 environment overlay 构建的场景/人物上下文。

N4 **不做**：

- 不选事实、不增删 N2 的选集；
- 不分组、不排序、不改写 N3 计划；
- 不生成正文、不调用模型、不写状态；
- 不根据缺失字段猜天气、外貌、位置或人物关系；
- 不把 task goal/taskId、理智数值、精确时长写进文本。

## 2. 接口

源码：`experiments/world-components/n4_input_renderer/`

```python
N4_VERSION = "n4-input-renderer-v0.1"

# N4.1
build_scene_context(state, perspective, selected_facts, environment=None)
# -> {status: ok|stopped, sceneContext?, worldView?, diagnostics}

# N4.2 formal entry
render_narrative_input(case, plan, world, selected_fact_ids=None,
                       scene_diagnostics=None)
# -> {status: ok, input, diagnostics, version}
#  | {status: error, code, detail, diagnostics, version}

# compatibility / dev preview
render_plan_input(case, plan, world, strict=False, selected_fact_ids=None)
render_input(case, world, strict=False)
```

`case` 形状：

```python
{
  "facts": [N1 fact, ...],
  "sceneState": {
    "locationId": str, "locationPath": [locId, ...],
    "time": str|None, "weather": str|None,
    "wind": str|None, "light": str|None, "atmosphere": str|None,
    "present": [entityId, ...], "visibleItems": [itemId, ...]
  },
  "characterContext": [{
    "entityId": str, "name": str, "personality": str,
    "appearance": str, "inventory": [itemId, ...]
  }],
  "perspective": {"entityId": str}
}
```

`world` 是 world view：`locations`（含小地点）、`items`、`characters` 的 `name/appearance`。所有被引用的 id 必须能解析。

## 3. 输入文本结构

```text
叙事任务。
场景：<地点链>。<最深处地点外貌>。天气：<weather>。时间：<time>。
<在场人物>（性格：…；外貌：…；随身：…）
可见物：<item>（<appearance>）；…
这一拍（按叙述分组）：
第 N 组：
1. <事实行>
这一组之后，过去了一会儿（不写具体时长）。
视角：<POV>（第三人称限知）；只写<POV>的内心，他人只写可见动作。
要求：不要写任务标题、数值面板、具体时长、‘性格/外貌’字段名；不要新增未列出的具名人物/物品/地点。
正文：
```

事实行模板（固定字节，见 `renderer.py`）：

| kind | 文本 | 必需字段 |
| --- | --- | --- |
| `moved` | `{name}从{from}来到{to}。` | name/from/to |
| `outcome` | `{name}{resultText}。` | name/resultText；**不含 goal** |
| `sanity_changed` | `{name}的呼吸比刚才顺了一些。/有些发紧。/没有变化。` | name/from/to（数值只用于选方向） |
| `appearance_changed` | `{name}的{text}。` | name/text |
| `personality_changed` | `{name}的行为倾向：{text}。` | name/text |
| `no_change` | `这一拍没有新的变化。` | — |
| `time` | 不进编号行；输出组后或全局模糊时间行 | amount/unit 只留在计划内部 |

## 4. 输入来源

| 输入 | 来源 | 说明 |
| --- | --- | --- |
| `facts` | N1 `extract_facts(point, before, narrative_outcome=True)` | 来自按目标 `pointId` 读取的已提交状态与原始 Δ；前状态按 `previousPointId` 读取 |
| `selected_fact_ids` | N2 `classify_facts(...)` | 叙事臂使用 `may_policy="select"`、`visible_other_actions=True`；他人内心与 task goal 仍不可见 |
| `plan` | N3 `plan_v3(selected, names, cross_group_guard=True)` | 句组、顺序、时间归属、称谓授权；已过 `check_plan_v3` |
| 地点链/外貌 | 权威 `state.locations` 初值＋生效 `appearanceChanges` | `build_scene_context` 沿 `parentLocationId` 上溯 |
| 在场人物 | 视角主体＋携带**已选事实**的实体 | 不做全员扫描；100 个无事实 NPC 不进入 present |
| 性格/外貌/随身 | `state.characters` 初值＋生效变化；物品 `position.containerId` | 性格是“读取”输入，不要求正文体现 |
| 可见物 | 容器为当前地点或在场人物的物品 | 当前实现会把随身物品同时列进“随身”和“可见物” |
| 天气/时段 | 显式 `environment` overlay | 缺失即省略，并记 `environment-field-missing`；不发明 |
| 视角 | N2 `resolve_perspective` | 默认主角；解析失败即停机 |

## 5. Fail-closed 规则

`render_narrative_input` / `strict=True` 在以下情况返回 `status=error`，不输出部分文本：

| code | 条件 |
| --- | --- |
| `plan-shape-invalid` | plan 不是 `{sentences:[{index,factIds}]}` |
| `plan-refusal` | N3 计划本身是拒绝结果（strict 路径） |
| `facts-shape-invalid` | facts 不是对象列表 |
| `plan-unknown-fact` | 计划引用不存在的 factId |
| `duplicate-fact` | 事实表或计划内重复 factId |
| `selected-unknown-fact` | `selected_fact_ids` 指向不存在的事实 |
| `plan-coverage-mismatch` | 计划的非时间事实集合 ≠ 已选非时间事实集合（时间可只走全局回退行） |
| `unsupported-fact-kind` | 未知 kind；不再 JSON dump 兜底 |
| `outcome-result-missing` | `outcome` 缺 `resultText`；不回退 goal |
| `missing-field` | 事实缺模板必需字段 |
| `world-location-missing` / `world-location-appearance-missing` | 地点 id/外貌无法解析 |
| `world-item-missing` / `world-item-appearance-missing` | 物品 id/外貌无法解析 |
| `world-character-missing` | 人物 id 无法解析 |
| `character-name-missing` / `character-personality-missing` / `character-appearance-missing` | 人物上下文缺字段 |
| `character-inventory-invalid` | 人物 inventory 不是列表 |
| `scene-state-invalid` | sceneState 不是对象 |
| `scene-location-path-missing` | 场景没有地点链 |
| `perspective-unresolved` | 视角主体无法解析 |

缺失 environment 字段**不是错误**：N4.1 省略该行并记录诊断，N4.2 继续渲染其余输入。

## 6. 字节稳定性与版本

- 同一 `case + plan + world` 两次渲染逐字节相同；无时间、随机、locale、I/O 或模型调用。
- 模板字符串集中在 `renderer.py`；任何文本改动都必须提升 `N4_VERSION` 并重跑回归。
- `n4_input_renderer/test_renderer.py` 锁定：
  - 已审 12 例的 grouped 输入（`pipeline_preview.json`）逐字节一致；
  - 已审 12 例的 flat 输入（`input_preview.json`）逐字节一致；
  - 时间 amount/unit、task goal 不进入文本；
  - 计划顺序即输出顺序；
  - 上述 fail-closed 分支。
- 回归结果归档：`artifacts/world-components/n4-input-renderer-r1.json`。

运行：

```text
python -X utf8 experiments/world-components/n4_input_renderer/test_renderer.py
python -X utf8 experiments/world-components/n4_narrative_dev/test_pipeline_narrative.py
```

## 7. 已知缺口（不假装完成）

1. **未训练 N5**：12 例是已审开发集；新契约输入 251–347 tokens，旧 v2 模型 160/96 不够。
2. **风/光/氛围未进文本**：N4.1 已采集 `wind/light/atmosphere`，N4.2 当前只渲染 weather/time；是否加入属于输入契约变更，需新回归。
3. **随身物品重复**：同一物品同时出现在“随身”和“可见物”；v0 为保持已审预览字节不变未改。
4. **resultText 契约未落地**：`WorldState.Task` 仍无 `resultText`，生产端到端依赖 B/server 加字段；当前 N1 只在组件 fixture 验证。
5. **未接 B**：页面、控制器、真实整链仍用旧叙事门与旧 v2 输入；N4 不改变 B 的现有验收范围。
6. **旧 renderer 文件保留**：`n4_narrative_dev/render_narrative.py` 与 `build_scene_context.py` 已改为兼容 shim；实验文件名不重命名，避免破坏历史链接与证据身份。

## 8. 下一步

1. N5 训练使用 N4 输出作为唯一输入，`max_input≥384`、`max_output≥128`。
2. 先扩样并冻结新留出，再训练；N5 质量门与 N6 判据另行预登记。
3. 若要修“随身物品重复”或加入风/光/氛围，先提 `N4_VERSION` 并重建 12 例预览基线，不在训练中途静默改输入。
