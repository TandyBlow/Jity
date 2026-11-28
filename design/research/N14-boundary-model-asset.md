# N14 句界模型资产：31KB、1,974 个非零权重，独立复算 267/267 一致

**Question.** N10 的句界模型能不能脱离 sklearn 打包成一个可部署资产，并且用独立实现
复算出完全相同的判定？

**Setup.** `export_boundary_model.py`：在全量 267 个片段对上拟合逻辑回归，把 4,096 维
哈希权重与截距导出为 JSON；再用一个只依赖该 JSON 与 `murmurhash3_32` 的独立打分器
（与 sklearn FeatureHasher 的桶规则一致）逐条对比。

**Results.**
- 资产 **31,274 字节**：4,096 维权重（**1,974 个非零**）+ 截距 + 特征说明。
- 独立复算与 sklearn 判定 **267/267 一致**（0 分歧）。
- 哈希规则：`abs(murmurhash3_32(feature)) % 4096`，同一特征重复出现时累加；这对 TS 移植
  是明确可实现的两行代码。

**Interpretation.**
- 句界模型已经是一个“可交付的模型资产”：31KB、约 2 千个有效参数、无依赖复算一致。
  参数量低于目标里的 0.1M–10M 区间，但这是线性头，不是神经网络；目标允许“不默认每项
  任务都需要神经网络”。
- 移植到浏览器只差三件事：murmurhash3_32 的 TS 实现、同一套特征函数、以及把权重表
  打进包里。没有 ONNX 会话、没有 WASM 运行时，加载成本可以忽略。
- 它仍只解决句界；主语/连接/指代头需要同样的导出流程，或在有足够标注后合并成一个小
  编码器。

**Caveats.** 267/267 是训练集上的复算一致性，不是泛化；模型只在 63 种上下文上训练；
资产未做量化（权重是 float32 精度的十进制文本）。

**Artifacts.** `artifacts/goal/narration-standalone/{export_boundary_model.py,
renderer-boundary-model.json}`。N14。
