# 交付项 2：模型、训练与运行时方案表

日期：2026-10-28。版本：C方案表0.3（0.2 → 0.3 追加 §3.1 任务进度表与 F14–F17：N4 六类短计划离线通过、N2 首轮对照、T5 零样本不适用该形状、0.6B 生成编号不懂视角；0.1 经 2026-10-29 复核轮修订：Mengzi 参数实数、F4 计时口径、F11 快照归属、MiniRBT 许可关闭、F2 版本来源注记）。依据：[组件接口表](component-contracts.md)（`79b8fa4`）、[C任务边界](README.md)（`886dfe8`）。本文只交方案与已核实事实，不运行模型、不产生质量结论；质量数字由交付项3的隔离实验产出。

证据分三类，引用时区分：**[实测]**=本仓库已提交试验/归档（可复跑核对）；**[核实]**=本轮本机核实（注明方法）；**[外部]**=官方模型卡/README（2026-10-28 抓取，锁定权重时逐项复核）。下载体积不是参数量，模型卡能力不代表本项目达标。

## 1. 已定事实（直接约束选型，不改）

| # | 事实 | 类别 | 证据 |
| --- | --- | --- | --- |
| F1 | transformers.js 4.3.1 web 版被拒：裸说明符、hub-only 文件解析、其 pinned ORT 1.31.0-dev 会话挂起 | [实测] | `run-classifier-trial.mjs` 头注 |
| F2 | ORT-web 稳定版 vendored 到 `/ort/` 由脚本直驱，可运行且计时；实际版本 1.30.0 来自 devDep `^1.30.0` 经 lockfile 固定——`copy-ort-assets.mjs` 只按文件名复制、无版本断言 | [实测] | `copy-ort-assets.mjs`、`package.json`/lockfile、分类器/标注器试验 |
| F3 | ORT wasm >1 线程的会话创建在本环境永久挂起（含 headless Edge，独立新页逐一验证），全部 ORT 推理按单线程计时；wllama 侧 4 线程正常 | [实测] | `run-classifier-trial.mjs` v2 头注、`run-target-benchmark.mjs` |
| F4 | MiniRBT-H256 浏览器 CPU 单线程全链：加载 2620ms、冷启动首推理 125ms、int8 热态每调用全链 7.7–10.1ms（中位 7.73ms、max 10.05ms；fp32 对照 10.3–15.3ms；含分词→feed→run→argmax），分词器对齐校验 PASS | [实测] | `classifier-trial-1791486826233-action.json`（已提交） |
| F5 | 同机同用例 Qwen3-0.6B 解析臂：compact 8/12 全调用中位 25.8s；split-state 11/12 子调用约 15s | [实测] | 同上 `reference` 字段及脚本头注 |
| F6 | MiniRBT-H256 全参微调（cuda）＋ONNX fp32/int8 导出＋数据纪律（评分句全排除）已走通；base 环境需 pyarrow 进程内桩 | [实测] | `train-action-classifier.py` 头注及正文 |
| F7 | CRF（Viterbi）对照轮在 cuda 跑完（30 epochs 固定预算、冻结切分）：与 MiniRBT 标注头同量级、未取代之；MiniRBT 头同轮 scored 批 greedy 7/12、constrained 8/12，CRF 臂数字见该 json 的 table/pairedFlips | [实测] | `crf-compare-1791714189547.json`（已提交） |
| F8 | 旧 span 任务的预登记封存门（per-field strict ≥90% 且 e2e ≤4s）从未以 `--with-acceptance` 评估，提交记录均为 not-evaluated；且该门属于旧 parse 任务体系，阈值不可平移到新组件任务 | [实测] | labeler/combo 试验 json 的 `acceptance.verdict` |
| F9 | Qwen3-0.6B Q4_K_M 真实浏览器叙事链：29 次调用 mean 13.986s、p50 13.497s（CPU 4 线程、n_ctx4096、maxTokens160） | [实测] | `artifacts/narration-eval-recheck/`（已提交） |
| F10 | wllama 3.8.1 打包的 llama.cpp wasm 内含 `t5`、`t5encoder` 架构字符串：T5 家族加载器已编译进 wasm；但其 JS API 能否端到端驱动 encoder-decoder **未验证** | [核实] | 本轮 `tr` 提取 `node_modules/@wllama/wllama/esm/wasm/wllama.wasm` 字符串 |
| F11 | MiniRBT-H256 权重快照（config.json＋pytorch_model.bin 41.5MB＋vocab.txt）**只在主工作树** 的 `artifacts/benchmark/minirbt-h256-snapshot`，被 `.gitignore` 排除、C 工作树内不存在——"微调不依赖网络"仅在主树成立；C 树开工须重新配置并记录获取方式 | [核实] | 本轮 `ls`（主树 frontend 相对路径）；C 树同路径不存在（复核轮确认） |
| F12 | Anaconda base：torch 2.7.0+cu126、transformers 4.57.3、onnx 1.21.0、onnxruntime 1.25.1 已装；**sentencepiece 未装**（T5 分词必需）；datasets/accelerate/peft 未装（当前方案不需要） | [核实] | 本轮 `importlib.metadata` 核查 |
| F13 | hf-mirror 对 Randeng 仓库 resolve 实测可达（本轮取回 config.json）；Mengzi 卡片经 huggingface.co 网页核到、mirror api 本轮空返回未通；MiniRBT 的具体 HF 仓库 ID 待定（GitHub 官方示例用 `hfl/minirbt-h256`，`iflytek/MiniRBT-H256` 本轮 resolve 401） | [核实] | 本轮 curl 实测 |

## 2. 骨干候选表（README 必填字段逐项）

