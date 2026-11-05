# world-components-next 工作树交接

创建日期：2026-11-05。来源：`D:/others/Jity/.local/world-components-worktree`。

分支从 `world-components` 末端 `f725d123964408beeab5991d119027e90b28f68a` 创建。
当前开发基线是该提交加来源工作树的未提交快照，不能只按最后一次提交理解方向。
快照保留为未提交改动，没有提交、推送、stash 或修改来源工作树。

## 阅读顺序与当前边界

1. `design/world-engine-reports/components/README.md`：组件范围与职责；其中历史状态不能覆盖后续实验结论。
2. `n4-training-plan.md`、`n4-task-shape-comparison.md`：完整输入/标签、不静默截断、EOS 结束、超时标记未完成；旧判据停止逐句补规则。
3. `n4-version-decision-2026-11-04.md` → `n4-stage-v2-transition.md`：后者修正前者的绝对成绩；431 曾作为研发默认，不能将 102/102 当作当前有效结论。
4. 同目录的保守编辑、关系授权和后续阶段记录，以及 `experiments/world-components/n4_narrative_dev/` 中新脚本：单事实表达之后已推进到授权边界、组织衔接与纠错试验。

另一个工作树 `D:/others/Jity` 的近期报告提供更晚的跨工作树上下文，可只读参考：
`design/world-engine-reports/boundary-arm-closing-record.md`、`organization-run-v2.md`、
`semantic-correction-run.md`、`background-selection-run.md`、`narration-service-loop.md`。
这些报告未复制进本分支；它们属于另一条仍在开发的工作线，不能当成这里已经实现的功能。
其中边界记录保留 u240，组织/纠错试验有明确失败结论；不要凭早期 README 或历史版本决定直接恢复旧训练方向。

## 快照范围与资源

已复制全部已跟踪改动（含删除）、非运行资源的未跟踪文件，并补入被忽略的组件实验源码、教材和诊断资料。
`experiments/` 被仓库忽略，所以部分新脚本不会显示在普通 `git status` 中；后续提交必须逐项检查并显式选择。
模型权重、assets、ckpt/checkpoint 目录、缓存、日志/中间文件、依赖环境未复制；它们仍在来源工作树中。
其他工作树的未提交源码与主工作树产品改动未混入。

逐文件 SHA-256、排除项及来源状态：`D:/others/Jity/.local/world-components-next-handoff/manifest.json`。
同目录保留来源状态与已跟踪改动补丁。来源文件和副本已逐文件比对；未运行模型训练或推理。
