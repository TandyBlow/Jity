# 外部评审问题的核对与处理（v1）

> 对象：云端评审对 `11cca05` 的静态审查（未取权重、未复跑）。
> 本文逐条核对，写明确认/不成立、证据位置、已做的处理。
> 结论：**七条代码/评测问题全部成立**；方向建议采纳。

| # | 评审意见 | 核对结果 | 证据 |
|---|---|---|---|
| 1 | 盲判只打乱编号、没打乱顺序；同一事实两种输出相邻；T1 输入泄露改前/改后提示词 | **成立** | 见 `results/blind-design-defect-v1.md`：batch-01 中 9 个相邻位有 5 对同事实；T1 一对输入的“要求”分句不同 |
| 2 | 验收样本事实来源有问题（ac01 用 goal；su01 换主体却 `authored=false`；移动事件由地点构造；sa01/sa02 隐藏数值却要求数值保真） | **成立** | `world.json`：`task_lamp.goal`=“把备用灯芯送到塔顶”，`resultText`=“换好了塔顶的灯芯”；`task_warnlamp.owner`=沈砚；`build_acceptance_set.py` 中 su01 `authored=False`；moved 单元来源均为 `locations.*.level`；sa01/02 输入不含数字 |
| 3 | 1.72 s / 4.69 s 是解码耗时，不含 tokenizer+encoder；整轮扣除后还差 18.77 s | **成立** | `run_diagnostic.py`：`make_scorer()` 先编码，`started` 在臂循环内；`raw` 合计 548.51 s，`run.json` 墙钟 568.1 s，加载 0.82 s |
| 4 | 运行目录会自动复用；完成后可能重写元数据；中断在 raw 与 order 之间会丢顺序 | **成立** | `run_diagnostic.py` 恢复逻辑只要求同 manifest + `raw.jsonl`，无 `finishedAt` 检查、无 order 计数校验；`run.json` 每次启动都写 |
| 5 | 提交里有两个 `.pyc`，含本地绝对路径；脱敏未覆盖 | **成立** | `scripts/__pycache__/beam2.cpython-311.pyc`、`-312.pyc` 的 `co_filename` = `<repo>\...\beam2.py` |
| 6 | 索引登记 143 份，漏了失败分析、人工核验清单、索引生成脚本 | **成立** | 目录实有 154 个非 env 文件；未登记：`results/cf24-catalog-v1.json`、`results/cf24-moved-rule-pairs-v1.json`、`results/failure-report-v1.md`、`review/batch-01.json`、`review/batch-02.json`、`scripts/build_final_index.py`、`scripts/redact_paths.py`（另有索引自身与 `.gitattributes`，属有意排除） |
| 7 | 不建议继续围绕旧题改提示；先修评测，再用真实已提交状态做 N3→N4 | **采纳** | 见 `results/next-steps-after-review-v1.md` |

## 已做的处理

1. **盲判**：新增 `scripts/build_blind_pack_v2.py`，整表洗牌（拒绝同事实相邻，17 批 ×10，`adjacentSameFact=0`），并隐藏“要求”分句（T1 一对输入隐藏后逐字相同）。生成 `blind-v2/`，**未判**。v1 判词保留，但“严格盲判”的说法撤回。
2. **验收**：`scripts/build_acceptance_set.py` 生成 v2 登记（`freeze/acceptance-registration-v2.json`）：ac01 改用 `resultText`（主语换成韩渡，标 `authored`）、su01 标 `authored`、moved 单元标 `derived`（注明世界文件无行动记录）、sa01/02 的判据改为“不得出现具体数值”。v1 保留为评审前记录；**v2 仍未运行**。
3. **耗时**：新增 `results/timing-scope-v1.md`；1.72/4.69 明确为解码耗时，墙钟差值 18.77 s / 19.89 s 单独列出。
4. **运行目录**：`run_diagnostic.py` 改为：完成的目录不再复用；恢复前要求 `raw`/`order` 行数一致；恢复时不重写 `run.json`。
5. **`.pyc`**：从工作区和提交中删除；本分支单提交已重写（新 SHA 见远端），旧 SHA 不再被分支引用。GitHub 可能仍保留旧对象缓存，无法由仓库侧删除。
6. **索引**：新索引 `freeze/final-index-v2.json` 覆盖上述遗漏文件（含 `review/`、失败分析、v2 生成脚本与 v2 包），并列出有意排除项。

## 仍未解决 / 需要人决定

- v1 的两套判词是在“配对相邻 + 提示可见”的条件下做的，**不重新判**；若要严格盲判，需在新包上重判 340 条（r1 170 + T1 170）。
- 完整调用耗时没有历史测量；只能给出解码合计与墙钟差值，不能反推每条玩家等待。
- 验收 v2 仍未运行；且世界文件没有行动日志，moved 类只能算“由地点层级构造”。
- 旧测试集反复使用造成的题目记忆，不会因为重打包消失。
