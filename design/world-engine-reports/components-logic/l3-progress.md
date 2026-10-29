# D / L3-1：暂停快照与恢复入口

日期：2026-10-29（Asia/Shanghai）。用户已要求暂停 L3，并授权先提交阶段版本。**当前是实验准备快照，未完成 L3、未运行模型、未验收模型语义或 500 ms 性能。** 恢复须有用户后续指令。

## 已保存内容

| 部分 | 本次进度 | 证据/范围 |
|---|---|---|
| 原创开发草稿 | 40 个来源组、42 个 case；34 个应调用、8 个结构守卫项 | [输入](../../../experiments/world-components-logic/data/dev-inputs.jsonl)、[AI 判据草稿](../../../experiments/world-components-logic/data/dev-review-drafts.jsonl)、[来源登记](../../../experiments/world-components-logic/data/dev-provenance.json)；人审和语义同源独立性均未通过，未建封存/训练/短链 |
| 工程核心 | 阶段输入隔离、确定性守卫、输出结构校验、全尝试耗时台账 | [lab.py](../../../experiments/world-components-logic/lab.py)；不是另一套服务/协议，不替模型判断开放语义 |
| 工程测试 | 50 项通过 | [test_lab.py](../../../experiments/world-components-logic/tests/test_lab.py)；不证明模型质量/性能 |
| 数据可复现 | 生成器 `--check` 重建同字节 | [生成器](../../../experiments/world-components-logic/generate_dev_drafts.py)；不会覆盖已被人工修改/签字的草稿 |
| 人审材料 | 生成可本地审阅/导出意见的 HTML 草稿 | [审阅页](../../../artifacts/world-components-logic/l3-1-review.html)、[生成程序](../../../experiments/world-components-logic/prepare_review.py)；浏览器界面/导出尚未验收，未替用户作审阅决定 |
| 独立环境 | 新建隔离 venv，安装 25 个依赖并保存版本/安装报告哈希 | [环境身份](../../../artifacts/world-components-logic/l3-1-environment.json)、[平台锁](../../../experiments/world-components-logic/requirements-probe-macos-arm64-py311.lock.txt)；无共享 system-site-packages，未改 Anaconda base |
| 小模型准备 | M02 固定 revision 的 6 个文件已下载并核对完整 SHA-256 | [获取脚本](../../../experiments/world-components-logic/fetch_model.py)；权重/缓存仅在本工作树 `.local/world-components-logic/`，不入库、不借 B/C 缓存 |
| 无业务试跑草稿 | 只执行过 `--prepare-only`，未 import/load 模型或推理 | [runtime_smoke.py](../../../experiments/world-components-logic/runtime_smoke.py)；有下列未修 P2，不能作为可运行交付或模型测试结果 |

全部 42 个开发输入均未交给候选模型；没有业务推理、训练、浏览器接线、真实服务调用、共享 GPU 或重 CPU 实验。环境安装和文件验真不等于模型运行。

## 复核与已知未完成项

1. 独立只读审查发现 D03 先前判定可能来自尚未冻结的来源或不完整记录。已修复并补反例：必须为已冻结其他人物的完整、自洽且唯一的判定。43 项测试通过。缺少目标确认账本/服务回执时，仍不能证明关系实际已确认，验证汇总如实标未核实。
2. **未修 P2：** `runtime_smoke.py` 的依赖导入、分词器/模型加载在生成尝试的 `try/finally` 之外。若此处失败，最终记录可能缺失，准备计划也可能被后续运行覆盖。用户暂停前尚未修复；恢复时先补完整失败台账/不覆盖规则，再复核，**不要直接执行推理模式**。
3. 审阅 HTML 已生成；2026-10-29 已完成只读浏览器显示/导航核验（10 道 D03 目标展示正确、42 项可载入、无脚本错误，见第 6 条）。本地保存与导出仍未验证。导出是待核对的用户声明，不能自动升级为正式人工签字；不得由代理点击认可冒充人审。
4. 用户已明确由本人先人工复核。题目与判据全部仍为 `pending`；正式独立评审角色、B/C 完整保护来源/语义同源核验及正式计算窗口尚待落实。没有正式筛选放行。
5. 首批只完成工程准备和开发草稿。A0 真实生成基线、小组件协同、封存筛选、短链、D06–D08/完整请求及 500 ms 观测全部未开展。
6. 独立审查 2f8ca38（范围 `6ba4dc9..2f8ca38`）提出 5 项 P2，已全部修复并补 5 项反例/边界测试（工程测试 43 → 48 项通过）：D04 判定来源限为本轮 source 或已冻结成员，堵住待生成反应者的未来关系泄漏——已提交 42 题经新校验复核无一泄漏，`dev-d04-09` 为受损探针题（source 文本为空，守卫以 `missing_frozen_source_text` 拒调），按受损探针保持数据有效；耗时台账按 arm/task/stage/绑定身份分节点计数，混臂混任务不再合并凑满 20 次，不足即 `latency_unverified`；审阅页改读 `targetIds`，10 道 D03 题经浏览器只读核验均显示拟定目标（空集显式「没有目标」，D02 无目标行），HTML 已重新生成；根 `.gitattributes` 为 D 字节绑定目录建立 LF 规则（公共文件变更提案），D 目录工作区字节与 Git blob 及登记哈希对齐后 `--check` 通过；`fetch_model.py`/`runtime_smoke.py` 登记读取显式 UTF-8，cp936 默认编码环境复现原失败、修复后通过。模型质量与 500 ms 性能仍未验证，L3 不签就绪；条目 2 的未修 P2 维持不变。
7. 复审 a7cf585 通过 D-R01/R03/R04/R05；D-R02 剩余两项缺口已修复并补反例（工程测试 48 → 50 项通过）：耗时节点仅当每条样本显式记录全部绑定身份（arm/task/stage/component/modelId/deviceId/configHash）才可越过 20 次样本门槛，缺任一维度或 workloadId 未经核验登记绑定一律 `latency_unverified`——维度不适用时必须显式写入数据，不允许默默省略；节点改用结构化键并以规范化 JSON 序列化展示，`job|arm=A0` 与 `job`+`arm=A0`、含分隔符的 component/modelId 组合均不再碰撞。第 3 条已同步只读浏览器核验事实。模型质量、500 ms 性能与 L3 就绪仍未签署；条目 2 未修 P2 维持。

## 提交前轻量复核

仅执行工程复核，不启动模型/训练/服务：

```bash
python3 -m unittest discover -s experiments/world-components-logic/tests -p 'test_lab.py'
python3 experiments/world-components-logic/generate_dev_drafts.py --check
git diff --check
```

模型文件、pip 缓存、venv 和准备计划保存在本工作树的忽略目录内，不会随 Git 提交传到其他电脑。其他电脑按固定来源及平台依赖另行重建。

## 独立于本准备快照的 CI 问题

本分支继承的全仓 CI 仍失败。已读取 [L2 提交运行记录](https://github.com/TandyBlow/Jity/actions/runs/40877705746)：前端通过，后端 814 通过/75 失败，接口导出报 `api-contract.json` 漂移；可见 `schemaVersion=1` 代码约束与使用 `2` 的测试资料不一致。此前最新提交的 [CI](https://github.com/TandyBlow/Jity/actions/runs/40880370097) 同样失败。未在 D 改写这些 A/B 所有的文件，也未因工程测试通过宣称全仓 CI 通过。

恢复顺序：先修无业务试跑的失败记录和审阅页 QA → 用户审题并核对来源准备门 → 按资源安排做小批真实模型实验 → 定位热点并按 500 ms 原则继续细拆。暂停期间不执行后续步骤。
