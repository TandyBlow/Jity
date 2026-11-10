# 晋级门（11/12/06 共用）：三种结果与用法

这是 `narration-quality` 的决策助手，不是质量判决。它只回答一件事：这段文字能不能作为"事实干净、可读的模型正文"展示；不能的话，是拦住还是重写。

## 三种结果

| 结果 | 含义 | 触发条件 |
|---|---|---|
| `accept_as_model_prose` | 没有事实错误、没有阻断级文风问题、没有未定来源 | 全部通过 |
| `hold_for_review` | 可以给人读，但不能算通过 | 只有 `review` 项或"疑似程序成文" |
| `regenerate` | 不能展示，重写 | 任一 `fact` 项；阻断级文风（字段句、面板、复读、截断、名单播报、元叙述）；缺少已结算的时间；长度越界；来源是程序成文或混合 |

`review` 项**永远不等于通过**：`hold_for_review` 只是"还没人读过"。

## 一条命令

```
cd frontend
NARRATION_QUALITY_ROWS=<rows.jsonl> \
NARRATION_QUALITY_GATE_REPORT=<gate.json> \
NARRATION_QUALITY_MIN_CHARS=50 \
npx vitest run src/lib/world-engine/local/narration-quality/gate-batch.test.ts --maxWorkers=1
```

`rows.jsonl` 每行：`{"id","input","text","textSource":"model"}`。`input` 是公开开发包里的结构化行（`视角/上回合状态/本回合变化/本回合状态`），`text` 是候选正文。

## 实跑示例（02 的三份新输出 + 一份变体）

| 样本 | 字数 | 结果 | 原因 |
|---|---|---|---|
| clean / prose | 144 | `regenerate` | 1 条事实（没结算的风铃） |
| clean / scene | 122 | `regenerate` | 2 条事实（枪声只存在于习惯里） |
| clean / beats | 59 | `hold_for_review` | 无事实错误；有复核项 |
| repair / prose | 97 | `regenerate` | 2 条事实（风铃、发圈写到路明非身上） |
| quiet / beats | 53 | `hold_for_review` | 无事实错误；有复核项（护目镜"紧贴双眼"在补规则后已判事实） |

注意最后一行：这是补规则**之前**的判定。检查器只会在证据支持下变严或放宽，不会为了让样本通过而改判。

## 给 06 的接入点

页面拿到模型正文后先调 `reviewNarration`，再调 `gateNarration(report, { textSource })`：

- `regenerate` → 不展示这段文字，回到生成；
- `hold_for_review` → 可以展示，但记录"未人工复核"；
- `accept_as_model_prose` → 仍需保留四层证据（原始/清洗/截去/显示）。

程序成文的文本必须带 `textSource: 'program_fallback'`，否则 `fallback_suspected_but_labelled_model` 会要求重写。

## 直接调用的样子（06 用）

```ts
import { reviewNarration } from '@/lib/world-engine/local/narration-quality/review';
import { gateNarration } from '@/lib/world-engine/local/narration-quality/gate';

const report = reviewNarration({ id: turnId, input: settledInput, text: candidate });
const gate = gateNarration(report, { textSource: 'model', minChars: 50 });
// gate.decision: 'accept_as_model_prose' | 'hold_for_review' | 'regenerate'
// gate.reasons: 人可读的原因列表；regenerate 时不要展示 candidate
```

- `settledInput` 是四字段结构化输入（`视角/上回合状态/本回合变化/本回合状态`），不是提示字符串。
- 页面已有的 `narration-alignment` 检查继续保留；这个门只补"事实与文风"的判断，不替代对齐检查。
- `hold_for_review` 可以展示，但证据里要记 `humanReviewed: false`。
