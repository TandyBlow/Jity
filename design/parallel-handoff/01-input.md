# 01-input handoff：与 10 线实际训练的 result-v2 对齐

日期：2026-11-10。分支 `goal/local-01-input`，基线
`865ae64e0901a70c3db4f1d0eb2af60268943c53`。只改本线独占目录；未改
`local/prompt.ts`、`game-model.ts`、训练源数据或其他线文件。

## 1. 问题与结论

10 线 completion.json 已登记两边都叫 `yuyan-prose-result-v2`，但 30 个共同行只有 1 个
字节相同。根因不是“措辞差异”，而是两套不同格式共用了同一个版本名：

- 10 线实际训练的是 `experiments/narration-runtime-v2` 的
  `src/v2_render.py`（提交 `8f22a086a24f0b1ce030cbaa622862b2b3a16ddc`）：
  - 物品状态行 `名称（位于<位置>）：<外貌>。`；
  - 结果块字段用 `，` 分隔，外貌/个性不带方括号；
  - 任务文本是 `任务<目标>（<状态>）`，**不**写“大任务/小任务/属于”标签；
  - `精神值0`、`外貌（空）`、`个性（空）` 显式。
- 01 旧草稿的 `result-v2` 是另一套：物品行漏位置、`外貌[...]`、字段用 `；`、任务带
  `大任务《…》/小任务《…，属于…》`。它从未被训练过。

本线已删除旧草稿格式，TS 适配器改为逐字节复现 10 线实际训练的 v2；旧格式保留为
`yuyan-prose-legacy-v1`，两套格式不再共用版本名。无需另立 v2 新版本，因为不是重定义，
而是采用 10 线已冻结并已训练的那一套。

## 2. 版本与 tokenizer 绑定

| 名称 | 值 | 用途 |
|---|---|---|
| projection | `narration-result-view-v2` | 四字段结构化投影 |
| serializer | `yuyan-prose-result-v2` | 10 线实际训练格式 |
| legacy projection | `narration-result-view-v1` | 仅历史登记；旧数据不再产出 |
| legacy serializer | `yuyan-prose-legacy-v1` | 旧 YuYan 权重，逐字节冻结 |
| model template | `yuyan-raw-completion-v1` | 原始 completion |
| tokenizer | `yuyan-char-v1` | 字符级 |
| tokenizer 文件 | `tokenizer/yuyan-v1/dict.txt` | 13,668 条 |
| tokenizer SHA-256 | `20287a9d1a2ec9d82b2a13f02c10c7b81e8bb015f114134bca6b06e5c8d376b4` | 与 10 线一致 |

`yuyan-charset-v1.json` 由该 dict 精确派生（13,658 个单字符），导入时校验源哈希和
词表大小。charset 不是另一份手写词表。

## 3. 调用方式（主集成与 02 可直接用）

目录：`frontend/src/lib/world-engine/local/narration-input/`。

```ts
import {
  buildNarrationInput, renderNarrationInput, projectNarrationInput,
} from '../local/narration-input';

// 一次调用拿到投影 + 文本 + 字节身份：
const out = buildNarrationInput({
  before,                          // 上一个已提交 WorldState，不能是 after
  after,
  delta: point.entityDeltas,       // 该点 EntityDelta
  timeAdvance: point.timeAdvance,  // 必填
  viewpointId: view,
});
out.rendered.text;                 // 喂模型的准确输入
out.rendered.serializerVersion;    // 'yuyan-prose-result-v2'
out.rendered.sha256;               // 精确 UTF-8 字节的 SHA-256
out.rendered.bytesUtf8Hex;         // 同一字节
out.rendered.segments;             // 块/实体/字段的字符偏移
out.tasks;                         // 完整任务层级（结构化元数据）
out.textCarryLimits;               // 文本无法携带的父子关系/深度
out.omittedFields;                 // 未进入实体/字段及理由

// 旧权重：
const legacy = renderNarrationInput(out.projection, { model: 'legacy' });
```

- `renderNarrationInput` 默认 v2。传 `{ model: 'legacy' }` 才走旧格式。
- `before` 必须是上一已提交状态；`after` 冒充 `before` 会让“上回合状态”错误。
- `rendered.version` 带 `projectionVersion/serializerVersion/tokenizerName/tokenizerHash/
  tokenizerVocabSize/tokenizerStatus`。
- `limits: { maxChars, maxUtf8Bytes }` 超限抛 `input_too_long`，错误上下文带实际
  `charCount` 和 `utf8Bytes`；不截断。
- `wiring-example.ts`（`frontend/scripts/parallel-input/wiring-example.ts`）是可直接复制的包装。

## 4. 物品位置与任务层级

**物品位置**：v2 物品行读 `位置`，输出 `名称（位于<位置>）：…`。row-0002 的
`报架放大镜` 现在包含 `（位于报刊架后）`。旧 `placeLine` 读 `位于` 的丢失只在
`yuyan-prose-legacy-v1` 路径保留，因为旧权重就是按那些字节训练的；不能把旧损失说成已修。

