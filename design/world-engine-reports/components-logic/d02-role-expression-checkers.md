# D02 角色／实体与表达类型检查：首轮冻结方案

2026-11-10。分支 `codex/d02-role-expression-20261110`，工作树 `.local/worktrees/d02-role-expression`，从 D 分支 `codex/d-short-semantics-20261109@1e9456c4` 隔离创建。

状态：**方案与标注试验稿，不是已训练或已验证能力**。本轮没有启动训练，没有修改生产 `act(text)`，没有接入浏览器模型。程序检查器、数据试验稿和一次 DeepSeek API 代理实验是工程与数据准备；任何 API 或助手判断都不是人审金标准。

## 1. 范围与职责

新增两个独立检查任务，不沿用现有 D02.3／D02.5 头的资格：

| 组件 | API | 小模型（本轮未训练） | 程序 |
|---|---|---|---|
| D02.3 角色与实体 | 疑难指代、冲突、最终修复 | M1：跨度、角色、实体绑定 | 核对 ID、跨度、类型、当前执行人 |
| D02.5 行动语义 | 世界可行性、工具可用性、理由、需求覆盖 | M2：表达类型与问题片段 | 检查返回结构、执行升级规则 |

D02.3 当前只接受登记名称或 `[[entityId]]`，且要求跨度文字与名称完全匹配；本方案**不直接把代词结果塞进旧头**，而是定义“提及跨度”与“解析实体”分离的新检查契约。旧 D02.3／D02.5 保持原样，新检查器只作候选诊断。

两个检查器都不决定 act/skip、不生成行动、不判断世界可行性、不判断需求覆盖。API 明确 skip 时检查器不运行；检查器只产生 `accept / upgrade / incomplete`。

## 2. M1 角色与实体

### 2.1 输入

- 完整行动原文及全部步骤（不是只检查第一句）。
- 当前执行人、玩家原始需求、输入消费状态、已确认前缀；D04 时另含完整反应约束。
- 完整实体登记：ID、类型、名称、合法别名；世界版本／上下文摘要。
- 表示方式：`natural` 或 `references`；首版自然名和引用标记分别验收。

### 2.2 输出

每个步骤输出 `mentions` 和 `roleStatus`：

```text
stepId
mentions[]:
  mentionId
  start, end, surface          # 完整原文 code point 半开区间
  roles[]                      # subject/object/tool/recipient/destination
  diagnosticRoles[]            # source/static_location/co_agent/... 内部诊断
  status                       # bound/unknown_entity/ambiguous/insufficient
  entityId | candidates[]
  bindingBasis                 # name/alias/marker/pronoun/ellipsis/context
  confidence
  scope
  issueCodes[]
roleStatus{subject,object,tool,recipient,destination}:
  status                       # absent/bound/unknown_entity/ambiguous/insufficient
  mentionIds[]
issues[]
```

`absent` 与 `unknown_entity`／`insufficient` 必须分开：前者是“这一步确实没有工具、接收人等角色”，后者是“文本提到了但实体不知道”或“无法判断”。不允许都用 `null` 或空数组表示。

同一跨度可承担多个公开角色；同一实体在不同步骤可以承担不同角色。来源、静态场所等只能进 `diagnosticRoles`，不能伪装成 `destination`／`recipient`。

### 2.3 程序权威检查

程序只核对结构事实，不补全语义：

- 文本 SHA、步骤覆盖、跨度切片与步骤边界、ID 唯一、角色枚举、状态一致性；
- 绑定实体的登记 ID、名称／别名／标记、实体类型；
- `subject` 是否包含当前执行人；不包含则 `actor_mismatch`；
- 仅诊断角色的提及 → 升级；
- 别名、代词、省略、上下文指代 → 首版升级；
- 未登记实体、歧义、信息不足 → 升级。

类型检查只复核模型已选角色，不按实体类别反推角色。例如“用钥匙拨动铁片”中钥匙必须是 tool；“把钥匙交给乙”中钥匙是 object；“从乙那里取回钥匙”中乙是 source；“在仓库等待”中仓库是 static_location，均不被程序改写成其他角色。

