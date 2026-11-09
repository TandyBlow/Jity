# 冻结副本：104 行原始数据

这份是改写前的原始数据集，逐文件 sha256 见 `manifest.json`。

- 行文件 113 个（`row-scene-only.jsonl` + `row-0002`…`row-0104`）
- 叙事 103 篇（`narratives/row-*.txt`）
- `rows-xy.jsonl`：切分后的 X/y
- 生成脚本与校验脚本一并冻结，保证能重放出同样的数据

后续任何格式改写（例如 YuYan 专用版）都写在新目录，不回改这里。
