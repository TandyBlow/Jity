# Jity Eval

Jity 仓库内的长期一致性评测工具，位于 `eval/`，与游戏运行环境和数据保持隔离。包含确定性模拟器、Jity 存档冻结与上下文审计、完整游戏录制/重放、版本化题库及三组问答试测工具。

从 Jity 仓库根目录执行 `cd eval`。迁移后的目录约定、离线验证命令与历史产物位置见 [仓库集成说明](docs/repository-integration.md)。`capture`、`replay` 和问答试测的输出必须放在 Jity 仓库之外；示例统一使用同级 `jity-eval-runs/`。旧运行的冻结源码、证据和审核状态保持原样。

**原有模拟器与 `replay` 命令仍不读取 API Key、不调用真实模型。新增 `capture record/resume` 仅在明确提供预算与授权后调用真实 API；所有模式均使用独立数据目录，不修改 Jity 原存档。** `replay` 命令会在独立运行目录及网络阻断边界内导入 Jity 的实际组件；第一阶段模拟器完全独立。模拟正确率和上下文组装成功均不代表模型能力。

真实剧情回放的用法、三组通道、历史调用缺失限制和已执行证据见 **[docs/jity-replay.md](docs/jity-replay.md)**。历史运行报告不随源码上传，位置见集成说明。

新增完整游戏录制与严格原始响应重放见 **[docs/full-game-recording.md](docs/full-game-recording.md)**。先通过含摘要的小规模录制与断网重放，再解锁四局采集；固定数据集不等于三组记忆探针的新答案。

## 直接运行

以下第一阶段命令需要 Python 3.9+ 和 macOS / Linux，仅用标准库。真实 Jity 集成另需 Python 3.11+ 与 Jity 已安装的后端依赖；未自动安装任何依赖。文件锁当前使用 `fcntl`，暂不支持 Windows 原生环境。

```bash
cd eval  # 从 Jity 仓库根目录开始
python3 -m jity_eval validate examples/pilot.json
python3 -m jity_eval plan examples/pilot.json
python3 -m jity_eval run examples/pilot.json --output runs/my-first-run --max-samples 7
python3 -m jity_eval status runs/my-first-run
python3 -m jity_eval resume runs/my-first-run
python3 -m jity_eval report runs/my-first-run --open
```

`run` 的输出目录必须不存在，避免覆盖历史结果。`--max-samples` 表示本次最多执行的样本数；不传时执行全部剩余样本。报告是自包含的 `report.html`，可直接双击打开，无须启动网站或安装前端依赖。

预置用例包含两个独立剧本，每个剧本 49 回合，覆盖叙事事实、结构化状态、已更新事实、未知事实；在间隔 10 / 20 / 40 回合时分别检查回忆和使用。共 48 个题目 × 3 组 × 1 次重复 = 144 个实验样本。一个样本是一道题在一个实验组的一次重复，并非一局真实游戏。

## 三组对照与证据边界

| 配置值 | 离线可见信息 | 工具验证目标 |
| --- | --- | --- |
| `full` | 近期上下文 + 历史叙事事实 + 结构化状态 | 完整记忆组 |
| `recent` | 仅固定窗口内的近期上下文 | 关闭持久记忆的对照组 |
| `state` | 近期上下文 + 结构化状态 | 关闭历史叙事记忆的对照组 |

三个模式共享同一份历史和检查点，每道题在独立分支作答，不会通过前一道题的答案提示后一道题。标准答案位于单独的 gold 文件，只交给评分器；后台完整状态仅进入审计 trace，不参与离线回答。

当前适配器按公开的事实注释查询字典，评分器核对值和决策枚举。`action` 只模拟“使用已知事实 / 请求更多信息”的决策，尚未执行真实游戏动作。原始回复、解析草稿、规则处理后输出、保存状态分别留存；规则处理目前为显式标注的 identity stub，并未调用 Jity 的校验器。

`repeats` 支持多次独立任务编排；当前离线策略是确定性的，同一用例重复会得到相同答案。`seed` 用于固定实验标识，为未来适配器预留，不代表当前实现了随机采样。当前报告不计算统计显著性，也不评价剧情连贯性或结局触发。

