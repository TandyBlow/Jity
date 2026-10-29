# C 交付项 1 签字记录

日期：2026-10-29。签字对象：`f0c7ae7`（`world-components`，已推送）。
签字：C 审查者（复审结论）。记录：C 实现者。
范围：**交付项 1「组件职责与接口表」完成**，限本轮五条验收及三项 P2 关闭。

**不扩大：** 独立盲标、κ、v3 冻结、N2/N3 模型臂、N4 浏览器端到端与接线、D2 能力样本，以及“接口已统一”的表述，均不在本签字内。交付项 2/3 的整体完成度也不因本记录改变。

## 五条验收

| # | 项目 | 结论 | 证据 |
| --- | --- | --- | --- |
| 1 | 四处状态行 | 一致，无残留“已完成/未完成”冲突 | `README.md`、`component-contracts.md` §8、`model-training-runtime.md` §3.1、`n2-content-selection.md` |
| 2 | §5.2 唯一口径 | 窄形状＋程序派生表只保留一处，N2 报告引用而不复写 | `component-contracts.md` §5.2；`n2-content-selection.md` §6 |
| 3 | N3 I2 探针 | 只查本句组 entityIds；九类篡改 **144/144**，有效计划 **16/16**；首位捏造编号、仅含捏造编号、空句组均返回违规列表，无异常 | `n3-baselines-r1.json` 的 `tamper` |
| 4 | 冒烟限定 | 只声明 factIds 消费 **36/36**（离线）；coreference、句组边界、跨组连贯未消费/未测，不是 N4 质量证据 | `n3-factids-smoke-r1.json` |
| 5 | 隔离数字 | 冻结 B `8878e97` 已提交语料：**4026 串 / 9 组、0 命中、0 缺失**；`poolDigest d7613154…`、`sourceDigest cae219d3…`、逐文件记录一致；live 4048 仅为诊断，未提交 `b3-dbg-a6/a7/a8` 单列 | `n2-isolation-r2.json` |

## 三项 P2 关闭

1. **隔离来源与数字**：v3 冻结 B 已提交语料，不再随 B 工作区写入漂移；README、F17、N2 报告统一引用 4026；4023/4041/4042 作为归档数撤回并写明差异。
2. **非法 factId 检查**：`check_invariants` 对首位捏造 factId、空句组返回问题而非 `KeyError`/`IndexError`；`--tamper` 新增 `fabricatedFirst`、`emptyGroup`，合计 144/144。
3. **N4 判据哈希**：`package_n4_offline.py` 直接哈希 `corpus_check.py`；`corpus.judge` 与 `corpus.all` 均为 `e16bd2c9…`，不再为 `null`；验收文件哈希一致。

## 证据哈希（git blob，LF）

| 文件 | sha256 |
| --- | --- |
| `artifacts/world-components/n2-isolation-r2.json` | `de2e536636cd955a6e0e28f1646c0abe75e65c1dcb61f9f6f98a9bd172fd034a` |
| `artifacts/world-components/n3-baselines-r1.json` | `5509c1fd068a1ec9a4d09fb1af71bf58fbed1e14ec4a449c0a2504b3f2d98fba` |
| `artifacts/world-components/n4-offline-package-r3-direction.json` | `7aa223668bb19c99ea557d93d0139900ad5396c363aa91169fc26f19b43b59ae` |
| `experiments/world-components/n2_selection/check_isolation.py` | `71d9ef7bec5a245734bbc574327e803c3b796bd7839b9f7eda15390f286c98ff` |
| `experiments/world-components/n2_selection/n3_plan.py` | `11824a208acdb4cc0f790072be9a9672dbb2171eb087a8b61b88f52fab8e8e09` |
| `experiments/world-components/n2_selection/run_n3_baselines.py` | `0ee43d4dac5a97e6cbfbf9846bb8e380bfbe737198747f22022519609fc33dbc` |
| `experiments/world-components/n4_corpus/package_n4_offline.py` | `3de8f821044fe74139331c39987a3bd8de5c8e49927171de4e6ad44a5a0f38d1` |

工作区副本在 `core.autocrlf=true` 下可能因换行转换得到不同字节哈希；上表按提交 blob 计。

## 仍未关闭

- N2：v3 独立标注、κ、标注冻结；编码器打分头训练；N2 模型臂未通过。
- N3：模型臂与 D2 的 H1/H2/G1–G4、8 项能力样本；coreference 下游消费与跨组连贯。
- N4：浏览器端到端、JS sentencepiece、与 B 的接线；离线结论只在六类短计划内。
- C1–C6：仍停留在接口方案。
