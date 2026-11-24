# micro-NLU 数据集（2026-11-24）

- 来源：run138（20 输入，桌面档，prompt 落盘）；prompt 是各语义调用的原始输入，答案是该次调用被接受的最终输出。
- 标签性质：银标（0.6B 自身输出），用于「小头能否复现 0.6B 决策」与延迟对比；质量对照需另做手标子集。
- action（act/skip）11、targets（目标 id 集）41、position（位置变更）15、results（判定/事实）31；reaction 10 条为生成，不进分类集。
- 构建脚本 `build_datasets.py`：按 prompt 首段识别任务族，按调用尝试数配对（用首个 prompt + 最终答案）。