## 用例与项目结构

格式说明及最小示例见 [docs/case-format.md](docs/case-format.md)。可从 [examples/pilot.json](examples/pilot.json) 复制配置，从 [examples/pilot.suite.json](examples/pilot.suite.json) 与 [examples/pilot.gold.json](examples/pilot.gold.json) 复制用例和答案。

```text
jity_eval/
  cli.py        命令行入口
  schema.py     严格校验配置、公开历史、测试问题与私有答案
  runner.py     任务计划、冻结输入、检查点分支、恢复与故障重试
  offline.py    离线会话与精确值评分器
  storage.py    SQLite 状态、原子 JSON 写入、进程锁
  report.py     自包含 HTML 报告
examples/       两个长历史用例及故障注入配置
tests/          标准库 unittest 回归测试
runs/           本机运行产物，已被 Git 忽略
```

每次运行保存：

```text
manifest.json      版本、实验配置、输入 SHA-256 与离线声明
inputs/            冻结的 config.json / suite.json / gold.json
run.sqlite3        样本状态、每次尝试与事件记录；进度的权威来源
checkpoints/       检查点审计导出
traces/            每个样本每次尝试的上下文、回答、评分或错误
results.json       当前结果快照
report.html        当前浏览器报告快照，已内嵌 trace
```

报告支持实验组、间隔、测试类型、状态和文本筛选，以及逐题答案与证据展开。正确率为 `passed / (passed + failed)`；运行失败、评分失败和未完成样本单独展示，不计入正确率。报告包含标准答案与完整审计证据，不能作为待测模型的输入。

## 恢复与重试

恢复始终使用运行目录内的冻结输入，不受原始 examples 文件后续修改影响。冻结输入、manifest 或任务计划发生变化会拒绝恢复。运行锁阻止两个进程同时执行同一个任务。

已提交的 `passed` / `failed` 样本不会重跑。进程中断后留下的 `running` 样本在下一次恢复时重新排队，旧尝试标记为 `interrupted`。检查点从冻结历史重建，避免信任被修改的检查点导出文件。

`adapter_error` 和 `grading_error` 需要显式重试；答错的 `failed` 不属于运行异常，不会被重试成“正确”。例如：

```bash
python3 -m jity_eval run examples/faults.json --output runs/my-fault-run
# 预期退出码 1：第一次尝试故意注入一条适配器故障和一条评分故障。
python3 -m jity_eval resume runs/my-fault-run --retry-errors
python3 -m jity_eval report runs/my-fault-run --open
```

每次尝试使用独立 trace 文件，SQLite 保留旧尝试和错误；报告展示样本的最新尝试。`Ctrl+C` 后可以使用 `resume`。强制终止后 HTML 可能仍是旧快照，恢复或执行 `report` 会重新生成。

断点粒度是一个实验样本。当前离线适配器可以安全重放中断样本；未来接入有外部副作用的游戏或模型时，还需要实现请求幂等与实际会话恢复，不能直接把当前机制视为外部调用的 exactly-once 保证。输入初始化期间若失败，保留目录供检查，需另选新目录重新创建任务。

退出码：`0` 正常执行或按数量暂停；`1` 存在运行/评分异常；`2` 配置、输入或文件错误；`130` 用户中断。答案错误通过结果统计表达，不改变退出码。

## 验证与后续接入

```bash
python3 -m unittest discover -s tests -v
```

回归测试覆盖格式拒绝、答案隔离、事实更新、未知事实、分支隔离、输入冻结、暂停恢复、异常重试、进程锁、报告转义和错误计数。第一阶段验收记录见 [docs/phase-1-validation.md](docs/phase-1-validation.md)。

第一阶段配置仍只接受 `offline`，与 `replay` 命令分开。旧存档可能缺少历史辅助响应，原始 API 完整游戏录制由独立的 `capture` 命令提供。题库与问答试测分别使用 `python -m jity_eval.question_bank_revision` 和 `python -m jity_eval.qa_pilot`；历史报告中的实验状态只描述其记录时点。本次仓库集成只验证离线工具，不生成新的模型回答或正式成绩。
