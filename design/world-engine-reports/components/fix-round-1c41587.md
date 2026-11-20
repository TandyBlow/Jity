# 修复轮 1c41587（2026-11-02）— 复验入口

对应 C 复审报告 `c-review-1c41587`（未签认；审查者本地保留，不作为提交证据）的四项阻塞与两项纠正。**状态更新（第一笔提交时）：本轮改动已随三笔预算的第一笔提交入库；下文「未提交——预算用尽」的表述为当时状态记录，保留不改。提交清单见 `fix-round-commit-manifest.json`（已按第一笔整改：双哈希、无自哈希，校验脚本 `experiments/world-components/verify_commit_manifest.py`）。** 以下每项给出改动位置与独立复验命令。

> **Qwen3-0.6B 已退役（2026-11-02）：** 本文的 0.6B 暂停门/批准状态是历史记录；模型已退役，不再有“解除暂停后启用”的路径。见 [退役记录](model-retirement-qwen3-06b.md)。

## #1 空生成 / N5 事实检查失败 / 语义待核 → 明确非成功状态；汇总反映 N5

- 改动：`run_composition.py` 的 `run_scenario`——最终状态由 N5 推导：空输出 → `empty-output`；N5 fails → `n5-failed`；语义待核 → `n5-review-pending`；否则 `ok`。归档新增 `n5Summary`（真场景与对照分列），汇总门 `pass` 因状态编码 N5 而必然反映之。
- 复验：`python -B -X utf8 experiments/world-components/run_composition.py`（12 场景/对照全 expectMet；端到端四象限对照：空输出、明确错误文本、语义待核、正常输出——各得其所）。归档 `artifacts/world-components/n1-n5-composition-r2.json`（r1 原样保留）。

## #2 真实 tokenizer 长度门（Python + 浏览器，含特殊 token；128/129 边界；超限不调模型）

- Python：`run_composition.py` `RealTokenizer`（T5Tokenizer legacy=False，`input_ids` 含特殊 token）作为**模型调用前的权威门**；桩检查只留在冻结夹具契约内。边界用例由 `build_length_case` 构造恰好 128 / 129 真实 token 的输入：128 → 模型被调用；129 → `unsupported/input-too-long-real`、模型未调用（`n4RealTokens` 字段留痕）。
- 浏览器：`n4_browser_adapter.mjs` `generate` 在任何 session 调用前检查 `ids.length > 128`（ids 含追加的 EOS）→ 结构化 `unsupported`，`modelCalled:false`。
- 复验：上条组合命令（归档 `realTokenGate.boundaryCases` = {128, 129}）；`node browser_probe/run_adapter_probe.mjs` → 归档 `n4-browser-adapter-r2.json` 的 `boundary.exact128.modelCalled===true`、`boundary.exact129.refusedNoModelCall===true`。

## #3 N1 无法表达/无法解析 → incomplete，停止成功路径

- 改动：`narration_pipeline.py`——`INCOMPLETE_DIAGNOSTIC_CODES`（unsupported-narration-kind、supersede-only-change、destination/sanity/task-unresolvable、entity-unregistered、**unknown-delta-field** 新增）；`extract_facts` 对 delta 中未知字段记 `unknown-delta-field`；`run_pipeline` 遇阻断诊断即停，状态 `incomplete`。
- 复验：`python -B -X utf8 experiments/world-components/narration_pipeline.py --selftest`（S6 子任务 → incomplete、S6b 未知字段 → incomplete）；组合场景 `incomplete-subtask` 模型未被调用。

## #4 冻结记录/规则臂哈希关系修订（旧登记保留、新登记可跑、篡改被拒）

