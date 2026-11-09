# 新方案与归档证据的比较边界

本分支仅执行新方案。旧方案不作运行回退，也没有为本任务重跑；下表读取 `d80a031` 已归档的原始摘要。场景、输入长度、代码、模型任务、机器环境及计时范围不同，不能据此计算新方案的加速比或质量提升。

| 范围及证据 | 质量观察 | 调用规模 | 实际成本 |
|---|---|---|---|
| 归档旧三步链，`action-chain-dev42-20261104-r1` | 24 项工程链完成；18 次生成均观察到提示复述错误，目标语义未通过；另 6 次 skip | 24 次判断、18 次生成、18 次目标调用；222 编码窗口、342 解码前向 | act 题局部中位约 410–466 ms；整批 12.065 s，峰值 891.16 MiB |
| 归档给定计划→自然表达，`m02-realizer-slots-20261105-r1` 两种子 | 新 24 题助手判合理 9/24、11/24；不是自主规划 | 与引用臂合计 168 次生成、640 优化步；不含开放规划/结算/状态更新 | 新题表达中位 101.68/89.20 ms；两进程含训练合计 136.288 s、峰值 1461.97 MiB |
| 同批归档引用表达 | 新题合理 14/24、15/24，但 seed42 旧回归退化；替换门未通过 | 与上一行属于同一归档批次，不能重复相加 | 新题表达中位 154.66/150.67 ms；没有速度或完整能力通过结论 |
| 新 `short-intent-20261109-r1` 训练与原子诊断 | 编码头助手草稿匹配 392/485；生成精确匹配 0/30。助手逐条检查为 24 个不满足输入、4 个可能合理但未证覆盖、2 个截断 | 两骨干各 160 优化步；515 个登记预测全部启动；17464 个编码窗口 | 整批 678.319 s、峰值 3155.20 MiB；是训练及诊断成本 |
| 新 `short-intent-eval-20261109-r1` | 24/24 上游链在主体绑定处未完成；309 个正确中间输入诊断有 98 个返回结果、211 个未完成。返回结果不代表语义通过 | 333/333 评估执行；911 次原子调用、9066 次编码前向、178 次生成调用；A 预览 0 次 | 整批 894.224 s、峰值 1357.44 MiB；自然名失败前缀中位约 2962.6 ms，引用失败前缀约 966 ms |
| 新 `short-all-20261109-r3` 全组件训练 | 62 个编码头中 61 个有非零数据梯度；1136 个原子预测中 705 个匹配草稿。128 个生成全部 EOS、6 个精确匹配；独立助手逐条初审为 92 个不符、23 个待复核、13 个仅满足局部目标，未通过语义验收 | 两骨干各 160 步；1277 个登记预测中 1264 个完成、13 个因父任务头未获有效梯度而未启动。生成器训练及评估合计 448 次 encoder 入口、1628 次顶层 forward，另有 128 次 generate | 整批 1409.83 s、峰值 2468.88 MiB，正常退出；包含训练、验证和日志 |

新引用臂没有引用形式训练材料，且较早失败；上表的较短失败前缀不是优化收益。程序不得把少做检查、失败后停止或无结果当成成功请求的低延迟。

## 后续任务与模型身份

以上新架构中的燃灯批次也已退出活动路线。以下各批继续保留完整范围与失败，不能把训练成本、开放诊断准确率、浏览器部署探针和完整游戏请求互换。

