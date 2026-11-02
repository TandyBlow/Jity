# N4 叙事开发语料 v0（待审）

日期：2026-11-02。目标：N4 不再逐条复述状态，而是在**已提交事实**的约束下写场景、行为与视角人物心理。

这是一份 **12 例审阅稿**，不是训练集，也不是留出集；世界族 `n4n-fog-harbor` 为本稿新写，不复用旧 C/B 行。`outcome` 类型与“用心理/行为表达理智变化”是**提议中的契约**，当前 N1/N5 尚未实现；先请审文字与边界，再改契约。

## 允许 / 禁止

| 允许 | 禁止 |
| --- | --- |
| 与地点/天气/道具 brief 一致的环境细节 | 新增具名人物、物品、地点 |
| 与事实一致的动作、表情、姿态 | 新增会改变世界状态的事件/任务/目标 |
| 视角人物（沈砚）的心理 | 其他角色的内心（只能写可见行为） |
| 连接、节奏、感官细节 | 任务标题/quest log 措辞；理智/外貌/个性/位置的数值面板 |
| 未具名的通用道具（brief 列出） | 产生承诺的具体对话 |

任务 `goal` 只作隐藏动机，不能出现在正文；表面只写 `resultText`。理智变化用心理/生理反应表达，不打印数值。外貌/个性变化用可见细节与行为表达，不打印字段名。

本稿把每个具体名词都绑定到世界状态/场景状态/物品表；身体部位（手、肩、后背等）属于人物自身，不再单列；比喻（如“金箔”）标注为 `narrative.simile`，不作世界事实。场景可覆盖物品位置（`itemOverrides`），默认位置见物品表。

## 世界

### 地点

- **潮生巷**（loc_alley）：沿河窄巷，石板常年潮湿，墙上挂纸灯笼，排水沟有水声；窄巷挡风，夜里灯笼光落在水洼里。
  - 小地点：巷子（level 1，湿石板、纸灯笼、排水沟、墙根、水洼）；沈砚的屋子（level 1，木桌、抽屉、床沿、蜡烛；窗外雨声）
  - 特征：石板, 纸灯笼, 排水沟, 墙根, 水洼；风：低（窄巷挡风）
- **旧灯塔**（loc_lighthouse）：白色石塔，外壁盐蚀；海雾天塔身只剩轮廓。石阶从巷侧通向旋梯，再上塔顶；塔顶有铜框信号灯，海风大时灯罩嗡嗡响。
  - 小地点：石阶（level 1，湿滑石阶，靠海一侧有铁链）；旋梯（level 2，狭窄旋梯，铜框窗，擦铜油味）；塔顶（level 3，铜框信号灯、玻璃罩、火苗、海风直吹）
  - 特征：石阶, 旋梯, 塔顶, 铜灯罩, 铁链；风：高（塔顶海风直吹）
- **潮渡**（loc_ferry）：河海交界的木栈桥，木桩缠旧缆绳，雾天只见船灯；桥边石阶通向退潮后的浅滩。
  - 小地点：栈桥（level 1，木桩、缆绳、船灯、水面）；石阶（level 1，湿滑石阶，通向浅滩）；浅滩（level 1，退潮后的泥滩、系泊绳、冷光）
  - 特征：木桩, 缆绳, 船灯, 水面, 浅滩, 石阶；风：中（河口风）
- **潮汐档案馆**（loc_archive）：低矮砖房，天窗漏雨，屋里有纸、墨和铜灯的气味；长桌靠窗，门槛磨得发亮。
  - 小地点：长桌（level 1，摊开的潮汐簿、墨、干纸、铜灯、笔）
  - 特征：天窗, 长桌, 门槛, 铜灯, 潮汐簿, 干纸, 墨, 笔尖；风：无（室内）
- **雾堤**（loc_seawall）：港口外侧石堤，浪大时白沫翻上堤面；堤上有石阶、铁链、钟架、雾警钟和警示灯。
  - 小地点：堤面（level 1，石壁、钟架、钟绳、警示灯、铁皮、白沫）
  - 特征：石阶, 铁链, 钟架, 钟绳, 雾警钟, 警示灯, 铁皮, 石壁；风：高（迎海风）
- **早市**（loc_market）：潮生巷尽头的鱼市，帆布棚、蒸汽、鱼鳞、泥水；人流拥挤，白汽不散。
  - 小地点：摊棚（level 1，帆布棚、鱼筐、案板、石板、银鳞鱼、白汽）
  - 特征：帆布棚, 鱼筐, 案板, 石板, 银鳞鱼, 白汽, 人流；风：低（棚下）

### 物品

