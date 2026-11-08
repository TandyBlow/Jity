# 独立验收集登记 v2（已登记，未运行）

> 状态：登记完成，**没有运行任何模型**，也没有生成或查看 u240 在这些单元上的输出。
> 单元数：17；其中事实值由人工撰写（authored）的 11 条，其余直接取自世界字段。
> 世界文件：`experiments/world-components/n4_narrative_dev/world.json`（`worldId=w_fog_harbor`，sha256 `f096f5bdb7539f5b…`）
> 判定标准：`comparison-protocol-v3.md` §4 + `freeze/failure-taxonomy-v1.json` 七类；U 不算通过；类别可重叠、不相加。

| 单元 | 类别 | 事实 | 来源 | authored | 输入 sha256 | 重叠 | 重点 |
|---|---|---|---|---|---|---|---|
| ac01 | outcome | 韩渡 outcome 换好了塔顶的灯芯 | `world.json#tasks.task_lamp.resultText（主语由沈砚换成韩渡）` | 是 | `13953a2b945cbbc5…` | 独立 | 新增动作/状态 |
| ac02 | moved | 顾行舟 移动 雾堤→潮渡 dir=平 | `world.json#locations.loc_seawall, loc_ferry（同为 level1）` | 否 | `84abb79b13410796…` | 独立 | 新增动作/状态 |
| ac03 | appearance_changed | 油布包 appearance_changed 边角磨出了线头 | `world.json#items.item_oilcloth.appearance（边角磨白）+ authored 变化` | 是 | `8f4da8b71f968aa6…` | 独立 | 新增动作/状态 |
| po01 | outcome | 沈砚 outcome 把系泊绳拖回栈桥 | `world.json#items.item_rope.afterPosition=loc_ferry_pier` | 是 | `c1a89fa030152b21…` | 独立 | 位置（合法位置不得删减） |
| po02 | outcome | 阿棠 outcome 把鱼筐放在摊棚边 | `world.json#items.item_fishbasket.afterPosition=loc_market_stalls` | 否 | `979719dc945e0d30…` | 独立 | 位置（合法位置不得删减） |
| po03 | moved | 顾行舟 移动 潮生巷→潮汐档案馆 dir=平 | `world.json#locations.loc_archive, loc_alley` | 否 | `dd0a494e4b231b74…` | 独立 | 位置（过度断言风险） |
| di01 | moved | 韩渡 移动 潮渡→旧灯塔 dir=上 | `world.json#locations.loc_ferry(level1) -> loc_lighthouse(level3)` | 否 | `6bdae4318ee52f69…` | 独立 | 方向 |
| di02 | moved | 韩渡 移动 旧灯塔→潮渡 dir=下 | `world.json#locations.loc_lighthouse(level3) -> loc_ferry(level1)` | 否 | `46a800894239f8d5…` | 独立 | 方向 |
| di03 | moved | 韩渡 移动 潮生巷→早市 dir=平 | `world.json#locations.loc_alley -> loc_market（同为 level1）` | 否 | `0e55976753657d35…` | 独立 | 方向 |
| su01 | outcome | 韩渡 outcome 把被风吹歪的警示灯扶正 | `world.json#tasks.task_warnlamp.resultText，改用韩渡为主语` | 是 | `55bdf876f50f2803…` | 独立 | 主体归属 |
| su02 | appearance_changed | 阿棠 appearance_changed 围裙上刮破了口子 | `world.json#characters.char_atang.appearance（围裙上有鱼鳞）+ authored 变化` | 是 | `c8e2de023dff299b…` | 独立 | 主体归属 |
| sa01 | sanity_changed | 沈砚 状态 12→7 | `authored（cf24 只有 12→9；此处换数值）` | 是 | `bd60f0e3cb39a8ce…` | 独立 | 理智描述（输入不含数值） |
| sa02 | sanity_changed | 韩渡 状态 15→11 | `authored（新主体与新数值）` | 是 | `c015c632e634c1c2…` | 独立 | 理智描述（输入不含数值） |
| rp01 | appearance_changed | 铜灯罩 appearance_changed 玻璃上蒙了一层水汽 | `world.json#items.item_lamp_cover.appearance + authored 变化` | 是 | `56bc3c498c687529…` | 独立 | 复述 |
| rp02 | outcome | 叶知微 outcome 把灯罩擦到能照见人影 | `world.json#tasks.task_wipe.goal 改写 + authored 结果` | 是 | `ccac3dabbfc254ab…` | 独立 | 复述 |
| lg01 | appearance_changed | 排水沟 appearance_changed 沟底积了泥 | `world.json#items（潮生巷排水沟现象）+ authored 变化` | 是 | `b0d726daa052a45e…` | 独立 | 语病 |
| lg02 | appearance_changed | 铁链 appearance_changed 链环之间的缝里卡了沙 | `world.json#locations.loc_lighthouse_top（铁链）+ authored 变化` | 是 | `f6ea3f1fe779ee30…` | 独立 | 语病 |

## 输入渲染示例（ac01）

```
短句任务。
地点=旧灯塔>塔顶
地点可见=铜框信号灯、玻璃罩、火苗、海风直吹、备用灯芯
场景=夜；夜雾，海风；铜灯已点亮
视角=沈砚；第三人称
事实=韩渡｜结果｜换好了塔顶的灯芯
要求：写一句话，把事实写成场景里可见的动作或状态；句中出现事实主体的名字；只用地点可见里的物件与场景给的现象；需要表示高低时用方向给的字；不写任务标题、数值、具体时长、字段名；不新增人物、物品、地点。
短句：
```

## 限制

- same N4 world as training; independence is signature/input level, not a new world
- authored values are declared per unit and are not world-authoritative records
- world.json has no committed action log: all moved units are derived from location levels
- v1 registration (freeze/acceptance-registration-v1.json) is kept as the reviewed-before-fix record
- no u240 output exists for this set yet; registration only
- judging will again be assistant-only unless a human reviewer is added
