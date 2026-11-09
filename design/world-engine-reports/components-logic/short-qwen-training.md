# Qwen3 短文本训练与转换证据

本轮自然语言组件使用 `Qwen/Qwen3-0.6B` 非思考模式；Randeng 活动入口已停用。旧实验、旧权重和原始失败记录保留。训练在本机 MPS 上执行，随后转换为浏览器资产；MPS 训练或 CPU 转换验证不构成 WebGPU 实测。

原厂底座固定到 `c1899de289a04d12100db370d81485cdf75e47ca`，Apache-2.0。来源、逐文件 SHA 和独立依赖见 `artifacts/world-components-logic/qwen-short/` 中的 `qwen3-06b-source-registration.json`、`qwen3-06b-stable-source-payload.json`、`stable-dependency-install-report.json`。任务专用权重与环境迁到 `/Users/davidz/.cache/jity-d-short-semantics-20261109/qwen/`，避免 Documents 占位文件阻塞。原文件未删、全局云同步设置未改。

`short_qwen_codec.py` 的 `jity-qwen-short-complete-chat-v2` 为训练和浏览器提供相同消息。完整世界与当前工作材料不截断；按真实字段指明行动者和名称/引用格式，不提供动作目录。`enable_thinking=False`，训练损失仅覆盖响应及 EOS。14 个短文本任务共390行（训练262、开发与测试128），仍为12个既有来源组的助手草稿；人审和独立来源核验均为0，旧暴露来源不能重新宣称独立泛化。

各任务的验证材料并不充分：U2.2为训练4/开发1/测试0，U4.2为6/1/1，U5.2为3/1/1。前11任务各覆盖8个训练来源，U2.2与U4.2各4个、U5.2仅3个；“每任务8步”包含重复曝光，不能当成8个独立来源或足量语义验证。

冻结计划 `qwen-short-20261109-r4.plan.json` 预登记112步、批量1、秩4/alpha8的 q/v LoRA、bf16底座、fp32适配参数与AdamW、14任务各8次曝光，以及训练前后各128次首次生成。完整提示最大3471 token、目标最大41；限制8192/128，超限明确未完成。总墙钟2400秒，MPS driver与进程树RSS各8GiB，无自动重试。

由于动态输入下实测 Metal driver 占用持续增长，r4 采用顺序短生命周期进程：预测每16条、训练每8步退出并回收进程资源。训练保存并核验适配张量、AdamW状态、CPU/MPS RNG、来源/代码/配置身份及采样位置；不重置学习过程。完整31段、每次冷载与进程往返都计入总耗时。小型数值测试中，4步连续训练与2+2步恢复的参数、优化器、损失和CPU RNG逐值相同；这只是程序正确性证据。

失败证据保留：r1仅准备中断；r2在基线阶段停止，0训练步，44条生成原文未被旧错误处理保留下来，不能补造；r3的81条首次生成均保留，80完成、1因driver达到8303.7MiB超过冻结门而未完成，0训练步。r3还发现新worker结算计时字段不完整，原记录仍标`invalid_journal`；167事件原始哈希链有效，另立失败摘要，未改原记录。r4修正计时并使用进程树资源监督。各批原始与gzip留本地，只提交SHA索引。

`short_qwen_export.py` 复用公共监督器：Optimum标准 Qwen3 `text-generation-with-past` 导出、opset18、fp32导出验证，再用ORT `MatMulNBits` 对MatMul权重量化（block32、对称）并转fp16。程序按实际图输入确定KV cache类型，写入浏览器配置，不能由“q4f16”文件名猜缓存类型。新导出预登记最多8GiB新增工作空间和至少6GiB剩余空间，不清除旧权重腾空间。小型bf16源模型经真实导出、量化和CPU ORT执行，输出相对原模型误差门通过；正式模型与WebGPU仍分别验证。

原厂社区ONNX包与本地新导出的资产有不同转换来源。两者浏览器结果不能单独归因于训练；本批MPS训练前后采用同底座、分词、完整输入与解码配置，提供同条件比较。完整游戏请求、真实C模型、ready等待及500毫秒目标均不能由本局部训练或转换宣称通过。

实际训练状态、首次输出、资源、模型身份以同目录批次plan/record/model与汇总为准。正式接口为公共 `short-qwen-prepare/execute/report`，转换模块提供 `freeze/execute` 并继续使用同一监督与日志机制。

r4已完成112步训练、训练前后各128条首次生成和合并门：14任务各8次非零梯度，112个LoRA参数张量全部变化，底座张量哈希未变。草稿逐字匹配为训前9/128、训后32/128，不等同语义评分。总墙钟1251805毫秒，31次实际冷载，进程树峰RSS2649.58MiB、MPS driver峰7710.86MiB。完整7,891,915字节journal和523,529字节record均保留，另有逐字节验证的gzip与SHA索引；见`qwen-short-20261109-r4.summary.json`。此批D08时间量尚未读到已选单位与边界，已登记真实接口缺陷；r4不抢先导出，保留merged与适配权重供后续修复比较。

