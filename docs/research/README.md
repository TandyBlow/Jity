# 研究材料与历史实验

这里保存已归档的实验报告，研究工具位于 [`tools/research`](../../tools/research/README.md)。这些文件记录特定时间、代码版本与测试集上的结果，不作为当前运行规则或持续更新的测试输出。

| 原位置 | 当前位置 | 用途 |
| --- | --- | --- |
| `artifacts/examiner/` | [`reports/examiner/`](reports/examiner/) | Examiner 开发集、保留集及前后对比的 7 份历史报告 |
| `artifacts/smoke/` | [`reports/smoke/`](reports/smoke/) | 2026-09-15、2026-09-16 幕间转换实跑的 4 份 JSON/Markdown 报告 |
| `scripts/generate_thesis.py`、`scripts/thesis/` | `tools/research/generate_thesis.py`、`tools/research/thesis/` | 历史论文草稿生成器及章节内容 |
| `scripts/embed_images.py`、`scripts/render_diagrams.py`、`scripts/render_mermaid.js`、`scripts/diagrams/` | `tools/research/` 下同名文件及目录 | 论文配图与插图工具 |
| 根目录 `package.json`、`package-lock.json` | `tools/research/package.json`、`tools/research/package-lock.json` | 仅研究配图使用的 Mermaid 依赖 |
| `frontend/src/lib/dev-log/entries/*.ts` | [`../dev-log/entries.json`](../dev-log/entries.json) | 开发日志原始内容；网页入口保留 |

报告文件原样迁移，保留其中的旧路径、时间戳和命令作为来源记录。`docs/evidence/`、`docs/verification/` 已在文档目录中，本轮不再移动；运行中的存档、数据库与 `playtest_logs/` 不属于历史归档。

新的自动跑测输出仍写入 `playtest_logs/` 或由命令行指定输出目录。幕间转换冒烟的新报告默认写入本地 `artifacts/smoke/`；只有需要长期保留的结果才归档到本目录。论文工具的默认输出位于 `generated/`，不提交到 Git。
