# 交付项 2：模型、训练与运行时方案表

日期：2026-10-28。版本：C方案表0.2（0.1 经 2026-10-29 复核轮修订：Mengzi 参数实数、F4 计时口径、F11 快照归属、MiniRBT 许可关闭、F2 版本来源注记）。依据：[组件接口表](component-contracts.md)（`79b8fa4`）、[C任务边界](README.md)（`886dfe8`）。本文只交方案与已核实事实，不运行模型、不产生质量结论；质量数字由交付项3的隔离实验产出。

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
| F11 | MiniRBT-H256 权重快照（config.json＋pytorch_model.bin 41.5MB＋vocab.txt）**只在主工作树** `D:/others/Jity/artifacts/benchmark/minirbt-h256-snapshot`，被 `.gitignore` 排除、C 工作树内不存在——"微调不依赖网络"仅在主树成立；C 树开工须重新配置并记录获取方式 | [核实] | 本轮 `ls`（主树 frontend 相对路径）；C 树同路径不存在（复核轮确认） |
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
| N4 成句 | Randeng-T5-77M 全参微调（含卡上 100 extra token 的 resize 注意项 [外部]） | "事实计划→正文"成对语料：程序模板句为种子＋人工改写（隔离新建） | 77M cuda 分钟级；fp16 先行 | 先离线：事实忠实/必述覆盖/时间/空点/中文自然度＋人工核对，过质量门才进浏览器适配 |
| 共同结果/反应/行动文本（升级臂） | Mengzi-T5-base 或 Qwen3-1.7B（仅当 Qwen3-0.6B 质量不达标才启动） | 不预建 | 届时定 | 届时定 |

不做的事：不训七份独立权重（骨干共享）；不先做蒸馏（教师标数据=程序枚举＋人工，模型蒸馏等小头质量瓶颈出现再议）；不用模型生成训练数据当监督源（接口表 §2.2 语义候选不得自证）。

**例外（方向 2026-10-29 问答选定；条款文本未经单独确认，以下为待确认草案）：N4 成句语料按事实/风格分层。** 事实计划由程序枚举构造并经权威校验；模型生成正文改写行。模型改写正文**承载事实主张**，逐条事实审核（planRefs 下标、必述覆盖、人物归属、方向、数值、任务引语、新增事件扫描）是其**准入条件**，不因生成用途的称呼而豁免；全部改写行另须协调人抽验，带 `rewriter` 标记、可整组剔除做消融对照。该例外仅覆盖 N4 正文改写行；上段约束对事实标签、判别头语料及其他监督来源继续适用；条款文本经单独确认前不作为已批准的方案变更。语料按组交付抽验，通过后才进微调；首批行数是构造与训练流程试验，不预设足以训练好 77M。

## 5. 运行时选型结论（本项交付核心）

1. **编码器路线（已定，不再重开）：** ORT-web 1.30.0 vendored 稳定版直驱＋手写 BertTokenizer 等价分词器＋int8 dynamic，单线程（F1–F4）。重评 transformers.js 的唯一条件：其新版修复 F1 全部三条且其 pinned ORT 在本环境不再挂起——否则不立项。
2. **生成路线（两步走）：** 近期全部生成任务用 Qwen3-0.6B＋wllama 跑质量基线；Randeng-T5-77M 先离线质量验证（含微调），质量门通过后才做浏览器化，浏览器路径先测 wllama GGUF 端到端（F10），证伪才考虑 ORT 直驱＋自实现 sentencepiece。
3. **共存与加载：** 编码器 int8 权重约 10–12MB 一份＋生成骨干一份；wllama 与 ORT 会话可并存但总内存与切换开销由第3项实测计总账（README 第4项交付要求），本文不预设数字。
4. **取消语义：** 统一 AbortSignal；ORT 不可中断 `run`，靠迟到隔离（接口表 §2.1）；wllama 用其已有中断。加载阶段可取消。
5. **WebGPU（jsep 文件已 staged 但从未测）：** 不立项、不做承诺；单线程 wasm 已满足编码器头量级（F4 毫秒级），生成侧瓶颈在自回归步数而非并行度。

## 6. 环境与通道待办（第3项开工前置）

- `pip install sentencepiece`（T5 离线分词必需，F12）；pyarrow 桩沿用 `train-action-classifier.py` 方案（F6）。
- MiniRBT ID 与许可已核（复核轮：`hfl/minirbt-h256`→200、`iflytek/MiniRBT-H256`→401、许可 apache-2.0）；Randeng/Mengzi 权重走 hf-mirror 下载。下载后许可落实：Mengzi 核对 LICENSE 文件；Randeng 仓库无 LICENSE 文件，以模型卡声明为准（§2 许可段）。
- Randeng 微调开工时：`T5Tokenizer` 的 legacy 分词行为须显式决策——`legacy=False` 会改变当前默认分词/规范化，训练、开发评估与零样本基线必须统一同一设置并重新验证后再比较（冒烟 r2 报告的 tokenizerConfig 记录了当前默认态）。
- 在 C 工作树重新配置 MiniRBT-H256 快照并记录获取方式（F11：主树快照不入库不共享；通道=hfl/minirbt-h256 经 hf-mirror）。主树 `train-action-classifier.py` 头注仍写旧 ID `iflytek/MiniRBT-H256`（历史注释、不影响产物；正确 ID 以 F13 为准，脚本修正归 B 线后续批次，C 运行记录只用正确 ID）。
- 浏览器分发：`public/models/` 当前为空（模型文件不入库），重建路径=各 train 脚本导出＋`copy-*-assets.mjs` 机制（已有）。
- N4 语料现为 150 组 / 600 行（构造器 v9.2），行校验/去重/A 侧权威核对全绿；dev 按渲染输入归并为 56 个独立输入（53 未见 / 3 回归）。两档 `--tier small|large` 均 360 步（`r2-small`/`r2-large`）；方向单变量臂 `r3-direction` 只改共享渲染器，53/53 未见输入过识别器。原始计数、人工裁决与未通过结论见[语料协议 §9–§10](../../../experiments/world-components/n4_corpus/corpus_protocol.md)。
- 旧试验资产只复用**方法学**（数据纪律、封存批协议、计时口径、导出脚本骨架）；旧语料、旧标签体系、旧门阈值一律不复用（F8）。

## 7. 明确未验证清单

T5 浏览器端到端；JS sentencepiece；T5 微调后质量；多模型共存内存与切换开销；WebGPU/jsep；H288 变体；编码器各新头的真实质量； ort int8 对 T5 的量化损失。以上全部留待交付项3/后续批次以实验关闭，本文不宣称其中任何一项成立。

## 8. 对交付项3的输出要求（本文的验收挂钩）

第3项报告必须产出：每对照臂的隔离开发批质量数字；编码器头每次调用全链耗时（同 F4 口径）；T5 质量门结果与浏览器化可行性结论；编码器＋生成骨干共存时的加载/切换/端到端总账（对照 F9 的 Qwen 单模型账）；失败与回退记录。缺任何一项即未完成交付项3。
