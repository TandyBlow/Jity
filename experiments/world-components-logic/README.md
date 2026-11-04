# D / L3 当前入口与实验记录

## 当前从这里开始（2026-11-04）

日常使用`experiment.py`一个入口。当前L3-18扩18组36条关联变体后，30训练/18检查、80步及96次对照完成。助手预检新开发4合理/6错/2含糊，6组仅1组双变体均合理；旧开发仍3/6且有语序退化，质量/完整500ms未通过。[当前结果页](../../artifacts/world-components-logic/l3-18-realizer-expanded.html)。人审0/来源未核，旧证据保留。

从仓库根目录运行：

```bash
python3 experiments/world-components-logic/experiment.py status
python3 experiments/world-components-logic/experiment.py check
python3 experiments/world-components-logic/experiment.py train-data
python3 experiments/world-components-logic/experiment.py train-audit
python3 experiments/world-components-logic/experiment.py train-report
python3 experiments/world-components-logic/experiment.py train-expand
python3 experiments/world-components-logic/experiment.py train-report --run-id m02-realizer-expanded-20261104-r1
```

`status`区分最新工程/数据批与最近业务模型批；`check`运行工程测试、九份历史模型报告及L3-13至17材料/训练记录核验，不加载预训练模型。数值单元测试使用随机小模型，不运行M02。`train-data`保留r1历史核验，`train-audit`核r2数据，`train-report`核本次真实拟合及全24输出；`--write-new`只新建相同材料，拒绝覆盖异稿。以下prepare/execute仍是历史L3-12诊断，不能当成新规划器训练命令：

```bash
.local/world-components-logic/venv/bin/python experiments/world-components-logic/experiment.py prepare NEW_RUN_ID
.local/world-components-logic/venv/bin/python experiments/world-components-logic/experiment.py execute /absolute/NEW_RUN_ID.plan.json
```

`prepare`核对本地模型/数据/环境并冻结新计划，不运行模型；`execute`真实执行本批三步协作，训练0步，使用新run-id。当前M03/readable批CPU单线程/并发1、120秒/4096MiB，原M02批为2048MiB；各批资源限制分别保留。当前活动配置仅FP32/逐字段可读输入；此前三臂动态8位批按其计划和实际源码恢复后另用新id，不用当前配置覆盖重跑。M01固定event2检查点，生成模型使用已登记M03/Qwen2.5-0.5B-Instruct的完整本地文件，FP32运行，无远程代码/共享缓存。当前生成质量和速度都未通过，不能将本入口作为产品方案。旧计划绑定旧代码，不能用当前代码覆盖重跑；历史复现须恢复原提交与环境后登记新批次。

| 角色 | 文件/位置 | 维护方式 |
|---|---|---|
| 当前运行入口与公共流程 | `experiment.py` | 入口、资源监督、阶段计时、追加日志与中断只读重放共同复用 |
| 当前训练实现与新来源 | `plan_training.py` | 短表达适配层训练、未审新来源、布局/数值检查及材料；训练需已核标签/冻结实例 |
| 原计划契约与准备 | `action_plan.py` | 计划结构/来源、10旧来源新标签草稿、全量选择器输入、表达预览及拟合提案守卫；不跑模型 |
| 最近模型协作实现 | `action_chain.py` | L3-12行动判断、真实生成与原文目标交接；复用公共监督/日志 |
| M01基础实现 | `m01_shared.py` | 完整事实编码、候选融合和冻结模型推理，拟合历史由对应Git提交定位 |
| 模型结果核验/展示 | `m01_shared_report.py`、`artifacts/world-components-logic/l3-12-*` | 报告核验原计划/记录，不以当前算法源码替代历史执行版本 |
| 共享基础工具 | `lab.py`、`fact_windows.py`、`pilot_codec.py` | 守卫、事实编码和原输入核对，按实际职责维护 |
| 历史模型入口 | `runtime_smoke.py`、`run_pilot.py`、`m01_probe.py`、`m01_infer.py` | 保留原记录/测试及被复用工具，不作为当前日常入口 |
| 数据/审阅准备 | `data/`、`prepare_*`、`review_io.py` | 原资料及工具保留，按实际数据工作使用，不冒充模型能力 |
| 运行证据 | `artifacts/world-components-logic/` | 原计划、记录、快照、页面只读；模型/检查点仍在D的`.local/`忽略目录 |

