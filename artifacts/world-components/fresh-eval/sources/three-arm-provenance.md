# 旧题变化事实的来源核对（自动生成，勿手改）

检查了 28 个已存点，覆盖：`design/world-protocol/v2/traces`, `artifacts/rule-facts`, `artifacts/world-page`, `artifacts/narration-eval`。

结论：authoritative-read **0** 条，undetermined **10** 条。

| 旧题 | 变化签名 | anchor | 夹具里不存在的 ID | 形状相同的已存点 | 依据 |
|---|---|---|---|---|---|
| `nv-move-1` | `moved*1|1|120s` | 占位（全 f） | hall | 0 处 | undetermined |
| `nv-task-pers-sanity-1` | `personality_changed*1+sanity_changed*1+task_achieved*1|1|60s` | 占位（全 f） | task_intro | 2 处 | undetermined |
| `nv-multi-1` | `moved*1|1|60s` | 占位（全 f） | hall | 0 处 | undetermined |
| `nv-task-only-1` | `task_achieved*1|1|30s` | 占位（全 f） | task_shelf | 0 处 | undetermined |
| `nv-refused-1` | `none|0|1s` | 占位（全 f） | 无 | 6 处 | undetermined |
| `nv-empty-1` | `none|0|300s` | 占位（全 f） | 无 | 0 处 | undetermined |
| `nv-cont-1` | `moved*1|1|2s` | 占位（全 f） | hall | 3 处 | undetermined |
| `nv-cont-2` | `none|0|120s` | 占位（全 f） | hall | 0 处 | undetermined |
| `nv-cont-3` | `none|0|300s` | 占位（全 f） | hall | 0 处 | undetermined |
| `nv-multi-opposite-1` | `moved*2|2|3s` | 占位（全 f） | hall | 0 处 | undetermined |

## 逐条理由

- `nv-move-1`（anchor 调用 `p_nv_move_1`）：sample 的 stateDigest 是占位值（全 f），不指向任何已提交读取；引用的 ID 在夹具里不存在：hall；登记的轨迹与归档里没有形状相同的已提交点
- `nv-task-pers-sanity-1`（anchor 调用 `p_nv_tps_1`）：sample 的 stateDigest 是占位值（全 f），不指向任何已提交读取；引用的 ID 在夹具里不存在：task_intro；形状相同 2 处，但无法按点位身份绑定
- `nv-multi-1`（anchor 调用 `p_nv_multi_1`）：sample 的 stateDigest 是占位值（全 f），不指向任何已提交读取；引用的 ID 在夹具里不存在：hall；登记的轨迹与归档里没有形状相同的已提交点
- `nv-task-only-1`（anchor 调用 `p_nv_task_1`）：sample 的 stateDigest 是占位值（全 f），不指向任何已提交读取；引用的 ID 在夹具里不存在：task_shelf；登记的轨迹与归档里没有形状相同的已提交点
- `nv-refused-1`（anchor 调用 `p_nv_refused_1`）：sample 的 stateDigest 是占位值（全 f），不指向任何已提交读取；形状相同 6 处，但无法按点位身份绑定
- `nv-empty-1`（anchor 调用 `p_nv_empty_1`）：sample 的 stateDigest 是占位值（全 f），不指向任何已提交读取；登记的轨迹与归档里没有形状相同的已提交点
- `nv-cont-1`（anchor 调用 `p_nv_cont_1`）：sample 的 stateDigest 是占位值（全 f），不指向任何已提交读取；引用的 ID 在夹具里不存在：hall；形状相同 3 处，但无法按点位身份绑定
- `nv-cont-2`（anchor 调用 `p_nv_cont_2`）：sample 的 stateDigest 是占位值（全 f），不指向任何已提交读取；引用的 ID 在夹具里不存在：hall；登记的轨迹与归档里没有形状相同的已提交点
- `nv-cont-3`（anchor 调用 `p_nv_cont_3`）：sample 的 stateDigest 是占位值（全 f），不指向任何已提交读取；引用的 ID 在夹具里不存在：hall；登记的轨迹与归档里没有形状相同的已提交点
- `nv-multi-opposite-1`（anchor 调用 `p_nv_opposite_1`）：sample 的 stateDigest 是占位值（全 f），不指向任何已提交读取；引用的 ID 在夹具里不存在：hall；登记的轨迹与归档里没有形状相同的已提交点

## 对签名比较的影响

- 变化签名仍然是可比较的**形状**，但 `undetermined` 的旧题只能说明“按当前转换口径同形”，不能据此断定某个新点是旧题的派生。
- 相应地，`c8d06` 第 2 点与 `nv-cont-2` 的关系写作“口径同形”，不写作“派生”。

## 边界

- 形状相同不等于同一事实：即使签名相同，也仍可能不是旧题当年的那个点。
- 本脚本只读登记的轨迹与归档；未登记的运行产物不在检查范围内。
