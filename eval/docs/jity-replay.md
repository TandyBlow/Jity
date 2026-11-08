# Jity 真实组件的离线回放

这一阶段将真实存档冻结为可审计的数据集，在独立目录里复用 Jity 的记忆、状态和提示词组件。整个流程不会启动 Jity 服务，不修改原存档，不调用真实模型。

## 当前完成范围与数据缺口

| 工作 | 实现 |
| --- | --- |
| 冻结剧情 | 只读 SQLite 一致备份；沿选定 head 的父节点取完整祖先链；保留玩家行动、原骰点、历史回复、状态和战役进度；排除兄弟分支 |
| 记忆与状态处理 | 实际复用 StoryOutput 解析、SCORE 校验、GameStateManager.apply_output、MemoryLifecycleMixin._feed_memory、MemoryController.maintain |
| 三组上下文 | 在同一冻结检查点的独立副本上，实际调用 MemoryController/NSB 检索、PromptBuilder 和 SimpleTruncationStrategy |
| 模型替身 | 替换 LLMClient._request_completion，按回合、调用顺序、purpose 和请求指纹严格匹配历史响应；缺失即报错 |
| 证据与报告 | 保存最终 messages、裁剪前后 section、命中及实际注入、结构化状态、来源、通道政策、泄漏审计和检查点指纹；单 HTML 可离线打开 |
| 延迟探针 | 从显式事实字段提取候选，扫描行动和历史输出全部字符串值的字面/别名重提，按最后提及安排 10/20/40 回合探针；标准答案单独保存 |

**上下文从已冻结状态恢复，不等于完整逐调用重演成功。** 当前存档缺少 Director、NSB、PCB 等辅助调用响应；成功的 `raw_output_text` 实际保存的是校验后的剧情 JSON，也不等于原始模型输出。数据集把它标为 `normalized_committed_output`，不会据此伪造完整调用记录。

真实 `ScenarioGenerator.generate()`、战役推进、原始向量请求和 Director 指令生成不在当前已重放范围。状态边界审计的每步也从各自冻结父检查点开始，结果不是一条重新生成并推进的完整游戏。当前 `pending=True` 的记忆快照保持原样，不假装已完成下一轮可能执行的记忆维护。

## 环境

冻结、探针提取及静态报告可用 Python 3.9+。真实组件组装/状态审计需 Python 3.11+ 和 Jity 已安装的后端依赖。本机已验证的解释器为：

```bash
/opt/anaconda3/envs/jity-backend/bin/python
```

所有命令从 Jity 仓库的 `eval/` 目录执行；运行输出放在仓库外。示例输出目录须不存在，避免覆盖旧实验。

## 从存档到报告

```bash
# 1. 只读列出活动分支长度
python3 -m jity_eval replay inventory ../backend/data/jity.sqlite3

# 2. 冻结指定剧情，原文件不动
python3 -m jity_eval replay freeze \
  --jity-root .. \
  --database ../backend/data/jity.sqlite3 \
  --session 023b0978-df89-4506-9e58-7690f5a2af25 \
  --output ../../jity-eval-runs/my-replay/dataset

# 3. 每种延迟先选8题；完整候选另存，全部保留待复核标签
python3 -m jity_eval replay extract ../../jity-eval-runs/my-replay/dataset \
  --output ../../jity-eval-runs/my-replay/probes --per-delay 8

# 4. A/B/C组装；先跑7个样本验证恢复
/opt/anaconda3/envs/jity-backend/bin/python -m jity_eval replay contexts \
  ../../jity-eval-runs/my-replay/dataset --jity-root .. \
  --probes-dir ../../jity-eval-runs/my-replay/probes --output ../../jity-eval-runs/my-replay/contexts \
  --recent-window 5 --budget 102400 --max-samples 7

/opt/anaconda3/envs/jity-backend/bin/python -m jity_eval replay resume \
  ../../jity-eval-runs/my-replay/contexts

python3 -m jity_eval replay report ../../jity-eval-runs/my-replay/contexts --open
```

`freeze --head` 可以明确选某个分支节点；不传 `--session` 时选择最长活动祖先链，选择理由写入 source。原数据库的完整一致备份留作审计，`dataset.json` 中仅含选定分支。

`contexts --repeats N` 重复安排相同检查点实验，但它仍是确定性上下文组装，不代表多局随机模型实验。已完成样本不会在 `resume` 时重跑；中断尝试单独保留。运行/缺调用错误只有加 `--retry-errors` 才重试。冻结输入、任务计划或 Jity 源码发生变化会拒绝混入同一实验。

## A/B/C 的可见内容

| 通道 | A full | B recent | C state |
| --- | --- | --- | --- |
| 近期玩家行动和历史回复 | 有 | 有 | 有 |
| 共同静态游戏规则与输出约定 | 有 | 有 | 有 |
| 当前结构化字段、物品生命周期 | 有 | 无 | 有 |
| NSB 历史摘要、PCB 人物档案 | 有 | 无 | 无 |
| 冻结前情提要、状态中的 recent_events | 有 | 无 | 无 |
| 历史 Director 指令、旧开场和锚点提示、外部知识库 | 均不注入新探针；单独声明未重放范围 |

后端完整状态始终保留。B 还覆盖 PromptBuilder 的自动状态头，避免仅清空摘要后，物品/NPC/事实甚至默认健康值仍被注入。C 允许结构化条目的 `description/notes` 等字段，但不允许 PCB 等独立叙事档案；报告记录信息来自哪个通道。若关闭通道的文字同时存在于允许的近期历史或结构化记录，会标成合法来源重叠，而非自动判作泄漏。

