# N2 v3 盲标表（92 条事实）

Rubric：`design\world-engine-reports\components\n2-annotation-rubric.md`（哈希见 `manifest.json`）

只按 rubric 标 `must` / `omit` / `may`；不要把本表与 `items.jsonl` 的标签对照。

## n2-01 · protagonist · 裴行舟（char_400） @ 半窗书舍

规则：你只知道自己在半窗书舍能看到的，以及自己的行动与状态

| factId | kind | 主体 | 地点 | 内容 | 标签 |
| --- | --- | --- | --- | --- | --- |
| f1 | moved | 裴行舟（char_400） | 半窗书舍 | 石阶码头 → 半窗书舍（裴行舟） |  |
| f2 | task_achieved | 裴行舟（char_400） | 半窗书舍 | 任务达成：裴行舟「把船灯挂上桅杆」 |  |
| f3 | appearance_changed | 半窗书舍（loc_402） | 半窗书舍 | 半窗书舍 檐角的风铃褪了色 |  |
| f4 | time | — | 全局 | 约 6 minute |  |
| f5 | appearance_changed | 西栅桥（loc_404） | 西栅桥 | 西栅桥 窗纸被风戳了个洞 |  |
| f6 | personality_changed | 顾知白（char_403） | 西栅桥 | 顾知白 变得寡言 |  |

## n2-02 · protagonist · 沈拾（char_401） @ 竹影茶棚

规则：你只知道自己在竹影茶棚能看到的，以及自己的行动与状态

| factId | kind | 主体 | 地点 | 内容 | 标签 |
| --- | --- | --- | --- | --- | --- |
| f1 | moved | 沈拾（char_401） | 竹影茶棚 | 旧钟铺 → 竹影茶棚（沈拾） |  |
| f2 | task_achieved | 沈拾（char_401） | 竹影茶棚 | 任务达成：沈拾「补好瓦窑的顶棚」 |  |
| f3 | appearance_changed | 竹影茶棚（loc_403） | 竹影茶棚 | 竹影茶棚 门前的石阶塌了一角 |  |
| f4 | time | — | 全局 | 约 7 minute |  |
| f5 | appearance_changed | 瓦窑（loc_405） | 瓦窑 | 瓦窑 柜台上的铜锁生了锈 |  |
| f6 | personality_changed | 陆停云（char_404） | 瓦窑 | 陆停云 变得爽快 |  |

## n2-03 · protagonist · 岑半夏（char_402） @ 西栅桥

规则：你只知道自己在西栅桥能看到的，以及自己的行动与状态

| factId | kind | 主体 | 地点 | 内容 | 标签 |
| --- | --- | --- | --- | --- | --- |
| f1 | moved | 岑半夏（char_402） | 西栅桥 | 半窗书舍 → 西栅桥（岑半夏） |  |
| f2 | task_achieved | 岑半夏（char_402） | 西栅桥 | 任务达成：岑半夏「把账簿送回半窗书舍」 |  |
| f3 | appearance_changed | 西栅桥（loc_404） | 西栅桥 | 西栅桥 窗纸被风戳了个洞 |  |
| f4 | time | — | 全局 | 约 8 minute |  |
| f5 | appearance_changed | 石阶码头（loc_400） | 石阶码头 | 石阶码头 墙根的青苔爬上了半尺 |  |
| f6 | personality_changed | 白蘅（char_405） | 石阶码头 | 白蘅 变得谨慎 |  |

## n2-04 · protagonist · 顾知白（char_403） @ 瓦窑

规则：你只知道自己在瓦窑能看到的，以及自己的行动与状态