| 字段 | MiniRBT-H256（编码器骨干首选） | Randeng-T5-77M-MultiTask（生成候选） | Mengzi-T5-base（容量对照） | Qwen3-0.6B（现役基线/对照臂） |
| --- | --- | --- | --- | --- |
| 全参数量 | 官方 10.4M（6层×隐256×8头）[外部] | 官方 77,440,384，复核轮与 safetensors.total 逐位一致 [外部] | **247,577,856（≈247.6M）**：HF safetensors.total 实数（复核轮经 mirror API 取元数据，未下载权重）[核实]；口径=encoder 7.08M/层＋decoder 9.44M/层（self 2.36M＋cross-attention 2.36M＋FF 4.72M，12+12 层）＋输入嵌入 24.67M＋lm_head 独立 24.67M（`tie_word_embeddings:false`）；独立复算 247,585,536 与实数差 7,680（LN/偏置零头）；此前 0.1 版 ≈223M 推算作废 | 0.6B；GGUF Q4_K_M 文件体积以锁定权重为准 |
| 架构/任务头方式 | BERT 编码器；每任务一个轻头（池化分类头／逐 token 标注头／句对 cross-encoder 打分头），**一份骨干多任务共享** | T5 encoder-decoder，text2text；任务即提示词模板 | 同左 | decoder-only chat；结构输出靠 GBNF/schema 约束 |
| 中文能力依据 | WWM 预训练＋两阶段蒸馏（官方README）；本仓库旧任务分类 8/8 旧批泛化、Python 侧 11/12 [外部+实测] | 在 Randeng-T5-77M 上用 100+ 中文多任务数据集（30万+样本）统一 text2text 微调；卡仅演示标签/摘要类短输出，无流畅度评测 [外部] | 300GB 中文语料预训练；卡无质量评测；社区用途为标点恢复/问答 [外部] | 本仓库叙事评测归档：requireTime 定档 natural 10/16，四失败模式已知 [实测] |
| 微调/蒸馏需求 | 每任务头全参微调（官方建议 lr≈1e-4、多于常规轮数）；微调期蒸馏可选非必需 | 先零样本测模板任务；N4 成句需本项目数据微调/评测；蒸馏暂不需要（模型够小） | 本轮仅作容量对照，不微调起步 | 不微调（基线臂）；提示词与操作点已归档 |
| 隔离开发样本 | 从接口表 V01–V09 检查族派生；标注=程序枚举＋人工复核，不用模型自标；按 README 排除 hv-*/nv-*/ns-* 及改名派生 | 同左；成句样本另需"事实计划→正文"成对语料，正文以程序模板句＋人工改写为种子 | 仅对照，不建训练样本 | 沿用已归档操作点作对照，不重用样本 |
| 离线框架 | torch 2.7.0+cu126＋transformers 4.57.3（已装，F12） | 同左＋**sentencepiece（缺，装后再跑）** | 同左 | llama.cpp 离线转换（工具与版本在 GGUF 化时锁定） |
| 导出图 | `torch.onnx` → fp32＋int8 dynamic（已走通，F6） | 未做；路径=optimum/手工导出 encoder、decoder、decoder-with-past 三图（相对位置桶与 KV cache 须保留） | 同左 | GGUF 转换即导出；转换脚本对 t5 架构的支持以锁定版本实测为准 |
| 量化 | int8 dynamic 已实测可跑（F4）；fp32 作对照 | fp16 先行；int8 后做且必须做量化前后质量对照 | 同左 | Q4_K_M 已归档（F9） |
| 浏览器运行时 | ORT-web 1.30 直驱＋手写分词器（已实测，F2/F4） | 首选 wllama GGUF（F10 架构字符串在，端到端未测）；备选 ORT 直驱（须自实现 JS sentencepiece＋decoder 循环，成本高，除非 wllama 路径证伪否则不做） | 同左（体积更大） | wllama（已接入，F9） |
| 分词器 | JS 手写 BertTokenizerFast 等价（中文按字、lowercase、ASCII wordpiece 回退），在跑对照 Python 参考 id 校验通过 [实测] | sentencepiece（unigram）；**浏览器侧 JS 实现是 T5 路线的最大单点成本**，wllama 路径则由 GGUF 内嵌 tokenizer 解决 | 同左 | GGUF 内嵌，llama.cpp 处理 |
| 取消/生成循环 | `session.run` 不可中途取消→AbortSignal 外包＋迟到结果按接口表 §2.1 隔离丢弃；加载与解码循环可取消 | wllama 有中断 API；ORT 直驱路径同左；生成循环=encoder 一次＋decoder 逐步（带 past），步数上限与早停显式配置 | 同左 | wllama 中断已在使用 |

许可状态：**三候选均声明 Apache-2.0**——Randeng/Mengzi 模型卡 [外部]；MiniRBT 经 `hfl/minirbt-h256` 模型卡 `cardData.license` 与 `license:apache-2.0` tag 核实（复核轮关闭；GitHub README 本身未标许可）。落实口径：Randeng 仓库无 LICENSE 文件（siblings 仅 README/config/权重/tokenizer，复核轮确认），Mengzi/MiniRBT 锁定权重时核对 LICENSE 文件；声明均以模型卡标签为准写入运行记录。

## 3. 组件×任务×方案映射

**首轮原则（防过度设计）：** 交付项3的首轮实验，一切生成类任务先走现有 Qwen3-0.6B＋wllama 通路（已接入、成本已归档），一切判别类任务先在生成骨干同一调用内完成（现任务形状即如此）；小模型头作为**逐个对照臂**验证，只有同时赢在质量和环境内总成本才替换。编码器骨干一份、多头共享，浏览器只加载一份 int8 权重；生成骨干一份（首轮 Qwen3-0.6B，T5 质量验证通过后才换）。