| 批次 | 质量与覆盖 | 调用规模及成本 |
|---|---|---|
| 历史短架构 `evaluation-short-all-eval-20261109-r5` | 400/400 槽执行、0 未启动；56 条真实上游全部未完成；344 正确中间输入诊断中 324 有结果、20 未完成，语义未通过 | 1,577 原子调用、27,873 编码窗口、195 次 generate；整批 628.94 s，峰值 RSS 1,881.77 MiB；A 预览与 C 均未到达 |
| `short-encoder-focus-20261109-r6` | 两个整臂各 70 条留出预测；聚焦臂 D02 判断 20/24、next 22/26、D04 next 5/8、D05 next 8/12 草稿匹配；全部质量门未通过 | 各 4,096 样本曝光，共 6,077 编码窗口；整批 99.526 s，峰值 RSS 427.58 MiB；无生成器调用 |
| `qwen-short-20261109-r2` | 0 训练；基线 103 已启动，其中 58 完成、44 资源未完成且原文缺失、1 中断；153 预测未启动 | MPS driver 越限后停止；原缺失不能由重跑补作首次输出 |
| `qwen-short-20261109-r3` | 0 训练；81 首发原文全保留，80 完成、1 资源未完成；175 未启动；原记录仍为 invalid_journal | 179.8 s，峰值 RSS 1,740 MiB；driver 8,303.7 MiB 超过 8,192 MiB 门 |
| `qwen-short-20261109-r4` | 14 任务各 8 次真实梯度；训前/后各 128 首发全部保留并 EOS；逐字草稿匹配 9/128→32/128，不等于语义通过；merge 单样本误差 0.5 恰达容差上限 | 112 训练步、256 generate、31 次冷载；冷载 31.13 s、generate 墙钟 465.94 s、训练步墙钟 546.05 s、监督器总墙钟 1,251.805 s；进程树 RSS 2,649.58 MiB，MPS driver 7,710.86 MiB |
| `qwen-short-time-20261109-r5` | 时间输入已含实际 boundary/unit；8 条新时间训前+128 条全任务训后均完成。训后助手初审 52 局部满足/62 不符/14 待审；16 条时间前后全为 1，明确五分钟等待仍错。共享适配器新增训练后，其他 12 任务有 21 条原文变化，改善与退化全保留 | 32 新步（累计 144）、136 generate、14 次冷载；生成调用+MPS 同步 234.263 s，完整生成请求 236.718 s，训练步 95.570 s、冷载 14.222 s；监督墙钟 439.684 s、进程树 RSS 2,654.58 MiB、记录到的 MPS driver 最大 4,021.08 MiB |
| `short-encoder-time-20261109-r8` | 仅修复两个 D08 unit 头，其他 60 头逐张量继承；8/8 草稿匹配但留出全部为 minute，不能签其他单位或时间语义通过。失败 r7 原件及无 provider 状态保留 | 32 步×2 样本，64 次曝光；两头各 minute/second 16 次数据梯度；242 次实际窗口 forward、8 首次预测、1 冷载。监督墙钟 21.205 s、RSS 654.69 MiB；窗口前向合计 3.594 s，预测合计 1.367 s（与前向重叠），冷载 0.068 s |
| `qwen-webgpu-base-20261109-r5` | 未微调浏览器基座；14 浏览器 EOS/result，组件层 13 result/1 超时 incomplete。每请求有真实 ORT 设备和正时长量化权重 kernel 证据；不是新训练模型或完整链 | 14 generate，总 242.615 s；138,328 kernel 的追踪时间合计 102.716 s。监督墙钟 316.269 s；附着/加载/ready 61.613 s；case 中位 9.431 s。Python RSS 312.45 MiB，浏览器/GPU 峰值及 CPU 节点时间未测 |
| `qwen-short-time-export-20261109-r1` | **数值门失败，登记已隔离**。atol=1e-4 被多输出超过；工具吞为 warning，旧 record 的 completed 不代表通过。未执行依赖的训练后 WebGPU 生成 | CPU 导出 1 批；监督墙钟 41.086 s、RSS 4,567.05 MiB。生成 ONNX 文件是转换产物，不是语义或浏览器调用。原失败成本与字节保留 |
| `qwen-short-time-export-20261109-r2` | 严格 57 输出核对，35 在原容差内、22 不在；最大绝对误差 0.000896453857421875。未量化、未发布，非浏览器模型 | 监督墙钟 58.279 s、RSS 3,793.92 MiB；原阈值未放宽，全部比较输出保留 |
| `qwen-short-time-export-20261109-r3` | 冷 worker 缺 Qwen3 导出注册，数值比较前失败；原拟关闭 ORT 优化的定位实验没有得到数值结果 | 监督墙钟 6.740 s、RSS 1,767.58 MiB；未量化/发布/浏览器生成，失败原件保留 |
| `qwen-short-time-export-20261109-r4` | 补齐注册并关闭 ORT 优化；全部输入数组 SHA/形状与 r2 相同，57 输出 29 通过/28 失败，maxAbsError=0.0014224052429199219；未量化/发布 | 监督墙钟 20.614 s、RSS 4,716.09 MiB；没有通过原数值门，失败原件保留 |
| `qwen-webgpu-base-profile-20261109-r1` | 两个完整输入各 on/off/on/off，共 8 result/EOS；只比较零训练步基座追踪成本，不是质量或训练效果对照 | 长输入调用及 checkpoint 为 60.914/85.896/86.063/46.565 s，不能推出 off 一定更快；监督墙钟 324.661 s、Python RSS 43.33 MiB，浏览器/GPU 峰值未知 |
| `qwen-webgpu-base-full-20261109-r6` | **已冻结并正在执行，结果待封存**。MiniRBT 已训练头+r6 聚焦整臂+零训练步 WebGPU 基座；48 行动+4 初始化+4 纯时间+380 诊断，真实 C/正式提交未接 | 显式资源观察上限 7,200 s，case 600/600/600/180 s；上限不是实测成本或 500ms 门放宽。全部首次输出与未启动槽保留 |

Qwen 的 `modelComputeMs` 实际计量是 `model.generate` 加 MPS 同步的墙钟，包含主机生成循环，不是纯 GPU kernel 时间。浏览器 WebGPU 的追踪时间另见 [实际验证](short-qwen-webgpu.md)，CPU 节点时间和浏览器峰值显存未知时不填 0。r4 时间数值接口后来查出缺少已选择单位，新接口的修复训练与回归必须另列，不能直接使用 r4 成绩签通过。