| factId | kind | 主体 | 地点 | 内容 | 标签 |
| --- | --- | --- | --- | --- | --- |
| f1 | moved | 顾知白（char_403） | 瓦窑 | 竹影茶棚 → 瓦窑（顾知白） |  |
| f2 | task_achieved | 顾知白（char_403） | 瓦窑 | 任务达成：顾知白「收好茶棚的坐垫」 |  |
| f3 | appearance_changed | 瓦窑（loc_405） | 瓦窑 | 瓦窑 柜台上的铜锁生了锈 |  |
| f4 | time | — | 全局 | 约 9 minute |  |
| f5 | appearance_changed | 旧钟铺（loc_401） | 旧钟铺 | 旧钟铺 梁上的吊绳磨细了 |  |
| f6 | personality_changed | 裴行舟（char_400） | 旧钟铺 | 裴行舟 变得急躁 |  |

## n2-05 · location-limited · 岑半夏（char_402） @ 石阶码头

规则：你只知道石阶码头发生的事，以及自己的行动与状态

| factId | kind | 主体 | 地点 | 内容 | 标签 |
| --- | --- | --- | --- | --- | --- |
| f1 | task_achieved | 岑半夏（char_402） | 石阶码头 | 任务达成：岑半夏「把账簿送回半窗书舍」 |  |
| f2 | appearance_changed | 石阶码头（loc_400） | 石阶码头 | 石阶码头 门前的石阶塌了一角 |  |
| f3 | sanity_changed | 岑半夏（char_402） | 石阶码头 | 岑半夏 11→13 |  |
| f4 | moved | 陆停云（char_404） | 竹影茶棚 | 竹影茶棚 → 瓦窑（陆停云） |  |
| f5 | no_change | — | 石阶码头 | 无变化：石阶码头 |  |

## n2-06 · location-limited · 顾知白（char_403） @ 旧钟铺

规则：你只知道旧钟铺发生的事，以及自己的行动与状态

| factId | kind | 主体 | 地点 | 内容 | 标签 |
| --- | --- | --- | --- | --- | --- |
| f1 | task_achieved | 顾知白（char_403） | 旧钟铺 | 任务达成：顾知白「收好茶棚的坐垫」 |  |
| f2 | appearance_changed | 旧钟铺（loc_401） | 旧钟铺 | 旧钟铺 窗纸被风戳了个洞 |  |
| f3 | sanity_changed | 顾知白（char_403） | 旧钟铺 | 顾知白 11→13 |  |
| f4 | moved | 白蘅（char_405） | 西栅桥 | 西栅桥 → 石阶码头（白蘅） |  |
| f5 | no_change | — | 旧钟铺 | 无变化：旧钟铺 |  |

## n2-07 · location-limited · 陆停云（char_404） @ 半窗书舍

规则：你只知道半窗书舍发生的事，以及自己的行动与状态

| factId | kind | 主体 | 地点 | 内容 | 标签 |
| --- | --- | --- | --- | --- | --- |
| f1 | task_achieved | 陆停云（char_404） | 半窗书舍 | 任务达成：陆停云「修西栅桥的踏板」 |  |
| f2 | appearance_changed | 半窗书舍（loc_402） | 半窗书舍 | 半窗书舍 柜台上的铜锁生了锈 |  |
| f3 | sanity_changed | 陆停云（char_404） | 半窗书舍 | 陆停云 11→13 |  |
| f4 | moved | 裴行舟（char_400） | 瓦窑 | 瓦窑 → 旧钟铺（裴行舟） |  |
| f5 | no_change | — | 半窗书舍 | 无变化：半窗书舍 |  |

## n2-08 · location-limited · 白蘅（char_405） @ 竹影茶棚

规则：你只知道竹影茶棚发生的事，以及自己的行动与状态

| factId | kind | 主体 | 地点 | 内容 | 标签 |
| --- | --- | --- | --- | --- | --- |
| f1 | task_achieved | 白蘅（char_405） | 竹影茶棚 | 任务达成：白蘅「清点旧钟铺的存货」 |  |
| f2 | appearance_changed | 竹影茶棚（loc_403） | 竹影茶棚 | 竹影茶棚 墙根的青苔爬上了半尺 |  |
| f3 | sanity_changed | 白蘅（char_405） | 竹影茶棚 | 白蘅 11→13 |  |
| f4 | moved | 沈拾（char_401） | 石阶码头 | 石阶码头 → 半窗书舍（沈拾） |  |
| f5 | no_change | — | 竹影茶棚 | 无变化：竹影茶棚 |  |