- **油布包**（item_oilcloth）：深褐色油布，边角磨白；position={"holderId": "char_shen"}
- **备用灯芯**（item_wick）：一小束浸过油的棉芯，用纸包着；position={"containerId": "loc_lighthouse_top"}；after={"containerId": "item_lamp_cover"}；state={"burning": true, "ash": "一小截黑灰"}
- **铜灯罩**（item_lamp_cover）：铜框玻璃罩，海风大时会嗡嗡响；position={"containerId": "loc_lighthouse_top"}；state={"lit": true}
- **系泊绳**（item_rope）：粗麻绳，沾满泥和盐；position={"containerId": "loc_ferry_shoal"}；after={"containerId": "loc_ferry_pier"}
- **缆绳**（item_mooring_rope）：旧麻缆绳，末端起毛；position={"containerId": "loc_ferry_pier"}
- **备用钥匙**（item_key）：黄铜钥匙，齿口磨圆；position={"containerId": "loc_alley_room"}；after={"holderId": "char_shen"}
- **潮汐簿**（item_tidebook）：厚纸簿，缺一页，边缘毛糙，页边有旧墨迹；position={"containerId": "loc_archive_desk"}
- **干纸**（item_paper）：一叠裁好的干纸；position={"holderId": "char_atang"}；after={"containerId": "loc_archive_desk"}
- **墨**（item_ink）：半砚旧墨，墨色发乌；position={"containerId": "loc_archive_desk"}
- **笔**（item_brush）：细杆毛笔，笔尖开叉；position={"containerId": "loc_archive_desk"}
- **铜灯**（item_archive_lamp）：铜座台灯，灯罩发暗；position={"containerId": "loc_archive_desk"}；state={"lit": true}
- **灯芯**（item_archive_wick）：烧出一小截黑灰的灯芯；position={"containerId": "loc_archive_desk"}；state={"ash": "一小截黑灰"}
- **冷茶**（item_tea）：凉透的茶，杯口凝着水汽；position={"containerId": "loc_archive_desk"}
- **蜡烛**（item_candle）：半截白蜡，火苗很小；position={"containerId": "loc_alley_room"}；state={"lit": true}
- **旧纸**（item_oldpaper）：压抽屉底的一层旧纸；position={"containerId": "loc_alley_room"}
- **油纸伞**（item_umbrella）：旧油纸伞，伞骨有一根修过；position={"holderId": "char_shen"}
- **外袍**（item_coat）：青灰外袍，下摆容易沾泥水；position={"holderId": "char_shen"}
- **渡船**（item_ferry）：旧木船，船头挂一盏船灯；position={"containerId": "loc_ferry_pier"}
- **船灯**（item_boat_light）：黄铜船灯，雾里只剩一团黄；position={"containerId": "item_ferry"}
- **抹布**（item_rag）：沾了擦铜油的软布；position={"containerId": "loc_lighthouse_spiral"}
- **擦铜油**（item_copper_oil）：小罐铜油，气味刺鼻；position={"containerId": "loc_lighthouse_spiral"}
- **油壶**（item_oilcan）：长嘴油壶，壶口有油痕；position={"containerId": "loc_lighthouse_spiral"}
- **银鳞鱼**（item_fish）：一筐银鳞鱼，鱼尾还在拍；position={"containerId": "item_fishbasket"}；after={"containerId": "loc_market_stalls"}
- **鱼筐**（item_fishbasket）：竹编鱼筐，边沿沾着鱼鳞；position={"holderId": "char_atang"}；after={"containerId": "loc_market_stalls"}
- **雾警钟**（item_bell）：青铜雾警钟，钟架被海盐蚀出白斑；position={"containerId": "loc_seawall_top"}
- **钟绳**（item_bell_rope）：粗麻钟绳，末端磨得起毛；position={"containerId": "loc_seawall_top"}
- **警示灯**（item_warning_lamp）：铁皮警示灯，玻璃罩被风吹得发晃；position={"containerId": "loc_seawall_top"}；state={"lit": true}

### 人物

- **沈砚**（char_shen）：青灰长衫，袖口常沾墨；随身带油布包；性格：慢而细，习惯把话咽回去；inventory=item_oilcloth, item_umbrella, item_coat
- **顾行舟**（char_gu）：旧短褂，手上有缆绳磨出的茧；性格：话少；inventory=item_mooring_rope
- **叶知微**（char_ye）：深蓝工作服，袖口有擦铜油；性格：干脆，眼睛很亮；inventory=item_rag, item_copper_oil, item_oilcan
- **阿棠**（char_atang）：十七岁，辫子，围裙上有鱼鳞；性格：手脚快，爱看热闹；inventory=item_paper, item_fishbasket
- **韩渡**（char_han）：旧呢外套，眉毛被雾打湿；性格：脾气硬，对雾天的规矩极认真；inventory=无

### 任务（隐藏动机，不可打印）

- `task_lamp`：把备用灯芯送到塔顶（owner char_shen；surface resultText=“换好了塔顶的灯芯”）
- `task_rope`：找回被潮水冲走的系泊绳（owner char_shen；surface resultText=“把系泊绳从浅滩拖了回来”）
- `task_log`：补全潮汐簿缺页（owner char_shen；surface resultText=“把潮汐簿缺的那页补全了”）
- `task_key`：找到档案库的备用钥匙（owner char_shen；surface resultText=“从抽屉底层翻出了备用钥匙”）
- `task_bell`：把雾警钟敲响（owner char_shen；surface resultText=“敲响了雾堤上的雾警钟”）
- `task_warnlamp`：把堤边的警示灯扶正（owner char_shen；surface resultText=“把被风吹歪的警示灯扶正”）
- `task_paper`：把干纸送到档案馆（owner char_atang；surface resultText=“把一叠干纸放在桌角”）
- `task_fish`：把银鳞鱼搬到案板上（owner char_atang；surface resultText=“把一筐银鳞鱼搬上案板”）
- `task_wipe`：把灯塔的灯罩擦干净（owner char_ye；surface resultText=“把灯罩擦得透亮”）
- `task_bell_rope`：把雾警钟的绳子系紧（owner char_han；surface resultText=“把松脱的钟绳重新系紧”）
- `task_wait`：在潮渡等到最后一班船（owner char_shen；surface resultText=“在潮渡等到了最后一班船”）

## 审阅方式

每例检查：事实是否全覆盖；有无任务标题；有无新增具名实体/物品/地点；有无他人内心；有无新增世界事件；场景/行为/心理是否自然；视角是否一致；有无数值面板。结论写回 `review-checklist.json`。

## n4n-01 · 塔顶的灯芯

**Facts**

| factId | kind | 主体 | 内容 |
| --- | --- | --- | --- |
| f0 | moved | 沈砚 | 潮生巷 → 旧灯塔（at 旧灯塔） |
| f1 | outcome | 沈砚 | surface=“换好了塔顶的灯芯”；hidden goal=“把备用灯芯送到塔顶”（task_lamp） |
| f2 | sanity_changed | 沈砚 | 10 → 12（内部数值，叙事不打印） |
| f3 | time | - | 8 minute |

**Scene state**

- 地点路径：旧灯塔 → 石阶 → 旋梯 → 塔顶
- 时间：夜；天气：夜雾，海风；风：塔顶海风直吹；光：塔顶铜灯已点亮
- 在场：沈砚；可见物品：油布包, 备用灯芯, 铜灯罩
- 氛围：风硬，铜灯罩嗡嗡响
- 场景物品覆盖：无
- 隐藏动机：task_lamp

**Grounding（每个具体名词 → 状态）**

