# N3 规则臂交付说明（运行后另记，登记文件保持运行前字节）

日期：2026-10-30。登记文件：`n3-rulearm-registration.json`（运行前字节，未因运行改动；本笔随修复更新过一次钉值，更新发生在运行前并先于归档提交）。

## 归档哈希（完整文件字节）

| 归档 | SHA-256 | 摘要 |
| --- | --- | --- |
| `n3-rulearm-gate8.json` | `0d3354881512685c9d695a8c3b8e3ddd92af83fbb0feb2ac9e7a5b3ab28c21b0` | 8/8 生成，差分 8/8 与 build_gold_row 逐条一致；H1/H2 8/8、G1=1.0、pass=true（构造性：同一冻结约定的程序化实现）；逐项原始计划在归档 `plans` 字段；B1/B2 对照入 `baselines`（B1 G1F1=0.5333、B2 0.0，均 pass=false，仅历史对照）；n4_out_of_range 1 处（n3cap-07 5 事实组，已标记未切分） |
| `n3-rulearm-diag16.json` | `357201a8c3ddcb097f0f81652c10f20f7e774102af5f56ca72247b934001983a` | 16/16 生成，差分 16/16（同一 target ∩ facts 选集）；H1/H2 16/16、gate=false、pass=false（diagnostic-only）；B1/B2 对照仅限 gate8，本归档不含 |
| `n3-rulearm-probes.json` | `4293bf3ff665e2133cd1580b337d0e65e3b3dc5141fbf891ad158848020dd349` | T-P1..T-P7 全过（传递合并/首位 time/紧邻前驱保持重排/前驱改变归属随动/重名异体/非法拒绝/unsupported 拒绝/连续 time 探索） |

## 含义限定

规则臂过线仅证明程序符合冻结机械约定；不宣称模型能力、自然叙事、N4 质量或生产可用。未完成项见方案 §6。
