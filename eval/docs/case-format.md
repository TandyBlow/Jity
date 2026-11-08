# 用例与实验配置格式

第一阶段只运行离线模拟，验证任务调度、信息可见范围、检查点隔离、断点恢复和报告。`facts` 是用例作者提供的结构化注释，离线适配器通过字典读取它们，不会理解正文，也不会调用 Jity、摘要模型或真实语言模型。示例中的正确率不能用来说明模型的长期记忆能力。

一次实验由三个独立的 UTF-8 JSON 文件组成：

| 文件 | 用途 | 可以提供给被测适配器吗 |
|---|---|---|
| config | 实验分组、重复次数、近期窗口、用例文件路径 | 可提供运行所需配置 |
| suite | 公共历史、事实注释、测试问题及检查点 | 可以；不包含评分答案字段 |
| gold | 每道题的标准值 | 不可以；只供校验器和评分器使用 |

现成文件：[实验配置](../examples/pilot.json)、[公共用例](../examples/pilot.suite.json)、[私有答案](../examples/pilot.gold.json)、[故障演示配置](../examples/faults.json)。

## 通用规则

- `schema_version` 当前必须是整数 `1`。
- 所有字段均按类型校验；`true` 不会被当成整数 `1`。
- 不接受未声明字段，也不接受同一 JSON 对象中重复的键名。
- 所有对象可以额外包含字符串 `description`，用于说明用途，不参与评分。
- ID 必须以英文字母或数字开头，之后只允许英文字母、数字、点、下划线和连字符。不能含空格或 `/`。
- 必填字符串必须非空。需要表示没有事实时使用空 `facts` 数组，而不是空字符串事实。
- 校验失败会停止创建任务，不会通过猜测字段含义继续运行。

## config：实验配置

| 字段 | 类型与要求 | 说明 |
|---|---|---|
| `schema_version` | 整数 `1` | 配置版本 |
| `suite` | 非空字符串 | 公共用例文件路径 |
| `gold` | 非空字符串 | 私有答案文件路径 |
| `adapter` | 字符串 `offline` | 当前只允许离线适配器；其他值会报错 |
| `modes` | 非空数组，元素不得重复 | 从 `full`、`recent`、`state` 中选择 |
| `repeats` | 大于等于 1 的整数 | 每个模式下重复安排实验的次数 |
| `seed` | 整数 | 记录实验配置身份，便于后续扩展 |
| `recent_window` | 大于等于 1 的整数 | 各模式都可以看见的最近 N 条回合记录 |
| `failure_injections` | 可选数组 | 离线故障注入，见后文 |

`suite` 和 `gold` 的相对路径以 **config 所在目录**为起点，不随执行命令时的工作目录改变。绝对路径也可以使用。

三种模式的第一阶段含义如下：

| 模式 | 离线适配器可见信息 |
|---|---|
| `full` | 近期回合记录、结构化事实字典、叙事事实字典 |
| `recent` | 仅近期回合记录及其中的事实注释 |
| `state` | 近期回合记录、结构化事实字典 |

`repeats` 在当前阶段产生独立编号的**确定性重复**，用于检查调度和恢复；不会制造不同的模型采样。`seed` 会随任务配置记录，但离线适配器不使用随机生成。因此仅改变 `seed` 或增加 `repeats`，不应期待出现随机的答案差异，也不能据此估计模型方差。

任务总数为：

```text
全部 case 的 probe 数量之和 × modes 数量 × repeats
```

示例包含 2 个剧本，每个剧本有 4 个目标 × 3 个延迟 × 2 种测试，共 48 个 probe。三个模式各执行一遍，得到 144 个实验样本。

## suite：公共历史和探针

suite 根对象的必填字段是 `schema_version`、`suite_id`、`title`、`cases`。`cases` 是非空数组；每个 case 必须有 `id`、`title`、`history`、`probes`，case ID 在整个 suite 中唯一。