| 细节 | 状态来源 | 值 |
| --- | --- | --- |
| 雾 | scene.weather | 夜雾 |
| 石阶 | loc_lighthouse.sublocations[0] | 石阶（level 1） |
| 油布包 | item_oilcloth | holder=沈砚 |
| 旧灯塔 | loc_lighthouse | 白色石塔，外壁盐蚀 |
| 一层一层 | loc_lighthouse.levels | 1 石阶 → 2 旋梯 → 3 塔顶 |
| 塔顶 | loc_lighthouse.sublocations[2] | 塔顶（level 3） |
| 巷子里 | loc_alley | 窄巷，windExposure=低 |
| 铜灯罩 | item_lamp_cover | container=塔顶；appearance=铜框玻璃罩，海风大时会嗡嗡响 |
| 备用灯芯 | item_wick | container=塔顶；after=铜灯罩 |
| 火苗 | item_lamp_cover.state.lit | true |
| 八分钟 | fact f3 | 8 minute |

**Narrative**

> 雾从石阶底下漫上来，沈砚把油布包往怀里按了按，一层一层登上旧灯塔。塔顶的风比巷子里硬，吹得铜灯罩嗡嗡作响；他换好备用灯芯，火苗重新站稳，胸口那口一直提着的气才慢慢落回去。前后不过八分钟，他却像在黑暗里走了很久。

**Annotations**

| 文本 | covers | 允许的展开 |
| --- | --- | --- |
| 雾从石阶底下漫上来，沈砚把油布包往怀里按了按，一层一层登上旧灯塔。 | f0 | weather, sensory, gesture |
| 塔顶的风比巷子里硬，吹得铜灯罩嗡嗡作响；他换好备用灯芯，火苗重新站稳，胸口那口一直提着的气才慢慢落回去。 | f1, f2 | sensory, interiority |
| 前后不过八分钟，他却像在黑暗里走了很久。 | f3 | time, interiority |

**Review**

- [ ] 事实全覆盖
- [ ] 无任务标题/quest 措辞
- [ ] 无新增具名实体/物品/地点
- [ ] 无他人内心（仅可见行为）
- [ ] 无新增世界事件/承诺性对话
- [ ] 场景/行为/心理自然
- [ ] 视角一致
- [ ] 无理智/外貌/个性/位置数值面板
- [ ] 每个具体名词都有状态依据（Grounding 表）

## n4n-02 · 浅滩上的系泊绳

**Facts**

| factId | kind | 主体 | 内容 |
| --- | --- | --- | --- |
| f0 | moved | 沈砚 | 旧灯塔 → 潮渡（at 潮渡） |
| f1 | outcome | 沈砚 | surface=“把系泊绳从浅滩拖了回来”；hidden goal=“找回被潮水冲走的系泊绳”（task_rope） |
| f2 | appearance_changed | 沈砚 | 内部文本=“外袍下摆结了一层盐霜”；叙事用可见细节 |
| f3 | time | - | 12 minute |

**Scene state**

- 地点路径：潮渡 → 石阶 → 浅滩
- 时间：黎明；天气：低潮，海风，湿冷；风：河口风；光：天刚亮；水：黑水
- 在场：沈砚；可见物品：系泊绳, 外袍
- 氛围：黑水退去，泥滩反着冷光
- 场景物品覆盖：无
- 隐藏动机：task_rope

**Grounding（每个具体名词 → 状态）**

| 细节 | 状态来源 | 值 |
| --- | --- | --- |
| 天刚亮 | scene.time | 黎明 |
| 潮渡 | loc_ferry | 河海交界的木栈桥 |
| 黑水 | scene.water | 黑水 |
| 木桩 | loc_ferry.features | 木桩 |
| 浅滩 | loc_ferry.sublocations[2] | 浅滩 |
| 石阶 | loc_ferry.sublocations[1] | 石阶 |
| 系泊绳 | item_rope | container=浅滩 |
| 泥 | loc_ferry.sublocations[2].appearance | 泥滩 |
| 外袍 | item_coat | holder=沈砚 |
| 盐霜 | fact f2 | 外袍下摆结了一层盐霜 |
| 海风 | scene.weather | 海风 |
| 十二分钟 | fact f3 | 12 minute |

**Narrative**

> 天刚亮，潮渡的黑水退到木桩以下，露出一截被潮水舔白的浅滩。沈砚踩着湿滑的石阶下去，把陷在泥里的系泊绳一寸一寸拖回岸上；等他直起腰，外袍下摆已经结了一层白花花的盐霜。十二分钟，海风把他的手指吹得发僵，绳子却总算回到了木桩边。

**Annotations**

| 文本 | covers | 允许的展开 |
| --- | --- | --- |
| 天刚亮，潮渡的黑水退到木桩以下，露出一截被潮水舔白的浅滩。 | — | scene, weather, sensory |
| 沈砚踩着湿滑的石阶下去，把陷在泥里的系泊绳一寸一寸拖回岸上；等他直起腰，外袍下摆已经结了一层白花花的盐霜。 | f0, f1, f2 | behavior, sensory, visual |
| 十二分钟，海风把他的手指吹得发僵，绳子却总算回到了木桩边。 | f3 | time, sensory |

**Review**

- [ ] 事实全覆盖
- [ ] 无任务标题/quest 措辞
- [ ] 无新增具名实体/物品/地点
- [ ] 无他人内心（仅可见行为）
- [ ] 无新增世界事件/承诺性对话
- [ ] 场景/行为/心理自然
- [ ] 视角一致
- [ ] 无理智/外貌/个性/位置数值面板
- [ ] 每个具体名词都有状态依据（Grounding 表）

## n4n-03 · 雾里的渡船

**Facts**

| factId | kind | 主体 | 内容 |
| --- | --- | --- | --- |
| f0 | moved | 沈砚 | 潮生巷 → 潮渡（at 潮渡） |
| f1 | moved | 顾行舟 | 河心 → 潮渡（at 潮渡） |
| f2 | time | - | 6 minute |

**Scene state**

- 地点路径：潮渡 → 栈桥
- 时间：黄昏；天气：雾，河面低；风：河口风；光：船灯
- 在场：沈砚, 顾行舟；可见物品：渡船, 船灯, 缆绳
- 氛围：雾压低河面，船灯只剩一团黄
- 场景物品覆盖：无
- 隐藏动机：task_wait

**Grounding（每个具体名词 → 状态）**

