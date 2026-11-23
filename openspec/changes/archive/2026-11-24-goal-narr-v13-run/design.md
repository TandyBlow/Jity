# Design: goal-narr-v13-run

## 结果

- v13 修掉 v12 的缺席过拟合；五回合 5/5、≤60 s、检查器 0。
- 20 输入部分：s06 强门（事实点名阿豹、无 blocked 判词）重试三次后中止；s07 自动链 330 s；chunk4/5 未跑（内存回收）。

## 门修正

- 强门在最后一次修复仍不合法时丢弃事实并记 `unknown_entity_named`，与弱证据的 `unknown_entity_no_name` 一致；不再中止整点。
- 单测 1259 passed。

## 判定

- v13 保留为评估臂；真机复跑待内存窗口。D-026 不变。