### 2.4 首版自动采纳范围

只自动采纳：显式登记名称或合法 `[[entityId]]` 标记，跨度逐字匹配，实体 ID 合法，类型一致，主体包含当前执行人，且没有其他阻断问题。代词、省略、别名、上下文指代、仅诊断角色一律交 API。API 可以重写明确表达；程序不能自行替换原文。

## 3. M2 表达类型

### 3.1 标签

| 标签 | 定义 | 首版 |
|---|---|---|
| `attempt` | 提出可供后续结算的行动，没有宣称本次结果已发生 | 无阻断问题则通过 |
| `result_assertion` | 把尚未结算的本次结果写成已发生事实 | 升级 |
| `non_action` | 只有愿望、评价等，没有明确可执行尝试 | 升级，交 API 决定 skip 或重写 |
| `mixed` | 行动尝试夹带未结算结果等冲突 | 升级 |
| `uncertain` | 文本／上下文本身不能稳定判断 | 升级 |

不要求出现“尝试”二字。“甲用钥匙开门。”在 D02 提议语境下可以是 `attempt`。

### 3.2 问题跨度与作用域

每个问题片段带 `start/end`、`stepId` 和 `scope`：

`main / condition / negation / quote / hypothesis / background`。

- “如果开锁成功，甲就进入房间。” → 条件式尝试；“成功”处于 condition，不是既成结果。
- “甲喊道：‘我已经拿到钥匙了！’” → 喊话是行动；引用内容处于 quote，不能直接认定世界中的钥匙已转移。
- “门已经打开，甲尝试进入。” → 若“门已经打开”是已确认背景，记 `background`；若是模型新编造结果，记 `main` 并升级。无法判断时 `uncertain` 或弃答。

### 3.3 模型不承担

M2 的 `attempt` 标签不能证明工具可用、行动合理或需求已覆盖。这些仍由 API 的 D02.4／D02.5 负责。M2 只检查表达类型、问题片段和作用域。

### 3.4 两种不确定

- `label=uncertain`：数据本身有歧义，升级给 API。
- `abstain`：模型因低置信度、输入过长或超出支持范围而弃答；`low_confidence`／`ambiguous_input` 升级，`input_too_long`／`out_of_support`／`missing_context` 记为 `incomplete`。两者分开记账。

## 4. 有限升级流程

```text
程序准备合法且充分的输入
→ API 返回行动决策、完整行动及约定检查结果
→ M1、M2 检查同一份原文
→ 程序核对引用、覆盖、工作身份
→ 接受并冻结
→ D03
```

- API 明确 skip：按既有流程处理，检查器不伪造行动。
- 两项通过且其他必要审核完成：进入接受流程。
- 明确错误：保留原文和问题跨度，交 API 复核或修复。
- 小模型不确定：交 API 判断，不能强选实体。
- 输入缺失：先补输入；无法补齐则 `incomplete`。
- 修复后重新检查新原文；再次有未解决问题则 `incomplete`，不无限循环。

默认每个行动机会最多 **一次初始生成＋一次 API 聚合修复**。修复请求一次带上本轮全部疑点，并重新检查修改后受影响的需求覆盖；修正人物时不能丢掉步骤。最终经 API 修复后才通过的，记录为 `api_repair`，不能记成“小模型通过”。

## 5. 索引与版本兼容

- wire 偏移是本方案内部契约的 **Unicode code point** 半开区间；不是 UTF-8 字节，也不是浏览器 UTF-16 索引。
- Python 端提供 `codepoint_to_utf16`／`utf16_to_codepoint`，拒绝落在代理对中间的索引。
- 浏览器在进入／离开检查器边界时转换；转换测试包含 CJK 与补充平面字符。
- 首版不修改公开 `act(text)`；新检查器是影子诊断，不写世界、不返回正式 skip／冻结。
- 旧 D02.3／D02.5 头不继承新任务资格；后续若接入指代解析，需要版本化修改内部引用契约，区分“提及跨度”和“解析后的实体”。

## 6. 程序实现

