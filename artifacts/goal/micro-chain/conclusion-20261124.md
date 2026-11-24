# micro-chain 结论（2026-11-24）

## 结构

- 12 个回合（8 act / 4 skip）：intent（t2 int8）→ skip 短路；act → targets 句对打分 → position 句对打分 → judgment（t2 int8，目标来自 targets 输出）。
- 输入按训练格式构造：targets 对 = `行动：…\n在场：…`；position 对 = `事实：…\n当前：…`；judgment = `行动：…\n目标：…\n骰点：…`。
- 浏览器内串行调用，逐调用计时；两线程档各跑一次。

## 结果（12 回合，int8，WASM）

| 指标 | 4 线程 | 1 线程 |
|---|---|---|
| 端到端 | 7/12 | 7/12 |
| act 回合端到端 | 4/8 | 4/8 |
| skip 回合 | 3/4 | 3/4 |
| intent | 10/12 | 10/12 |
| targets | 5/8 | 5/8 |
| position | 8/8 | 8/8 |
| judgment | 7/8 | 7/8 |
| 调用数 | 46 | 46 |
| 总耗时（12 回合） | 170.1 ms | 279.0 ms |
| 每回合 p50 | 17.2 ms | 31.1 ms |

- 计时更正：上一版 `totalMs` 漏计 skip 分支（提前 `continue`）；170.1/279.0 是全部 12 回合，上一版 173.4/292.8 只含 act 回合。
- targets 基线：逐字匹配在 12 回合上是 8/8，模型 5/8——4 个空标签回合被模型误报。
- position 8/8 的前提是输入为人工写好的结算事实；按行动文本喂 position 对会掉到 3/8。位置不依赖前面模型的输出。
- judgment 的骰点文本已含结果词（接过/被卡住/没有回应）；targets 错时 judgment 3/3 正确，不能证明没有错误传播。
- NPC 意图与后续的玩家行动属不同角色，短路只是演示，不是产品形态。

## 判定

- 协同链能跑：46 次调用、170 ms（4 线程），每回合 p50 17.2 ms。
- 真正的依赖只有 targets → judgment，且骰点文本泄露结果；position 是独立分支，输入是人工事实。
- 端到端 7/12 主要受 targets 误报与 intent 误判限制；targets 基线更强，说明这一级应先用程序匹配，再在非词面匹配的例子上用模型。
- 下一步：结构化事实生成（动作/施事/受事/位置/否定/先后），用真实中间结果替换人工事实，再重测链。

## 复现

```bash
python artifacts/goal/micro-chain/build_chain.py
bash artifacts/goal/micro-chain/run_chain.sh
```
