# D / L3 实验准备快照

2026-10-31：模型执行继续暂停。第二步已收用户本人 42/42 项开发题初审、全部认可，来源及正式复核仍待完成，见[人审说明](../../design/world-engine-reports/components-logic/human-review.md)和 [L3 进度](../../design/world-engine-reports/components-logic/l3-progress.md)。本目录不是生产服务或新权威协议。

- `lab.py`：纯标准库结构与阶段守卫、严格解码、完整尝试台账。
- `generate_dev_drafts.py`、`data/`：40 个开发来源组/42 项 AI 草稿，输入与人审判据分离，全部待人工/来源复核；没有封存、训练和短链数据。
- `prepare_review.py`：生成人工审阅 HTML，保留说明草稿并提示本地保存失败；实际浏览器显示/下载/恢复尚待验证，导出不自动构成正式签字。
- `review_io.py`：构建审阅批次、要求三份批次文件哈希必填并只读核对导出声明、核查 D 来源身份与 B/C Git 元数据；不改标签，不读取保护题正文，不授予执行/正式评测权限。新增工具独立工程审查无剩余 P2，来源/正式人工复核仍待。
- `fetch_model.py`：只下载已登记 M02 到 D 独立忽略目录，实际文件 SHA-256 验真。
- `requirements-probe.txt` 与平台 `.lock.txt`：隔离实验依赖，后者仅适用于 macOS ARM64/Python 3.11；不修改根依赖。
- `runtime_smoke.py`：失败台账与并发发布工程问题已在进度记录条目 13 闭环；真实模型加载/推理仍未验证，未恢复前不运行推理模式。此前只执行了 `--prepare-only`。

提交前的工程检查为：

```bash
python3 -m unittest discover -s experiments/world-components-logic/tests -p 'test_lab.py'
python3 -m unittest discover -s experiments/world-components-logic/tests -p 'test_review.py'
python3 experiments/world-components-logic/generate_dev_drafts.py --check
python3 experiments/world-components-logic/check_run_manifest.py --self-test
```

已有核心 65 项、新增审阅 13 项，共 78 项工程检查都不证明模型质量或 500 ms。缺来源登记哈希的反例已对旧实现反向验证。审阅逻辑测试需要本机已有 Node.js，仅跑合成内存夹具，不启动浏览器或写人审决定。业务模型输入尚未曝光，本人题目/判据初审意见以独立回执收录，原数据不改；正式来源/模型语义/性能结论仍未评测。
