# D2 准备批次：8 项能力样本、AI gold 冻结、隔离与指标预登记

日期：2026-10-29。分支：`world-components`。范围：D2 准备（d1-ai-closure.md §5.3 前置项）；**未运行任何模型推理**，N3 模型臂等 prompt 冻结后才跑。

## 1. 结论

- 8 项 N3 能力样本已构建（4 项含时间考 G3、4 项双人同事件考 G1），与 16 项 v2 集同形，结构自检通过。
- gold 已按项目负责人裁决完成**双 AI 独立标注**并冻结：两份标签 **24 句组/45 指代条目全部一致，池化共组 κ=1.0000**（门 0.7），分歧 0，无裁决项；冻结件 `artifacts/world-components/n2-labels-d2-gold.jsonl`（记录 `n2-labels-d2-gold.json`），与程序化 rubric 实现逐条一致（诊断对照）。这是 **AI gold，不是人工标注**。
- 三件工具就绪：标注一致度/裁决/冻结工具、预登记指标工具（H1/H2/G1–G4＋通过线）、D2 隔离扫描；自检与篡改探针全过；冻结 gold 的 CLI 端到端自检 PASS（`d2-gold-metrics-selfcheck.json`）。
- 隔离：对 B 冻结语料（4026 串，poolDigest `d7613154…`）**0 命中**；对 C 内部 16 项集与 N4 语料亦无字符串重叠（诊断）。
- prompt 预登记草案已成文，**待签认冻结**；冻结前不运行模型臂。

## 2. 8 项能力样本

`experiments/world-components/n2_selection/d2_capability_items.jsonl`（构造器 `build_d2_capability_items.py`，sha256 见协议登记）。

- 形状与 16 项 v2 集一致（`viewpoint`＋`facts`），`task: "n3-plan"`；事实表即已选集，**无** must/target/omittable/forbidden 标签，**无**分组提示 note。
- 新来源组：角色洛九针/孟潮生/温白山/桑晚照/阮听澜，地点潮音渡/铁锚巷/望火楼/苇塘集/老闸口；表面文本手写，结构字段（注册表、fact 字段、完整性规则）由构造器程序断言。
- 能力分组：`n3cap-01..04` 各恰含 1 条 time 事实（输入序位置分别在中段/首位/末位/中段），考 R3 时间归属（G3）；`n3cap-05..08` 各含一组逐字相同 `goal` 的协作任务（05/06 两人、07 三人、08 两人＋同地点不同目标干扰项），考 R2 合组（G1）。
- 时间集不含协作目标、协作集不含 time 事实（两集分开，不混淆能力）。

## 3. AI gold：协议与标注结果（按项目负责人裁决）

`annotation/d2-gold-protocol.json`，沿用 D1 形态：两个无继承会话的 AI 标注者，只读四个已哈希输入（rubric、盲表=条目文件本身、任务说明、输出模板）；κ 门 0.7（预登记定义=全部条目无序事实对的合并池化共组 κ）；分歧存在时全部分歧条目逐条裁决（source 标签＋书面理由）；原始 κ 不达标则回 rubric，不得以裁决后标签冒充原始一致度。

- rubric `annotation/d2-gold-rubric.md`：机械化约定 R1–R6（实体内聚、逐字 goal 合并、时间归前驱句组、其余独立成组、输入序排序、coreference 逐事实登记），是本实验的 gold 定义而非叙事优劣主张。
- **执行结果（2026-10-29）**：`labels-d2-ai-a.jsonl` 与 `labels-d2-ai-b.jsonl` 两份原始标签 24 句组全一致，κ=1.0000，分歧 0；顺序一致 44/44，可比句组指代一致 45/45；身份声明 `identity-d2-ai-a.json`、`identity-d2-ai-b.json`（均声明未接触四输入之外的文件）。冻结件与冻结记录见 `artifacts/world-components/n2-labels-d2-gold.jsonl`、`n2-labels-d2-gold.json`（含 κ 表、输入/工具哈希、局限照录）。
- 记录在案的判断点：rubric R3 对「time 位于输入首位」的字面自指（首个事实即 time 自身）；两位标注者独立按同一解读（并入首个含实体事实的句组）执行，结果一致。rubric 已按登记哈希冻结，措辞不改，此处留痕。
- 局限照录协议：AI gold 非人工标注；同模型家族相关偏差可能存在；κ 不证明语义正确性。

## 4. 工具与自检

| 工具 | 职责 | 自检 |
| --- | --- | --- |
| `d2_labels_agreement.py` | 双标签结构校验（复用 `n3_plan.check_invariants`＋coreference 数量/对齐/实名严格检查）、池化共组 κ、顺序/指代一致报告、裁决强制、冻结产物 | 合成场景：完全一致 κ=1；已知分歧 κ 手算核对；两标注者同向恒定→简并报错；缺编号/跨组指代/指代错位/索引断裂全抓；裁决缺失/理由缺失/无效裁决全拒 |
| `d2_metrics.py` | 预登记指标 H1/H2（门）、G1 池化 pairwise F1、G2 先行词正确率（可比句组、按位配对）＋代词位点产出率（全 gold 位点分母）、G3 时间位置、G4 顺序（只报告）；通过线 H1/H2 全过＋G1≥0.80＋G2≥0.80 且产出≥0.50＋G3≥0.75 | gold 对 gold 全 1.0 且 PASS；9 类篡改探针（捏造编号/跨组指代/合而不分/分而不合/先行词换位/双时间错位/组内乱序/代词位点全删/覆盖缺失）逐一按预期移动指标或否决 |
| `check_isolation_d2.py` | 复用 `check_isolation` 冻结池（钉 B `8878e97`）扫描 D2 字符串 | 植入串必中、子串包含必中 |

