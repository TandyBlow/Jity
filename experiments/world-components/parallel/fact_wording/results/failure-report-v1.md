# c4：cf24 失败分类 v1

支持 R11 / narration N4。档位：**有归档分析结果**；没有新推理、训练或接线。

冻结 cf24 输入交给 u240 的旧 CPU 贪心运行产生原文，旧 assistant 判读给出逐条标签；
本脚本按 unitId 连接原文、判读、机械判分、训练重叠和冻结夹具，分类并保留原标签。
本轮没有真人核验；review/batch-*.json 是待核验清单。

## 已证明：归档里记录了什么

逐条连接 85 单元 / 24 源；归档 factSupported=85。这不是本轮重新证明模型事实正确。
原标签缺陷 11 条：新增 6、复述 2、语病 3；全干净源 15。
签名独立 74 条，其中缺陷 5 条；签名独立不等于新场景或短语独立。

## 已失败：分类到原文

分类可重叠。subject 指鞋底充当新增小句的主语，不改判为核心人物互换。position 指额外停留，物件出现在可见列表不授权停留。

| 类别 | 已失败单元 | 无法判断单元 |
|---|---|---|
| subject | t07:f0, t15:f0 | — |
| direction | 无已登记失败 | t14:f0, t18:f0 |
| sanity_value | 无已登记失败 | t10:f3, t16:f2 |
| position | t07:f0, t15:f0 | — |
| extra_action_state | t07:f0, t07:f1, t11:f0, t12:f0, t15:f0, t17:f0 | — |
| repetition | t11:f1, t23:f2 | — |
| language | t21:f0, t22:f0, t24:f1 | — |

输入、事实、输出原文、原始路径和耗时详见 results/cf24-catalog-v1.json。待人工核验按以下批次拆分，当前均为pending：

- review/batch-01.json（10条）：t07:f0、t07:f1、t10:f3、t11:f0、t11:f1、t12:f0、t14:f0、t15:f0、t16:f2、t17:f0
- review/batch-02.json（5条）：t18:f0、t21:f0、t22:f0、t23:f2、t24:f1

## 无法判断：覆盖与来源缺口

- 关系双方互换没有专门样本；移动起终点是另一维度，不以起终点正确替代关系方向验收。
- 移动10条，direction均为平；上升、下降未覆盖。t14:f0和t18:f0的“上来”仅列措辞风险，原factSupported不变。
- 理智仅t10:f3和t16:f2，都是12→9，实际输入只写“发紧”、禁止数值；不能验证数值保真、上升和不变。
- 85条缺entityId/pointId/世界fieldPath。记录冻结contract行号和materials JSON指针，保留缺失值，不按姓名造ID。可复核旧夹具，但不能据此冒充已提交世界点或新的独立验收。
- 归档reviewer明确为assistant；标题里“人工”不能当作真人签字。新核验状态一律pending。

## 旧提示变体与重试、回退

results/cf24-moved-rule-pairs-v1.json保存全部10条移动的基线/提示变体原文和实际输入；其中3条输出变化。
变体仅在10条移动输入插入归档提示，其余75条输入逐字相同；变化后的文本不继承旧片段判读，结论记undetermined。
旧文件各记录一次基线与一次提示变体；没有完整尝试历史，不能声称仅尝试过两次。本轮新增生成0、重试0、未执行回退。

## 运行身份、速度与复跑

权重sha256：`ab8a98264ee6b4f83eba17d624d7b92b23522c8eacef07d07a5be960e390184a`。原文来自CPU/4线程的贪心运行，EOS或20秒预算；每条seconds/newTokens保存在catalog中。
本轮只做文件分析，不把旧seconds当作本轮推理速度，不与CUDA探针混比。原生成完整SHA缺失；旧报告仅给43d897b前缀，分类HEAD、脚本哈希、输入哈希在context/sources中。

```powershell
python -X utf8 scripts/classify_cf24.py
python -X utf8 scripts/classify_cf24.py --check
```

来源哈希、每条连接、输入不变性和归档summary均通过后才写结果；--check只读核对生成文件。review清单不承载已完成的人类判定，真人反馈应另存文件。

## 可单独阅读的结论

当前明确的旧失败是新增动作/状态、复述和语病；没有证据把这些改写成主体互换或理智数值错误。
这份分类完成诊断材料整理，不能宣告模型泛化通过。后续对照必须固定u240身份，用登记的独立输入验收，不能围绕这些旧句子删尾或打补丁后宣称新场景有效。
证据：results/cf24-catalog-v1.json、results/cf24-moved-rule-pairs-v1.json、freeze/failure-classification-v1.json。
