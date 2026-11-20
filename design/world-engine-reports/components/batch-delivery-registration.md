# C 批次交付总登记（五次提交安排，2026-11-01）

> **2026-11-02 补记：** 本文是「五次提交」安排的历史集中登记，不再是当前唯一进度入口。其后按「三笔预算」完成的 N3 plan_v3／N4 v2 grouped／N5 关系头及浏览器适配见 [README 交付进度](README.md)。本文「仍未完成」中的 N4-coref 与 N5 JS 项已有后续证据，但**N5 质量门 G2 未过、N4 v2 仍有 2/66 残留**，不能据本文旧状态或新浏览器一致性宣告完成。**Qwen3-0.6B 已退役（2026-11-02）：本文的 0.6B 暂停/modelId 门是历史记录，不再有“解除暂停后启用”的路径；见 [退役记录](model-retirement-qwen3-06b.md)。**

对象：总指挥「五次提交」安排下 C 分支（`world-components`）的全部交付。基线 `2ef930e` → 顶端本笔。每笔同轮推送 `origin/world-components`。本文是集中登记；逐批细节见 README「交付进度」与各证据归档。

## 提交清单

| 笔 | 提交 | 内容 |
| --- | --- | --- |
| 1 | `5b0c805` | 合法输入单位扩展（渲染器/判据器）＋N1–N5 可运行管线＋N4 浏览器最小可行性探针＋隐私整改 |
| 2 | `b5e041e` | N3 runner 按签认钉定＋解码配置获批（modelId 暂停编码）＋N2 编码头实测否决 |
| 3 | `2ae199f` | N4 浏览器适配集中交付：KV 缓存图＋sentencepiece-js＋int8＋步级取消＋Python 对齐 |
| 4 | `c717c71` | 真实模型组件组合＋N5 核对（正常/失败/超限）＋F22 记录更正 |
| 5 | 本笔 | 最终集中登记＋全门终验 |

## 验证命令与结果（终验口径，本笔复跑）

| 门 | 命令（在 `experiments/world-components/` 或注明） | 结果 |
| --- | --- | --- |
| 判据自检 | `python -X utf8 n4_corpus/corpus_check.py` | 23/23 负例＋3/3 等价式；150/150 组一致 |
| 单位扩展回归 | `python -X utf8 n4_corpus/n4_units_regression.py --out <artifacts>/n4-units-regression-r1.json` | 648 冻结计划字节等价、90 条归档输出复判一致、新空间 9/9 |
| 接口夹具 | `python -X utf8 n2_selection/n3_n4_fixture.py --selftest`／`--out` | 28/28 |
| N1–N5 管线自检 | `python -X utf8 narration_pipeline.py --selftest` | PASS（含合法 `second`、零时长端到端） |
| ONNX/贪心环对齐 | `python -X utf8 n4_corpus/export_n4_onnx.py --verify-only` | PARITY: EXACT（HF greedy == ORT 环） |
| KV 缓存图 | `python -X utf8 n4_corpus/export_n4_onnx.py --verify-only --kv` | KV-EXACT（与无状态环逐 token 一致，23.5ms/步 CPU） |
| int8 质量门 | `python -X utf8 n4_corpus/quantize_n4_onnx.py --verify-only` | 5/5 判据全净（2 例合法等价措辞） |
| 组合链 | `python -X utf8 run_composition.py` | 5/5 场景符合预期；N5 全净；失败/超限模型未被调用 |
| 浏览器适配 | `node browser_probe/run_adapter_probe.mjs`（需 node_modules） | 分词 7/7 逐 id 一致、fp32 生成 7/7 逐 token 对齐、取消步级生效 |
| 隔离 | `python -X utf8 n2_selection/check_isolation.py` | 0 命中 / 0 缺失源 |
| 隐私扫描 | `python -X utf8 experiments/world-components/scan_privacy_paths.py` | 驱动绝对路径 0；余 13 处均为版式说明或审查者文档（见下） |

## 仍未完成的能力（如实登记，不缩小验收）

1. **N2 模型臂**：编码头被批次2实测否决（must-R 0.531，15/16 硬失败）；扩展语料/换任务形状需新预登记，本批未做。
2. **N3 模型臂**：runner 已钉、解码已批，**modelId 未钉**——唯一门级生成候选 0.6B 在总指挥暂停令下；暂停解除后钉 modelId 即可按预登记通过线运行。
3. **N4 浏览器接线的 B 侧部分**：页面接线、共存开销总账（README 交付项4的账目）归 B；C 已交经验证的 adapter 模块与两条硬约束（宏任务让出、ORT 环对齐目标）。
4. **N4-coref／跨组连贯**：coreference 仍未被渲染消费，跨句衔接未测（既有登记，未变）。
5. **正式留出集**：各组件新留出集与正式泛化结论仍待规则冻结后独立建立；本批全部为开发集证据。
6. **C1–C6**：仍在接口方案，无训练与质量证据（原范围不变）。
7. **B 侧门控的 JS 判据**：N5 的 JS 运行时版本未交付（B 门控继续用现有实现）。

## 交接与待复审项

- **冻结记录取代**：`freeze-r3-direction.json` 的渲染器/判据器/训练报告旧钉值按预期失效（修订证据 `n4-units-regression-r1.json`＋`n4-batch1-amendment-r1.json`）；冻结材料本体（语料、holdout、检查点、基座、解码配置）经 `--verify-only` 证明未动。请审查者对修订哈希复验。
- **审查者文档的 `.local` 引用**（`review-148f412.md`、`review-cf22a65.md`、`signoff-d5ca042.md`）：按隐私边界属审查者自改项，C 未代改。
- **其他辖区泄漏**：`artifacts/benchmark/*` 与共享设计文档中的本地路径属 B 辖区/共享提交来源，已单列上报总指挥，不在 C 笔内改动。
- **F22 更正**：批次3「HF-ORT 再结合漂移」为切片伪象，已更正（HF==ORT 逐 token）；浏览器对齐结论不变。
- GPU 任务按指令走外部 GPU 环境（批次2 N2 训练实测）；本地 GPU 除批次1探针前的环境核查外未动，组合链与浏览器验证均为 CPU/wasm 口径。
