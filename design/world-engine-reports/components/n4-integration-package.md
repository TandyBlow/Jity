# N4 接入包（B 侧工程接入用）

日期：2026-10-29（复核轮 18）。对象：**冻结的 N4 短计划成句组件 `r3-direction`**。离线质量门已在六类短计划范围内关闭（独立留出 44/44，见[语料协议 §11](../../../experiments/world-components/n4_corpus/corpus_protocol.md)）。

C 负责解释接口与定位差异；页面、控制器、运行层与接线归 B。**离线验收与浏览器验收分别记录，不能互相顶替**：本包给出的是离线结论，浏览器侧（T5 端到端、JS sentencepiece、共存开销）仍未验证。

## 1. 组件边界

| 项 | 内容 |
| --- | --- |
| 输入 | 已提交事实计划（`plan` 条目数组）＋视角；事实来自 Python 权威路径，不由 B 侧结果文本反推 |
| 输出 | 一段中文正文（1–2 句）；不含对话、不含新增实体或事件 |
| 不负责 | 事实提取、内容选择（N2）、排序/指代（N3）、事实核对门（判据由程序承担） |
| 事实种类 | `moved`、`task_achieved`、`personality_changed`、`sanity_changed`、`appearance_changed`、`positioned_at`、`time`、`no_change` |
| 组合范围 | 六类短计划：单点移动、空点（含/不含时间）、任务达成、任务→人格→理智联动、地点外貌、同点多人物 |
| 已验证规模 | 输入 **1–4 条事实**（含时间条目；不含时间时 1–3 条），输出 1–2 句；训练输入上限 128 token、输出上限 64 token |

## 2. 共享渲染器（必须一致）

渲染器是训练与推理的唯一输入格式，**B 侧不要自己拼提示词**：

```python
# experiments/world-components/n4_corpus/n4_render.py
render_input(plan: list) -> str
sha256 = 65bfe89adfbb75d5637d3661cab383aa9bc678dffb97ab5eb8a0d28ac1e3f2ef
```

```python
def render_entry(e):
    moved                -> f"位置：{name} 从{from}到{to}"
    task_achieved        -> f"任务达成：{name}「{goal}」"          # goal 原文逐字
    personality_changed  -> f"个性：{name}{text}"
    sanity_changed       -> f"理智：{name} {from}→{to}（上升|下降|不变）"  # 方向由程序算
    appearance_changed   -> f"外貌：{name} {text}"
    positioned_at        -> f"现状：{name} 已在{at}"
    time                 -> f"时间推进：约{num_cn(amount)}{分钟|小时}"
    no_change            -> "无变化"
# 输出： "叙事生成任务。\n事实：\n1. …\n2. …\n正文："
```

输入示例（六类，均为冻结语料真实渲染）：

```
叙事生成任务。                                    叙事生成任务。
事实：                                            事实：
1. 位置：陈舟 从东门到钟楼                         1. 时间推进：约八分钟
2. 时间推进：约三分钟                              2. 无变化
正文：                                            正文：
```

```
叙事生成任务。                                    叙事生成任务。
事实：                                            事实：
1. 任务达成：陈舟「把铜铃挂回钟楼」                 1. 任务达成：苏晚「整理柴房」
2. 时间推进：约十二分钟                            2. 个性：苏晚变得沉稳
正文：                                            3. 理智：苏晚 10→13（上升）
                                                  4. 时间推进：约二十五分钟
                                                  正文：
```

```
叙事生成任务。                                    叙事生成任务。
事实：                                            事实：
1. 外貌：石桥 门柱上的漆皮剥落了大半                1. 位置：陈舟 从东门到柴房
2. 时间推进：约四十分钟                            2. 现状：林望 已在柴房
正文：                                            3. 时间推进：约三分钟
                                                  正文：
```

输出示例（**逐字取自** `artifacts/world-components/n4-holdout-eval-r3-direction.json` 的 `arms.finetuned.results.unseen`；括号内是留出集条目 ID，可与归档核对）：

| 输入族 | 归档条目 | 模型输出（原文，含半角标点） |
| --- | --- | --- |
| loc（含时间） | `n4h-loc-01` expressed | `陆知微由柳堤进入药圃。前后大约九分钟。` |
| loc（省略时间） | `n4h-loc-01` omitted | `陆知微从柳堤来到药圃。` |
| empty | `n4h-empty-01` expressed | `一切如旧。前后大约九分钟。` |
| task（省略时间） | `n4h-task-01` omitted | `陆知微完成了任务「把风灯挂上檐角」。` |
| chain（含时间） | `n4h-chain-01` expressed | `陆知微完成了任务「把风灯挂上檐角」,变得从容,精神值从9升到了12。前后大约九分钟。` |
| appear（含时间） | `n4h-appear-01` expressed | `柳堤的外观变了:檐下水痕洇成了深色。前后大约九分钟。` |
| multi（含时间） | `n4h-multi-01` expressed | `陆知微从柳堤来到药圃时,苏砚已经在药圃了。前后大约九分钟。` |

注意：模型输出使用半角逗号与半角冒号，与语料参考正文（全角）不同；判据 `corpus_check` 显式接受这种标点变体。**B 侧判据若只认全角标点，需自行放宽，否则会把正确输出判成不一致。**

