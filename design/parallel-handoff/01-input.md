# 01-input handoff: WorldState → 叙事输入投影与序列化

日期：2026-11-10。分支 `goal/local-01-input`，基线 `865ae64e0901a70c3db4f1d0eb2af60268943c53`。本线只改了自己独占的目录，未改 `local/prompt.ts`、`game-model.ts`、训练源数据或其他线文件。

## 1. 解决的问题

主树里未提交的 `legacyNarrationInput` 原型把真实 `WorldState` 直接拼成旧格式，存在四个会改变事实的偏差：

1. **结束态冒充上回合态**：`【地点】【人物】【物品】` 用 `after` 渲染，导致输入里的“上回合状态”已经是本回合结束后的值。
2. **同地点全部物品进入**：`sameRoomItems(after, view)` 把同房间所有物品塞进 `【物品】`；数据规则只收本回合变化的物品。
3. **任意 slice**：物品 `slice(0,4)`、地点 `slice(0,6)` 静默丢实体，且没有省略记录。
4. **中文 localeCompare**：`name.localeCompare(..., 'zh')` 按拼音/区域排序；Python 数据侧用码点排序，非 BMP 名字顺序会不同。

另外补上了原型没有的：容器链到最内层地点的可见性、槽位不切场景、父子任务结果、0 值/空列表的显式结果、长度超限拒绝、旧 YuYan 词表/空白拒绝，以及旧结果块漏写的独立版本。

## 2. 实现与版本

目录：`frontend/src/lib/world-engine/local/narration-input/`。

| 版本 | 用途 | 结果块 |
|---|---|---|
| `narration-projection-v1` | 结构化投影 | — |
| `yuyan-prose-legacy-v1` | 现有 YuYan-700M 权重，逐字节兼容旧 199 行 | 无 |
| `yuyan-prose-result-v2` | 修复后的新格式，另立版本 | 有 |

两个序列化器共用同一个 projection。**不能**把 `result-v2` 的字符串喂给旧权重后声称同条件兼容。

### 2.1 投影入口

```ts
projectNarrationInput({ before, after, delta, timeAdvance, viewpointId, policy? })
  -> { projection, includedEntities, visibleEntities, omittedFields, version }
```

- `before`/`after`：已提交 `WorldState`；`delta`：该点的 `EntityDelta` 记录；`timeAdvance`：该点时间推进；`viewpointId`：视角人物 id。
- `before` 必须是**上一个**已提交状态，不能传 `after` 顶替；根点没有上一状态时不要调用本入口伪造。
- 取数规则按数据侧 README：所有变化实体进入；人物收主角及结束后同最内层地点的人；地点收这些人的变化前后位置、变化实体位置及各自一级上级；物品只收本回合变化的。
- 可见性单独返回：`visibleEntities` 是结束后同最内层地点的全部人物/物品和地点祖先链；`includedEntities` 是真正写进输入的集合；两者不是同一个集合。
- `omittedFields` 逐项记录未进入的实体/未变化的字段/理由（`item_not_changed`、`character_outside_scene`、`field_not_changed` 等），同房间未变化物品也会出现在这里，证明不是漏了。
- 投影只含状态/变化/结果/视角元数据，不含 `叙事`、参考答案、rubric 或评测标签（有测试遍历键名）。

### 2.2 旧格式序列化

```ts
const { text, utf8Sha256, serializerVersion } = renderLegacyInput(projection);
```

- 移植 `convert_yuyan.py::render_row`：`squash`、标题顺序、名字码点排序、列表 `、`/`；` 规则、任务大任务+小任务顺序、`时间推进<值>。`、`【正文】` 结尾。
- 旧版没有结果块；`resultState` 不参与旧格式。
- 输出前检查：任何空白（旧转换只删普通空格/制表符/全角空格的少数位置，其他空白会直接拒绝）、YuYan 词表外字符、长度超限，均抛 `NarrationInputError`，不静默截断或替换。
- 除时间推进外，投影字段里出现空格会报 `whitespace`，不再悄悄 `squash` 掉任务目标等文本。

### 2.3 新结果块序列化

```ts
const { text, utf8Sha256, serializerVersion } = renderResultInput(projection);
```

在 `【变化】` 与 `【正文】` 之间插入：

```text
【本回合状态】名称（类型）：位置…；精神值0；外貌[…、…]；个性[…]；任务大任务《…》（…）；小任务《…》（…，属于《…》）。
```

- 只含本回合变化的实体和变化的字段；字段缺失表示“本结果没携带该字段”，不表示删除或 0。
- `精神值0`、`外貌[]`、`个性[]` 都显式写出。
- 人物、物品的位置变化都会给出结算后的位置；物品位置不会被 `place_line` 漏掉。
- 任务只含本回合完成/新增的任务；子任务带 `属于《父目标》`，保留父子关系。
- 无变化时没有 `【本回合状态】`；此时 v2 文本与 legacy 完全相同。

## 3. 主 agent 接线

当前主树 `frontend/src/lib/world-engine/local/prompt.ts` 的 `legacyNarrationInput(before, delta, after, view)` 用原型拼接。建议只改它的函数体（或调用它的地方）：

```ts
import {
  projectNarrationInput, renderLegacyInput, renderResultInput,
} from '../local/narration-input';

const { projection } = projectNarrationInput({
  before: stateBeforePoint,              // 上一个已提交 WorldState，不能是 after
  after: stateAfterPoint,
  delta: point.entityDeltas ?? {},
  timeAdvance: point.timeAdvance,        // 不能省
  viewpointId: view,
});

// 旧 YuYan 权重：
const input = renderLegacyInput(projection);
// 新 result-v2 权重：
// const input = renderResultInput(projection);
// await input.utf8Sha256 可记录哈希
```