当前近期窗口按最近 N 个冻结时间线回合统一构造，尚未复现生产按章节筛选的差异。Jity 的 builder 仍会进一步只取最后 10 条消息，并对单条消息截到 300 字符；结构化列表最多 8 条。这些内部裁剪和之后的 token 预算裁剪都写入 trace。使用 Jity 本地 token 估计器，避免首次下载词表；原始向量检索不在重放结果中。

来源分两种：NSB/PCB 自带游戏回合字段；结构化字段通过快照差异记录最后变更的时间线回合。后者**不是最后提及回合**。无法可靠映射的来源标成 unknown，不推测。

## 探针、最后提及与人工复核

`probes.json` 只有题目和检查点等公开元数据；`gold.json` 存标准值和原句依据；`candidates.json` 留存完整候选及所有备选题。gold 不会传入上下文 builder。每个探针/组别/重复都有独立分支，不写回剧情，不把此前问题的答案加入历史。

当前自动扫描范围包括玩家行动，以及历史输出的叙事、对话、选项、地点、当轮记忆更新等全部字符串值；不把每回合原样保存的持久 state 当作重新提及。检查点满足：

```text
checkpoint_turn = last_mention_turn + delay
```

探针发生前若再次明确提及同一事实/实体或别名，就从新位置计时。只在未来出现的事实值或别名不会用于更早检查点。自动匹配仍可能漏掉代词、改写或隐含事实，因此默认 `review_required=true`，不能直接据此报告模型遗忘曲线。

可用 `extract --annotations annotations.json` 补充复核记录。该文件为数组，每条格式如下（必须使用真实存在的事实 ID、回合、通道与原句）：

```json
[
  {
    "fact_id": "fact-真实ID",
    "mention_turns": [2, 5, 20],
    "reviewed_through_turn": 54,
    "reviewer": "复核者",
    "evidence": [
      {"turn": 20, "channel": "output.narration", "quote": "此回合确实存在的语义重提原句"}
    ]
  }
]
```

标注不能抹去程序已检测到的重提。所有人工新增提及都需原句支持，复核范围之后的探针仍待复核。当前 action 探针仅组装行动问题，不执行新行动，也不拿历史回复冒充新题答案。

## 严格调用回放与状态边界审计

```bash
# 严格要求历史模型调用响应；现有存档预期明确报缺记录并退出1
/opt/anaconda3/envs/jity-backend/bin/python -m jity_eval replay transitions \
  ../../jity-eval-runs/my-replay/dataset --jity-root .. --output ../../jity-eval-runs/my-replay/strict

# 显式使用已提交剧情JSON核对状态/记忆写入；仍不得伪造辅助模型响应
/opt/anaconda3/envs/jity-backend/bin/python -m jity_eval replay transitions \
  ../../jity-eval-runs/my-replay/dataset --jity-root .. --output ../../jity-eval-runs/my-replay/committed \
  --committed-outputs
```

替身保留 Jity 自身的 JSON 解析和修复链路。缺调用异常继承专用边界异常，避免被 Jity 的普通 `except Exception` 回退逻辑吞掉。独立进程还阻断 socket/DNS、外部进程、`.env` 读取及运行目录之外的写入；这用于防误调用，不是面向恶意原生代码的系统级安全沙箱。

未来如有完整录制，可通过 `transitions --calls calls.json` 提供严格调用数组。每条含 `turn`、`purpose`、`request_sha256`、`response_text`、`provenance`；指纹按 `storage.digest` 计算，输入为 `purpose/messages/model/temperature/max_tokens/json_object`。实际缺失请求的完整指纹与参数已写入 `calls.json` 诊断。请求不匹配、顺序不对、响应缺失都会停止，不用下一条或别的回合响应兜底。

## 本机验收产物

冻结源为 `endingtestv0.1`：54 个时间线回合、36 条骰点记录、54 个记忆快照；活动链排除了 3 个兄弟节点。初次审查发现选项文本重提漏检后，已补全扫描并重新生成 `-v2` 探针和上下文；无后缀目录仅保留为开发过程记录，不作为交付结果。

- [冻结数据集](../runs/jity-replay-20261105/dataset/dataset.json)
- [三组上下文浏览器报告](../runs/jity-replay-20261105/contexts-v2/report.html)
- [候选覆盖与抽样信息](../runs/jity-replay-20261105/probes-v2/coverage.json)
- [严格回放缺记录详情](../runs/jity-replay-20261105/strict-transitions/result.json)
- [提交输出模式的记忆维护缺记录详情](../runs/jity-replay-20261105/committed-transitions-v2/result.json)
- [最终验收摘要](../runs/jity-replay-20261105/acceptance.json)

严格回放在第 2 回合缺少 `story_narrator` 响应而停止；显式提交输出模式在第 6 回合缺少 `memory_nsb_summary` 响应而停止。它们是预期且必须保留的缺口，不是已完成的完整游戏重演。上下文报告中 `assembled` 只表示真实代码成功组装了该分支的信息，不是答案正确、记忆有效或剧情连贯。

完整验证命令：

```bash
/opt/anaconda3/envs/jity-backend/bin/python -m unittest discover -s tests -v
```

2026-11-05 最终验收：Python 3.11 环境下 **115 项测试全部通过，无跳过**；系统 Python 3.9 运行 96 项、跳过 3 个依赖集成测试类，其余通过。已实际完成 7→72 样本暂停恢复，所有样本均只执行一次；24 个探针各自三组的检查点指纹一致，后端状态无变化。浏览器筛选与逐题证据展开已人工操作验证。原数据库 SHA-256、Jity Git 状态和代码差异指纹均与开始前一致。

系统 Python 3.9 会明确跳过真实 Jity 依赖测试；不能把这类跳过算作真实组件已测试。
