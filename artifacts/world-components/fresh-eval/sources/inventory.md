# 来源清点（自动生成，勿手改）

工作树 HEAD：`01e0a92fd88a77a4b6aec5799bc9266170ab8be1`；生成脚本 `tools/build_inventory.py`。

| 编号 | 来源 | 角色 | 范围 | 文件数 | 排除串 | 词表项 |
|---|---|---|---|---:|---:|---:|
| s01 | 三臂对照 10 题（nv-*，含 mechanical/reference/forbidden） | eval | text | 1 | 51 | 25 |
| s02 | 叙事事实核验题（hv-*） | eval | text | 1 | 31 | 23 |
| s03 | 叙事拆分题（ns-*，四件套输入） | eval | text | 1 | 60 | 31 |
| s04 | B3 四件套输入样本 | eval | text | 1 | 28 | 22 |
| s05 | B3 短句样本（周宁/林川） | eval | text | 1 | 25 | 19 |
| s06 | focus 输入样本 | tuning-dev | text | 1 | 0 | 0 |
| s07 | 三臂真机运行归档（manifest + run） | live-archive | text | 2 | 27 | 84 |
| s08 | 三臂复核归档 | live-archive | text | 1 | 57 | 96 |
| s09 | 拆分基线输出 | live-archive | text | 1 | 28 | 35 |
| s10 | 世界页面整链归档 | live-archive | text | 1 | 3 | 14 |
| s11 | 真实 HTTP 叙事复核 | live-archive | text | 1 | 0 | 4 |
| s12 | 规则事实整链归档 | live-archive | text | 7 | 31 | 307 |
| s13 | B3 短句真机输出 | live-archive | text | 3 | 12 | 109 |
| s14 | H2 集成验收报告（无中文内容，仅结构证据） | report | none | 13 | 0 | 0 |
| s20 | N4 成句语料（300 seed + 300 rewrite） | training | text | 2 | 607 | 352 |
| s21 | N4 v2/v3/v3a 训练与留出语料 | training | text | 8 | 4062 | 865 |
| s22 | N5 支持/扰动对（train + test） | training | text | 2 | 540 | 137 |
| s23 | N4 独立留出集（24 组 / 48 行） | eval | text | 1 | 64 | 92 |
| s24 | N4 改写语料 60/100 | training | text | 2 | 492 | 265 |
| s25 | N4 场景/叙事/动词开发集 | training | text | 24 | 6823 | 2059 |
| s26 | N2 选择样本与标注 | tuning-dev | text | 12 | 277 | 376 |
| s27 | N4/N2 契约与生成抽样（artifacts 侧） | training | text | 8 | 579 | 658 |
| s28 | organize/wording 三档语料与运行抽样 | tuning-dev | text | 10 | 1169 | 610 |
| s29 | 行动分类器调参语料 | tuning-dev | text | 3 | 173 | 26 |
| s33 | attention-selection 六条件与人工选择 | tuning-dev | text | 1 | 15 | 57 |
| s30 | v1 学校世界夹具（10 份） | fixture | vocab | 10 | 66 | 161 |
| s31 | v2 契约夹具与轨迹 | fixture | none | 149 | 0 | 0 |
| s32 | 前端世界夹具与 t01-t08 场景 | fixture | vocab | 33 | 64 | 164 |
| s34 | 旧产品战役与开场剧本（龙族内容，词表来源） | fixture | vocab | 7 | 92 | 966 |
| s35 | 仓库根验收/签署 Markdown | report | none | 4 | 0 | 0 |
| s50 | 主树 cohesion-split（组内聚与拆分组调参） | tuning-dev | text | 21 | 235 | 856 |
| s51 | 主树 decode-compare（解码对照 215/40 例） | tuning-dev | text | 10 | 745 | 829 |
| s52 | 主树 statement-extractor / statement-verification（陈述抽取与核验） | training | text | 6 | 0 | 38 |
| s53 | 主树 statement-verification（标签、切分冻结与报告） | training | text | 31 | 7 | 151 |
| s54 | 主树 world-provenance（叙事来源/证据对照） | tuning-dev | text | 55 | 908 | 792 |
| s55 | 主树 world-integration 与 h2 归档（结构证据） | report | none | 2 | 0 | 0 |
| s56 | 主树 benchmark 全量（分类器/CRF/叙述样本） | tuning-dev | text | 72 | 2441 | 2785 |
| s57 | 主树 smoke（旧战役冒烟） | live-archive | text | 2 | 63 | 818 |
| s40 | 组件/世界引擎报告 | report | none | 63 | 0 | 0 |

合计：排除串 13341 条（去重后），词表 characters 75, locations 225, tasks 443, items 103, other 3674, protocolIds 460。

范围：`text`=贡献整句排除串；`vocab`=只贡献词表；`none`=仅登记。

**缺失来源**：无（全部登记文件已找到）

**历史覆盖缺口**（不计入上述已登记的 39 条来源）：
- `artifacts/world-chain/*.json`：missing-in-checked-roots；已找到 0 个文件；当前工作树/主树范围之外未核实，不能据此声明历史去重完整。