| 细节 | 状态来源 | 值 |
| --- | --- | --- |
| 雾 | scene.weather | 雾 |
| 潮渡 | loc_ferry | 木栈桥 |
| 木桩 | loc_ferry.features | 木桩 |
| 石阶 | loc_ferry.sublocations[1] | 石阶 |
| 船灯 | item_boat_light | container=渡船 |
| 顾行舟 | char_gu | 渡口老船夫 |
| 渡船 | item_ferry | container=栈桥 |
| 缆绳 | item_mooring_rope | container=栈桥 |
| 水面 | loc_ferry.sublocations[0].appearance | 水面 |
| 六分钟 | fact f2 | 6 minute |

**Narrative**

> 雾把河面压得很低，潮渡的木桩只剩一截影子。沈砚在石阶尽头站了一会儿，才听见船灯从雾里透出来；顾行舟把渡船靠上木桩，缆绳在他手里绕了两圈，船身轻轻一磕，水面上的灯影就碎了。六分钟，雾没有散，船总算到了。

**Annotations**

| 文本 | covers | 允许的展开 |
| --- | --- | --- |
| 雾把河面压得很低，潮渡的木桩只剩一截影子。 | — | weather, scene |
| 沈砚在石阶尽头站了一会儿，才听见船灯从雾里透出来； | f0 | behavior, sensory |
| 顾行舟把渡船靠上木桩，缆绳在他手里绕了两圈，船身轻轻一磕，水面上的灯影就碎了。 | f1 | behavior, sensory |
| 六分钟，雾没有散，船总算到了。 | f2 | time, weather |

**Review**

- [ ] 事实全覆盖
- [ ] 无任务标题/quest 措辞
- [ ] 无新增具名实体/物品/地点
- [ ] 无他人内心（仅可见行为）
- [ ] 无新增世界事件/承诺性对话
- [ ] 场景/行为/心理自然
- [ ] 视角一致
- [ ] 无理智/外貌/个性/位置数值面板
- [ ] 每个具体名词都有状态依据（Grounding 表）

## n4n-04 · 潮汐簿的缺页

**Facts**

| factId | kind | 主体 | 内容 |
| --- | --- | --- | --- |
| f0 | outcome | 沈砚 | surface=“把潮汐簿缺的那页补全了”；hidden goal=“补全潮汐簿缺页”（task_log） |
| f1 | time | - | 20 minute |
| f2 | moved | 阿棠 | 早市 → 潮汐档案馆（at 潮汐档案馆） |
| f3 | outcome | 阿棠 | surface=“把一叠干纸放在桌角”；hidden goal=“把干纸送到档案馆”（task_paper） |

**Scene state**

- 地点路径：潮汐档案馆 → 长桌
- 时间：午后；天气：雨；风：无（室内）；光：铜灯
- 在场：沈砚, 阿棠；可见物品：潮汐簿, 干纸, 墨, 笔, 铜灯
- 氛围：雨点敲天窗，屋里只有笔尖和雨声
- 场景物品覆盖：无
- 隐藏动机：task_log, task_paper

**Grounding（每个具体名词 → 状态）**

| 细节 | 状态来源 | 值 |
| --- | --- | --- |
| 雨 | scene.weather | 雨 |
| 档案馆 | loc_archive | 低矮砖房 |
| 天窗 | loc_archive.features | 天窗 |
| 潮汐簿 | item_tidebook | container=长桌 |
| 灯 | item_archive_lamp | container=长桌；lit=true |
| 旧墨迹 | item_tidebook.appearance | 旧墨迹/缺页 |
| 阿棠 | char_atang | 早市学徒 |
| 干纸 | item_paper | holder=阿棠 → 长桌 |
| 桌角 | loc_archive.sublocations[0] | 长桌 |
| 门槛 | loc_archive.features | 门槛 |
| 二十分钟 | fact f1 | 20 minute |

**Narrative**

> 雨点密密地敲着档案馆的天窗，沈砚把潮汐簿摊在灯下，缺页的边缘毛糙得像被咬过。他照着旧墨迹补完最后一个字，阿棠正好推门进来，把一叠干纸放在桌角，鞋底在门槛上蹭了两下。二十分钟，屋里只有笔尖和雨声，纸页终于接上了。

**Annotations**

| 文本 | covers | 允许的展开 |
| --- | --- | --- |
| 雨点密密地敲着档案馆的天窗，沈砚把潮汐簿摊在灯下，缺页的边缘毛糙得像被咬过。 | — | weather, scene, sensory |
| 他照着旧墨迹补完最后一个字， | f0 | behavior |
| 阿棠正好推门进来，把一叠干纸放在桌角，鞋底在门槛上蹭了两下。 | f2, f3 | behavior |
| 二十分钟，屋里只有笔尖和雨声，纸页终于接上了。 | f1 | time, sensory |

**Review**

- [ ] 事实全覆盖
- [ ] 无任务标题/quest 措辞
- [ ] 无新增具名实体/物品/地点
- [ ] 无他人内心（仅可见行为）
- [ ] 无新增世界事件/承诺性对话
- [ ] 场景/行为/心理自然
- [ ] 视角一致
- [ ] 无理智/外貌/个性/位置数值面板
- [ ] 每个具体名词都有状态依据（Grounding 表）

## n4n-05 · 雾堤上的钟

**Facts**

| factId | kind | 主体 | 内容 |
| --- | --- | --- | --- |
| f0 | moved | 沈砚 | 潮汐档案馆 → 雾堤（at 雾堤） |
| f1 | outcome | 沈砚 | surface=“敲响了雾堤上的雾警钟”；hidden goal=“把雾警钟敲响”（task_bell） |
| f2 | sanity_changed | 沈砚 | 12 → 9（内部数值，叙事不打印） |
| f3 | time | - | 4 minute |

**Scene state**

- 地点路径：雾堤 → 堤面
- 时间：夜；天气：大雾，浪高；风：迎海风；光：无（雾中）
- 在场：沈砚；可见物品：雾警钟, 钟绳
- 氛围：浪头撞石壁，白沫翻上堤面
- 场景物品覆盖：无
- 隐藏动机：task_bell

**Grounding（每个具体名词 → 状态）**

