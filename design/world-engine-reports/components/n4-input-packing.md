# N4.0 叙事输入装配（N4 生成模型的程序子步骤）

日期：2026-11-02。分支：`world-components`。源码基线：`483259c`。状态：**结构化输入装配已实现并通过回归；N4 生成模型未训练、未接 B**。

## 编号

| 编号 | 组件 | 类型 |
| --- | --- | --- |
| N1 | 事实提取 | 程序 |
| N2 | 内容选择 | 模型/规则 |
| N3 | 组织表达（句组计划） | 程序/模型 |
| **N4.0** | **叙事输入装配（场景上下文＋结构化记录）** | **程序子步骤** |
| **N4** | **叙事生成（写正文）** | **模型** |
| **N5** | **事实核对** | **程序＋语义复核** |

N4.0 不是独立组件，也不写句子。它只把 N1/N2/N3 的结果和场景上下文打包成 N4 模型可读的结构化记录。上一条把 renderer 单列为 N4、把生成模型顺延到 N5 的安排作废；旧 N4/N5 的历史文档与证据编号恢复有效。

## 为什么改

旧输入是预先写好的事实句：

```text
1. 沈砚从潮生巷来到旧灯塔。
2. 沈砚换好了塔顶的灯芯。
3. 沈砚的呼吸比刚才顺了一些。
```

这种格式把“怎么起句、怎么连接、怎么省略”提前写死，模型只能重写，且输入模式高度重复。新契约改成记录：

```text
事实：
f0｜移动｜沈砚｜潮生巷→旧灯塔
f1｜结果｜沈砚｜换好了塔顶的灯芯
f2｜理智｜沈砚｜上升
分组：
G1｜f0 f1 f2
```

句子由 N4 模型自己写。N4.0 不再输出完整事实句，不再决定“从……来到……”“的呼吸……”这些措辞。

## 接口

源码：`experiments/world-components/n4_input_renderer/`

```python
N4_INPUT_VERSION = "n4-input-pack-v0.1"

# current N4 input contract
pack_narrative_input(case, plan, world, selected_fact_ids=None,
                     scene_diagnostics=None)
# -> {status: ok, input, diagnostics, version}
#  | {status: error, code, detail, diagnostics, version}

# N4.0a scene context from authoritative state
build_scene_context(state, perspective, selected_facts, environment=None)
# -> {status: ok|stopped, sceneContext?, worldView?, diagnostics}

# legacy sentence-row renderer (frozen v2/v3 models and byte regression only)
render_plan_input(case, plan, world, strict=True, selected_fact_ids=None)
render_input(case, world, strict=True)
```

`case` 形状与之前相同：`facts`、`sceneState`、`characterContext`、`perspective`；`world` 是地点/物品/人物名称与外貌的视图。

## 结构化输入格式

```text
叙事任务。
场景：
地点=旧灯塔>石阶>旋梯>塔顶
地点外貌=铜框信号灯、玻璃罩、火苗、海风直吹
天气=夜雾，海风
时段=夜
风=塔顶海风直吹
光=塔顶铜灯已点亮
氛围=风硬，铜灯罩嗡嗡响
人物：
沈砚｜性格=慢而细，习惯把话咽回去｜外貌=青灰长衫，袖口常沾墨｜随身=油布包、油纸伞、外袍
可见：
油布包=深褐色油布，边角磨白
备用灯芯=一小束浸过油的棉芯，用纸包着
铜灯罩=铜框玻璃罩，海风大时会嗡嗡响
事实：
f0｜移动｜沈砚｜潮生巷→旧灯塔
f1｜结果｜沈砚｜换好了塔顶的灯芯
f2｜理智｜沈砚｜上升
f3｜时间｜时间经过
分组：
G1｜f0 f1 f2 f3｜组后时间=过去了一会儿
视角：沈砚；第三人称限知；只写沈砚的内心，他人只写可见动作。
要求：写场景、行动与视角人物心理；不写任务标题、数值面板、具体时长、字段名；不新增未列出的具名人物/物品/地点；他人只写可见动作。
正文：
```

记录规则：

| kind | 记录 | 说明 |
| --- | --- | --- |
| `moved` | `name｜from→to` | 不写“从……来到……” |
| `outcome` | `name｜resultText` | 不写任务 goal |
| `sanity_changed` | `name｜上升/下降/不变` | 数值只用于判方向，不打印 |
| `appearance_changed` | `name｜text` | N1 的可见细节原文 |
| `personality_changed` | `name｜text` | 行为倾向原文 |
| `no_change` | `—` | 合法无变化 |
| `time` | `时间经过` | amount/unit 不进入输入 |