**任务层级**：v2 文本只写 `任务<目标>（<状态>）`，按大任务在前、其余按状态列表平铺。
父子关系和深度**不在文本里**，由 `ProjectionResult.tasks` 保留
（`parentTaskId/parentGoal/depth`），并由 `textCarryLimits` 明确记录：

- `task_parent_relation_not_in_v2_text`：非根任务的直接父目标不在该行文本；
- `task_depth_not_in_v2_text`：深度 ≥2 的任务，文本无法表达它是孙任务。

因此不会“静默丢层级”，也不会声称旧训练文本含层级。若产品要求文本显式写
“大任务/小任务/属于”，那是 **另一个序列化格式**，必须与 10 线协商新版本并重建训练数据，
不能改现有 v2 的字节。

## 5. 金标来源与验证

金标全部来自确定的参考实现，不按 TS 代码改预期：

- 10 线冻结向量：`goldens/runtime-v2/vectors.jsonl`（49 条：20 真实、16 synthetic、
  13 负例），原样复制自 `experiments/narration-runtime-v2/golden/vectors.jsonl`；
  `golden-manifest.json` 的 SHA 与 10 线登记一致。
- 199 条训练投影：`goldens/runtime-v2/train-projections.jsonl`（`{id, x}`，来自
  `data/rows-v2.jsonl`）；`train-rows-index.json` 记录每行 v2 `xProse` 的
  SHA/字符/UTF-8 字节，以及旧 `xProseLegacy` 的 SHA/字符数。
- 本地 `.gitattributes` 强制金标/词表用 LF，避免 Windows checkout 改写行尾后整文件哈希失效。
- 源文件哈希：`source.json` 记录 `rows-v2.jsonl`、`rows-yuyan-v2.jsonl`、
  `golden/vectors.jsonl`、`data/manifest.json` 的登记值与实际值。
- 旧格式：`goldens/legacy-rows-v1.json`（30 行）和
  `legacy-rows-v1-manifest.json`（199 行），来自原数据集提交
  `1ab6ca791f97529a7bffed1f4837bf81a28badcb`。

实际执行（本工作树，2026-11-10）：

```bash
cd frontend
npx vitest run src/lib/world-engine/local/narration-input --maxWorkers=1
npx tsc --noEmit --target ES2020 --module esnext --moduleResolution bundler --strict \
  --skipLibCheck --resolveJsonModule --lib ES2020,DOM \
  src/lib/world-engine/local/narration-input/index.ts
npx eslint src/lib/world-engine/local/narration-input --ext .ts
```

结果：

- 6 个测试文件、97 个测试通过。
- 30/30 旧分歧共同行的 v2 字节与 10 线参考一致（旧 01 样本只对 1/30）。
- 49/49 向量：v2 文本、UTF-8 hex、SHA、segments 全部逐字节相同；13 个负例的
  `stage/errorCode/errorPath` 全部相同。
- 199/199 训练行：v2 的 SHA/字符数/字节数与 10 线 `xProse` 全部相同；同一投影的
  legacy 输出与 `xProseLegacy` 的 SHA/字符数全部相同；存在 10 线活数据时逐字节再对照。
- 199/199 旧数据集行逐字节等于原 `xProse`；源文件哈希一致。
- 真实自由一日世界：同巷不同槽位仍互见；同巷 7 件物品只有变化的护目镜进入；移动后
  诺诺离开可见集；空增量不虚构物品集。
- 边界：0 精神值、空外貌/个性、物品移动、任务层级、非 BMP 码点排序、容器链、未知实体、
  after 不一致、纯删除无 supersede、多个任务根、任务环、换行/NBSP/OOV、长度超限。

刷新冻结：

```bash
cd frontend
python -X utf8 scripts/parallel-input/sync_v2_contract.py
python -X utf8 scripts/parallel-input/build_legacy_goldens.py
```

## 6. 限制与未做

- 本线没有跑真实 GPU/浏览器生成；v2 权重属于 10 线，正文质量和延迟留给质量线与集成运行。
  本线通过只证明输入格式/字节/错误类别一致，不证明叙事质量。
- v2 文本任务层级是平铺的；层级只在 `tasks`/`textCarryLimits` 元数据。不要从文本“推断”
  父子关系。
- 旧格式有损（物品位置、任务层级、无结果块），忠实复现，不提供通用反解析。
- 一个角色没有任务树或多个根任务时拒绝（`empty_tasks`/`multiple_task_roots`），不凭空
  补层级。
- 地点依赖只加“场景种子 + 一级父地点”（源数据规则）；更深的祖先策略需要新投影版本。
- 只测字符数和 UTF-8 字节数，没有真实 tokenizer token 计数；长度上限由调用方按模型上下文给。
- `renderNarrationInput` 对旧三字段投影会补空结果块以走 legacy；v2 仍要求四字段，缺字段报错。
