# 研究与论文工具

这些工具不参与游戏启动、部署或回合结算。章节文字与图示是历史论文草稿，目录迁移不会更新其中的实现描述或实验结论；用于新报告前应对照当前代码和实际测试重新审核。

从仓库根目录运行：

```sh
python -m pip install -r tools/research/requirements.txt
python tools/research/generate_thesis.py
python tools/research/embed_images.py
```

默认输出为 `docs/research/generated/PartialThesis_AI_TRPG_Context_Engineering.docx`，第二步插图会更新这份生成文件。可通过 `JITY_THESIS_OUTPUT` 为两个脚本指定同一个输出路径，路径不再依赖某台 Windows 机器。迁移不改变论文内容或排版。

配图源文件与现有 PNG 位于 `diagrams/`。生成论文及插入已有 PNG 不需要网络。若要重新渲染配图，可运行 `python tools/research/render_diagrams.py`（调用 mermaid.ink）；旧的 `render_mermaid.js` 使用 Puppeteer 和 Windows Edge，并从 CDN 加载 Mermaid，需先安装此目录的 Node 依赖并按本机环境修改浏览器路径：

```sh
npm ci --prefix tools/research
node tools/research/render_mermaid.js
```

配图工具的 Node 依赖已从仓库根目录迁到这里，前端依赖仍独立位于 `frontend/`。历史实验报告见 [研究材料索引](../../docs/research/README.md)。
