# 开发日志

`entries.json` 是开发日志的唯一内容源，按原有展示顺序保存完整条目。前端 `/dev-log` 继续提供搜索和范围筛选，`frontend/src/lib/dev-log/index.ts` 只导入数据，页面不再维护另一份历史记录。

新增日志时更新此 JSON 数组，字段遵循 `frontend/src/lib/dev-log/types.ts`。历史条目中的路径、测试数量和实验结论记录的是当时状态；迁移后的目录对应关系见 [研究材料索引](../research/README.md)，不要把旧实验结果当作当前版本的验证结果。
