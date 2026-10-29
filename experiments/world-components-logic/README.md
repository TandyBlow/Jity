# D / L3 实验准备快照

2026-10-29：按用户要求暂停。范围、检查与未完成项见 [L3 进度](../../design/world-engine-reports/components-logic/l3-progress.md)。本目录不是生产服务或新权威协议。

- `lab.py`：纯标准库结构与阶段守卫、严格解码、完整尝试台账。
- `generate_dev_drafts.py`、`data/`：40 个开发来源组/42 项 AI 草稿，输入与人审判据分离，全部待人工/来源复核；没有封存、训练和短链数据。
- `prepare_review.py`：生成人工审阅 HTML；界面及导出尚未 QA，导出不自动构成正式签字。
- `fetch_model.py`：只下载已登记 M02 到 D 独立忽略目录，实际文件 SHA-256 验真。
- `requirements-probe.txt` 与平台 `.lock.txt`：隔离实验依赖，后者仅适用于 macOS ARM64/Python 3.11；不修改根依赖。
- `runtime_smoke.py`：**未完成且未执行推理的草稿**。导入/加载阶段失败未全部落入结果台账，恢复后先修并复核；暂停版本不要运行推理模式。此前只执行了 `--prepare-only`。

提交前的工程检查为：

```bash
python3 -m unittest discover -s experiments/world-components-logic/tests -p 'test_lab.py'
python3 experiments/world-components-logic/generate_dev_drafts.py --check
```

43 项工程测试不证明任何模型或完整非叙事请求达到 500 ms。业务模型输入尚未曝光，用户会先复核题目和判据；正式来源/语义/性能结论仍未评测。