| 任务（接口表） | 形状 | 首轮方案 | 小模型对照臂（第3项验证目标） | 优先级依据 |
| --- | --- | --- | --- | --- |
| C2 行动：act/skip＋文本 | 分类＋生成（可合并） | 合并臂：生成骨干单调用结构输出（现 `action` 形状） | 拆分臂：编码器 act/skip 打分头＋生成文本。注意旧 5 类 action_type 是玩家命令解析任务，**不是** act/skip，旧头语料与标签不可复用 | V01 |
| C3 目标分析 | 多标签/候选打分＋生成 | 生成骨干列举＋程序核对（现 `targets` 形状） | 编码器候选实体对打分头（冻结行动原文×实体） | V02 |
| C3 反应文本 / C4 共同结果 | 条件生成 | 生成骨干（现 `reaction`/`results` 形状） | 长文本质量若不达标，升级容量对照（Mengzi/Qwen3-1.7B），不先拆小 | V02/V03 |
| C5 U1 位置 | 引用选择 | 生成骨干＋程序引用校验 | 编码器实体×地点/槽位打分头 | V04 |
| C5 U2 外貌 | 判别＋生成＋引用选择 | 生成骨干 | 判别用编码器二分类头；新描述生成仍生成骨干 | V04 |
| C5 U3 任务达成 | 全任务逐项判断（句对） | 生成骨干批量结构输出 | **编码器 cross-encoder 头（任务原文×结果/状态文本，逐任务分）**——全人物×全任务的批量判定是编码器最有量的场景 | V04/V05 |
| C5 U4 新小任务 | 生成 | 生成骨干 | 无（草稿键由程序分配，生成天然合适） | V04 |
| C5 U5 个性 | 逐人判别＋文本 | 生成骨干 | 判别头同 U3 方式 | V04 |
| C5 U6 理智 | 数值预测或受限分类 | 生成骨干结构输出 | 对照臂三选一：编码器分桶分类＋程序边界处理／小回归头／生成整数；**第3项必须含对照，不预设** | V04 |
| C6 继续判断 | 候选短生成＋双条件判别 | 生成骨干单调用（拟行动＋依据，程序核对双条件表述） | 拆分臂：生成骨干出候选＋编码器双头（发生可能性、主角关联）分别打分 | V06 |
| C0 time/pointPlan | 程序为主＋可选提议 | 程序参照（固定时间增量），模型提议列为可选 | 不单列小模型 | 原设计程序权威 |
| C1 初始世界 | 分批生成＋抽取判别 | 生成骨干（现 `initial` 兼容出口） | 排在最后（原设计集成顺序），方案随第3项结果修订 | R15/接口表 §3 |
| C7 N1 事实提取 | 程序枚举＋可选归类 | 程序（接口表 §5.2 已定：不让生成模型猜差异） | 编码器"变化类型"归类头仅作可选加速，不承担正确性 | V07 |
| C7 N2 内容选择 | 打分/引用选择 | 生成骨干（mustExpress 由程序硬性保底全收，模型只表达 mayMention 取舍——必述漏选=失败不变） | **编码器打分头（事实条目×视角）**：首轮优先验证 | 首批聚焦叙事 |
| C7 N3 组织表达 | 排序/分组/指代 | 生成骨干 | 编码器 pairwise 排序头；指代建议属生成侧 | 首批聚焦叙事 |
| C7 N4 成句 | 短文本生成 | Qwen3-0.6B（现役） | **Randeng-T5-77M 微调臂**：先离线验证质量（含模板种子微调语料），质量过了再走 wllama GGUF 端到端实测；浏览器化是质量门之后的事 | 首批聚焦叙事 |
| C7 N5 核对 | 程序核对＋语义复核 | 程序为主＋人工复核 | 编码器 NLI/一致性头仅作候选，不自动放行 | V08 |

### 3.1 任务进度（复核轮 21 修复）

**D1 更新（2026-10-29）：** v3 AI 独立标注已冻结，κ=1.0；既有输出重算与不降级结论见 [D1 交付](d1-ai-closure.md)。该结果不是人工评测，不增加 N2 模型质量通过记录。

阶段口径：**仅方案 → 已训练 → 离线验证 → 浏览器验证 → 已接线**。逐组件明细见[接口表 §8](component-contracts.md)。

| 任务 | 首选候选（当前依据） | 备选 | 阶段 | 本轮新增证据 |
| --- | --- | --- | --- | --- |
| N4 成句 | Randeng-T5-77M 全参微调 `r3-direction`（方向由程序给出） | Qwen3-0.6B（现役基线，未微调） | **离线验证通过**（六类短计划 44/44）；浏览器与接线未验证 | `n4-holdout-eval-r3-direction.json`、`n4-offline-package-r3-direction.json`（D3 离线包） |
| N2 内容选择 | MiniRBT 编码器打分头（事实×视角）——**尚未训练** | 0.6B instruct 生成编号（旧判据两轮均 4/16） | **v3 AI 标注冻结并重算，无模型通过；D1 不触发降级** | `n2-selection-r2.json`、`n2-labels-v3.json`、`n2-must-v3.json` |
| N3 组织表达 | 程序基线 B1/B2 先行（窄形状） | 0.6B instruct | **基线已实现＋I2 探针通过；模型臂未跑** | `n3-baselines-r1.json`、`n3-factids-smoke-r1.json`；承接见[N2 报告](n2-content-selection.md) §6 |
| N5 核对 | 程序识别器（Python，v5） | 编码器一致性头（不自动放行） | 离线可用 | `corpus_check.py`、13 例篡改自检 |
| C2/C3/C4/C5/C6/C1 | 生成骨干单调用（Qwen3-0.6B）为起点 | 编码器头拆分 | 仅方案 | — |

补充事实（本轮实测，编号续 §1）：

