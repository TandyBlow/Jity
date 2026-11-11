# action-next-step — MiniRBT-H256 next-action classifier (04 experiment)

产品协议不变。本目录只做用户指定的分类实验：给一个角色自己知道的信息，预测他最可能立刻做的 0/1/2 步动作（每步一个细谓词 + 可选对象）。

## 为什么不是一个 12 分类器

Y 是 `steps: [{action, object}]`（0/1/2 步）。12 个粗组永远表示不了“几步、哪步是哪个细谓词、指向哪个候选”。所以模型有：

| 头 | 形状 | 说明 |
|---|---|---|
| step | 3 类 | skip / 1 步 / 2 步 |
| action ×2 | 115 细谓词 | 每步一个，掩掉不存在的步 |
| object ×2 | [null, 候选1…候选n] | 候选列表随场景变化，不是固定 id 词表；null 是可学习向量 |

粗 12 组只用于报告（`evaluate.py`），不参与输出。

## 冻结顺序（`freeze.py` → `freeze.json`）

1. `freeze.py` 先登记：标签文件、判据原文、序列化器、模型/训练/评测/分词长度脚本的 sha256，种子、臂、超参、损失与掩码规则、指标口径。
2. `train.py` 启动时核对整棵树；任何一个登记文件变了就拒绝训练。
3. 种子在**加载编码器、创建任何新头之前**设置（旧 N5 是初始化之后才 seed，那一步不复用）。
4. `measure_tokens.py` 先量真实 token 长度，`maxLen = ceil(p100/32)*32`，上限 384；超了报数量，不静默截断。

## 序列化器读的是真实 13 行

`serialize.py` 读九槽 X：角色/目标/地点/在场/物品/刚才/精神/个性/候选。它已对着 13 的 `project_x` 真实输出验证过（`tests/fixture/row13-shape.jsonl`，X 是提交快照 `3f65452daf352c63` 里 caesar 的真实投影，只有 `y` 是 04 写的指针测试目标，标了 `labelSource=fixture`）：

- `goals` 是 `"task_id：目标文本"` 字符串；
- `character.holds` 打印成 `（持有：…）`，否则拿在手里的东西和箱子里的东西分不出来；
- 候选带上自己的容器/槽位（`@ 短讯机电池盒（在红方集结点）/第一格`），因为“指哪件东西”和“够不够得着”是同一个问题；
- 未知键（appearance 等）忽略；空槽打印 `（无）`，不省略行。

## 损失与掩码

- skip 是正式类，权重 0.3；skip 行只训练 step 头，没有 action/object 损失；
- 1 步行掩掉第 2 槽；2 步行两槽都训练；
- action 权重 = `clip(中位计数/该类计数, 1.0, 1.5)`，只用训练集算，报告里打印实际值；训练集缺失的细谓词权重 0 并列在报告里；
- object 用 `CrossEntropyLoss` 多项（null 也是选项），padding 候选被掩掉。

## 命令

```bash
# 本机 CPU 机制测试（32 维随机编码器；报告标 mechanism，不允许导出/当真训练）
python -m pytest tests -q

# 冻结 / 校验
python freeze.py --rev
python freeze.py --verify

# 真实训练（HPC；本机没有 MiniRBT 权重）
python measure_tokens.py --base base/minirbt-h256 --rows data/train.jsonl data/validation.jsonl --out token-lengths.json
python train.py --base base/minirbt-h256 --train data/train.jsonl --validation data/validation.jsonl \
  --token-lengths token-lengths.json --arm frozen_encoder --out runs/frozen
python evaluate.py --rows data/validation.jsonl --base base/minirbt-h256 --head runs/frozen/head.pt --max-len <measured>
```

## 边界

- 不训练未审的行；测试集的 15 个目标只开一次，答案由 01 冻结；
- 训练只在 HPC；本机 4060 不跑；
- 300 行一版不达标 ≠ 任务不可学；12 组命中 ≠ 完整 Y；
- 本目录不碰产品文件、不改动作协议、不加导出/服务框架。导出这一步要等训练有结果再单独定。