`frontend/scripts/parallel-input/wiring-example.ts` 是可直接复制的包装。需要删掉/停用原型里的 `sameRoomItems`、`slice(0,4)`、`slice(0,6)`、`localeCompare(..., 'zh')` 路径；新入口已经包含同地点不同槽位、容器链、变化物品和码点排序。

## 4. 验证

实际执行（2026-11-10，本工作树）：

```bash
cd frontend
npx tsc --noEmit --target ES2020 --module esnext --moduleResolution bundler --strict \
  --skipLibCheck --resolveJsonModule --lib ES2020,DOM \
  src/lib/world-engine/local/narration-input/index.ts
npx eslint src/lib/world-engine/local/narration-input --ext .ts
npx vitest run src/lib/world-engine/local/narration-input --maxWorkers=1
```

结果：TypeScript 无错误；ESLint 0 error/0 warning；6 个测试文件 47 个测试通过。关键证据：

- 真实 199 行逐字节：`legacy-golden.test.ts` 读取源数据 `rows-xy.jsonl` + `yuyan/rows-yuyan.jsonl`，对每一行用 TS 重渲染，与 Python 已存 `xProse` **逐字节相同**，并与 manifest 的 SHA/字符数/UTF-8 字节全部一致；同时核对源文件哈希。30 行代表性金标冻结在 `goldens/legacy-rows-v1.json`，199 行哈希在 `goldens/legacy-rows-v1-manifest.json`。
- 旧结果块漏写：row-0008 无变化行 v2 无结果块；row-0095 的 `外貌[]` 在 v2 显式出现；row-0002 的物品移动/任务/位置在 v2 出现。
- 真实自由一日世界：路明非/诺诺同在西侧服务巷不同槽位仍互见；同巷 7 件物品只有变化的护目镜进入输入，其余 6 件 `item_not_changed`；路明非移到钟楼后诺诺离开可见集但仍因未变化而不进入；开局空增量没有虚构物品集。
- 合成边界：0 精神值、空外貌/个性、物品移动、父子/孙任务、非 BMP 名字码点排序、容器链、未知实体、after 不一致、空白、OOV、长度超限、结果字段类型错误。
- v2 长度分布（199 行真实输入）：字符 min 197 / p50 427 / p75 501 / max 921；UTF-8 字节 min 575 / p50 1262 / p75 1479 / max 2741；记录在 `goldens/result-length-stats-v1.json`。这是字符/字节数，不是 tokenizer token 数。

重新生成金标：

```bash
cd frontend
python -X utf8 scripts/parallel-input/build_legacy_goldens.py
WRITE_RESULT_GOLDENS=1 npx vitest run src/lib/world-engine/local/narration-input/result-golden.test.ts
WRITE_LENGTH_STATS=1 npx vitest run src/lib/world-engine/local/narration-input/length-stats.test.ts
```

源材料：`D:/others/Jity/.local/world-components-worktree/experiments/world-components/narration-dataset-v1`，提交 `1ab6ca791f97529a7bffed1f4837bf81a28badcb`；`rows-xy.jsonl`、`yuyan/rows-yuyan.jsonl`、`convert_yuyan.py`、`rows_common.py`、`split_xy.py` 的 SHA-256 已写入金标 meta。YuYan 字符集来自 `D:/others/Jity/.local/yuyan/_vocab.json`（SHA-256 `c67c92370d90be7960e53b96dde940d334d5100d3d642478f2be0d2ebe5ac237`），派生文件为 `yuyan-charset-v1.json`。

## 5. 限制与未做

- **没有跑真实 GPU/模型生成**。本线只交付可调用输入适配与字节/结构验证；正文质量、整链等待和 35 次终验留给主集成与预约运行。不得把本线测试写成模型语义验收通过。
- `yuyan-prose-result-v2` 没有已训练权重。格式已冻结、有 30 行样例金标，但质量未验证；不能拿旧权重跑 v2 后声称兼容。
- 旧格式本身有损：物品行不写位置（`place_line` 只读 `位于`）、任务层级被压成一个大任务+小任务列表、没有结果块。`renderLegacyInput` 忠实复现这些损失，不宣称可通用反解析旧自然语言。
- 旧格式只能表达一个大任务加一个小任务列表；一个角色有多个根任务时投影直接拒绝（`multiple_task_roots`），不会静默拍平或任选一个。
- 位置文本会把容器/槽位标签一起写出（例如 `大厅（窗前）`、`路明非的身上（在西侧服务巷里）`），可见性判断本身只用最内层地点；如果主 agent 要求纯地点名，需要在投影策略里另立版本，不能直接改现有字节。
- 地点只补一级上级（数据源规则），不展开全部祖先/同级。本版不提供运行时父层深度开关；如需更深父层，必须另立投影版本并重建对应训练输入。
- `timeAdvance` 是必填；根点/无时间点没有伪造默认值。`before` 不能为空；不要用 after 冒充上一状态。
- 字符集/空白拒绝是 YuYan 路径的约束；换 tokenizer 时传自己的 `charset`，不要删除检查假装通用。
- 未实现真实 tokenizer 的 token 计数、长输入截断策略（策略是拒绝而不是截断）、开局专用投影扩展；这些需主集成按实际模型上下文决定。
