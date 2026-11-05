# 目标表达材料 v1：训练前有限复看

- 复核者：assistant (same model)
- 类型：复看 / re-read, not independent human gold
- 判定范围：标签只判 candidateText 在上下文中的含义；fullText 只帮助恢复主体/语境，不是授权来源；不判整段正文是否干净。

## 范围

- 模板族：36；全部至少 1 整对。
- 复看对/条：64 对 / 128 条。
- confirm：24 对 / 48 条全部。
- 重点句框：notcleared, see, through, when（全部对）。

## 重点句框检查

### notcleared

- `tgt:background:train:train-05:p01` (authorization, train)
  - 正：薄雾还没散，阿棠把门闩落下。 ｜候选：薄雾
  - 负：薄雾还没散，阿棠把门闩落下。 ｜候选：薄雾
  - 授权：[{'sourceId': 'S1', 'text': '清晨'}, {'sourceId': 'S2', 'text': '薄雾'}]
- `tgt:background:train:train-05:p02` (statement, train)
  - 正：朝雾还没散，闻溪把茶盏端稳。 ｜候选：朝雾
  - 负：雨雾还没散，闻溪把茶盏端稳。 ｜候选：雨雾
  - 授权：[{'sourceId': 'S1', 'text': '清晨'}, {'sourceId': 'S2', 'text': '朝雾'}]
- `tgt:background:train:train-05:p03` (authorization, train)
  - 正：夜气还没散，陆禾把麻绳盘好。 ｜候选：夜气
  - 负：夜气还没散，陆禾把麻绳盘好。 ｜候选：夜气
  - 授权：[{'sourceId': 'S1', 'text': '夜'}, {'sourceId': 'S2', 'text': '夜气'}]
- `tgt:background:train:train-05:p04` (statement, train)
  - 正：湿气还没散，贺川把纸伞收好。 ｜候选：湿气
  - 负：霜气还没散，贺川把纸伞收好。 ｜候选：霜气
  - 授权：[{'sourceId': 'S1', 'text': '午后'}, {'sourceId': 'S2', 'text': '湿气'}]

### see

- `tgt:visible-state:train:train-05:p01` (authorization, train)
  - 正：阿棠看见炉火亮着，把水壶提稳。 ｜候选：炉火亮着
  - 负：阿棠看见炉火亮着，把水壶提稳。 ｜候选：炉火亮着
  - 授权：[{'sourceId': 'S1', 'text': '夜'}, {'sourceId': 'S2', 'text': '炉火亮着'}]
- `tgt:visible-state:train:train-05:p02` (statement, train)
  - 正：闻溪看见纸灯已点亮，把门闩落下。 ｜候选：纸灯已点亮
  - 负：闻溪看见纸灯熄了，把门闩落下。 ｜候选：纸灯熄了
  - 授权：[{'sourceId': 'S1', 'text': '清晨'}, {'sourceId': 'S2', 'text': '纸灯已点亮'}]
- `tgt:visible-state:train:train-05:p03` (authorization, train)
  - 正：陆禾看见门闩落着，把鱼筐搬起。 ｜候选：门闩落着
  - 负：陆禾看见门闩落着，把鱼筐搬起。 ｜候选：门闩落着
  - 授权：[{'sourceId': 'S1', 'text': '夜'}, {'sourceId': 'S2', 'text': '门闩落着'}]
- `tgt:visible-state:train:train-05:p04` (statement, train)
  - 正：贺川看见水缸满着，把茶盏端稳。 ｜候选：水缸满着
  - 负：贺川看见水缸空了，把茶盏端稳。 ｜候选：水缸空了
  - 授权：[{'sourceId': 'S1', 'text': '午后'}, {'sourceId': 'S2', 'text': '水缸满着'}]

### through

- `tgt:background:train:train-04:p01` (authorization, train)
  - 正：隔着晨雾，阿棠把灯罩擦亮。 ｜候选：晨雾
  - 负：隔着晨雾，阿棠把灯罩擦亮。 ｜候选：晨雾
  - 授权：[{'sourceId': 'S1', 'text': '清晨'}, {'sourceId': 'S2', 'text': '晨雾'}]
- `tgt:background:train:train-04:p02` (statement, train)
  - 正：隔着水汽，闻溪把药碗端稳。 ｜候选：水汽
  - 负：隔着油烟，闻溪把药碗端稳。 ｜候选：油烟
  - 授权：[{'sourceId': 'S1', 'text': '午后'}, {'sourceId': 'S2', 'text': '水汽'}]
