# 全分支与工作树来源审计

生成时间：2026-11-08T07:55:50.532978+00:00；工作树 HEAD `b9d62354e652`。

## 范围与方法

- 分支与远端引用：63 条，去重后 24 个尖端。
- 工作树：67 个（每个工作树只读未提交文件，已提交内容由尖端覆盖）。
- 已提交 blob：3350 个，按内容去重后 3545 份。
- 扫到的世界出现：1572 次，按身份集合合并后 11 个世界。
- 未读文件：0 个（见 audit.json 的 unread）。

分类规则：按世界的名字被哪些角色的文件提到——训练/调参语料、调参运行、评测样本、真机归档、旧产品内容、判分器、运行时代码、夹具/测试、协议夹具、设计文档、仅定义。**没有一条统一标 undetermined**；每个世界都有具体理由。

## 世界分类

| 世界摘要 | 人物/地点 | 出现 | 分类 | 理由 | 独立? |
|---|---|---|---|---|---|
| `98eb58137676`  | 2/2 | 816 | used-in-tuning-run | 被 53 个 tuning-run 文件提到 | 否 |
| `e1436447e113` world_school | 6/7 | 627 | used-in-tuning-run | 被 47 个 tuning-run 文件提到 | 否 |
| `51c3f9bbe023` w_pipe | 2/2 | 68 | undetermined-name-overlap | 只有 0 个专有名字，其余名字在多个世界间共用，无法用名字判定它是否被使用；记为无法判断，不作为独立来源 | 否 |
| `2229a03227db` world_school | 3/2 | 22 | used-in-tuning-run | 被 1 个 tuning-run 文件提到 | 否 |
| `4554f07a9ac2` w_snow_pass | 4/4 | 13 | design-doc-only | 被 2 个 design-doc 文件提到 | 否 |
| `397fc04d0c6d` w_fog_harbor | 5/6 | 13 | used-in-tuning-run | 被 52 个 tuning-run 文件提到 | 否 |
| `55f0b7e57189` w_pipe | 3/2 | 4 | undetermined-name-overlap | 只有 0 个专有名字，其余名字在多个世界间共用，无法用名字判定它是否被使用；记为无法判断，不作为独立来源 | 否 |
| `b818633bf778` world_fixture | 1/1 | 3 | definition-only | 只有定义该世界的文件提到它的专有名字 | 否 |
| `986eccf58cd3`  | 2/2 | 2 | undetermined-name-overlap | 只有 0 个专有名字，其余名字在多个世界间共用，无法用名字判定它是否被使用；记为无法判断，不作为独立来源 | 否 |
| `0c05f69f9020`  | 7/7 | 2 | design-doc-only | 被 1 个 design-doc 文件提到 | 否 |
| `4b308be4922d`  | 4/4 | 2 | undetermined-name-overlap | 只有 1 个专有名字，其余名字在多个世界间共用，无法用名字判定它是否被使用；记为无法判断，不作为独立来源 | 否 |

## 入选与排除理由

| 世界 | 分类 | 是否可用作独立来源 | 具体理由 |
|---|---|---|---|
| `98eb58137676` | used-in-tuning-run | 否 | 被 53 个 tuning-run 文件提到；已有曝光记录，不能作独立来源 |
| `e1436447e113` | used-in-tuning-run | 否 | 被 47 个 tuning-run 文件提到；已有曝光记录，不能作独立来源 |
| `51c3f9bbe023` | undetermined-name-overlap | 否 | 名字在多个世界间共用，无法用证据判断用途；按无法判断处理，不作独立来源 |
| `2229a03227db` | used-in-tuning-run | 否 | 被 1 个 tuning-run 文件提到；已有曝光记录，不能作独立来源 |
| `4554f07a9ac2` | design-doc-only | 否 | 被 2 个 design-doc 文件提到；已有曝光记录，不能作独立来源 |
| `397fc04d0c6d` | used-in-tuning-run | 否 | 被 52 个 tuning-run 文件提到；已有曝光记录，不能作独立来源 |
| `55f0b7e57189` | undetermined-name-overlap | 否 | 名字在多个世界间共用，无法用证据判断用途；按无法判断处理，不作独立来源 |
| `b818633bf778` | definition-only | 否 | 仅定义级，但只有 2 个专有名字、1 人物/1 地点，不满足多人物/多地点覆盖，且用于单元测试夹具 |
| `986eccf58cd3` | undetermined-name-overlap | 否 | 名字在多个世界间共用，无法用证据判断用途；按无法判断处理，不作独立来源 |
| `0c05f69f9020` | design-doc-only | 否 | 被 1 个 design-doc 文件提到；已有曝光记录，不能作独立来源 |
| `4b308be4922d` | undetermined-name-overlap | 否 | 名字在多个世界间共用，无法用证据判断用途；按无法判断处理，不作独立来源 |

结论：可用作独立来源的世界 **0** 个。因此本次改为新建评测专用注册夹具（见 `../fresh/`），不把任何旧世界改名冒充新来源。

## 各类数量

- used-in-tuning-run：4
- undetermined-name-overlap：4
- design-doc-only：2
- definition-only：1

## 边界

- 名字匹配只能证明“该文件提到过这个名字”，不等于证明该世界被用于训练或调参。
- 已删除的历史文件、仓库外的使用记录不在本次扫描范围。
- 工作树只读未提交文件；已提交内容由分支尖端覆盖。