| # | 事实 | 类别 | 证据 |
| --- | --- | --- | --- |
| F14 | Randeng-T5-77M 基座在 N2 "编号选择" 形状上零样本无效：两种提示形态（指令在后 / 答案槽前置）均 0/16，输出复述事实行或无关短句 | [实测] | `artifacts/world-components/n2-selection-r1.json` M1a/M1b |
| F15 | Qwen3-0.6B 零样本在**补齐视角信息后**仍不守视角：16 项中 9 次选到视角不可知事实，must 覆盖 0.875，pass 4/16；单次约 24s（CPU 4 线程，真实 Edge＋wllama）。v1 的 11 次/14.37s 属设计缺陷批次，作废 | [实测] | `n2-selection-r2.json` M2 |
| F16 | 视角可见性可由程序严格判定：P1-rule 只读视角字段＋事实位置即 16/16、F1 0.818，且对"只改标签"免疫（0 项移动）、对"改视角"敏感（12 项移动）；读标签的参照臂在标签探针下移动 12 项 | [实测] | `n2-selection-r2.json` selfTest 与 P1 臂 |
| F17 | N2 开发集（v2）与 B 语料零字面重合：**9 组来源、4026 条串**（**含 <4 字短串**），双向子串 0 命中、0 缺失源；自检确认植入的 3 字人名与 2 字串都能被抓。口径为**冻结 B `world-browser` 提交 `8878e97` 的已提交语料**（`poolDigest d7613154…`、`sourceDigest cae219d3…`）；B 工作区未提交的 `b3-dbg-a6/a7/a8` 不计入冻结数，单列在 `excludedWorkingFiles`；同脚本的 live 诊断为 4048 串、0 命中。旧引用的 4023（未归档中间值）、4041（16:57Z 部分写入）与 4042（复核复跑）撤回。归档：`n2-isolation-r2.json`（2026-10-29T09:10Z） | [实测] | `n2_selection/check_isolation.py --archive` |
| F18 | D1 must 口径重算（只用归档输出，不新增推理）：P1-rule must-R 1.0 / must-P 0.433；Qwen must-R 0.875 / must-P 0.459；Randeng 0/16（空选择/无效内容）；P0 must-P 0.35。**P1-rule 的失败分支未在 v2 触发**（must-P<0.85），v3 标注后才可判定 | [实测] | `n2-must-r1.json` |
| F19 | N3 I2 旧检查把**整份计划**的 factId 集合当锚定域，跨组/全局 factId 篡改可漏检；改为只查**本句组 entityIds** 后，`--tamper` **九类**变异 144/144 适用项全部被捕获，16/16 有效计划零问题；新增**首位捏造 factId**与**空句组**两类，检查器返回违规列表而不抛异常 | [实测] | `n3-baselines-r1.json` 的 `tamper` |
| F20 | factIds 消费冒烟：36/36 B1 句组经共享渲染器喂冻结 `r3-direction`（离线 Python，cudnn deterministic、benchmark=False），本次归档墙钟均值 0.8s（同一检查点重复运行在 0.5–0.8s 间波动）；**仅证明 factIds 可被 N4 消费，coreference 未被 `render_input` 消费，跨组连贯未测** | [实测] | `n3-factids-smoke-r1.json` |
| F21 | 冻结 r3-direction 的 T5 encoder-decoder 以 fp32 ONNX（torch.onnx opset 17，encoder＋无 KV 缓存 decoder 步进图）在 headless Edge＋vendored ORT-web 1.30.0 单线程 wasm 运行：**7/7 case 与 ORT-python 贪心环逐 token 精确一致**（4 冻结留出＋3 合法扩展空间输入；预烘焙真实 spiece ids）。会话冷加载 7.0s、编码 98–358ms、步进 80–194ms（无缓存 O(n²)，localhost 静态服务非网络口径）。图级可行性证据，非整链验收 | [实测] | `artifacts/world-components/n4-browser-probe-r1.json`（批次1） |
| F22 | **（批次4更正）**批次3所记「HF 与 ORT 存在 fp32 再结合漂移」是**伪象**：当时 HF 臂因 `[input_len:]` 切片误用于 decoder-only 序列而整体为空（判分与浏览器对齐用的是 ORT 环，不受影响）。修正切片并统一「尾部 EOS 不入 id」约定后，**HF greedy 与 ORT-python 环在全部 7 个烘焙输入上逐 token 精确一致**；跨运行时对齐目标=ORT 环的结论不变且现在双向互证 | [实测] | `export_n4_onnx.py`（PARITY: EXACT）、`probe_inputs.json`（7/7 hf==ort，批次4） |
| F23 | 合法输入空间修复：共享渲染器/判据器覆盖六个 TimeAdvance 单位＋amount 0；冻结语料 648 计划字节等价、90 条归档输出复判一致；判据覆盖核心抽为 `check_narration(plan,text,refs,must)` 供 N5 管线复用（语料行为不变） | [实测] | `n4-units-regression-r1.json`、`n4-batch1-amendment-r1.json`（批次1） |
| F24 | N2 编码头候选实测否决：MiniRBT-H256 三分类头（must/may/omit，条目级两折 CV，每折 46 样本）在冻结 v3 集上 must-R 0.531、must-P 0.667，15/16 评测条目触发硬失败（must 漏选）；同折程序规则臂 must-R 1.000 / must-P 0.433（逐位复现归档 F18）。结论：当前数据规模下编码头不承担 N2 选择；扩展语料属新预登记事项 | [实测] | `n2-encoder-arm-r1.json`（批次2，GPU 环境单列：RTX 4090 D / torch 2.5.1+cu124 / transformers 4.51.3） |
| F26 | N4 浏览器适配验证（批次3）：自研 ONNX 图（encoder＋self-KV decoder 步进图，cross 注意力每步由图内重算——`from_legacy_cache` 的 4 元组契约会把 cross 标记为已算，trace 后 `encoder_hidden_states` 整个从图里消失，self-only 契约才可导出）＋ sentencepiece-js（真实 spiece.model 经垫片加载，id 与 Python T5Tokenizer 逐位一致——T5 需补尾 `</s>`=1）＋ KV 贪心环：headless Edge 中 **7/7 case fp32 生成与 ORT-python 环逐 token 精确一致**；int8 动态量化 5 case 判据全净（2 例换合法等价措辞）；AbortSignal 步级取消实测生效（步 4 AbortError，部分结果不落地） | [实测] | `n4-browser-adapter-r1.json`、`n4-int8-quality-r1.json` |
| F27 | 单线程 wasm 的 ORT run 同步执行且 Promise 在微任务级联内解决：连续 await 的生成循环会**饿死宏任务**——setTimeout 的取消信号永远不触发、页面冻结。适配器每步显式 `setTimeout(0)` 让出宏任务后取消才可观测（实测步 4 生效）。这是 B 侧接线的硬约束 | [实测] | `n4-browser-adapter.mjs` 头注、`n4-browser-adapter-r1.json` abortTest |
| F28 | 批次4真实模型组合：程序 N1→N2→N3＋冻结 r3-direction N4（HF generate，fp32 贪心 64，CPU 离线——本地 GPU 不动，GPU 任务按指令走外部 GPU 环境）＋程序 N5。五场景全过预期：三个正常路径真实成句且 **N5 全净（0 fail / 0 uncertain）**，版本断裂在绑定层停机（模型未被调用），五事实计划 unsupported（模型未被调用）。离线单次成句 315–1622ms（CPU fp32）；浏览器证据仍为批次3归档，两口径不合并。冻结评测的解码路径（`decode(out[0])` 不切片）复核无误 | [实测] | `n1-n5-composition-r1.json`、`run_composition.py`（批次4） |
| F29 | N4 v2 grouped 语料与训练（commit 2）：三个新故事族（渔市 A/山驿 B/盐场 C，与旧 28 名池、D2 与 B 冻结池零命中），514 行训练/开发＋66 行 family-C 冻结测试；案例矩阵覆盖跨句指代、同名、性别未知、时间三位置、新种类、同现、无变化、个性增删改。Randeng-T5-77M 全参微调走 HPC（RTX 4090D）：**12 epochs×54 步=648 步，37.1 秒**，fp32，seed 20261102；训练器内建 holdout sha 守卫与渲染器字节守卫。冻结测试：硬门 64/66、代词使用率 1.0（阈值 dev 固定）、消融差分 39/43；两处失败（subtask 句末缺句号、co-presence 第三实体未覆盖；后者属旧 N1 口径）如实入册 | [实测] | `n4-v2-corpus-report.json`、`train-v2-report.json`、`n4-v2-holdout-eval.json`、`n1-n5-composition-v2-r1.json` |
| F30 | N4 v2 浏览器适配（commit 3）：encoder＋self-KV decoder 图在 headless Edge＋ORT-web 单线程 wasm 中跑 grouped 接口；8 个 family-C 场景 **8/8 分词 ID 与 Python 一致、8/8 token 序列与 ORT-python 精确一致、文本逐字相同**；生成 0.29–2.00 秒（步均 26–51 ms），冷加载 3.56 秒。浏览器文本经 v2 判据 **6/8**，失败与离线 holdout 相同（co-presence case 属旧 N1 口径）。**HF↔ORT 的 fp32 再结合漂移**：8 例仅 2 例逐 token 精确，6 例在近并列 token 处翻转（logit 差约 1e-5）；浏览器对齐目标为 ORT-python 同引擎族，不宣称 HF 精确等价 | [实测] | `n4-v2-browser-adapter.json`、`n4-v2-browser-parity-python.json` |
| F31 | N5 关系头（commit 3）：MiniRBT-H256＋masked-mean-pool＋linear(3)，数据来自 v2 语料（训练 6764 pair：5919 train＋845 dev；冻结测试 758：256/246/256，8 类程序扰动，family C only，freeze sha 先登记）。HPC 8 epochs/1480 steps/31.3 秒。阈值在 dev 上按预登记规则固定为 0.4/0.4；冻结测试 support 0.9805、contradiction 0.9959、wrongPass 0、**wrongReject 5/256**、unknown→unknown 0.8906。G1/G3/G4 通过，**G2 失败，pass:false**；不调阈、不改门 | [实测] | `n5-corpus-report.json`、`train-n5-report.json`、`n5-relation-eval.json` |
| F35 | N3 跨组代词守卫 smoke（真实 ckpt-v2，4 个历史 v2 行，facts 固定以隔离 N3）：守卫移除 3 个授权（cross-reference 1、alternating 1、core-move-task 1；conflict 0），旧/新计划的事实组与时间完全一致；按**新计划**判分，**3/4 通过** v2 硬门。alternating 行模型仍用“他”把秦叔的任务挂到闻人镜，G1/G2 失败；r1 曾用旧计划的授权判分而误报 4/4，r2 更正并保留 r1 作为判分错误记录。**守卫必要但不充分，N4 在 guard-on 输入下仍需重训/评估**；旧 v2 语料/评测仍是 guard-off 口径 | [实测] | `n3-coref-guard-smoke-r2.json`、`run_coref_guard_smoke.py`（r1 保留为错误判分记录） |
| F40 | N2→N3→N4 管线输入预览 v0（已审通过语料）：N2 `select + visible_other_actions=True` 选入同地他人 moved/outcome/可见变化（task goal/status 与 inner state 仍不可见），N3 `plan_v3`，N4 `render_plan_input`。12/12 无丢弃 fact，N3 `check_plan_v3` 全 ok；输入 **251–347** tokens，目标 75–99。旧 v2 臂不传 flag，行为不变；N1 仍未产出 `outcome/resultText`，`run_pipeline_v2` 未参数化，故为直接 N2→N3→N4 预览，不是生产链；未训练 | [preview] | `n4-narrative-pipeline-input-preview.md`、`n4_narrative_dev/{preview_pipeline_inputs.py,pipeline_preview.json,render_narrative.py}` |
| F39 | N4 叙事输入预览 v0（已审通过语料）：12 例输入 **238–329** 真实 token，目标 **75–99**；输入含场景/地点外貌/小地点/可见物/在场人物性格与外貌/事实约束，任务 goal/ID 不进入，理智只给呼吸方向，时间只写“过去了一会儿”；不含具体时长、数值面板、任务标题。当前 v2 N4 `max_input=160`/`max_output=96` 不够；新训练建议 `max_input≥384`、`max_output≥128`（T5 支持 512）。12 例只是开发集，训练需扩样；未训练 | [待接线] | `n4-narrative-input-preview.md`、`n4_narrative_dev/{render_narrative.py,preview_inputs.py,input_preview.json}` |
| F38 | N4 叙事开发语料 v0（已审通过）：新世界族 `n4n-fog-harbor` 12 例，目标是场景/行为/视角心理，不是逐条复述；任务 goal 仅隐藏动机，表面只用 resultText；时间事实只内部、正文不写具体时长；理智用心理/行为、外貌/个性用可见细节；角色个性写入语料读取上下文（不要求体现；N4 renderer 尚未接线）；禁止新增具名实体/物品/地点、他人内心、新增世界事件、承诺性对话与数值面板。世界状态含地点外貌/小地点层级/物品表/人物 inventory，每例有 sceneState 与逐句 Grounding；语料与 v2/v3 零人名/地名命中；`outcome`/定性理智是提议契约，N1/N5 未实现；未跑模型、未训练，12 例 reviewStatus=approved（用户 2026-11-02 审阅通过；开发集，非训练集/留出集） | [已审通过] | `n4-narrative-dev.md`、`n4_narrative_dev/{world.json,corpus.jsonl,review-checklist.json}` |
| F36 | N4 v3 语料/目标（优化实验）：从 v2 行派生，事实/世界固定；删旧 N1 共现 positioned_at 886 条；N3 guard-on plan；compose_v3 把同一实体内事实合并成一句（不同实体不合并）。v3 目标 78 句（v2 193），平均 1.04 句/组、2.41 事实/句；v3a 为同输入、旧的一事实一句目标（125 句，1.67/1.50）。family-C 行复用 v2 冻结行，是直接对照，不是新独立留出集 | [实测] | `n4-v3-corpus-report.json`、`n4-v3a-corpus-report.json`、`build_corpus_v3*.py`、`compose_v3.py` |
| F37 | N4 v3 训练/评测：HPC RTX 4090D，12 epochs/648 步/约 41 秒，基座复用远程。guard-on 输入上旧 v2 模型 48/66；v3a（一事实一句）60/66；v3b（merged）62/66，表面 1.03 句/组、2.64 事实/句，合并风格成功转移。v3b 失败 4 行：alternating 丢中间任务、same-name 重复首任务、time-mid 任务挂先行者、new-subtask 括号残缺。**硬门未超过历史 v2-on-v2 64/66；v3b 是 guard-on 候选，不是默认替换**。旧 v2 仍是 guard-off 基线 | [实测] | `n4-v3-holdout-eval-v3model.json`、`n4-v3a-holdout-eval-v3amodel.json`、`n4-v3-holdout-eval-v2model.json`、`n4-v3-style-diagnostic.json`、`train-v3-report.json`、`train-v3a-report.json` |
| F34 | N3 程序规则诊断（审查后）：`n3_eval/run_n3_plan_eval.py` **28 个构造用例**（基础 25 + 跨组守卫 3），判据先登记；基础 25 旧 plan_v3 20/25，修正后 25/25；含守卫 28/28。修正：R2 同目标合并增加“同解析地点且地点名不歧义”前提（地点不同/缺失/歧义不合并；三条按地点成对合并）；孤立 no_change 改为合法单组；**跨组代词守卫默认开**（前一组存在不同同代词实体则拒绝授权，legacy 关守卫可复现旧 v2 计划）。重跑 v2 全部 580 个计划：组/时间 0 差异；守卫开启时 214 行（194 train + 20 holdout）coref 变化，legacy 关守卫 0 差异；组合链 select+legacy 臂 3/6 状态不变。仍留：守卫仅看前一组/长程链、场景时间作用域、实体桶重排、组大小/句界。N3 模型臂未跑 | [实测] | `n3-plan-v3-eval-r2.json`、`n3-coref-guard-impact-r1.json`、`run_n3_plan_eval.py`、`run_coref_guard_impact.py` |
| F33 | 审查修正（N1/N2 口径）：N1 删除“目的地在场者”扫描（`state.characters/items` 中与 moved 目的地相同的实体不再自动成为 `positioned_at`）；同处一地不是“注意到”，也不是一次状态变化。回归 S4/S4b：同行者场景只输出 delta 事实，100 NPC 目的地只输出 `moved`+`time`。N2 的 v2 管线默认改为 `omit`（只选 must），`select` 降为显式对照臂；组合链归档是 select 臂。`gender_hints` 明确为实验输入，不在状态结构，默认保名。旧 v2 co-presence 语料/评测/浏览器 case/N5 positioned_at pair 标为旧口径；冻结语料与模型不重写、不重训 | [实测] | `narration_pipeline.py` S4/S4b/S17c/S17d；README 审查修正 |
| F32 | N5 ONNX＋浏览器（commit 3）：encoder+mean-pool+head 融合单图，24 个烘焙 pair 的 HF↔ORT-python max-abs logit 漂移 6.44e-6（门 1e-4）；浏览器手写 BertTokenizer 等价分词＋ORT-web：24/24 分词 ID 一致、24/24 logits 在 1e-4 内（最大 7.03e-6）、24/24 冻结阈值标签一致；单次 25–134 ms（p50 23.4 ms），冷加载 1.52 秒。**一致性通过不等于质量门通过**；B 页面门未接线 | [实测] | `n5-onnx-export.json`、`n5-browser-probe.json` |
| F25 | N3 runner 钉定完成：已审查字节（7189e233…，signoff-f9c1190）写入冻结记录 `runner.status=EXECUTABLE`；解码配置获批（贪心 / maxNewTokens 512——256 方案在审查者实测最宽 gold 321–386 token 面前会必然截断，经负责人改批 512）；`decodingConfig.modelId` **保持未钉**——唯一门级生成候选是 0.6B 因果 LM，其推理被总指挥暂停，runner 的 modelId 门恰好编码该暂停；暂停解除后钉 modelId 即可开跑 | [实测] | `d2-n3-prompt-freeze.json`（批次2 状态行）、`pin_n3_freeze.py`、`precheck_real` 空问题单 |