指标操作化选择（属本次冻结，由自检钉住）：比率全部**池化**（合并所有条目后计单一比率，与预登记"正确率/F1"口径一致）；G2 先行词分母限可比句组（分组错误已由 G1 计罚），代词位点产出率保留全 gold 分母（产出位点以成组为前提）；H1/H2 对原始计划判定，任何结构违规直接否决且该条目 G 指标作废。

## 5. 隔离

`artifacts/world-components/n2-isolation-d2.json`：B 冻结语料 4026 串（poolDigest `d7613154…`，与复核轮 22 归档一致），D2 扫 36 串/8 项，**ZERO_HIT**；来源清单与逐文件哈希入档。附加诊断：与 16 项集、N4 语料（1831 串）无重叠（首版样本中「变得急躁」与 C 内部语料撞串，已改「变得焦躁」后清零——撞串发生在 C 内部集之间，不涉 B 隔离，仍按来源组卫生处理）。

## 6. Prompt 预登记（待冻结）

`d2-n3-prompt-draft.md`：唯一 prompt 模板（R1–R6 原文进 prompt）、固定重试后缀、总重试 1 次、盲 A/B 只作佐证、解析与判定走 `d2_metrics.py`。**待 C 审查者与项目负责人签认后冻结哈希**；冻结前不运行任何模型推理。

指标工具、一致度工具、判据线与操作化选择的哈希已先于 gold 标注和任何模型推理预登记：`artifacts/world-components/d2-metrics-preregistration.json`。

## 7. 待办与顺序

1. ~~双 AI 标注 → 一致度 κ → 冻结 gold~~ **已完成（2026-10-29）**：κ=1.0000、零分歧、冻结件落库。
2. prompt 草案 v2 签认 → 冻结哈希。**（当前阻塞项，等 C 审查者与项目负责人）**
3. 两者齐备后才运行 N3 模型臂；16 项与 8 项分开报告；跑输归档失败，本批不调参。
4. 代词渲染仍归 N4-coref，不在本轮。

## 8. 复核轮 24 修复（五项 P2，全部关闭）

C 审查者复审发现五项 P2（未签认 D2 准备完成或 prompt 冻结）；修复如下，原预登记 v1 记录保留不动（`d2-metrics-preregistration.json`），修订原因与新哈希登记在 `artifacts/world-components/d2-preregistration-revision.json`。

| # | 缺陷 | 修复与证据 |
| --- | --- | --- |
| P2-1 | 隔离检查只按命中数判断，缺失语料来源仍判 `ZERO_HIT`＋退出码 0 | `verdict_for(hits, missing)`：任一来源缺失即 `MISSING_SOURCE`＋失败；自检补三例（零命中过/命中败/缺失败），归档 verdict 带缺失数 |
| P2-2 | 顺序一致度用 frozenset 查元组集合且不读实际位置，组内全反转仍报 44/44 | 改为对双方共组的事实对按**各自实际组内位置**比较方向；自检补**反转探针**（组内 factIds+coreference 全反转 → 顺序一致 0/2，κ 表不变） |
| P2-3 | 冻结入口接受被改为全零的登记哈希；身份文件未绑定；`core.autocrlf=true` 下干净检出六份预登记文件哈希全失配 | 冻结前强制校验：协议登记哈希须同时等于**工作树字节**与**提交 blob**（临时仓库自检：清零登记哈希/未提交工作树漂移/身份暴露标记/身份文件清单不匹配四类全拒）；身份文件经协议 `annotators[].identity` 绑定校验（ID/无继承声明/exposure=false/四输入清单）并连同 sha256 写入冻结记录；`.gitattributes` 钉登记材料 `-text`、工具 `eol=lf`；write-tree→git-archive 干净检出模拟：六份预登记文件＋三件工具哈希**全部 MATCH** |
| P2-4 | 指标工具对合法 JSON 缺 `coreference` 抛 `KeyError` | 形状守卫前置（sentences/factIds/coreference 结构先行校验，形状违规不再进入 `check_invariants`）；H1/H2 对形状违规计失败、该条目 G 指标作废，进入既定失败/重试流程；探针 T10（缺 key）/T11（畸形条目）钉住；一致度工具同型守卫 |
| P2-5 | prompt 草案 R3 首位 time 自指；条目 ID 提供方式与 16 项集已选规则未定义 | 草案升 v2（`d2-n3-prompt-draft.md` §修订记录）：R3 兜底明确为「首个含 entityId 的事实所在组」（与冻结标注解释语义一致）；占位符逐字替换规则（`<条目ID>`/viewpoint/facts）成文；16 项集已选=冻结 `target` 按 facts 输入序过滤（与 `selected_of` 一致）。**rubric 与标注证据一字不改** |

修复后复跑：三工具自检全过；冻结记录重生成（**冻结标签字节不变**，sha256 `cb86aa46…` 与 f27af30 一致，κ=1.0000 不变；记录新增 inputVerification 四行＋双身份绑定）；gold CLI 端到端自检 PASS；隔离复扫 ZERO_HIT、缺失 0。本轮未运行模型推理。
