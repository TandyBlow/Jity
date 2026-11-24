# micro-chain 结论（2026-11-24）

## 结构

- 12 个回合（8 act / 4 skip）：intent（t2 int8）→ skip 短路；act → targets 句对打分 → position（规则结算：动作 + 骰点 → 目的地）→ judgment（t2 int8，目标来自 targets 输出）。
- position 不再读手写事实：`rules.settle` 从动作与骰点推出目的地（含「拦在门口」类阻断）；turns 3/6 的动作加上移动短语，目的地由动作给出。
- 浏览器内串行调用，逐调用计时。

## 结果（12 回合，int8，WASM）

| 指标 | 4 线程 | 1 线程 |
|---|---|---|
| 端到端 | 6/12 | 6/12 |
| act 回合端到端 | 2/8 | 2/8 |
| skip 回合 | 3/4 | 3/4 |
| intent | 10/12 | 10/12 |
| targets | 4/8 | 4/8 |
| position（规则） | 8/8 | 8/8 |
| judgment | 7/8 | 7/8 |
| 调用数 | 30 | 30 |
| 总耗时（12 回合） | 113.1 ms | 174.1 ms |

- position 改成规则结算后调用数从 46 降到 30，position 仍 8/8。
- targets 4/8：1 次漏报（turn 3，动作加入移动短语后）、3 次误报（turn 4/8/11，在场但未被点名的角色）。
- 错误传播仍不可判：骰点文本含结果词；targets 错时 judgment 4/4 正确。
- skip 短路正常：4 个 skip 回合各 1 次调用。

## 判定

- 链现在读生成的事实（规则结算），不再读手写目的地；端到端 6/12 受 targets 误报限制。
- 规则在事实测试集上 24/24，而模型组合 16/24（targets）与 15/24（destination）——当前应先用规则，模型只在规则失败的非词面构造上试用。
- 限制：12 回合手写、单种子；targets 模型仍是主要瓶颈；judgment 的骰点文本泄露结果。

## 复现

```bash
python artifacts/goal/micro-chain/build_chain.py
bash artifacts/goal/micro-chain/run_chain.sh
python artifacts/goal/micro-facts/eval_facts.py
```