N3 的句组只以 `G1｜f0 f1 f2` 形式出现；组后时间用 `组后时间=过去了一会儿` 标出。N4.0 不重排、不改写、不新增事实。

## 输入来源

| 输入 | 来源 |
| --- | --- |
| `facts` | N1 `extract_facts(point, before, narrative_outcome=True)`，来自按 pointId 读取的已提交状态与原始 Δ |
| `selected_fact_ids` | N2 `classify_facts(..., may_policy="select", visible_other_actions=True)` |
| `plan` | N3 `plan_v3(..., cross_group_guard=True)`＋`check_plan_v3` |
| 地点链/外貌 | 权威 `state.locations` 初值＋生效 `appearanceChanges` |
| 人物性格/外貌/随身 | `state.characters` 初值＋生效变化；物品 `position.containerId` |
| 可见物 | 容器为当前地点或在场人物的物品 |
| 天气/时段/风/光/氛围 | 显式 `environment` overlay；缺失即省略并记诊断 |
| 视角 | N2 `resolve_perspective` |

`present` 仍只含视角主体＋携带已选事实的实体，不做全员扫描。

## Fail-closed

`pack_narrative_input` 在以下情况返回 `status=error`，不输出部分文本：

| code | 条件 |
| --- | --- |
| `plan-shape-invalid` / `facts-shape-invalid` | plan/facts 形状错误 |
| `plan-refusal` | N3 计划是拒绝结果 |
| `plan-unknown-fact` / `duplicate-fact` / `selected-unknown-fact` | 引用不存在或重复 |
| `plan-coverage-mismatch` | 计划的非时间事实集合 ≠ 已选非时间事实集合 |
| `unsupported-fact-kind` | 未知 kind |
| `outcome-result-missing` | outcome 缺 resultText；不回退 goal |
| `missing-field` | 模板所需字段缺失 |
| `world-location-missing` / `world-item-missing` / `world-character-missing` | id 无法解析 |
| `character-*-missing` / `character-inventory-invalid` | 人物上下文缺字段 |
| `scene-state-invalid` / `scene-location-path-missing` | 场景形状错误 |
| `perspective-unresolved` | 视角主体无法解析 |

缺失 environment 字段不是错误：省略该行并记录诊断。

## 回归与证据

运行：

```text
python -X utf8 experiments/world-components/n4_input_renderer/test_packer.py
python -X utf8 experiments/world-components/n4_input_renderer/test_renderer.py
python -X utf8 experiments/world-components/n4_narrative_dev/test_pipeline_narrative.py
```

- `test_packer.py`：已审 12 例全部 pack ok；计划 factId/组全覆盖；无旧事实句；无 task goal；无具体时长；两次运行逐字节一致；fail-closed 分支。
- `test_renderer.py`：旧句子格式的 12+12 字节回归，仅证明 legacy 路径未被破坏。
- `test_pipeline_narrative.py`：N1→N2→N3→N4.0 结构化输入；同时保留 legacy 句子臂对照。

结构化输入真实 tokenizer 统计：**299–402** tokens（12 例），目标 75–99。旧 v2 模型 `max_input=160` 不适用；N4 新训练建议 `max_input=512`、`max_output=128`。预览见 [N4.0 结构化输入预览](n4-narrative-input-packing-preview.md)，证据见 `artifacts/world-components/n4-input-packing-r1.json`。

## 已知缺口

1. **N4 生成模型未训练**：现有 v2/v3 模型只认旧句子格式；结构化输入需要新语料与训练。
2. **resultText 来源未接线**：协议落点是 `FrozenGroupView.members[].resultText`（C4 已确认组员结果），当前 N1 读的是 fixture 的 `Task.resultText`，而 `WorldState.Task` 没有该字段。
3. **12 例是开发集**，不是训练集/留出集；训练前需扩样、冻结与预登记。
4. **未接 B**：页面、控制器、真实整链仍用旧叙事门与旧 v2 输入。
5. **随身物品重复**：同一物品同时出现在“随身”和“可见物”；v0 未改，避免破坏旧预览。
6. **旧句子 renderer 保留**：`renderer.py` 继续服务冻结 v2/v3 模型与字节回归，不是新 N4 输入契约。

## 下一步

1. 用 N4.0 输出重建训练/开发语料，扩样并冻结新留出。
2. 训练 N4 生成模型（Randeng-T5-77M 起步，`max_input=512`、`max_output=128`），目标直接写场景/行动/视角心理。
3. 预登记 N4 质量门与 N5 核对判据；不得复用旧 v2 的句子模板门。
4. 质量通过后再做浏览器适配与 B 侧接线。