## 4. 训练方案表


每头一行；数据纪律统一按 [README 样本隔离](README.md)：排除 hv-*/nv-*/ns-*、B历次校准实例与改名派生，来源组哈希登记，评分/验收样本与训练语料显式分离（F6 的纪律照用）。

| 任务头 | 基座/结构 | 训练数据来源 | 预算参考 | 评估 |
| --- | --- | --- | --- | --- |
| act/skip（C2 拆分臂） | H256 池化二分类头 | V01 场景派生：pending/consumed、主角/非主角、可执行/不可执行 | H256 全参微调 cuda 分钟级（10.4M；F6 先例 30 epochs 量级） | 开发批指标＋预登记门；门值由第3项定，**不照抄 F8 旧门** |
| 目标打分（C3） | H256 cross-encoder（行动原文×实体） | V02：脚本化构造牵连/非牵连对＋人工复核 | 同上 | 同上＋误杀/漏标分列 |
| U3/U5 判别（任务达成、个性变化） | H256 cross-encoder（任务或个性原文×状态/结果文本） | V04/V05 派生；全名册批量判定样本；合法"无变化"必须占一定比例防全yes偏置 | 同上 | coverage 完整性单独核（接口表 §C5） |
| U6 理智对照臂 | 分桶分类头 / 回归头 | V04 有个性变化的联动样本 | 同上 | 与生成臂同批对照 |
| N2 选择打分 | H256 打分头（条目×视角/必选标签） | V08 派生：mustExpress/mayMention/省略理由 | 同上 | 必述漏选=硬失败单列 |
| N3 排序 | H256 pairwise 头 | V08：句序、指代链 | 同上 | 逆序/碎序分列 |
| N4 成句 | Randeng-T5-77M 全参微调（含卡上 100 extra token 的 resize 注意项 [外部]）；**v2 grouped 接口（commit 2）** | "事实计划→正文"成对语料：程序模板句为种子＋人工改写（隔离新建）；**v2 改为程序 case-matrix 生成、先冻结后训练** | 77M cuda 分钟级；fp16 先行；**v2 实测 12 epochs/648 步/37.1 秒（HPC RTX 4090D）** | 离线：事实忠实/必述覆盖/时间/空点/中文自然度＋人工核对；**扁平 44/44 已过；v2 64/66（2 处残留）**；浏览器适配已做（v2 8/8 token 对齐） |
| 共同结果/反应/行动文本（升级臂） | Mengzi-T5-base 或 Qwen3-1.7B（仅当 Qwen3-0.6B 质量不达标才启动） | 不预建 | 届时定 | 届时定 |