r5 的生成请求时间包括其生成调用时间，r8 的预测时间包括相应编码窗口，表内各分项不能直接求和。冷载事件只计模型加载区段，进程导入、文件哈希、发布和日志等仍在监督器墙钟；不通过相减把剩余值伪称纯程序成本。MPS driver 是已记录事件处最大值，未连续测量真实峰值；Python RSS、MPS driver、浏览器峰值也不是同一指标。

当前候选身份分别登记于 [活动选择](../../../experiments/world-components-logic/data/short-semantics/active-selection.json)：数据为 `8aa0875d…` 的 4,750 行 time-choice-v2；r8 provider 为 `ef3266c2…`、合并编码头为 `9adf110c…`；r6 聚焦整臂仅通过未改四头数据迁移证明沿用，未改原权重；Qwen r5 合并权重为 `a4d42694…`、模型清单为 `c14b86f2…`。全文 SHA 及路径见 [交付状态](short-results.md) 与各冻结清单。此登记不赋予语义资格；训练后浏览器 provider 当前为空，export-r1 的两份提前登记见 [隔离索引](../../../artifacts/world-components-logic/qwen-short/quarantine-export-r1/index.json)。

新方案后续批次的实际结果在 [训练实验](short-experiment.md) 和 [交付状态](short-semantics.md) 更新，原始前批摘要与失败保留。修改后的同来源数据属于开放诊断材料，不升级为新的独立泛化测试。

## 分项计时

首批评估的历史字段 `generatorForwards` 统计一次完整 `generate` 调用；178 不能解释为逐 token 的底层 decoder 前向次数。编码器字段统计实际窗口前向。以上表格采用“生成调用”这一实际含义。

离线实验记录 D 模型调用、加载、程序/日志和进程墙钟；实际离线 A 预览在调用时计入程序部分。生产服务往返、C 生成和 ready 等待尚未连接，必须标记未测，不能填 0。首批评估的模型加载字段没有覆盖导入与完整文件哈希的全部准备成本，这些仍包含在 case/进程墙钟，不应从整批成本扣除。

旧评估（包括 WebGPU base r5）的 `resultJournalMs` 和 `snapshotEndMs` 写入了 0 占位，实际没有分别测量，不能解释为日志/快照零成本；总监督器墙钟包含这些工作，原记录不回写。后续冻结评估已改为分别实测结果落盘、快照和计时日志，并保留包含这些工作的完整结束时间。

完整请求目标仍是 500 ms，包含全部必要 D 调用、服务、反应、六阶段、合法关联段、自动后续、重试、C 和 ready。上表没有一行可以验证该目标；训练、组件诊断、失败前缀、给定计划表达及完整请求是不同的工作负载。

## 可复核来源

- [旧三步链摘要](../../../artifacts/world-components-logic/l3-11-action-chain-summary.json) 与 [原协议](action-chain-probe.md)。
- [旧自然/引用摘要](../../../artifacts/world-components-logic/l3-22-realizer-slots-summary.json) 与 [原协议](realizer-slots-protocol.md)。
- [首批新训练摘要](../../../artifacts/world-components-logic/short-semantics/short-intent-20261109-r1.summary.json)、[全部生成助手初审](../../../artifacts/world-components-logic/short-semantics/short-intent-20261109-r1.generator-assistant-review.json)。
- [首批新链摘要](../../../artifacts/world-components-logic/short-semantics/evaluation-short-intent-eval-20261109-r1.summary.json)。
- [全组件训练摘要](../../../artifacts/world-components-logic/short-semantics/short-all-20261109-r3.summary.json)、[128 条生成逐例助手初审](../../../artifacts/world-components-logic/short-semantics/short-all-20261109-r3.generator-assistant-review.json)、[初审说明](short-generator-review-r3.md)。
- [Qwen 时间修复摘要](../../../artifacts/world-components-logic/qwen-short/qwen-short-time-20261109-r5.summary.json)、[全部 136 条语义初审](short-qwen-time-review-r5.md)；调用/加载/训练分项来自同批完整 journal 的 406 个已验证事件。
- [单位头 r8 摘要](../../../artifacts/world-components-logic/short-semantics/short-encoder-time-20261109-r8.summary.json)；242 个窗口前向来自同批 570 事件完整日志，8/8 单类留出的限制不能省略。
- [浏览器基座独立技术审计](../../../artifacts/world-components-logic/qwen-short/webgpu-base-r5.technical-audit.json)；真实设备与 token/kernel 对账不等于任务语义通过。

旧权重身份、旧代码和记录保持归档身份；本地没有的旧适配权重不以同名新权重替代。大日志、模型和依赖保留在本工作树本地，不进入 Git；小型索引给出原件及压缩副本的路径、大小和哈希。