| 细节 | 状态来源 | 值 |
| --- | --- | --- |
| 雾堤 | loc_seawall | 港口外侧石堤 |
| 石阶 | loc_seawall.features | 石阶 |
| 浪花 | scene.weather | 浪高 |
| 铁链 | loc_seawall.features | 铁链 |
| 钟绳 | item_bell_rope | container=堤面 |
| 雾警钟 | item_bell | container=堤面 |
| 钟声 | item_bell | 雾警钟的声音 |
| 海风 | scene.wind | 迎海风 |
| 雾 | scene.weather | 大雾 |
| 四分钟 | fact f3 | 4 minute |
| 冷汗 | char_shen.body | 后背冷汗（心理/生理反应） |

**Narrative**

> 雾堤上的石阶被浪花打湿，沈砚摸着冰冷的铁链往上走，鞋底几次打滑。他抓住钟绳，把雾警钟一下一下敲响；钟声撞进雾里，又被海风撕碎。四分钟，他的后背全是冷汗，手指抖得几乎握不住绳子——直到钟声散尽，他才发觉自己一直屏着呼吸。

**Annotations**

| 文本 | covers | 允许的展开 |
| --- | --- | --- |
| 雾堤上的石阶被浪花打湿，沈砚摸着冰冷的铁链往上走，鞋底几次打滑。 | f0 | weather, scene, sensory, behavior |
| 他抓住钟绳，把雾警钟一下一下敲响；钟声撞进雾里，又被海风撕碎。 | f1 | behavior, sensory |
| 四分钟，他的后背全是冷汗，手指抖得几乎握不住绳子——直到钟声散尽，他才发觉自己一直屏着呼吸。 | f2, f3 | time, interiority |

**Review**

- [ ] 事实全覆盖
- [ ] 无任务标题/quest 措辞
- [ ] 无新增具名实体/物品/地点
- [ ] 无他人内心（仅可见行为）
- [ ] 无新增世界事件/承诺性对话
- [ ] 场景/行为/心理自然
- [ ] 视角一致
- [ ] 无理智/外貌/个性/位置数值面板
- [ ] 每个具体名词都有状态依据（Grounding 表）

## n4n-06 · 抽屉底层的钥匙

**Facts**

| factId | kind | 主体 | 内容 |
| --- | --- | --- | --- |
| f0 | moved | 沈砚 | 潮汐档案馆 → 潮生巷（at 潮生巷） |
| f1 | outcome | 沈砚 | surface=“从抽屉底层翻出了备用钥匙”；hidden goal=“找到档案库的备用钥匙”（task_key） |
| f2 | sanity_changed | 沈砚 | 9 → 11（内部数值，叙事不打印） |
| f3 | time | - | 3 minute |

**Scene state**

- 地点路径：潮生巷 → 沈砚的屋子
- 时间：夜；天气：雨；风：低（室内）；光：蜡烛
- 在场：沈砚；可见物品：备用钥匙, 蜡烛, 旧纸, 外袍
- 氛围：雨声不停，屋里只有一点烛光
- 场景物品覆盖：无
- 隐藏动机：task_key

**Grounding（每个具体名词 → 状态）**

| 细节 | 状态来源 | 值 |
| --- | --- | --- |
| 潮生巷 | loc_alley | 沿河窄巷 |
| 雨 | scene.weather | 雨 |
| 屋 | loc_alley.sublocations[1] | 沈砚的屋子 |
| 蜡烛 | item_candle | container=屋子；lit=true |
| 抽屉 | loc_alley_room.appearance | 抽屉 |
| 旧纸 | item_oldpaper | container=屋子 |
| 备用钥匙 | item_key | container=屋子；after=holder 沈砚 |
| 铜齿 | item_key.appearance | 黄铜钥匙，齿口磨圆 |
| 木板 | loc_alley_room.appearance | 抽屉/木板 |
| 床沿 | loc_alley_room.appearance | 床沿 |
| 桌角 | loc_alley_room.appearance | 木桌 |
| 三分钟 | fact f3 | 3 minute |
| 肩膀 | char_shen.body | 肩膀（生理反应） |

**Narrative**

> 潮生巷的雨还没停，沈砚摸黑进了屋，点亮桌角的蜡烛。抽屉最底层压着一层旧纸，他一张张掀开，终于摸到那把冰凉的备用钥匙；铜齿磕在木板上，发出很轻的一声。三分钟，他攥着钥匙坐到床沿，才发现肩膀一直绷得发酸。

**Annotations**

| 文本 | covers | 允许的展开 |
| --- | --- | --- |
| 潮生巷的雨还没停，沈砚摸黑进了屋，点亮桌角的蜡烛。 | f0 | weather, scene, behavior |
| 抽屉最底层压着一层旧纸，他一张张掀开，终于摸到那把冰凉的备用钥匙；铜齿磕在木板上，发出很轻的一声。 | f1 | behavior, sensory |
| 三分钟，他攥着钥匙坐到床沿，才发现肩膀一直绷得发酸。 | f2, f3 | time, interiority |

**Review**

- [ ] 事实全覆盖
- [ ] 无任务标题/quest 措辞
- [ ] 无新增具名实体/物品/地点
- [ ] 无他人内心（仅可见行为）
- [ ] 无新增世界事件/承诺性对话
- [ ] 场景/行为/心理自然
- [ ] 视角一致
- [ ] 无理智/外貌/个性/位置数值面板
- [ ] 每个具体名词都有状态依据（Grounding 表）

## n4n-07 · 档案馆的十五分钟

**Facts**

| factId | kind | 主体 | 内容 |
| --- | --- | --- | --- |
| f0 | no_change | - | scope=全局 |
| f1 | time | - | 15 minute |

**Scene state**

- 地点路径：潮汐档案馆 → 长桌
- 时间：夜；天气：雨渐匀；风：无（室内）；光：铜灯
- 在场：沈砚；可见物品：潮汐簿, 冷茶, 铜灯, 灯芯
- 氛围：雨声、灯芯、凉茶；没有脚步
- 场景物品覆盖：无
- 隐藏动机：无

**Grounding（每个具体名词 → 状态）**