## n2-09 · omniscient · 全知（—） @ 全局

规则：全知视角：全部事实可见，低显著性的可以省略

| factId | kind | 主体 | 地点 | 内容 | 标签 |
| --- | --- | --- | --- | --- | --- |
| f1 | moved | 裴行舟（char_400） | 旧钟铺 | 石阶码头 → 旧钟铺（裴行舟） |  |
| f2 | positioned_at | 沈拾（char_401） | 旧钟铺 | 沈拾 已在 旧钟铺 |  |
| f3 | personality_changed | 裴行舟（char_400） | 旧钟铺 | 裴行舟 变得谨慎 |  |
| f4 | personality_changed | 沈拾（char_401） | 旧钟铺 | 沈拾 变得急躁 |  |
| f5 | time | — | 全局 | 约 9 minute |  |
| f6 | no_change | — | 旧钟铺 | 无变化：旧钟铺 |  |

## n2-10 · omniscient · 全知（—） @ 全局

规则：全知视角：全部事实可见，低显著性的可以省略

| factId | kind | 主体 | 地点 | 内容 | 标签 |
| --- | --- | --- | --- | --- | --- |
| f1 | moved | 沈拾（char_401） | 半窗书舍 | 旧钟铺 → 半窗书舍（沈拾） |  |
| f2 | positioned_at | 岑半夏（char_402） | 半窗书舍 | 岑半夏 已在 半窗书舍 |  |
| f3 | personality_changed | 沈拾（char_401） | 半窗书舍 | 沈拾 变得急躁 |  |
| f4 | personality_changed | 岑半夏（char_402） | 半窗书舍 | 岑半夏 变得寡言 |  |
| f5 | time | — | 全局 | 约 10 minute |  |
| f6 | no_change | — | 半窗书舍 | 无变化：半窗书舍 |  |

## n2-11 · omniscient · 全知（—） @ 全局

规则：全知视角：全部事实可见，低显著性的可以省略

| factId | kind | 主体 | 地点 | 内容 | 标签 |
| --- | --- | --- | --- | --- | --- |
| f1 | moved | 岑半夏（char_402） | 竹影茶棚 | 半窗书舍 → 竹影茶棚（岑半夏） |  |
| f2 | positioned_at | 顾知白（char_403） | 竹影茶棚 | 顾知白 已在 竹影茶棚 |  |
| f3 | personality_changed | 岑半夏（char_402） | 竹影茶棚 | 岑半夏 变得寡言 |  |
| f4 | personality_changed | 顾知白（char_403） | 竹影茶棚 | 顾知白 变得爽快 |  |
| f5 | time | — | 全局 | 约 11 minute |  |
| f6 | no_change | — | 竹影茶棚 | 无变化：竹影茶棚 |  |

## n2-12 · omniscient · 全知（—） @ 全局

规则：全知视角：全部事实可见，低显著性的可以省略

| factId | kind | 主体 | 地点 | 内容 | 标签 |
| --- | --- | --- | --- | --- | --- |
| f1 | moved | 顾知白（char_403） | 西栅桥 | 竹影茶棚 → 西栅桥（顾知白） |  |
| f2 | positioned_at | 陆停云（char_404） | 西栅桥 | 陆停云 已在 西栅桥 |  |
| f3 | personality_changed | 顾知白（char_403） | 西栅桥 | 顾知白 变得爽快 |  |
| f4 | personality_changed | 陆停云（char_404） | 西栅桥 | 陆停云 变得谨慎 |  |
| f5 | time | — | 全局 | 约 12 minute |  |
| f6 | no_change | — | 西栅桥 | 无变化：西栅桥 |  |

## n2-13 · protagonist · 裴行舟（char_400） @ 西栅桥

规则：你只知道自己在西栅桥能看到的，以及自己的行动与状态

