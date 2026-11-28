# E37 替换层：短语改写数据与微型 seq2seq（负结果）

**Question.** E34 的替换操作（22.6%）能否作为独立的一层建模：从对齐里抽
(源短语 → 目标短语) 对，训一个微型改写模型？

**Setup.** `build_replace_pairs.py`：oracle 计划与目标按词对齐，取 difflib
`replace` opcode 为对；共 1,406 对，过滤为局部改写（两侧 ≤8 字、不跨句）得
**867 对**（228 个不同源、75 个一源多译，如 沿着→沿/贴着、懂了→完/明白、
接近→靠近）。`rewrite_model.py`：字符级 Transformer encoder-decoder
（**303,330 参数**），40 轮，按源哈希留出（694/173）。

**Results.** 训练 loss 3.33 → 0.41；留出 **exactMatch 1.2%、charF1 0.212**。
样例输出与输入无关（停下脚步 → "前冲了一拳"；沿着服务巷的 → "没有别的动作"）。
数据里大量对是"压缩型替换"（长源 → 短目标，如整句 → "巷口"），不是可学习的
同义映射，另有对齐噪声；一源多译说明脱离上下文的映射本身不成立。

**Interpretation.** 替换层不能作为独立的短语翻译器存在：
1) 数据量不足且歧义大（694 训练对，75/228 源多译）；
2) 映射依赖上下文（同一"沿着"在不同句子里改写成"沿/贴着/顺着"）；
3) difflib 的 replace opcode 混合了压缩与改写两类操作。
架构结论：编辑流水线不能是"指针 + 翻译器 + 标点"三个独立块，需要**看到
整个计划的联合解码器**（在同一序列里决定保留哪些 span、替换成什么、插什么
连接词），或用高频稳定对的小词表兜底、把学习留给联合模型。这也与 goal 的
"局部文本编辑"表述一致——编辑是联合决策，不是三个互不相看的模块。

**Caveats.** 867 对来自 348 段单世界语料；对齐噪声未人工清洗；留出按源哈希，
多译源的变体分布可能跨折。

**Artifacts.** `build_replace_pairs.py`、`replace-pairs.jsonl`、
`replace-pairs-local.jsonl`、`replace-pairs-summary.json`、`rewrite_model.py`、
`rewrite-run.log`、`rewrite-summary.json`。E37。