| 细节 | 状态来源 | 值 |
| --- | --- | --- |
| 档案馆 | loc_archive | 低矮砖房 |
| 雨声 | scene.weather | 雨渐匀 |
| 灯芯 | item_archive_wick | container=长桌 |
| 黑灰 | item_archive_wick.state.ash | 一小截黑灰 |
| 潮汐簿 | item_tidebook | container=长桌 |
| 茶 | item_tea | container=长桌 |
| 水汽 | item_tea.appearance | 杯口凝着水汽 |
| 门 | loc_archive.features | 门槛/门 |
| 十五分钟 | fact f1 | 15 minute |

**Narrative**

> 档案馆的雨声渐渐匀了，灯芯烧出一小截黑灰。沈砚把潮汐簿合上，又翻开，指尖停在同一行字上；桌上的茶早就凉了，杯口凝着一圈水汽。十五分钟过去，门外没有脚步声，他也就没有起身。

**Annotations**

| 文本 | covers | 允许的展开 |
| --- | --- | --- |
| 档案馆的雨声渐渐匀了，灯芯烧出一小截黑灰。 | — | weather, scene |
| 沈砚把潮汐簿合上，又翻开，指尖停在同一行字上；桌上的茶早就凉了，杯口凝着一圈水汽。 | f0 | behavior, sensory |
| 十五分钟过去，门外没有脚步声，他也就没有起身。 | f0, f1 | time, interiority |

**Review**

- [ ] 事实全覆盖
- [ ] 无任务标题/quest 措辞
- [ ] 无新增具名实体/物品/地点
- [ ] 无他人内心（仅可见行为）
- [ ] 无新增世界事件/承诺性对话
- [ ] 场景/行为/心理自然
- [ ] 视角一致
- [ ] 无理智/外貌/个性/位置数值面板
- [ ] 每个具体名词都有状态依据（Grounding 表）

## n4n-08 · 早市的鱼鳞

**Facts**

| factId | kind | 主体 | 内容 |
| --- | --- | --- | --- |
| f0 | moved | 沈砚 | 潮生巷 → 早市（at 早市） |
| f1 | outcome | 阿棠 | surface=“把一筐银鳞鱼搬上案板”；hidden goal=“把银鳞鱼搬到案板上”（task_fish） |
| f2 | appearance_changed | 沈砚 | 内部文本=“衣摆沾了鱼鳞和泥水”；叙事用可见细节 |
| f3 | time | - | 5 minute |

**Scene state**

- 地点路径：早市 → 摊棚
- 时间：清晨；天气：潮湿，白汽；风：低（棚下）；光：棚下散光
- 在场：沈砚, 阿棠；可见物品：银鳞鱼, 鱼筐, 外袍
- 氛围：白汽、鱼鳞、泥水、人流
- 场景物品覆盖：无
- 隐藏动机：task_fish

**Grounding（每个具体名词 → 状态）**

| 细节 | 状态来源 | 值 |
| --- | --- | --- |
| 早市 | loc_market | 潮生巷尽头的鱼市 |
| 帆布棚 | loc_market.features | 帆布棚 |
| 白汽 | scene.weather | 白汽 |
| 鱼鳞 | loc_market.features | 鱼鳞 |
| 石板 | loc_market.features | 石板 |
| 人缝 | loc_market.atmosphere | 人流拥挤 |
| 阿棠 | char_atang | 早市学徒 |
| 银鳞鱼 | item_fish | container=鱼筐 |
| 鱼尾 | item_fish.appearance | 鱼尾还在拍 |
| 筐 | item_fishbasket | holder=阿棠 → 案板 |
| 案板 | loc_market.features | 案板 |
| 衣摆 | item_coat | holder=沈砚 |
| 泥水 | scene.atmosphere | 泥水 |
| 五分钟 | fact f3 | 5 minute |

**Narrative**

> 早市的帆布棚下全是白汽，鱼鳞在石板上闪成一片碎光。沈砚从人缝里挤过去，正看见阿棠抱着一筐银鳞鱼往案板上送，鱼尾拍得筐沿啪啪响；他往旁边让了一步，衣摆还是沾上了鱼鳞和泥水。五分钟，白汽还没有散，他低头看了一眼衣摆，又往前走了。

**Annotations**

| 文本 | covers | 允许的展开 |
| --- | --- | --- |
| 早市的帆布棚下全是白汽，鱼鳞在石板上闪成一片碎光。 | — | scene, sensory |
| 沈砚从人缝里挤过去，正看见阿棠抱着一筐银鳞鱼往案板上送，鱼尾拍得筐沿啪啪响；他往旁边让了一步，衣摆还是沾上了鱼鳞和泥水。 | f0, f1, f2 | behavior, sensory, visual |
| 五分钟，白汽还没有散，他低头看了一眼衣摆，又往前走了。 | f3 | time, behavior |

**Review**

- [ ] 事实全覆盖
- [ ] 无任务标题/quest 措辞
- [ ] 无新增具名实体/物品/地点
- [ ] 无他人内心（仅可见行为）
- [ ] 无新增世界事件/承诺性对话
- [ ] 场景/行为/心理自然
- [ ] 视角一致
- [ ] 无理智/外貌/个性/位置数值面板
- [ ] 每个具体名词都有状态依据（Grounding 表）

## n4n-09 · 灯塔上的那句话

**Facts**

| factId | kind | 主体 | 内容 |
| --- | --- | --- | --- |
| f0 | moved | 沈砚 | 潮渡 → 旧灯塔（at 旧灯塔） |
| f1 | personality_changed | 沈砚 | 内部文本=“不再把话咽回去”；叙事用行为表现 |
| f2 | outcome | 叶知微 | surface=“把灯罩擦得透亮”；hidden goal=“把灯塔的灯罩擦干净”（task_wipe） |
| f3 | time | - | 7 minute |

**Scene state**

- 地点路径：旧灯塔 → 旋梯
- 时间：傍晚；天气：海风；风：旋梯口海风；光：海光从窄窗照进来
- 在场：沈砚, 叶知微；可见物品：抹布, 擦铜油, 油壶, 铜灯罩
- 氛围：擦铜油味，铜框窗透进海光
- 场景物品覆盖：铜灯罩 → {"containerId": "loc_lighthouse_spiral"}
- 隐藏动机：task_wipe, task_lamp