每条 `history` 记录包含：

| 字段 | 类型与要求 | 说明 |
|---|---|---|
| `turn` | 大于等于 1 的整数 | 必须从 1 开始，之后每条恰好加 1，不能重复或跳号 |
| `text` | 非空字符串 | 本回合公开历史正文 |
| `facts` | 数组，可以为空 | 本回合明确披露或更新的事实注释 |

每条 `facts` 注释包含：

| 字段 | 类型与要求 | 说明 |
|---|---|---|
| `id` | 合法 ID | 事实身份，例如 `potion_state` |
| `value` | 非空字符串 | 本回合披露的值，例如 `已消耗` |
| `storage` | `narrative`、`structured` 或 `both` | 指定该注释写入哪个离线事实字典 |

`storage` 的含义：

- `narrative`：只写入叙事字典；超出近期窗口后，只有 `full` 能从该字典读取。
- `structured`：只写入结构化字典；超出近期窗口后，`full` 和 `state` 可以读取。
- `both`：两个字典都写入。

同一回合内不能重复声明同一个事实 ID；后续回合可以使用同一个 ID 更新其值。例如第 2 回合 `potion_state=持有`，第 8 回合 `potion_state=已消耗`。当前值以测试时已经发生的最后一次更新为准。

这些标签是用例作者控制的测试条件，不代表系统已经实现或验证了真实摘要、语义检索、人物记忆或事实抽取。

每条 `probes` 记录包含：

| 字段 | 类型与要求 | 说明 |
|---|---|---|
| `id` | 合法 ID | 在该 case 内唯一 |
| `fact_id` | 合法 ID | 此题检查的事实身份；未知题可以指向尚未出现的事实 |
| `kind` | `recall` 或 `action` | 回忆题或行动题 |
| `question` | 非空字符串 | 交给适配器的问题或行动要求 |
| `source_turn` | 大于等于 1 的整数 | 目标事实最近一次披露的回合；必须是历史中存在的回合号 |
| `delay` | 大于等于 1 的整数 | 距离该次披露的延迟 |

检查点回合号按下面的式子计算：

```text
checkpoint_turn = source_turn + delay
```

检查点不能超出历史的最后回合。历史必须从第 1 回合开始逐回合连续填写，不能只提供第 1 和第 41 回合两条记录来声称有 40 回合间隔；这也保证近期窗口按记录条数计算时与实际回合数一致。

已知事实的 `source_turn` 必须等于检查点之前（含检查点）该事实最后一次被披露的回合。例如第 3 回合披露地点，第 20 回合再次提及，就不能仍将第 43 回合测试称为“间隔 40 回合”；以第 3 回合作为 source 的用例会被拒绝。

校验器通过 `facts` 注释检测重新披露。**它不会语义分析 `text`**；若正文重复了事实但作者没有填写注释，校验器无法自动发现。编写历史时仍需核查正文，确保实际披露与注释一致。

未知题在检查点之前没有目标事实，因此可以用 `source_turn` 标记主题首次出现的回合。此时 `delay` 是主题的测试安排，不应被解释成“某条已知事实被遗忘了”。测试之后才出现的事实不会用于回答当前问题。

每个 probe 在检查点副本中单独执行，回忆题的答案不会成为后续行动题的提示，也不会写回继续回放的主历史。

## gold：私有标准答案

gold 根对象只要求 `schema_version` 和非空 `records` 数组。每条记录包含：

| 字段 | 类型与要求 | 说明 |
|---|---|---|
| `case_id` | 合法 ID | 对应的 case |
| `probe_id` | 合法 ID | 对应的 probe |
| `expected_value` | 非空字符串或 JSON `null` | 已知事实标准值；未知信息使用 `null` |

每个 `case_id/probe_id` 必须且只能出现一次，不能缺题，也不能为不存在的题目添加答案。加载时会根据公共历史中的事实注释检查标准答案：