- 新登记：`artifacts/world-components/n3-rulearm-registration-r2.json`（由 `build_registration_r2.py` 按磁盘字节生成；重绑 runner 与冻结记录两项，其余依赖逐项复核与 v1 一致）；v1 原样保留。
- 旧记录可复核证明：`git show 2ef930e:artifacts/world-components/d2-n3-prompt-freeze.json | sha256sum` → `77b37b43…` == v1 钉值。
- gate8：`python -B -X utf8 experiments/world-components/n2_selection/n3_rule_arm.py --scope gate8 --registration artifacts/world-components/n3-rulearm-registration-r2.json --out artifacts/world-components/n3-rulearm-gate8-r2.json` → 8/8、差分 8/8、gate=True。
- 篡改探针：改 r2 冻结钉值后同命令 → exit 3 GATE 拒绝。
- 总修订记录：`artifacts/world-components/n3-freeze-amendment-r1.json`。

## #5 「老板已批准解码配置」表述纠正

- **（11-02 二轮统一，总指挥裁定）**批准状态统一为 `PENDING-TRACEABLE-OWNER-CONFIRMATION`：实现者转述（2026-11-01）与当日渠道内所有人口头确认（2026-11-02，`record_approval_confirmation.py` 所录）**均不作为批准依据**——仅可追溯的所有人原始确认可作依据；**即使将来批准也不解除 0.6B 暂停**。确认事件保留在 `approvalProvenance` 作为已发生事实记录。统一脚本：`unify_approval_pending.py`。文档三处（本文件、README、d2-gold-prep）已统一同口径。

## #6 0.6B 暂停在模型加载前生效

- `run_n3_arm.precheck_real` 新增 modelId 门（在 torch/transformers 导入之前拒）。复验：`precheck_real(当前记录)` 返回三条拒绝（modelId/approval/runner status）；`run_n3_arm.py --selftest` PASS（stub 路径不受影响）。runner 字节变更 → 冻结记录 `runner.status=PENDING-REVIEW`＋新 sha，待审查者复验后翻 EXECUTABLE。

## 11-02 二轮复审四项发现的处置

1. **无计数器绕过模型门**：`run_scenario` 在 `real_tok=None` 且模型在场时于调用前结构化拒绝（`stopped-at-token-gate`，模型未调用）；`FrozenN4.generate` 作为可直接调用的入口自带真实 tokenizer 计数自卫门（>128 抛错拒绝，不截断）。实证：组合归档 `gateChecks.noCounterRefused`（真实检查点在场、无计数器 → 拒绝）；`limit-real-129` 继续走 unsupported。
2. **批准状态统一**：按总指挥裁定统一为 `PENDING-TRACEABLE-OWNER-CONFIRMATION`（`unify_approval_pending.py`；2026-11-01 转述与 2026-11-02 渠道内确认均不作为批准依据，确认事件仅作已发生事实保留在 provenance；即使将来批准也不解除暂停）。precheck 恢复三条拒绝；三处文档同口径。复验可见的唯一批准依据仍为空——如实。
3. **P1 位置分量**：`extract_facts` 对 Position 的 slotId/relativeTo 逐分量前后对比。**（第一笔更新：分量变化现已表达为 `position_relative`/`slot_changed` 独立事实，本节当年的 `unsupported-position-aspect` 阻断码随之退役；同容器无变化的位置集仍记 `no-op-position-change` 并阻断；普通容器移动与"随移动保持不变的 beside 关系"不误拒；Position 未知键由新增的 `unknown-position-field` 扫描阻断。）复验：审查者 P1 原探针矩阵现产出分量级事实 + 冻结模型种类门停机、无渲染文本；自检 S6c/S6d 全过。
4. **gitignore 隐藏脚本**：四个新脚本（amend_freeze_fixround / build_registration_r2 / record_approval_confirmation / unify_approval_pending）位于被忽略目录，对 git status 不可见、普通提交会静默丢弃——已在 [提交清单](fix-round-commit-manifest.json) 的 `untrackedForceAdd` 显式列出（含当前哈希与 `git add -f` 要求），并附干净检出复验命令序列与提交前重对哈希纪律。

## 运行记录声明

本批与修复轮**未运行 N3 模型臂**（0.6B 暂停；无运行归档即无运行）；历史 N2 0.6B 归档早于暂停令，不作为本批运行。冻结材料本体（语料、holdout、检查点、基座）未动。