不做的事：不训七份独立权重（骨干共享）；不先做蒸馏（教师标数据=程序枚举＋人工，模型蒸馏等小头质量瓶颈出现再议）；不用模型生成训练数据当监督源（接口表 §2.2 语义候选不得自证）。

**例外（方向 2026-10-29 问答选定；条款文本未经单独确认，以下为待确认草案）：N4 成句语料按事实/风格分层。** 事实计划由程序枚举构造并经权威校验；模型生成正文改写行。模型改写正文**承载事实主张**，逐条事实审核（planRefs 下标、必述覆盖、人物归属、方向、数值、任务引语、新增事件扫描）是其**准入条件**，不因生成用途的称呼而豁免；全部改写行另须协调人抽验，带 `rewriter` 标记、可整组剔除做消融对照。该例外仅覆盖 N4 正文改写行；上段约束对事实标签、判别头语料及其他监督来源继续适用；条款文本经单独确认前不作为已批准的方案变更。语料按组交付抽验，通过后才进微调；首批行数是构造与训练流程试验，不预设足以训练好 77M。

## 5. 运行时选型结论（本项交付核心）

1. **编码器路线（已定，不再重开）：** ORT-web 1.30.0 vendored 稳定版直驱＋手写 BertTokenizer 等价分词器＋int8 dynamic，单线程（F1–F4）。重评 transformers.js 的唯一条件：其新版修复 F1 全部三条且其 pinned ORT 在本环境不再挂起——否则不立项。
2. **生成路线（两步走）：** 近期全部生成任务用 Qwen3-0.6B＋wllama 跑质量基线；Randeng-T5-77M 先离线质量验证（含微调）。N4 的浏览器路径已走 ORT 直驱＋自实现 sentencepiece（sentencepiece-js），扁平 r3-direction 7/7、v2 grouped 8/8 token 对齐；wllama GGUF 端到端（F10）保留为生成骨干候选，不因 N4 结果自动推广到其他生成任务。**v2 质量门未全绿（64/66），浏览器适配通过不解除质量缺口与 B 侧接线验收。**
3. **共存与加载：** 编码器 int8 权重约 10–12MB 一份＋生成骨干一份；wllama 与 ORT 会话可并存但总内存与切换开销由第3项实测计总账（README 第4项交付要求），本文不预设数字。
4. **取消语义：** 统一 AbortSignal；ORT 不可中断 `run`，靠迟到隔离（接口表 §2.1）；wllama 用其已有中断。加载阶段可取消。
5. **WebGPU（jsep 文件已 staged 但从未测）：** 不立项、不做承诺；单线程 wasm 已满足编码器头量级（F4 毫秒级），生成侧瓶颈在自回归步数而非并行度。

