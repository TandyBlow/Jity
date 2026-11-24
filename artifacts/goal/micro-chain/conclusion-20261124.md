# micro-chain 结论（2026-11-24）

## 结构

- 12 个回合（8 act / 4 skip）：intent（t2 int8）→ skip 短路；act → targets 句对打分 → position（浏览器内 JS 规则结算：动作 + 骰点）→ judgment（t2 int8，目标来自 targets 输出）。
- position 结算在浏览器运行时执行（`rules.settle` 的 JS 移植），不再由 Python 预计算；turns 3/6 的动作带移动短语。
- 浏览器内串行调用，逐调用计时。

## 结果（12 回合，int8，WASM）

| 指标 | 4 线程 | 1 线程 |
|---|---|---|
| 端到端 | 6/12 | 6/12 |
| act 回合端到端 | 3/8 | 3/8 |
| skip 回合 | 3/4 | 3/4 |
| intent | 10/12 | 10/12 |
| targets | 4/8 | 4/8 |
| position（JS 规则） | 8/8 | 8/8 |
| judgment | 7/8 | 7/8 |
| 调用数 | 30 | 30 |
| 总耗时（12 回合） | 107.8 ms | 178.5 ms |
| 每回合 p50 | 10.3 ms | 16.7 ms |
| 结算耗时 | ≤0.155 ms | ≤0.135 ms |

- 上一版把 act 写成 2/8，与 6/12 不符；实际 act 3/8（6 个成功回合里 skip 占 3）。
- position 结算已进浏览器计时：单次 ≤0.155 ms，可忽略。
- targets 4/8：1 次漏报（turn 3）、3 次误报（turn 4/8/11，在场但未被点名的角色）。
- 错误传播仍不可判：骰点文本含结果词；targets 错时 judgment 4/4 正确。

## 判定

- 链现在含实时结算，端到端 6/12 仍受 targets 误报限制；调用数 30、总耗时 107.8 ms（4t）。
- 规则在事实测试集上总体领先（27/29），但反例的 targets 子集模型 4/5 > 规则 3/5——互补性出现，样本只有 5 条。
- 限制：12 回合手写、单种子；targets 模型仍是主要瓶颈；judgment 的骰点文本泄露结果。

## 复现

```bash
python artifacts/goal/micro-chain/build_chain.py
bash artifacts/goal/micro-chain/run_chain.sh
python artifacts/goal/micro-facts/eval_facts.py
```
