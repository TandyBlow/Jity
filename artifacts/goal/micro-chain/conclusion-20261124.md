# micro-chain 结论（2026-11-24）

## 结构

- 12 个回合（8 act / 4 skip）：intent（t2 int8）→ skip 短路；act → targets 句对打分 → position 句对打分 → judgment（t2 int8，目标来自 targets 输出）。
- 输入按训练格式构造：targets 对 = `行动：…\n在场：…`；position 对 = `事实：…\n当前：…`；judgment = `行动：…\n目标：…\n骰点：…`。
- 浏览器内串行调用，逐调用计时；两线程档各跑一次。

## 结果（12 回合，int8，WASM）

| 指标 | 4 线程 | 1 线程 |
|---|---|---|
| 端到端 | 7/12 | 7/12 |
| intent | 10/12 | 10/12 |
| targets | 5/8 | 5/8 |
| position | 8/8 | 8/8 |
| judgment | 7/8 | 7/8 |
| 调用数 | 46 | 46 |
| 总耗时 | 173.4 ms | 292.8 ms |
| 每回合 p50 | 18.5 ms | — |

- 错误传播：targets 错时 judgment 3/3 正确；targets 对时 judgment 4/5。8 个 act 回合，看不到传播信号。
- 失败模式：intent 2（act→skip、skip→act）；targets 3（在场但未被点名的角色被误报）；judgment 1（骰点「没有回应」判成 achieved）。
- position 8/8：事实驱动的移动/停留都判对；按动作文本喂 position 会掉到 3/8，输入构造必须是事实而不是行动。
- 短路正常：4 个 skip 回合各只 1 次调用。

## 判定

- 协同链在浏览器里成立：46 次调用、173 ms（4t）；端到端 7/12，受 intent 与 targets 误报限制。
- 未观察到错误传播（样本 8 个 act 回合）；targets 误报是当前端到端的主要杀手。
- 限制：12 回合手写、单种子、单机；judgment 的骰点文本只有 8 个 act 回合。

## 复现

```bash
python artifacts/goal/micro-chain/build_chain.py
bash artifacts/goal/micro-chain/run_chain.sh
```