- 已知题必须匹配检查点时最新的事实值，不能使用已经过期的旧值。
- 未知题必须使用真正的 JSON `null`，不能写字符串 `"null"`、`"不知道"` 或虚构值。
- 标准答案只用于加载校验和评分，不能复制到 suite 的 probe 中；suite 中增加 `expected_value` 字段会触发未知字段错误。

当前评分使用值和决定类型的精确匹配，不进行自然语言语义评分，也不支持多个同义答案。回忆题使用 `answer` 或 `abstain`；行动题使用 `use_fact` 或 `ask_for_information`。这些结构化决定由离线适配器生成，仅用于验证评分与证据格式。

## 可以直接保存并校验的最小例子

在同一个目录创建下面三个文件。这个例子只有两回合和一个短延迟，适合检查格式；真实的几十回合用例见 [pilot.suite.json](../examples/pilot.suite.json)。

`mini.json`：

```json
{
  "schema_version": 1,
  "suite": "mini.suite.json",
  "gold": "mini.gold.json",
  "adapter": "offline",
  "modes": ["full", "recent", "state"],
  "repeats": 1,
  "seed": 42,
  "recent_window": 1
}
```

`mini.suite.json`：

```json
{
  "schema_version": 1,
  "suite_id": "mini-offline-v1",
  "title": "离线格式示例，不代表模型成绩",
  "cases": [
    {
      "id": "archive",
      "title": "档案位置与未知生日",
      "history": [
        {
          "turn": 1,
          "text": "诺诺把档案放在西塔。管理员随后到场，没有说明自己的生日。",
          "facts": [
            {"id": "archive_location", "value": "西塔", "storage": "narrative"}
          ]
        },
        {
          "turn": 2,
          "text": "你检查大厅照明，并整理值班登记页。",
          "facts": []
        }
      ],
      "probes": [
        {
          "id": "location-recall",
          "fact_id": "archive_location",
          "kind": "recall",
          "question": "档案被放在哪里？",
          "source_turn": 1,
          "delay": 1
        },
        {
          "id": "birthday-action",
          "fact_id": "administrator_birthday",
          "kind": "action",
          "question": "要安排管理员的生日庆祝，请判断现在能否确定日期。",
          "source_turn": 1,
          "delay": 1
        }
      ]
    }
  ]
}
```

`mini.gold.json`：

```json
{
  "schema_version": 1,
  "records": [
    {"case_id": "archive", "probe_id": "location-recall", "expected_value": "西塔"},
    {"case_id": "archive", "probe_id": "birthday-action", "expected_value": null}
  ]
}
```

在项目根目录运行；将配置路径替换成实际保存位置：

```sh
python3 -m jity_eval validate /path/to/mini.json
python3 -m jity_eval plan /path/to/mini.json
```

该例共安排 2 题 × 3 模式 = 6 个样本。近期窗口只有一条记录，因此 `recent` 看不到第一回合的地点；地点是叙事通道事实，`state` 也不会通过长期字典看到它。这是预定的离线模式差异，不是模型遗忘实验结果。

## 故障注入

可在 config 中添加 `failure_injections`，例如：

```json
{
  "case_id": "campus-archive",
  "probe_id": "archive-location-d10-recall",
  "mode": "full",
  "repeat": 1,
  "stage": "adapter",
  "attempt": 1
}
```

上面的对象是数组中的一项。`case_id` 和 `probe_id` 必须存在；`mode` 必须是本次配置选择的模式；`repeat` 从 1 开始且不能超过配置的 `repeats`；`attempt` 从 1 开始；`stage` 只能是 `adapter` 或 `grader`。完全相同的注入记录不能重复。

故障配置用于确认运行错误和评分错误不会被当成答对，也不会被当成模型答错。[faults.json](../examples/faults.json) 已安排两种首次尝试故障。使用 `resume --retry-errors` 可以显式重试这些错误；普通的答案错误不属于需要重新运行的系统故障。
