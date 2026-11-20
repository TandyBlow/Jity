# 模型适配器修复＋三个任务的浏览器真机短测

日期：2026-10-27。实现提交 `c25ede498c4f80028b389d491043c0b5feacd49e`。

**适配与短测已完成，模型语义尚未达到直接驱动世界状态的条件。**
六条都正常 EOS、通过结构解码；本任务逐条内容复核为 action 2/2、updates 0/2、
narration 1/2。没有重跑全量 B3，没有接完整模型链或用户交互页面。

- [qwen3-0.6b.json](qwen3-0.6b.json)：逐条输入、完整提示词、原始输出、codec/judge 结果、
  首 token 耗时、总耗时、底层 prefill/decode/cache 计数及实际设备配置。
- [review.json](review.json)：逐条人物/事实/变化核对，保留自动底线误放行及风格问题。
- [manifest.json](manifest.json)：报告哈希与实现提交的源码绑定。

## 修复内容

- `createChatCompletion` 使用模型聊天模板；`enable_thinking=false`，`cache_prompt=true`。
  流式收集原文和结束原因，不用截取第一个 JSON 或删除思考文本来掩盖失败。
- action 使用 act/skip 互斥 JSON grammar；updates 约束调用阶段、实体名册和该阶段字段。
  最终仍经原 codec 校验；split 模式还核对返回 stage 等于请求 stage。
  narration/reaction 不加 JSON grammar，泄漏思考/结束标记则拒绝。
- 默认 token 上限：action 80、updates 192、narration 128、reaction 80，其他任务 256；
  显式调用参数可覆盖。长度截断和缺失正常结束原因均拒绝，保留付出的生成成本及原文。
- 适配器默认生成期限 120 秒；本次短测为 90 秒，外层浏览器 watchdog 为 110 秒。
  正常完成、结构拒绝、引擎失败都逐条落盘，流式中间输出也做断点保存。
  泛用 B3 harness 同步补齐引擎失败的 onSample 回调及部分输出，避免丢失失败证据。
- action 提示词明确当次角色与主角的区别；updates 教清字段；叙事要求只表达提交事实。

本次仅为上述三个任务补 JSON/文本适配与短测，未为其他 B3 JSON 任务补全生成 grammar。

## 固定配置与实际结果

真实 Edge headless `155.0.4283.62`，本地 Qwen3-0.6B-Q4_K_M.gguf，wllama 3.8.1，
libllama `b11364-46ca246`。CPU i7-13700H，实际 `multithread=true / numThreads=4`，
CPU 推理、无 GPU offload；n_ctx=4096、temperature=0、seed=42。
模型、JS bundle 与 wasm 的 SHA-256 均在原报告中。没有下载或提交新权重。

输入是独立的小型完整世界：林川守门，主角周宁与盒子都在走廊，另有门厅。
每任务两条显式反例/正例；不是原 20 条冻结样本的子集，也不代表全量覆盖。
叙事移动样本的 before/Δ/after 已独立核对一致。

| 样本 | 秒 | 原始输出要点 | 内容复核 |
| --- | ---: | --- | --- |
| action-npc | 55.4 | 林川在走廊守门 | 通过窄判据，没有代主角开盒 |
| action-player | 36.8 | 周宁打开盒子 | 行动提议归属正确，成功与否仍待结算 |
| updates-position | 39.4 | person_a 仍设 corridor，slotId 为字符串 "null" | 失败；应移到 hall，slotId=null |
| updates-sanity | 37.1 | sanitySet=10 | 失败；确认结果要求 8 |
| narration-root | 35.9 | 周宁站在门厅 | 失败；实际仍在走廊，自动底线误放行 |
| narration-move | 68.2 | 周宁留走廊、林川入门厅、盒盖关闭 | 三个事实正确；只写一句，未满足两句风格指令 |

codec 结构正确率 6/6；原自动底线为 4/6；逐条内容复核为 3/6。
这三者分别记录，不能把 COMPLETED 或 JSON 合法当作语义验收。
内容复核由当前编码任务完成，不冒称用户签字或独立人工复核。

六次调用共 272.8 秒，中位数 38.3 秒，模型加载另计 8.0 秒。
底层 prompt_ms 合计占生成墙钟约 92.4%；只有第二个 action 命中 120 个缓存 token，
其余 cache_n=0。当前主要成本是长输入处理，不是输出过长。
输入、线程数、提示词及 token 上限均与旧 20 条基线不同，不将耗时差异单独归功于某项修复。
所有样本此次均以 stop 结束；截断/超时拒绝路径另由回归测试验证，未故意烧长调用做破坏实测。

## 分工决定与下一批

| 环节 | 本批结论 | 接线要求 |
| --- | --- | --- |
| 人物身份、输入是否已消费、合法 ID、状态提交 | 程序/服务端规则持有 | 不交给模型重新生成或解释 |
| action | 小模型可继续作为受约束的行动提议候选 | 名册/角色归属/命令消费门控在程序；2 条不足以认定通用能力达标 |
| updates | 当前模型不能直接产出权威状态 Δ | 先得到可核对的结构化已确认事实，再确定性映射并 preview/校验；不能泛称规则能无损解析任意自然语言结果 |
| narration | 全状态直接写作不可靠 | 程序提取已提交事实/差异，规则模板或分段表达；小模型润色后复核事实，失败退回模板 |

最小页面下一批宜先限制少量可核对指令，打通结构化事实→规则更新→提交→叙事→刷新续接，
再增加自由文本范围。当前 36–68 秒的调用成本也不适合直接承诺交互速度。
没有比较其他模型，不据本次失败推断所有小模型的能力，也未宣布完整 B3/完整模型链通过。

## 复跑与来源绑定

在实现提交上、前端依赖与本地模型/wasm 已就绪时：

```powershell
# B/frontend；输出路径相对仓库根，使用私有目录避免覆盖已归档报告
node scripts/run-b3-short.mjs --out .local/b3-short-replay.json
# 只复跑一条指定样本
node scripts/run-b3-short.mjs --samples updates-position --out .local/b3-position-replay.json
```

归档本身可从仓库根目录只读核对：`node artifacts/b3-short/verify.mjs`。

脚本临时起 Vite，并对自定义 HTML 显式设置 COOP/COEP；加载模型前检查 isolation。
浏览器及 Vite 均在 finally 中关闭，不启动 world-app，也不写真实世界状态。
首次探索发现自定义 HTML 在 Vite header 中间件之前结束，实际仍是单线程，已主动中断。
该次没有已完成样本；原预检报告在成功保存独立副本前被覆盖，已在 review.json 明示来源与限制，
不将其当作六条正式样本或已保存生成证据。

正式短测发生在 `f73ab3f` 的实现变更工作区。8 项实测源文件哈希与当前实现工作副本
逐字节一致，并逐一与 `c25ede4` 的 Git blob 比对（Git 比对时仅统一 LF）。
原报告保留实际 head/status，没有把脏树伪装成干净提交运行，也未为改写身份再次付费重跑。
测试后另行修正的泛用 b3-eval 回调类型不参与本短测 runner 路径；已通过全套回归。

验证：前端 **541/541**、`tsc -p tsconfig.world-contract.json`、`tsc --noEmit`、runner 语法检查。
H2 固定组合及摘要不变，未改其服务端、契约、恢复控制器或共享 pin。