## 6. 环境与通道待办（第3项开工前置）

- `pip install sentencepiece`（T5 离线分词必需，F12）；pyarrow 桩沿用 `train-action-classifier.py` 方案（F6）。
- MiniRBT ID 与许可已核（复核轮：`hfl/minirbt-h256`→200、`iflytek/MiniRBT-H256`→401、许可 apache-2.0）；Randeng/Mengzi 权重走 hf-mirror 下载。下载后许可落实：Mengzi 核对 LICENSE 文件；Randeng 仓库无 LICENSE 文件，以模型卡声明为准（§2 许可段）。
- Randeng 微调开工时：`T5Tokenizer` 的 legacy 分词行为须显式决策——`legacy=False` 会改变当前默认分词/规范化，训练、开发评估与零样本基线必须统一同一设置并重新验证后再比较（冒烟 r2 报告的 tokenizerConfig 记录了当前默认态）。
- 在 C 工作树重新配置 MiniRBT-H256 快照并记录获取方式（F11：主树快照不入库不共享；通道=hfl/minirbt-h256 经 hf-mirror）。主树 `train-action-classifier.py` 头注仍写旧 ID `iflytek/MiniRBT-H256`（历史注释、不影响产物；正确 ID 以 F13 为准，脚本修正归 B 线后续批次，C 运行记录只用正确 ID）。
- 浏览器分发：`public/models/` 当前为空（模型文件不入库），重建路径=各 train 脚本导出＋`copy-*-assets.mjs` 机制（已有）。
- N4 语料现为 150 组 / 600 行（构造器 v9.2），行校验/去重/A 侧权威核对全绿；dev 按渲染输入归并为 56 个独立输入（53 未见 / 3 回归）。两档 `--tier small|large` 均 360 步（`r2-small`/`r2-large`）；方向单变量臂 `r3-direction` 只改共享渲染器，53/53 未见输入过识别器并经复核保留。独立留出验收：`n4_holdout/`（新词表，冻结集实际覆盖 9/11/13/18 分钟，44 未见 + 1 共享回归），冻结清单 `freeze-r3-direction.json`，一次运行 44/44 + 1/1 pass；冻结校验已含训练报告、留出权威报告与解码配置（13 例自检），`--verify-only` 可只验证不推理。口径与两项收口见[语料协议 §9–§12](../../../experiments/world-components/n4_corpus/corpus_protocol.md)。
- 旧试验资产只复用**方法学**（数据纪律、封存批协议、计时口径、导出脚本骨架）；旧语料、旧标签体系、旧门阈值一律不复用（F8）。

