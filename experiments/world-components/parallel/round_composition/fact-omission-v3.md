# v3 事实遗漏原因分析（10 个样本，首次调用）

只分析已归档文本，没有新的模型调用。每一条必述事实一行，分类口径写在 `make_fact_omission.py` 头部。

合计 22 条必述事实：ambiguous 1、conflated 2、conveyed 2、meta_only 1、missing_component 6、not_attempted 1、paraphrased_conveyed 8、wrong_fact_aspect 1

| 样本 | 事实 | 类型 | 记录 | 类别 | 正文实际写了什么 |
| --- | --- | --- | --- | --- | --- |
| rb-move-outcome | f0 | moved | 管线镇→钟楼 | missing_component | 正文从「钟楼的旧木门……推门而入」开始，起点从未出现，到达也没有陈述 |
| rb-move-outcome | f1 | outcome | 把铜铃挂回了钟楼 | paraphrased_conveyed | 「他熟练地将铜铃挂回原位」 |
| rb-time-vague | f0 | moved | 管线镇→钟楼 | missing_component | 「他缓缓走向钟楼内部」——已在钟楼内，无起点 |
| rb-time-vague | f1 | outcome | 把铜铃挂回了钟楼 | paraphrased_conveyed | 「轻轻挂回原位」 |
| rb-time-vague | f2 | time | 时间经过 | conveyed | 「过去了一会儿」 |
| rb-inner-change | f0 | appearance_changed | 外袍被雨浸透 | paraphrased_conveyed | 「雨水顺着衣襟滴落，浸透了衣料」 |
| rb-inner-change | f1 | personality_changed | 话少了许多 | not_attempted | 只写了步伐与心情，没有触碰说话多少 |
| rb-inner-change | f2 | sanity_changed | 理智上升 | ambiguous | 「他心中却渐渐平静下来」方向可上可下 |
| rb-two-actors-move | f0 | moved | 管线甲 管线镇→钟楼 | missing_component | 从钟楼内部写起，「穿过破旧的走廊」 |
| rb-two-actors-move | f1 | moved | 管线乙 管线镇→钟楼 | missing_component | 「管线乙急匆匆地跟在后面」——跟随，无起终点 |
| rb-same-name | f0 | moved | 管线甲 管线镇→钟楼 | missing_component | 「他从管线镇出发……钟楼的轮廓」——给了起点，没有到达 |
| rb-same-name | f1 | moved | 管线乙 管线镇→钟楼 | conflated | 两个「管线乙」被写成同一个跟随者 |
| rb-same-name | f2 | moved | 管线乙 管线镇→钟楼 | conflated | 同名第二人被并入同一个跟随者，身份没有分开 |
| rb-subtask | f0 | moved | 管线镇→钟楼 | missing_component | 「推门而入……沿着楼梯缓缓而上」 |
| rb-subtask | f1 | subtask_added | 找梯子（属于：把铜铃挂回钟楼） | wrong_fact_aspect | 「环视四周，寻找着可以攀爬的梯子」——自己去找，不是被交付 |
| rb-sanity-only | f0 | personality_changed | 对雾天格外警觉 | paraphrased_conveyed | 「雾气如丝般弥漫……目光中透出一丝警觉」 |
| rb-sanity-only | f1 | sanity_changed | 理智下降 | paraphrased_conveyed | 「他的理智却在逐渐模糊」 |
| rb-time-only | f0 | time | 时间经过 | conveyed | 「过去了一会儿」 |
| rb-time-only | f1 | no_change | 无变化 | paraphrased_conveyed | 「管线镇依旧保持着那份宁静」 |
| rb-conflict-two-actors | f0 | outcome | 合力把钟抬离了地面 | paraphrased_conveyed | 「我们齐心协力，将钟缓缓抬离了地面」 |
| rb-conflict-two-actors | f1 | outcome | 抬钟时肩膀抵住了钟沿 | paraphrased_conveyed | 「他的肩膀不由自主地抵住了钟沿」 |
| rb-move-other-appearance | f0 | moved | 管线镇→钟楼 | meta_only | 「到达了钟楼的顶层，完成了任务指令中的移动」——陈述的是指令，不是位移 |

## 移动事实（6 个样本、9 条事实）

没有一条完整写出「从 A 到 B」。具体缺法：

| 缺法 | 条数 | 例子 |
| --- | --- | --- |
| 缺起点（正文从目的地内部开始） | 4 | rb-move-outcome「推门而入」 |
| 缺终点（只写了出发） | 1 | rb-same-name「他从管线镇出发」 |
| 起终点都缺（只有局部走动） | 1 | rb-two-actors-move「跟在后面」 |
| 只陈述指令，不陈述位移 | 1 | rb-move-other-appearance「完成了任务指令中的移动」 |
| 同名两人被并成一个 | 2 | rb-same-name 两个「管线乙」 |

## 结果事实（4 条）

4 条全部在语义上传达了（挂回原位、抬起钟、肩膀抵住钟沿），只是没有使用记录里的原话。**只放宽结果帧，能改变 4 条事实，但一个样本也不会翻盘**——同一段正文里移动事实仍然缺失。

## N6 的两处更正

- `rb-sanity-only` `f0`：原判「fail: the personality change is not conveyed」→「conveyed (weakly): fog plus a wary glance is the recorded trait」。verdict unchanged: the sample still fails on invented residents and an unknown danger。
- `rb-time-only` `f1`：原判「fail: the no-change fact is not conveyed」→「conveyed: 管线镇依旧保持着那份宁静 states that nothing changed」。verdict unchanged: the sample still invents a walk to an abandoned factory area。

## 这组数据说明什么

1. 模型不是「不会写结果」，而是**不会按记录组织一段有位移的正文**：开头默认已经在目的地，或者用局部走动（上楼、穿过走廊、跟在后面）代替记录里的起终点。
2. 任务交付（新任务）被写成自己动手找梯子——模型把「被交付」理解成「去做」。
3. 因此下一轮该改的是 N4 的输入组织（按句组逐条列出必述事实、移动显式给起点和终点、只允许补充不改变世界状态的场景描写），而不是继续放宽正则。
4. 这一分析也暴露单复核者的风险：两处 N6 判定（`rb-sanity-only` 的个性、`rb-time-only` 的无变化）经复核应改判为已传达，样本结论不变，但说明需要第二复核者。
