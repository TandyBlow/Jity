# 工作树称呼与职责

更新日期：2026-10-29。本表统一项目协作中的 A、B、C、D 称呼；字母是工作树代号，不是组件编号。

| 代号 | 分支 | 职责与状态 |
| --- | --- | --- |
| A | `world-server` | Python 服务、协议、存储与权威状态计算。既定计划已收口，已随验收组合进入 `agent`；本地 A 工作树已移除，分支和本地材料归档保留。 |
| B | `world-browser` | 浏览器调度、控制／运行层、页面及真实模型整链。继续独立推进。 |
| C | `world-components` | 组件总纲与小模型研究，当前主要推进叙事拆分 N1–N5。由 B 延伸。 |
| D | `world-components-logic` | 非叙事组件架构、组件数量分析、程序／模型分工、模型选型及验证。由 C 延伸；首批深入行动、目标／反应和共同结果。 |
| 基线 | `agent` | 接收已审查、已验证的阶段成果；A 收口记录见 [集成说明](agent-integration-20261029.md)。 |

分支来源：

```text
B / world-browser
└─ C / world-components（创建基线 50c1c22）
   └─ D / world-components-logic（创建基线 3006935）
```

D 即此前所称的 logic／非叙事组件专项。今后任务、交接和审查统一称“D 工作树”，分支名及目录名保持不变。本机路径为 `.local/world-components-logic-worktree`，远端协作者使用自己的检出路径。

原设计中的 C1–C7、N1–N5 等仍是组件职责编号，不因工作树命名改变。D 的组件数量、模型数量及共享方式需要分析与实验，不按这些编号预先固定。

各线保留对应实现与审查职责，跨线接口、资源和集成由项目协调人统筹。该命名更新不自动合并 B/C/D 最新实验，也不扩大既有验收结论。

D 的详细任务入口：[非叙事组件架构与模型选型](https://github.com/TandyBlow/Jity/blob/world-components-logic/design/world-engine-reports/components-logic/README.md)。