- `experiments/world-components-logic/short_d02_checkers.py`：M1／M2 校验、组合、有限升级、索引转换。
- `experiments/world-components-logic/schemas/d02.role_audit.v1.schema.json`
- `experiments/world-components-logic/schemas/d02.expression_audit.v1.schema.json`
- `experiments/world-components-logic/tests/test_short_d02_checkers.py`

程序检查器不依赖模型库，纯标准库；测试覆盖主体错位、别名、代词、省略、未登记、歧义、对象→工具、接收人／来源、静态场所、类型不一致、结果断言、条件／引用／背景、非行动、不确定、弃答、修复上限和 UTF-16 转换。

## 7. 数据试验稿

见 [标注规则](../../../experiments/world-components-logic/data/d02-checkers/pilot-v1/ANNOTATION.md) 与 `manifest.json`。

- 20 个独立场景组，每组 5 条针对性样本，共 100 条；按 12/2/2/4 组分为训练／开发／校准／封存，样本数为 60/10/10/20。
- 另加 20 条 API 自然首输出（每组 1 条），单独统计，不混入针对性样本；合计 120 条，训练／开发／校准／封存样本数为 72/12/12/24。
- 同一场景的改名、改写、角色交换和正反例留在同一分组。
- 全部为助手草稿，人审 0；助手已逐条复核并修正，记录见 [REVIEW.md](../../../experiments/world-components-logic/data/d02-checkers/pilot-v1/REVIEW.md)；不是训练集，不是封存测试，不能据此签验收。
- 针对性样本以模板化短句为主；它覆盖规则分歧，不代表自然分布。
- 现有 D02.3／D02.5 的 38／32 条整体标注没有直接改写成本批标签；原语数量不等于独立行动样本数。
- **封存污染**：20 条 `sealed` 试点样本已被 API 代理检查打开，不能再作为最终封存测试；最终验收必须新建封存集。
- **人审入口**：`artifacts/world-components-logic/d02-checkers/pilot-review.html`。页面不联网，先读原文再展开草稿，分别记录 M1／M2 的认可／需修改／不确定；导出 JSON 带批次哈希。操作与裁决流程见 [人审标注操作说明](../../../experiments/world-components-logic/data/d02-checkers/pilot-v1/HUMAN_REVIEW.md)，回收用 `python3 d02_review.py reconcile <导出文件>`。当前 `humanReview.status=pending`，助手复核不能替代人审。

### 7.1 首批扩样 scale-v2

- 40 个场景组、400 条针对性样本，训练／开发／校准／封存为 240/40/40/80（60%/10%/10%/20%）。
- 每组 10 条：5 条原有变体＋multi／condition／quote／result2／actor-pronoun，共 400 条；全部为助手草稿，人审 0。
- 当前分布：预期接受 197 条、升级 203 条；主体错位 40、未结算结果 80、代词 47。
- 未知实体 5、歧义 4、别名 5、诊断角色 10、类型错误 5、非行动 2，**尚未达到每类 ≥30 的验收分母**；后续需要定向补充，不能拿 400 条总数掩盖类别不足。
- `sealed` 80 条尚未被 API 检查打开，保持未读；在规则冻结前不得查看或调参。
- 扩样审阅页：`artifacts/world-components-logic/d02-checkers/scale-v2-review.html`；生成命令 `python3 d02_review.py build --batch scale-v2`。

## 8. API 代理实验

配置只读取现有 `backend/.env` 的 `DEEPSEEK_API_KEY`、`LLM_BASE_URL`、`LLM_MODEL`；密钥不打印、不写日志、不进 Git。最小请求验证通过后，使用 `deepseek-flash` 非思考模式、JSON 输出做两件事：

1. 按场景生成自然首输出，保留完整首次文本、结束原因、token 与延迟。
2. 用同一 API 作为 B 臂代理，对试点样本输出 M1／M2 检查，经程序校验后统计：结构可解析率、与助手草稿的决策一致率、误放行、升级率、token 和延迟。

这是**代理实验**，不是生产 API 版本，也不是小模型成绩；不能替代 A/B/C 对照。实际用量与费用见 `artifacts/world-components-logic/d02-checkers/`。