后续试验优先复用同一入口，以配置和新批次计划表达差异；不按每轮试验复制一套监督器或新建状态页。新职责确实需要独立模块时再拆文件。已有模型头质量和完整500ms问题继续按最新标准解决，不以整理目录代替实测。

历史报告核验优先检查已保存源码；当前文件已变化时，使用本地Git中的实际执行提交 `d3b21a53eb901fdfded100ae41a3201d7bbb05b5` 并核SHA。浅克隆缺少该提交会明确报错，不自动下载或放宽核验；直接查看已归档HTML不需要运行检查。既有r1/r2快照和全部记录原样保留，动作/截层批次追加新计划、证据与结果；同一提交内失败提示或精度附批的实际源码按SHA保存为只读证据快照；当前源码变化后从本地Git按已登记SHA查找实际执行字节，找不到时明确失败。

## 历史准备快照（2026-10-31）

以下按当次日期保存，早期“暂停/未运行”不是当前状态；当前入口以上表和`status`为准。

2026-10-31：模型执行继续暂停。第二步已收用户本人 42/42 项开发题初审、全部认可，来源及正式复核仍待完成，见[人审说明](../../design/world-engine-reports/components-logic/human-review.md)和 [L3 进度](../../design/world-engine-reports/components-logic/l3-progress.md)。本目录不是生产服务或新权威协议。

同日第三步：第二步当前交付收口，来源/人选为并行待办。`round1_scenarios.py` 与 `prepare_round1.py` 准备了另外90张来源卡及判据，保存在 `data/round1/`，附独立审阅页和覆盖表。44开发+46封存候选尚未冻结，均待新一轮人审与来源核验；不是 `lab.py` 可执行输入，原42题不抵扣。原78+来源卡10=88项工程测试通过，不等于模型或来源通过。

