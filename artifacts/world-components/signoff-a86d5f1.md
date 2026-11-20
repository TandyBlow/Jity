# N3 规则臂签认记录（程序对照臂）

日期：2026-10-30。签字：C 审查者（复审结论）。记录：C 实现者。
签字对象：`a86d5f1`（含修复笔 `36a3776`、归档笔 `9f06905`；`world-components`，已推送）。
范围：**c66236b 五项问题全部关闭**，程序对照臂（规则臂）的实现、登记、归档与交付说明通过复审。

## 复审方式

C 审查者在独立 `core.autocrlf=true` 新鲜克隆中复核：规则臂、间接依赖（`n3_plan`）、登记文件、三份归档与交付说明的工作区、提交 blob 与实现者工作区字节一致；自检、gate8 与 diagnostic16 重放通过；冻结记录、输入与 `n3_plan` 的登记错钉探针均被拒绝。

## 证据哈希（工作树＝HEAD blob＝实现者工作区，sha256）

| 文件 | sha256 |
| --- | --- |
| `experiments/world-components/n2_selection/n3_rule_arm.py` | `75bee589987f72c1…`（完整值见登记文件钉值） |
| `artifacts/world-components/n3-rulearm-registration.json` | `cbdc6be8532c9ccc…`（运行前字节，未因运行改动） |
| `artifacts/world-components/n3-rulearm-gate8.json` | `0d3354881512685c…` |
| `artifacts/world-components/n3-rulearm-diag16.json` | `357201a8c3ddcb09…` |
| `artifacts/world-components/n3-rulearm-probes.json` | `4293bf3ff665e213…` |
| `artifacts/world-components/n3-rulearm-delivery.md` | `520e618b91c8040b…` |

完整哈希以各文件内容与 [`n3-rulearm-delivery.md`](n3-rulearm-delivery.md) 为准。

## 结果与限定

- gate8：8/8 生成、差分 8/8 与 `build_gold_row` 逐条一致、H1/H2 8/8、G1=1.0、pass=true；diagnostic16：16/16、gate=false；探针 T-P1..T-P7 全过；`n4_out_of_range` 1 处已标记未切分；B1/B2 对照入档（仅历史对照）。
- **含义限定**：规则臂结果仅证明程序符合冻结的机械约定；不宣称模型能力、自然叙事质量、N4 质量或生产可用。

## 未关闭项

- 模型臂是否立项、runner 钉定、真实推理：继续按暂停指令等待总指挥与项目负责人安排。
- N4 超限切分方案未立项；指代表达未验证（N4-coref）；浏览器整链未测。
- `signoff-f9c1190.md` 仍未跟踪，原样保留（其入库由后续指令决定）。
