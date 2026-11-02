# D / L3 当前入口与实验记录

## 当前从这里开始（2026-11-02）

日常使用 `experiment.py` 一个入口；模型实现仍在 `m01_shared.py`。当前模型结论从已有汇总读取，不在多份说明中手工重复维护数值。当前阶段是探索性离线验证，尚无质量/局部50ms/完整500ms通过结论；任务范围以[工作树说明](../../design/world-engine-reports/components-logic/README.md)为准。

从仓库根目录运行：

```bash
python3 experiments/world-components-logic/experiment.py status
python3 experiments/world-components-logic/experiment.py check
```

`status`只读当前状态，`check`运行工程测试并核验三份历史结果报告和本批动作/截层报告，二者不导入模型、不训练或推理。实际新批次使用D独立环境：

```bash
.local/world-components-logic/venv/bin/python experiments/world-components-logic/experiment.py prepare NEW_RUN_ID
.local/world-components-logic/venv/bin/python experiments/world-components-logic/experiment.py execute /absolute/NEW_RUN_ID.plan.json
```

`prepare`核对本地模型/数据/环境并冻结新计划，不运行模型；`execute`会真实训练和推理，须符合该批工作安排，使用新run-id且仍限CPU单线程、120秒/2048MiB。本次已按附批协议执行动作表示/截层比较，结果由`status`读取。旧计划绑定旧代码，不能用当前代码覆盖重跑；历史复现须恢复原提交与环境后登记新批次。

| 角色 | 文件/位置 | 维护方式 |
|---|---|---|
| 当前运行入口与公共流程 | `experiment.py` | 入口、资源监督、阶段计时、记录和中断收尾共同复用 |
| 当前模型实验实现 | `m01_shared.py` | 完整事实编码、候选融合、拟合与预测，后续算法主要改这里及对应测试 |
| 当前结果核验/展示 | `m01_shared_report.py`、`artifacts/world-components-logic/l3-7-*` | 报告核验原计划/记录，不以当前算法源码替代历史执行版本 |
| 共享基础工具 | `lab.py`、`fact_windows.py`、`pilot_codec.py` | 守卫、事实编码和原输入核对，按实际职责维护 |
| 历史模型入口 | `runtime_smoke.py`、`run_pilot.py`、`m01_probe.py`、`m01_infer.py` | 保留原记录/测试及被复用工具，不作为当前日常入口 |
| 数据/审阅准备 | `data/`、`prepare_*`、`review_io.py` | 原资料及工具保留，按实际数据工作使用，不冒充模型能力 |
| 运行证据 | `artifacts/world-components-logic/` | 原计划、记录、快照、页面只读；模型/检查点仍在D的`.local/`忽略目录 |

后续试验优先复用同一入口，以配置和新批次计划表达差异；不按每轮试验复制一套监督器或新建状态页。新职责确实需要独立模块时再拆文件。已有模型头质量和速度问题继续按原标准解决，不以整理目录代替实测。

历史报告核验优先检查已保存源码；当前文件已变化时，使用本地Git中的实际执行提交 `d3b21a53eb901fdfded100ae41a3201d7bbb05b5` 并核SHA。浅克隆缺少该提交会明确报错，不自动下载或放宽核验；直接查看已归档HTML不需要运行检查。既有r1/r2快照和全部记录原样保留，动作/截层批次追加新计划、证据与结果，仍不新增源码快照；当前源码变化后从本地Git按已登记SHA查找实际执行字节，找不到时明确失败。

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