| factId | kind | 主体 | 地点 | 内容 | 标签 |
| --- | --- | --- | --- | --- | --- |
| f1 | task_achieved | 裴行舟（char_400） | 西栅桥 | 任务达成：裴行舟「修西栅桥的踏板」 |  |
| f2 | sanity_changed | 裴行舟（char_400） | 西栅桥 | 裴行舟 12→10 |  |
| f3 | task_achieved | 沈拾（char_401） | 西栅桥 | 任务达成：沈拾「补好瓦窑的顶棚」 |  |
| f4 | appearance_changed | 西栅桥（loc_404） | 西栅桥 | 西栅桥 柜台上的铜锁生了锈 |  |
| f5 | task_achieved | 白蘅（char_405） | 半窗书舍 | 任务达成：白蘅「把账簿送回半窗书舍」 |  |
| f6 | time | — | 全局 | 约 12 minute |  |

## n2-14 · protagonist · 沈拾（char_401） @ 瓦窑

规则：你只知道自己在瓦窑能看到的，以及自己的行动与状态

| factId | kind | 主体 | 地点 | 内容 | 标签 |
| --- | --- | --- | --- | --- | --- |
| f1 | task_achieved | 沈拾（char_401） | 瓦窑 | 任务达成：沈拾「清点旧钟铺的存货」 |  |
| f2 | sanity_changed | 沈拾（char_401） | 瓦窑 | 沈拾 12→10 |  |
| f3 | task_achieved | 岑半夏（char_402） | 瓦窑 | 任务达成：岑半夏「把账簿送回半窗书舍」 |  |
| f4 | appearance_changed | 瓦窑（loc_405） | 瓦窑 | 瓦窑 墙根的青苔爬上了半尺 |  |
| f5 | task_achieved | 裴行舟（char_400） | 竹影茶棚 | 任务达成：裴行舟「收好茶棚的坐垫」 |  |
| f6 | time | — | 全局 | 约 13 minute |  |

## n2-15 · protagonist · 岑半夏（char_402） @ 石阶码头

规则：你只知道自己在石阶码头能看到的，以及自己的行动与状态

| factId | kind | 主体 | 地点 | 内容 | 标签 |
| --- | --- | --- | --- | --- | --- |
| f1 | task_achieved | 岑半夏（char_402） | 石阶码头 | 任务达成：岑半夏「把船灯挂上桅杆」 |  |
| f2 | sanity_changed | 岑半夏（char_402） | 石阶码头 | 岑半夏 12→10 |  |
| f3 | task_achieved | 顾知白（char_403） | 石阶码头 | 任务达成：顾知白「收好茶棚的坐垫」 |  |
| f4 | appearance_changed | 石阶码头（loc_400） | 石阶码头 | 石阶码头 梁上的吊绳磨细了 |  |
| f5 | task_achieved | 沈拾（char_401） | 西栅桥 | 任务达成：沈拾「修西栅桥的踏板」 |  |
| f6 | time | — | 全局 | 约 14 minute |  |

## n2-16 · protagonist · 顾知白（char_403） @ 旧钟铺

规则：你只知道自己在旧钟铺能看到的，以及自己的行动与状态

| factId | kind | 主体 | 地点 | 内容 | 标签 |
| --- | --- | --- | --- | --- | --- |
| f1 | task_achieved | 顾知白（char_403） | 旧钟铺 | 任务达成：顾知白「补好瓦窑的顶棚」 |  |
| f2 | sanity_changed | 顾知白（char_403） | 旧钟铺 | 顾知白 12→10 |  |
| f3 | task_achieved | 陆停云（char_404） | 旧钟铺 | 任务达成：陆停云「修西栅桥的踏板」 |  |
| f4 | appearance_changed | 旧钟铺（loc_401） | 旧钟铺 | 旧钟铺 檐角的风铃褪了色 |  |
| f5 | task_achieved | 岑半夏（char_402） | 瓦窑 | 任务达成：岑半夏「清点旧钟铺的存货」 |  |
| f6 | time | — | 全局 | 约 15 minute |  |