### 8.1 实际结果（一次调用、无修复）

- 针对性 100 条：99 次 HTTP 成功，98 条 JSON 可解析；`accept/upgrade/incomplete` 为 7/14/77；与助手草稿决策一致 15 条；应接受且接受 4/39，应升级且升级 11/61；**错误放行 3 条**。
- 三条错误放行都是“来源→接收人”或“静态场所→目的地”的语义角色错误；程序核对 ID、跨度和类型后仍会放行。复核后对当前文本做 3 条点检，其中“阅览室→目的地”再次被直接放行，另两条被跨度偏移挡住。这说明程序检查不能替代 M1 的角色语义正确性。
- 自然 20 条：JSON 全部可解析，但 0 条出结果、20 条未完成；没有错误放行，但也不可用。
- 主要结构失败：跨度 `surface_mismatch` 51 次（大量起点偏 1）、结果标签／问题码不一致 19 次、无角色提及 13 次、诊断角色名不合法 11 次。
- 费用：175 次调用、209,379 tokens，保守估算 **0.6501 元**（含一次中止重跑的 28 次调用和 3 条当前文本点检）；针对性检查 p50 1.68s、p95 2.40s。详见 [代理实验报告](../../../artifacts/world-components-logic/d02-checkers/proxy-checker-report.md)。

该结果只支持一个结论：**单次 API 检查不能直接当作 B 臂或金标准**，必须先冻结提示、词表和一次修复规则，再做公平比较。它不证明小模型能力，也不证明 B 臂失败。

## 9. 验收提案（尚未取得）

| 项目 | 建议标准 |
|---|---|
| 程序契约 | 必测跨度、ID、主体绑定、版本、恢复、冻结全部通过；失败不得变 skip |
| M1 | 自动采纳绑定精确正确率 ≥99%；分角色和整段全部绑定报告 |
| M2 | 五类宏平均 F1 ≥95%；自动判安全尝试的样本正确率 ≥99% |
| 关键错误 | 封存反例中错主体、错误实体、未结算结果直接放行为零；只声明测试集零观测 |
| 弃答与覆盖 | 合法支持范围内 ≥70% 无需额外 API 检查；有效行动误标明确失败 ≤5% |
| 分母 | ≥200 条自动放行、≥200 条有明确问题，覆盖 ≥20 场景组，关键类各 ≥30 |
| C vs B | 正确完成率不降低、关键错误不增加；每正确行动 API token 实际下降 |
| C vs A | 明确报告减少的错误与增加的 token／等待；无收益不启用 |
| 部署 | 原生、导出、真实浏览器分别验证，记录转换后的判定变化 |
| 延迟 | 报告完整本地检查与 D02 的 p50/p95；局部成绩不证明整链 500ms |

阈值只在校准集选择；封存测试不能调阈值。`flag`、弃答、API 升级、最终未完成分开统计。

## 10. 未决与下一步

1. 人审本批 100＋条标签，解决“完成体动词是否算结果”“诊断角色能否自动接受”“别名是否放行”的分歧。
2. 扩充到约 200–300 个独立场景组、2,000–4,000 条完整行动样本；当前 20 组只够规则试验。
3. 获得新的训练授权后，再比较 R0（两层冻结编码器＋新头）、R1（完整 MiniRBT-H256 冻结＋新头）、R2（完整编码器与两头联合微调）。本轮没有训练，不报告任何模型分数。
4. 在影子模式接入，先分别验收 M1／M2；只有一个达标就先启用一个。
5. 在明确的本批 API 预算内做 A/B/C；当前 API 代理实验不计为 A/B/C 结果。

## 11. 复现

```bash
cd experiments/world-components-logic
python3 -m pytest tests/test_short_d02_checkers.py -q
python3 d02_pilot.py
python3 d02_api_experiment.py check \
  --env-file /path/to/Jity/backend/.env --limit 100 --tag targeted-r1
```

API 脚本会拒绝超过本地 18.5 元安全线的请求；本次授权上限为 20 元。密钥只从环境文件读取，不进入命令参数或产物。