2026-11-01 修订2：只修正 `r1-sealed-d05-02` 的四人入组过程和判据，其他89项不变。清单保存旧提交2184a39与旧三文件SHA；新页标明修订2，旧批次意见不自动迁移。新增3项回归，合计91项通过；新路径回归对实际旧数据必失败。旧42题、三份本人回执及其页面不受影响。人审/来源/完整输入与模型执行仍待，详见[人审说明§9](../../design/world-engine-reports/components-logic/human-review.md#9-来源卡修订2与旧意见的处理2026-11-01)。

- `lab.py`：纯标准库结构与阶段守卫、严格解码、完整尝试台账。
- `generate_dev_drafts.py`、`data/`：40 个开发来源组/42 项 AI 草稿，输入与人审判据分离，全部待人工/来源复核；没有封存、训练和短链数据。
- `prepare_review.py`：生成人工审阅 HTML，保留说明草稿并提示本地保存失败；实际浏览器显示/下载/恢复尚待验证，导出不自动构成正式签字。
- `review_io.py`：构建审阅批次、要求三份批次文件哈希必填并只读核对导出声明、核查 D 来源身份与 B/C Git 元数据；不改标签，不读取保护题正文，不授予执行/正式评测权限。新增工具独立工程审查无剩余 P2，来源/正式人工复核仍待。
- `fetch_model.py`：只下载已登记 M02 到 D 独立忽略目录，实际文件 SHA-256 验真。
- `requirements-probe.txt` 与平台 `.lock.txt`：隔离实验依赖，后者仅适用于 macOS ARM64/Python 3.11；不修改根依赖。
- `runtime_smoke.py`：失败台账与并发发布工程问题已在进度记录条目 13 闭环；真实模型加载/推理仍未验证，未恢复前不运行推理模式。此前只执行了 `--prepare-only`。

提交前的工程检查为：

```bash
python3 -m unittest discover -s experiments/world-components-logic/tests -p 'test_lab.py'
python3 -m unittest discover -s experiments/world-components-logic/tests -p 'test_review.py'
python3 experiments/world-components-logic/generate_dev_drafts.py --check
python3 experiments/world-components-logic/check_run_manifest.py --self-test
python3 -m unittest discover -s experiments/world-components-logic/tests -p 'test_round1.py'
python3 experiments/world-components-logic/prepare_round1.py --check
```

已有核心 65 项、新增审阅 13 项，共 78 项工程检查都不证明模型质量或 500 ms。缺来源登记哈希的反例已对旧实现反向验证。审阅逻辑测试需要本机已有 Node.js，仅跑合成内存夹具，不启动浏览器或写人审决定。业务模型输入尚未曝光，本人题目/判据初审意见以独立回执收录，原数据不改；正式来源/模型语义/性能结论仍未评测。

新卡导出用 `review_io.py reconcile FILE --batch round1-source-cards --out NEW_FILE`，默认仍核对旧42题。新旧批次/意见不互通；`prepare_round1.py --write-new` 拒绝覆盖不同的已有材料。完整阶段输入、同源骰点派生、D02守卫探针和短链运行器留待补齐，训练数据另立。

## 2026-11-01：完整输入、审阅及试跑准备

在原来源卡修订2之外新增`data/round1-inputs/`七文件：80基础任务+4同源骰点对照，10短链初态/计划，2辅助守卫。全部新增上下文待人审/来源，模型未运行；短链动态执行器未实现。`development-inputs.jsonl`只含开发项，不能把结构ready当执行授权。

```bash
python3 experiments/world-components-logic/prepare_round1_inputs.py --check
python3 experiments/world-components-logic/prepare_input_review.py --check
python3 experiments/world-components-logic/prepare_run_batch.py --check
python3 -m unittest discover -s experiments/world-components-logic/tests -p 'test_*.py'
```

完整输入页面为`artifacts/world-components-logic/l3-3-input-review.html`，导出核对用`review_io.py reconcile /absolute/export.json --batch round1-inputs --out /absolute/new.json`。生成器`--write-new`只新建，差异拒绝覆盖。运行准备的PASS是静态身份一致，后续BLOCKED列明缺失项；不执行模型。具体材料见`design/world-engine-reports/components-logic/round1-review-handoff.md`和`round1-run-preparation.md`。原42题、90卡页与历史回执保留。

## 2026-11-01：首批真实运行

`run_pilot.py`已接入原42项已审开发题、M02固定本地权重和独立venv，`pilot_codec.py`可完整还原编码，`pilot_report.py`从原始记录生成查看页。r1/r2在512下共40次输入超限；r3扩大至1024的独立诊断及r4工程修复后复验共40次业务生成，当前零样本配置明显失败。512内完整分块、实际M01协同和短链尚未实现。原42/90数据及人审记录不变。

运行器只用CPU单线程/单并发，离线、本地模型，监督120秒/2048MiB；进入生成前记账，生成异常与监督中断都保留，未启动项单列。新运行必须用独立run-id，计划/记录/日志拒绝覆盖。r1–r3执行源码按原SHA保存在`artifacts/world-components-logic/pilots/code/`；回放时先恢复其原执行路径及对应依赖，不能用改后的代码冒充旧版本。`--execute`会真实运行模型，重放前按新的工作安排登记批次，不复用旧id。

```bash
python3 -m unittest discover -s experiments/world-components-logic/tests -p 'test_pilot*.py'
python3 experiments/world-components-logic/pilot_report.py --check
```

查看`artifacts/world-components-logic/l3-4-pilot-results.html`与`l3-4-pilot-summary.json`。独立组件调用耗时不能当完整请求；格式通过不证明语义正确，所有完整500ms/正式质量结论仍未通过。

## 2026-11-02：M01完整分窗及两小头拟合探针

新增`fetch_m01.py`获取原L2固定10M模型；`fact_windows.py`保留全部原子事实并装成≤512token窗口，单条超长事实明确拒绝。`m01_probe.py`在已审旧D02/D03开发标签上冻结编码器、拟合两个线性头，16拟合/4保留组；`m01_infer.py`锁定真实检查点后独立推理，不再拟合或改阈值。它是正式独立训练流程之前的工程附批，不冒充新训练配额；90组不进训练。

真实编码器10,279,424参数＋两头514参数，拟合200步/头。D02保留判别2/2、D03完整集合1/2，D03漏目标且整体耗时仍超50ms。每个窗口只编码部分事实，全窗加权聚合语义仍待验证；D02不生成行动正文，M01/M02协同及完整500ms未完成。原子分窗、实际模型学习与性能/语义通过分别报告。

大原始记录以`.json.gz`/`.jsonl.gz`无损归档，汇总保存压缩和解压SHA；复现读取可直接解压到其原路径。未压缩副本、模型和头检查点仅在`.local/world-components-logic/`；权重不入库。旧执行源码按当时计划SHA保留在`artifacts/world-components-logic/m01-fitting/code/`。测试用元数据替身验证配置与身份边界，不要求下载本地权重，也不启动训练。

```bash
python3 -m unittest discover -s experiments/world-components-logic/tests -p 'test_m01*.py'
python3 experiments/world-components-logic/m01_report.py --check
```

查看`artifacts/world-components-logic/l3-5-m01-results.html`与机器汇总。实际执行需要先按新run-id冻结计划、固定模型/数据/环境，`--execute`会真实消耗CPU；不得复用旧记录或拿缓存特征签推理速度。拟合与推理均有单线程、120秒/2048MiB监督，所有中断与未启动项分开。

## 2026-11-02：完整场景共享编码与候选融合

`m01_shared.py`保留原代码与记录，新增完整事实共享编码、逐事实token池和可学习候选条件注意力；新两头180,418参数，骨干冻结。20旧开发组仍16拟合/4保留，但保留答案已公开，不能称未见留出；新90组训练0。r1在`ps`监测权限处停止、40项未启动，原监督漏slot记录与源码保留，修后回归可区分双臂同题中断。r2原学习率0.01拟合塌缩，r3按独立纠正附批改0.0003，均200步/头和阈值0.5；旧臂原检查点不再训练。

两批各40项交替计时，新旧每臂每题5次；完整重新分词/编码，不用计时缓存。r3目标12窗→4窗，约493–503→199–207ms；行动略慢约186–188ms。新头拟合两任务均8/8，保留D02为2/2、D03仍1/2：开闸不再漏人，空目标题反而误选两人。不是质量或速度通过，也不能把头本身的耗时当整项推理。完整D02–D05协同、500ms、浏览器/生产仍未测。

查看`artifacts/world-components-logic/l3-6-m01-shared-results.html`及对应汇总。r1/r2执行源码固定在`m01-fitting/code/`；r3源码SHA绑定本次代码。四份大记录使用gzip原字节归档，解压到原`.record.json`/`.record.windows.jsonl`路径即可核查；原始副本/权重在D的`.local/`忽略目录。报告检查与测试不导入Torch、不需要本地权重；历史运行必须恢复对应源码、模型和环境并登记新的run-id，禁止覆盖原证据。

```bash
python3 -m unittest discover -s experiments/world-components-logic/tests -p 'test_m01_shared*.py'
python3 experiments/world-components-logic/m01_shared_report.py --check
```


## 行动三步实测（2026-11-04）

[结果页](../../artifacts/world-components-logic/l3-11-action-chain-results.html)包含三批全部52条尝试、39次生成和39次目标分析。两批77M零样本输出都复述提示；494M指令模型能写动作，但三条中两条有明显人物/任务问题，一条待复核，生成链1322–1558ms超500ms。原输入全部保留，skip不调用后两步，空目标不计正确；所有结果均为旧题探索，不是正式语义验收。

`m01_shared_report.py --chain --check`只读核验计划/源码/协议、gzip原字节哈希、日志重放、原判别概率、完整上下文、生成原文和下游逐字交接、全部调用/计时。新增attempt_checkpoint是实验台账，不接管游戏权威；模型/头均冻结，无训练、新90组使用、浏览器接线或生产写入。下一笔处理人物/任务定位和生成瓶颈，不能仅因放宽50ms把本次结果当通过。


## 人物定位、编码与精度实测（2026-11-04）

[最新结果页](../../artifacts/world-components-logic/l3-12-action-focus-results.html)保存48条新流程、36次生成。重复人物原资料和逐字段中文JSON均仍执行旧命令/混淆人物；本机qnnpack动态8位更慢且退化，未采用为达标方案。新增生成顶层前/后钩子区分完整输入prefill与后续decode；不删除模型真实上下文。计时/所有失败/全部重复可展开，完整500ms与正式质量继续未通过。

`m01_shared_report.py --focus --check`复用三步证据核验，并检查实际前向配对/成本、169个量化模块整数/qparams/残余浮点身份和focus/int8逐token输入相同；旧三步报告字节保持不变。`pilot_codec.readable/restore_readable`只替换字段名、无损往返；没有程序写动作或按内容筛世界。下一步转动作选择/引用计划与短表达的专用小模型拆分，先登记独立监督数据与训练协议。


## 动作计划/短表达准备（2026-11-04）

[准备查看页](../../artifacts/world-components-logic/l3-13-action-plan-preparation.html)用中文列出每个人物、原任务、输入状态、拟尝试动作的对象/工具/目的地/接收人和旧约束；结构化细节可展开。当前是AI标签草稿，没有新的模型答案或500ms成绩。`data/action-plan/`保存10项计划及5份短表达参考草稿和来源/哈希，旧42题意见不变、新90组未用。

`action_plan.py`只验证结构/typed ID/引用/来源和构建输入；即使动作内容不合理，结构合法也不会成为semanticApproved。planner完整输入不含标注计划；realizer短输入只是未审计划预览，不能视为真实规划/全量覆盖。新计划意见与旧场景意见按批次/annotationSHA隔离，拟合导出也只是8fit/2保留开发提案，不是新独立训练集或执行授权。当前新标签未审、实际导出0、训练0。

用途勘误：原记录一直为01/07 fit、03/05 retained_development，前两页文字说明曾写反；最初r1协议“0107曾拟合”并非笔误。当前页与新材料读取原记录，历史页面/协议/数值字节保持。后续先补独立动作计划监督数据/标签和冻结训练配置，再分别验证真实选择与短表达；原审核不用重做，不能把AI草稿自签成真值。


## 短表达训练器与12个新来源候选（2026-11-04）

日常`train-data`只读核验新来源/训练准备，`--write-new`仅写缺少的同批文件。`train-inspect --prepare NEW_ID`冻结无业务检查，`train-inspect --execute PLAN`加载原模型装适配层、做合成数值检查，禁止业务输入。`train-prepare NEW_ID --reviews REVIEW_JSON`先核本12组意见与SHA再冻结真实训练实例，缺新标签意见在模型加载/写计划前拒绝；`train-execute PLAN`才实际训练。旧`prepare/execute`仍是L3-12诊断，不是训练命令。

新场景/计划/表达候选在`data/action-plan-training/`，6训练候选/6开发候选、全部未审；同源/语义独立性未核实，不能只按哈希宣布独立集完成。当前已审0/12、业务训练/推理0、无已训练适配权重；原L3-13的10旧组仍独立保留。人工给定计划的表达训练不等于开放规划能力。

实际无业务检查：原M02 77,440,384参数、48适配位置、172,032可训练，总推理77,612,416；不把0.17M说成整个模型。只做装配无M02 forward，另用8维数值层8步验证梯度和重载，业务指标仍0。原记录/哈希日志在m01-fitting，模型/以后适配层只在D .local忽略目录。

[分词检查](../../artifacts/world-components-logic/l3-14-realizer-tokenizer-check.json)记录12组完整输入/目标token和哈希，最大169/25，符合256/64限制；只分词无神经前向。训练实现的真实业务路径、表达质量、开放规划器、浏览器/生产及完整500ms均未验收。参考[训练协议](../../design/world-engine-reports/components-logic/realizer-training-protocol.md)。


## 真实M02合成数字训练通路（2026-11-04）

`train-smoke --prepare NEW_ID`固定合成数字检查计划；`train-smoke --execute PLAN`复用同一监督器，加载真实原M02，在两行固定token上执行2步适配层优化，并检查零适配/原模型一致、底座无梯度/不变、磁盘存档/清空重载后logits及全部生成token一致。`train-smoke --report`只读核原日志并新建结果材料，拒绝覆盖异稿。固定[协议](../../design/world-engine-reports/components-logic/realizer-training-smoke-protocol.md)先于实际执行，CPU1线程/并发1/120秒/2048MiB。

实际r1为22次顶层前向，4.16秒/RSS727.41MiB；不是业务训练、语义或500ms成绩。合成适配层仅在D忽略目录`realizer-smoke/`，与将来的`realizer-adapters/`业务训练身份隔离，不纳入模型候选。原12候选/新90卡/旧42意见原样，业务训练0。`plan_training.py --check-smoke`只读核计划/代码/记录/哈希日志；原材料的作者源码按b24767a固定Git字节核验，不随活动代码升级改写。查看[本批结果](../../artifacts/world-components-logic/l3-15-realizer-smoke.html)。


## 十二组逐项核对与修订2（2026-11-04）

`train-audit`只读核对记录和`data/action-plan-training/r2/`，`--write-new`新建材料；核对规则/逐项理由见[说明](../../design/world-engine-reports/components-logic/label-audit.md)。只有10号补初始灯具和灯芯嵌套位置、更新计划basis/哈希，12条表达输入/标签保持原文。原r1/sourceGroup/split不改，05/06同源风险保留；助手核对不会生成真实人工意见或训练实例。

`train-prepare --reviews`及`train-execute`现在按r2批次/packet/annotation及修订manifest核验；完整旧r1意见也不能打开新训练。缺r2意见仍在加载模型前拒绝。原r1材料及L3-15原执行源码可从固定Git身份核验，未追溯修改。本次业务模型/训练0，语义和500ms无新结果。


## 首批真实短表达探索训练（2026-11-04）

用户在知悉样本少/人工未审后“可以开始吧”，据此新增窄范围`--authorization`入口，和`--reviews`互斥。authorization只说明唯一runId/r2 packet/配置/6+6组/来源风险/正式许可false，不生成逐题人工同意。当前固定80步、全12条训练前后各首次生成，不按开发答案调参/早停。原人工review路径和未授权拒绝仍保留，旧批次材料不追溯改写。执行依据见[探索协议](../../design/world-engine-reports/components-logic/realizer-exploratory-fit-protocol.md)。

真实r1：80优化步，24生成；顶层调用before102/training80/after171，encoder12/80/12；14.42秒/RSS1337.77MiB、CPU1，原文件/底座SHA不变，适配层存档仅在D忽略目录。训练后助手预检训练6条合理、开发3条合理/3条错，错误为04缺对象、08人物/接收关系混乱、10物品/步骤错误。局部82–164ms，完整500ms/正式质量未验；开发题已公开，不当独立封存。

`train-report`只读重放原日志、校验训练组隔离/全部尝试/输入/token/输出与助手意见；`--write-new`只新建结果材料。再次execute原计划会因原记录存在而拒绝，不会续训或重采样。新训练需另行登记相应数据/授权，当前授权绑定本次唯一runId。权重不入库，没有浏览器或生产接线。

## 扩充样本与冻结模型对照（2026-11-04）

`realizer_expansion.py`只管理18组/36条新草稿及来源，训练/日志/报告继续复用`plan_training.py`。30训练含原6条与新24条；18开发含原6条已曝光回归和12新条。相关变体按sourceGroup不跨边，annotationId唯一，逐步同时登记；旧失败开发不进训练，全部来源仍未核实。

用户“继续”授权本轮有界探索。runId为m02-realizer-expanded-20261104-r1，先加载上批冻结适配层比较，再精确恢复新初始化重训80步，非续训。原M02底座冻结/超参/资源保护不变；96次生成、80优化步、全部失败/含糊/退化保留。结果见[新旧对照](../../artifacts/world-components-logic/l3-18-realizer-expanded.html)及[协议](../../design/world-engine-reports/components-logic/realizer-expansion-protocol.md)。`train-expand`只读/只新建，`train-report --run-id`核指定批次；`check`同时核L3-18，需使用D独立venv运行完整检查，系统Python可能没有实验依赖。权重/本地依赖不入库。
