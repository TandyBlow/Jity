# N3 规则臂交付说明（运行后另记，登记文件保持运行前字节）

日期：2026-10-29。登记文件：`n3-rulearm-registration.json`（运行前字节，未因运行改动）。

## 归档哈希（完整文件字节）

| 归档 | SHA-256 | 摘要 |
| --- | --- | --- |
| `n3-rulearm-gate8.json` | `' + hashes['n3-rulearm-gate8.json'] + '` | 8/8 生成，差分 8/8 与 build_gold_row 逐条一致；H1/H2 8/8、G1=1.0、**pass=true**（构造性：同一冻结约定的程序化实现）；n4_out_of_range 1 处（n3cap-07 5 事实组，已标记未切分） |
| `n3-rulearm-diag16.json` | `' + hashes['n3-rulearm-diag16.json'] + '` | 16/16 生成，差分 16/16；H1/H2 16/16、gate=false、pass=false（diagnostic-only） |
| `n3-rulearm-probes.json` | `' + hashes['n3-rulearm-probes.json'] + '` | T-P1..T-P7 全过（传递合并/首位 time/紧邻前驱保持重排/前驱改变/重名异体/非法拒绝/unsupported 拒绝/连续 time 探索） |

## 含义限定

规则臂过线仅证明程序符合冻结机械约定；不宣称模型能力、自然叙事、N4 质量或生产可用。未完成项见方案 §6。