**Grounding（每个具体名词 → 状态）**

| 细节 | 状态来源 | 值 |
| --- | --- | --- |
| 旧灯塔 | loc_lighthouse | 白色石塔 |
| 旋梯 | loc_lighthouse.sublocations[1] | 旋梯（level 2） |
| 擦铜油 | item_copper_oil | container=旋梯 |
| 叶知微 | char_ye | 守灯人 |
| 灯罩 | item_lamp_cover | scene override: container=旋梯 |
| 抹布 | item_rag | container=旋梯 |
| 铜框 | item_lamp_cover.appearance | 铜框玻璃罩 |
| 亮光 | item_lamp_cover.appearance | 铜框擦亮 |
| 沈砚 | char_shen | protagonist |
| 门口 | loc_lighthouse_spiral.appearance | 旋梯口/门口 |
| 灯芯 | item_wick | container=塔顶 |
| 七分钟 | fact f3 | 7 minute |

**Narrative**

> 旧灯塔的旋梯里有股擦铜油的味道。叶知微正踮着脚擦灯罩，抹布在铜框上转出一圈亮光；沈砚站在门口，本来想好的客气话到了嘴边，却没有像往常那样咽回去，而是直接问她灯芯还够不够用。七分钟，灯罩被擦得透亮，他的话也比平时多了一句。

**Annotations**

| 文本 | covers | 允许的展开 |
| --- | --- | --- |
| 旧灯塔的旋梯里有股擦铜油的味道。 | — | scene, sensory |
| 叶知微正踮着脚擦灯罩，抹布在铜框上转出一圈亮光； | f2 | behavior, sensory |
| 沈砚站在门口，本来想好的客气话到了嘴边，却没有像往常那样咽回去，而是直接问她灯芯还够不够用。 | f0, f1 | behavior |
| 七分钟，灯罩被擦得透亮，他的话也比平时多了一句。 | f1, f3 | time |

**Review**

- [ ] 事实全覆盖
- [ ] 无任务标题/quest 措辞
- [ ] 无新增具名实体/物品/地点
- [ ] 无他人内心（仅可见行为）
- [ ] 无新增世界事件/承诺性对话
- [ ] 场景/行为/心理自然
- [ ] 视角一致
- [ ] 无理智/外貌/个性/位置数值面板
- [ ] 每个具体名词都有状态依据（Grounding 表）

## n4n-10 · 雨里的潮生巷

**Facts**

| factId | kind | 主体 | 内容 |
| --- | --- | --- | --- |
| f0 | moved | 沈砚 | 旧灯塔 → 潮生巷（at 潮生巷） |
| f1 | sanity_changed | 沈砚 | 11 → 12（内部数值，叙事不打印） |
| f2 | time | - | 6 minute |

**Scene state**

- 地点路径：潮生巷 → 巷子
- 时间：夜；天气：雨渐小；风：低（窄巷）；光：纸灯笼
- 在场：沈砚；可见物品：油纸伞, 外袍
- 氛围：灯笼光落在湿石板上，巷子很静
- 场景物品覆盖：无
- 隐藏动机：无

**Grounding（每个具体名词 → 状态）**

| 细节 | 状态来源 | 值 |
| --- | --- | --- |
| 雨 | scene.weather | 雨渐小 |
| 潮生巷 | loc_alley | 沿河窄巷 |
| 纸灯笼 | loc_alley.features | 纸灯笼 |
| 湿石板 | loc_alley.features | 湿石板 |
| 金箔 | narrative.simile | 像一层薄薄的金箔（比喻，非状态事实） |
| 伞 | item_umbrella | holder=沈砚 |
| 墙根 | loc_alley.features | 墙根 |
| 水洼 | loc_alley.features | 水洼 |
| 六分钟 | fact f2 | 6 minute |
| 凉气 | scene.weather | 夜雨凉气 |

**Narrative**

> 雨势小了些，潮生巷的纸灯笼一盏接一盏亮着，光落在湿石板上，像一层薄薄的金箔。沈砚收了伞，沿着墙根慢慢往回走；鞋底踩过水洼，凉气从裤脚钻上来，他却觉得胸口比出门时松了一点。六分钟，巷子不长，他走得比平时慢。

**Annotations**

| 文本 | covers | 允许的展开 |
| --- | --- | --- |
| 雨势小了些，潮生巷的纸灯笼一盏接一盏亮着，光落在湿石板上，像一层薄薄的金箔。 | — | weather, scene, sensory |
| 沈砚收了伞，沿着墙根慢慢往回走；鞋底踩过水洼，凉气从裤脚钻上来，他却觉得胸口比出门时松了一点。 | f0, f1 | behavior, sensory, interiority |
| 六分钟，巷子不长，他走得比平时慢。 | f2 | time, behavior |

**Review**

- [ ] 事实全覆盖
- [ ] 无任务标题/quest 措辞
- [ ] 无新增具名实体/物品/地点
- [ ] 无他人内心（仅可见行为）
- [ ] 无新增世界事件/承诺性对话
- [ ] 场景/行为/心理自然
- [ ] 视角一致
- [ ] 无理智/外貌/个性/位置数值面板
- [ ] 每个具体名词都有状态依据（Grounding 表）

## n4n-11 · 雾堤上的警示灯

**Facts**

| factId | kind | 主体 | 内容 |
| --- | --- | --- | --- |
| f0 | moved | 沈砚 | 潮渡 → 雾堤（at 雾堤） |
| f1 | outcome | 韩渡 | surface=“把松脱的钟绳重新系紧”；hidden goal=“把雾警钟的绳子系紧”（task_bell_rope） |
| f2 | outcome | 沈砚 | surface=“把被风吹歪的警示灯扶正”；hidden goal=“把堤边的警示灯扶正”（task_warnlamp） |
| f3 | time | - | 4 minute |
| f4 | sanity_changed | 沈砚 | 12 → 10（内部数值，叙事不打印） |

**Scene state**

- 地点路径：雾堤 → 堤面
- 时间：夜；天气：雾，风横，浪高；风：迎海风；光：警示灯
- 在场：沈砚, 韩渡；可见物品：雾警钟, 钟绳, 警示灯
- 氛围：浪撞石壁，白沫翻上堤面
- 场景物品覆盖：无
- 隐藏动机：task_bell_rope, task_warnlamp