**省略时间的行**：`plan` 里不含 `time` 条目，正文不得出现时长（判据会把时长视为残句）。渲染器对 omitted 计划自然不输出第 1/2 行时间条目。

## 3. 模型取得方式与完整哈希

权重**不入库**（`experiments/world-components/assets/` 被 `.gitignore` 排除），B 需要按下述任一方式取得，并用哈希核对：

| 步骤 | 说明 |
| --- | --- |
| 1. 基座 | `IDEA-CCNL/Randeng-T5-77M-MultiTask-Chinese`（经 hf-mirror），全参 77,440,384 |
| 2a. 直接取检查点 | 由协调人/CI 提供 `n4-finetune/r3-direction/` 目录副本；按下表核对 7 个文件 |
| 2b. 自行重建 | `python experiments/world-components/n4_corpus/train_n4_sentence.py --tier large --run-tag <新标签>`（**不要用 `r3-direction`**：该脚本的 r1 护栏只防旧语料，同 tag 重跑会覆盖冻结检查点）；360 步、batch 8、lr 1e-4、seed 20261029、cuda、fp32；语料哈希见 §4，重建后与新标签目录逐文件比对 §3 哈希 |

检查点（`r3-direction`）sha256 前 16 位：

| 文件 | sha256[:16] |
| --- | --- |
| `model.safetensors` | `baceebff5d33eacf` |
| `config.json` | `a35e9d4382657106` |
| `generation_config.json` | `691648bea8d35875` |
| `special_tokens_map.json` | `65d84a9271d68f12` |
| `tokenizer_config.json` | `553da19a6ed43c57` |
| `spiece.model` | `c65feffa65ff0378` |
| `added_tokens.json` | `a247922ac010bc17` |

基座（Randeng-T5-77M）sha256 前 16 位：`config.json 9b2480c0a39fd09b`、`model.safetensors 5cdc572109cf2591`、`special_tokens_map.json 09059cedc26bc46b`、`spiece.model c65feffa65ff0378`、`tokenizer_config.json af072c7d91576727`。

## 4. 分词与解码配置（唯一一份）

| 项 | 值 | 说明 |
| --- | --- | --- |
| 分词器 | `T5Tokenizer(legacy=False)`，`spiece.model` 由检查点自带 | 训练、评测、推理同一设置；`legacy` 改动会使冻结校验失败 |
| 最大输入 | 128 token | 超出即视为**不支持**（见 §6），不要静默截断 |
| 解码 | greedy（`do_sample=false`）、`max_new_tokens=64`、`num_beams=1` | 冻结在 `freeze-r3-direction.json` 的 `decode` 字段 |
| 语料/渲染器/判据哈希 | `corpus.seeds.jsonl f14e451a…`、`rewrites.jsonl 2811d731…`、渲染器 `65bfe89a…`、判据 `e16bd2c9…` | 判据 = `corpus_check.py`（Python，离线） |

## 5. 支持范围（可接线的部分）

- **支持**：§1 的八种事实种类、六类短计划组合、1–2 句输出、**1–4 条事实**的计划（语料实际覆盖范围，未测试更长计划）。
- **不在范围**：对话生成、人物外貌/物品描述、跨场景长叙事、多轮上下文、事实选择与省略（N2 未通过验收）、排序与指代（N3 未验证）、浏览器内运行（未验证）。
- **不承诺**：风格多样性（通过项普遍偏模板）、超过 4 条事实的计划、跨句衔接。

## 6. 异常与降级约定

| 情况 | 约定 |
| --- | --- |
| 计划含不支持的种类 / 结构 | **不调用模型**，直接走 B 现有模板；记录 `unsupported-plan` |
| 渲染后超出 128 token | 视为不支持（`plan-too-long`），不截断、不拆分调用；当前无拆分路径 |
| 生成空串或只有标点 | 走模板回退，记录 `empty-output` |
| 输出被 B 侧门控判为事实不一致 | 走模板回退，保留原始输出与判定原因，供 C 定位差异 |
| 超时/取消 | 按 B 现有 AbortSignal 语义丢弃迟到结果，不进状态、不重试 |
| 时间条目被有意省略 | 正常路径：正文不得提时长；出现时长按事实不一致处理 |

回退时**不要**把模板文本记成模型输出；两条路径分开统计，用于后续对照。

## 7. 接入时需要 C 配合的事项

- 输入事实与 B 侧 `projectCommittedNarration` 投影的差异：投影当前不支持物品/地点变化、外貌、复杂位置，N4 的 `appearance_changed` 等事实需要直接取 `entityDeltas`，不能经过投影后再喂模型。
- 输出差异定位：提供模型输入（`render_input` 结果）、原始输出、B 侧判定，C 用同一判据复算。
- 浏览器适配属于独立工作项：需要 sentencepiece 的 JS 实现与 encoder-decoder 生成循环（wllama 或 ORT 直驱），**当前没有结论**。

## 8. 验收记录分离

| 验收 | 状态 | 证据 |
| --- | --- | --- |
| 离线（六类短计划） | **通过**（协调人签字，复核轮 17） | `artifacts/world-components/n4-holdout-eval-r3-direction.json`（44/44 + 1/1） |
| 浏览器（T5 端到端） | **未验证** | 无 |
| 接入后整链 | **未验证** | 待 B 接线 |