## 6.1 同条件比较协议（复核轮 18 增补，待执行）

现有 N4 结果只证明 Randeng-T5-77M 在限定 N4 任务上"可用"，**没有证明它是最佳配置**。后续选型按下列顺序，不再按参数量或单次推理时间下结论：

1. **每个任务先定少量候选（2–3 个）**，包含：任务的首选候选、一个容量对照或架构对照、以及**程序/模板基线与现役 Qwen 基线**（有可比对象时必须纳入）。
2. **同输入、同判据、同解码**：同一开发集文件、同一判据脚本、同一贪心/温度设置；分栏记录每臂原始输出。
3. **报告三件事**：质量（任务判据的三态与人工抽验）、中文自然度（人工、抽样）、**环境内总成本**（加载、每调用、串行总账、回退率；离线与浏览器分开记，不混算）。
4. **先小后大**：小规模对照足以否决候选；通过后再决定是否投入训练/微调。
5. **数据纪律**：训练与调参用开发集；**已用于验收的 N4 独立留出集保持独立用途**，不再参与任何选型或调参；新任务各自建隔离开发集，来源与哈希登记。
6. 失败与回退单独统计，不能把模板输出算作模型通过。

已按此协议完成的对照：N2 首轮（P0/P1/M1a/M1b/M2，见 [N2 报告](n2-content-selection.md)）；N4 两档（r2-small/r2-large）与方向单变量（r3-direction）也按同输入同判据执行。

## 7. 明确未验证清单

T5 浏览器端到端；JS sentencepiece；T5 微调后质量；多模型共存内存与切换开销；WebGPU/jsep；H288 变体；编码器各新头的真实质量； ort int8 对 T5 的量化损失。以上全部留待交付项3/后续批次以实验关闭，本文不宣称其中任何一项成立。

## 8. 对交付项3的输出要求（本文的验收挂钩）

第3项报告必须产出：每对照臂的隔离开发批质量数字；编码器头每次调用全链耗时（同 F4 口径）；T5 质量门结果与浏览器化可行性结论；编码器＋生成骨干共存时的加载/切换/端到端总账（对照 F9 的 Qwen 单模型账）；失败与回退记录。缺任何一项即未完成交付项3。