**Grounding（每个具体名词 → 状态）**

| 细节 | 状态来源 | 值 |
| --- | --- | --- |
| 雾堤 | loc_seawall | 港口外侧石堤 |
| 风 | scene.wind | 迎海风 |
| 浪头 | scene.weather | 浪高 |
| 石壁 | loc_seawall.features | 石壁 |
| 白沫 | loc_seawall.appearance | 白沫翻上堤面 |
| 韩渡 | char_han | 港务管事 |
| 钟架 | loc_seawall.features | 钟架 |
| 钟绳 | item_bell_rope | container=堤面 |
| 沈砚 | char_shen | protagonist |
| 警示灯 | item_warning_lamp | container=堤面；lit=true |
| 灯罩 | item_warning_lamp.appearance | 玻璃罩 |
| 火苗 | item_warning_lamp.state.lit | true |
| 铁皮 | item_warning_lamp.appearance | 铁皮警示灯 |
| 四分钟 | fact f3 | 4 minute |
| 掌心 | char_shen.body | 掌心（生理反应） |

**Narrative**

> 雾堤上的风比潮渡更横，浪头撞在石壁上，碎成一片白沫。韩渡蹲在钟架下，把松脱的钟绳重新系紧；沈砚扶正被风吹歪的警示灯，灯罩里的火苗晃了两下，才勉强稳住。四分钟，他的掌心被铁皮冰得发麻，心里那点没来由的慌却越压越重。

**Annotations**

| 文本 | covers | 允许的展开 |
| --- | --- | --- |
| 雾堤上的风比潮渡更横，浪头撞在石壁上，碎成一片白沫。 | — | weather, scene, sensory |
| 韩渡蹲在钟架下，把松脱的钟绳重新系紧； | f1 | behavior |
| 沈砚扶正被风吹歪的警示灯，灯罩里的火苗晃了两下，才勉强稳住。 | f0, f2 | behavior, sensory |
| 四分钟，他的掌心被铁皮冰得发麻，心里那点没来由的慌却越压越重。 | f3, f4 | time, interiority |

**Review**

- [ ] 事实全覆盖
- [ ] 无任务标题/quest 措辞
- [ ] 无新增具名实体/物品/地点
- [ ] 无他人内心（仅可见行为）
- [ ] 无新增世界事件/承诺性对话
- [ ] 场景/行为/心理自然
- [ ] 视角一致
- [ ] 无理智/外貌/个性/位置数值面板
- [ ] 每个具体名词都有状态依据（Grounding 表）

## n4n-12 · 潮渡的九分钟

**Facts**

| factId | kind | 主体 | 内容 |
| --- | --- | --- | --- |
| f0 | moved | 沈砚 | 潮生巷 → 潮渡（at 潮渡） |
| f1 | moved | 顾行舟 | 河心 → 潮渡（at 潮渡） |
| f2 | time | - | 9 minute |
| f3 | personality_changed | 沈砚 | 内部文本=“开始愿意等”；叙事用行为表现 |

**Scene state**

- 地点路径：潮渡 → 栈桥
- 时间：夜；天气：雾；风：河口风；光：船灯
- 在场：沈砚, 顾行舟；可见物品：渡船, 船灯, 缆绳
- 氛围：雾重，船灯只剩一团黄
- 场景物品覆盖：无
- 隐藏动机：task_wait

**Grounding（每个具体名词 → 状态）**

| 细节 | 状态来源 | 值 |
| --- | --- | --- |
| 潮渡 | loc_ferry | 木栈桥 |
| 雾 | scene.weather | 雾 |
| 船灯 | item_boat_light | container=渡船 |
| 木桩 | loc_ferry.features | 木桩 |
| 沈砚 | char_shen | protagonist |
| 顾行舟 | char_gu | 老船夫 |
| 渡船 | item_ferry | container=栈桥 |
| 船头 | item_ferry.appearance | 旧木船，船头挂船灯 |
| 水面 | loc_ferry.sublocations[0].appearance | 水面 |
| 缆绳 | item_mooring_rope | container=栈桥 |
| 九分钟 | fact f2 | 9 minute |

**Narrative**

> 潮渡的雾到夜里更重，船灯只剩一团模糊的黄。沈砚靠在木桩上，没有像从前那样来回踱步；顾行舟的渡船从河心慢慢靠过来，船头切开水面，缆绳甩上木桩时发出一声闷响。九分钟，他一直没有催，等船停稳，才向前走了一步。

**Annotations**

| 文本 | covers | 允许的展开 |
| --- | --- | --- |
| 潮渡的雾到夜里更重，船灯只剩一团模糊的黄。 | — | weather, scene |
| 沈砚靠在木桩上，没有像从前那样来回踱步； | f0, f3 | behavior |
| 顾行舟的渡船从河心慢慢靠过来，船头切开水面，缆绳甩上木桩时发出一声闷响。 | f1 | behavior, sensory |
| 九分钟，他一直没有催，等船停稳，才向前走了一步。 | f2, f3 | time, behavior |

**Review**

- [ ] 事实全覆盖
- [ ] 无任务标题/quest 措辞
- [ ] 无新增具名实体/物品/地点
- [ ] 无他人内心（仅可见行为）
- [ ] 无新增世界事件/承诺性对话
- [ ] 场景/行为/心理自然
- [ ] 视角一致
- [ ] 无理智/外貌/个性/位置数值面板
- [ ] 每个具体名词都有状态依据（Grounding 表）

## 已知缺口（先记录，不在审阅稿里假装完成）

1. 当前 N1 没有 `outcome`/`resultText`，任务完成只有 `goal`；本稿假定上游提供结果文本。
2. 当前 N5 的 G1 对理智/外貌/个性使用字段/数值式匹配；本稿用心理/行为/视觉表达，需要新的语义/人工核对口径。
3. 本稿未跑模型、未训练、未做完整 B 冻结池隔离；训练前须重新跑隔离与预登记。
4. 对话暂不纳入（避免模型替角色做出承诺）；如需对话，另立契约。