r4身份清单有已知缺口：当时Qwen CODE未单独列入间接调用的`short_contracts.py`。不回写旧冻结计划；同会话其它快照可定位其来源，但不能把它冒充当时Qwen计划已有的独立绑定。后续修复与导出将该依赖及训练辅助依赖纳入新快照。

参考实现依据：[Qwen3原厂模型](https://huggingface.co/Qwen/Qwen3-0.6B)、[Optimum导出说明](https://huggingface.co/docs/optimum-onnx/onnx/usage_guides/export_a_model)、[Transformers.js 3.8.1量化脚本](https://github.com/huggingface/transformers.js/blob/3.8.1/scripts/quantize.py)、[PyTorch MPS显存接口](https://github.com/pytorch/pytorch/blob/main/torch/mps/__init__.py)。本机driver增长是实测；其与MPS图缓存有关的解释仍是诊断推断，不把公开问题报告当成本机根因证明。

## D08 同来源修复与继承身份

时间编排已改为 boundary→unit→amount，amount 完整输入携带已选择的边界和单位。`time-choice-v2` 的4750行中仅4任务48行输入改变，其他4702原行字节相同；迁移证明逐行重算，保留原来源、目标、划分及已暴露身份。CODEC v3只改变两项amount指令，其余12项消息经原v2快照核验相同。

编码器 `short-encoder-time-20261109-r8` 完成32步，两unit头各32次非零梯度，其中second/minute各16；其余60头逐张量完全继承。8条开发/测试首次预测全匹配草稿，但目标全是minute，不能支持其它单位泛化。其余hour/day/month/year正类训练计数为0，provider仍拒绝其输出。r7已有相同真实训练但发布校验失败；r8与r7损失、8条预测和检查点张量逐值一致，原失败不删除。r8总21.205秒，峰RSS654.69MiB。

Qwen `qwen-short-time-20261109-r5` 使用同一个共享适配器，继承r4权重、AdamW和CPU/MPS RNG，再按新冻结schedule训练32步（两amount任务各16非零梯度），累计优化器144步。其他12任务继承原训练来源；适配张量变化影响全部14任务，不能宣称它们行为不变。因此全部128条训后输出重跑，另有8条新D08输入的训前输出，首次原文全部保留。总439.684秒，14次冷载，峰RSS2654.58MiB、记录的MPS driver峰4021.08MiB。

逐例助手初审：r5训后52项局部满足、62明确不符、14待复核；这不是人工验收。16条D08训前/后均输出`1`，其中五分钟场景明确错误，其余时间边界依据待进一步审查。共享适配器使非时间任务21条原文发生变化，回归退化保留。详见`qwen-short-time-20261109-r5.assistant-review.json`和`short-qwen-time-review-r5.md`。r5合并的单个固定样本最大logit差0.5、argmax相同，仅满足当批有限合并门；不能推广为完整数值或语义等价。

正式导出首批r1实际生成了q4f16资产，但完整日志揭示Optimum顶层函数捕获数值超限异常只写警告，包装器错误记为完成。原记录不改，另附资格补正和隔离索引；该资产不得接入浏览器。已改为逐个完整输出核验finite、shape、allclose，实际数值错误必须失败，只有完整证明才可发布。r2显式eager参考路径仍在57输出中22项超过原atol=1e-4/rtol=1e-5，最大差8.9645e-4，严格阻止量化与发布。r3复用图冷进程的ONNX注册缺失在模型比较前失败，随后新增冷进程反例。

旧r2数值验证只固定Torch RNG，Optimum mask还调用Python random。为进行相同输入的优化对照，后续冻结按r2记录的实际mask SHA唯一恢复其二值连续padding，全部输入SHA必须一致；恢复不读模型输出或误差。新验证同时固定Python/NumPy/Torch RNG并保存实际输入数组，避免再次依靠反推。小型导出、完整输出、非有限值、遗漏输出、冷进程注册与同输入两优化路径共7项工程检查通过，仍不等同真实模型数值通过。

最终r4转换诊断复用r2同一浮点图，并逐项核对全部实际输入数组SHA和形状相同；只将ORT_BASIC改为ORT_DISABLE_ALL。57输出29项通过、28项数值不近，logits最大差4.7135e-4、整体最大1.4224e-3，未通过原阈值；20.614秒、峰RSS4716.09MiB。禁用优化未解决问题，后层KV差值累积是观察，不足以指认某个算子缺陷。本轮不继续盲试或放宽门，r4未量化、未发布浏览器模型。下一步需在该固定图与实际输入上定位逐算子差异，再登记新的数值路径。

因此本轮Qwen训练与MPS回归已完成；训练后WebGPU链仍因严格转换数值门未通过而未接通。社区原始Qwen的浏览器实验是另一模型身份，不能代替本次训练后模型验证。全部失败、原始模型/merged、输入数组和日志留本地，压缩逐字节SHA核对后仅提交小型索引。最新统一清单为`artifacts/world-components-logic/qwen-short/data-model-inventory-qwen-time.json`；它明确区分76任务的真实梯度资格、数据覆盖不足及最终生成器部署阻断。