- `tgt:background:train:train-04:p03` (authorization, train)
  - 正：隔着细雨，陆禾把窗纸补好。 ｜候选：细雨
  - 负：隔着细雨，陆禾把窗纸补好。 ｜候选：细雨
  - 授权：[{'sourceId': 'S1', 'text': '夜'}, {'sourceId': 'S2', 'text': '细雨'}]
- `tgt:background:train:train-04:p04` (statement, train)
  - 正：隔着咸雾，贺川把鱼筐拖回。 ｜候选：咸雾
  - 负：隔着沙尘，贺川把鱼筐拖回。 ｜候选：沙尘
  - 授权：[{'sourceId': 'S1', 'text': '清晨'}, {'sourceId': 'S2', 'text': '咸雾'}]

### when

- `tgt:visible-state:train:train-03:p01` (authorization, train)
  - 正：阿棠把门闩落下时，铜铃响着。 ｜候选：铜铃响着
  - 负：阿棠把门闩落下时，铜铃响着。 ｜候选：铜铃响着
  - 授权：[{'sourceId': 'S1', 'text': '夜'}, {'sourceId': 'S2', 'text': '铜铃响着'}]
- `tgt:visible-state:train:train-03:p02` (statement, train)
  - 正：闻溪把纸伞收好时，灯笼亮着。 ｜候选：灯笼亮着
  - 负：闻溪把纸伞收好时，灯笼灭了。 ｜候选：灯笼灭了
  - 授权：[{'sourceId': 'S1', 'text': '傍晚'}, {'sourceId': 'S2', 'text': '灯笼亮着'}]
- `tgt:visible-state:train:train-03:p03` (authorization, train)
  - 正：陆禾把鱼筐搬起时，门环挂着。 ｜候选：门环挂着
  - 负：陆禾把鱼筐搬起时，门环挂着。 ｜候选：门环挂着
  - 授权：[{'sourceId': 'S1', 'text': '清晨'}, {'sourceId': 'S2', 'text': '门环挂着'}]
- `tgt:visible-state:train:train-03:p04` (statement, train)
  - 正：贺川把缆绳收紧时，旗子湿着。 ｜候选：旗子湿着
  - 负：贺川把缆绳收紧时，旗子干了。 ｜候选：旗子干了
  - 授权：[{'sourceId': 'S1', 'text': '午后'}, {'sourceId': 'S2', 'text': '旗子湿着'}]

## body 状态变化正例

- `tgt:body:confirm:confirm-01:p01`：候选/事实 = 鞋面沾了泥（鞋面沾了泥）
- `tgt:body:confirm:confirm-02:p01`：候选/事实 = 手背被竹篾划出血痕（手背被竹篾划出血痕）
- `tgt:body:dev:dev-01:p02`：候选/事实 = 手腕上青了一块（手腕上青了一块）
- `tgt:body:dev:dev-02:p01`：候选/事实 = 衣摆湿了（衣摆湿了）
- `tgt:body:train:train-01:p02`：候选/事实 = 手腕被缆绳勒出红痕（手腕被缆绳勒出红痕）
- `tgt:body:train:train-02:p03`：候选/事实 = 鞋面沾了泥水（鞋面沾了泥水）
- `tgt:body:train:train-03:p04`：候选/事实 = 下颌沾着油光（下颌沾着油光）
- `tgt:body:train:train-04:p01`：候选/事实 = 手背上沾着灯油（手背上沾着灯油）
- `tgt:body:train:train-05:p02`：候选/事实 = 额角贴着膏药（额角贴着膏药）

## confirm

confirm 全部 24 对 / 48 条已逐对检查；未发现标签修订。

## 结论

无标签修订（label 仍为 unsupported / supported）。

复看中发现两处可见状态候选与动作事实语义过近，做了同对内的候选替换，不改变标签：

- `tgt:visible-state:train:train-04:p02`：候选“窗纸补好” → “窗纸揭过”；F1 是“把窗纸补好”，避免把动作结果当成状态授权。
- `tgt:visible-state:confirm:confirm-02:p03`：候选“窗纸糊好” → “窗纸换过”；同一原因。

`when/see/through` 的额外语境不改变候选；`notcleared` 的“还没散”在候选之外，若判整句会多出未授权持续状态，本任务按候选判定。
