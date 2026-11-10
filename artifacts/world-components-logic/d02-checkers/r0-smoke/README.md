# R0 工程试跑（engineering smoke only）

日期：2026-11-10。执行者：助手。授权：用户明确选择“授权 R0 工程试跑”。

## 结论

- 只验证数据装载、冻结编码器、M1/M2 新任务头、反向传播、保存与重载。
- **不是质量实验**：没有开发集/封存集评估，没有 A/B/C，没有小模型成绩。
- 编码器（MiniRBT-H256 第 0、1 层，fp32）权重哈希前后一致；新头全部发生参数变化。
- 头文件 `heads.pt` 只留在本地（77KB），不纳入 Git；记录含 SHA。
- M1 只实现 token mention BIO + 5 角色多标签 + 实体分类；M2 只实现 5 类整段分类，**没有实现问题跨度/作用域头**。
- `sealed` 未读取；只用了 `train` 切分的 96 条。

## 配置

| 项目 | 值 |
|---|---|
| 基座 | `/Users/davidz/.cache/jity-d-short-semantics-20261109/encoder/M01/446e1b4012b10946f479563005700c54c9db3f7c` |
| 层 | MiniRBT 第 0、1 层，冻结，fp32，CPU |
| 分词 | 本地 vocab 的 WordPiece＋BertNormalizer/BertPreTokenizer，含字符偏移 |
| 样本 | scale-v2 `train` 96 条 |
| 步数 / batch | 8 / 8 |
| 头 | mention 3 类、role 5 维 BCE、entity 59 类、expression 5 类 |
| 优化器 | AdamW，lr 2e-3，仅新头 |
| 运行 | `python3 experiments/world-components-logic/d02_r0_smoke.py --samples 96 --steps 8 --batch-size 8` |

## 实际记录

- 8 步 loss：8.25 → 7.25 → 6.42 → 5.27 → 4.82 → 4.65 → 4.94 → 5.58。
- 最后一步（工程训练集，不是泛化）：
  - mention token acc 0.606
  - role multi-label acc 0.818
  - entity acc 0.400
  - expression acc 0.500
- 重载后同一 batch：loss 3.333，mention 0.650、role 0.838、entity 0.476、expression 1.000。
- 编码器哈希前后一致：`0d2d067f368ac1db3f0468312947687c38009911bef8ff984c7853d4615d5a9b`。
- 新头全部参数变化；完整记录见 `record.json`。
- 机器时间：主流程约 0.5s；进程墙钟约 1.2s（含本次缓存命中下的导入）；这不是正式训练耗时。

## 限制

1. 这些准确率来自 96 条训练样本的同一批前向，不能当验证或泛化成绩。
2. M1 没有评估跨度边界、问题片段的 scope、歧义/未知状态；M2 没有 issue span/scope 头。
3. 手动 MiniRBT 前向只用于工程链路验证，不是正式 R0 训练实现；正式 R0 仍应使用项目冻结的编码器/训练器。
4. 头文件未入库；本记录不能生成 provider、不能接生产、不能写世界。
5. 没有人类审阅；数据仍是 assistant draft。

## 下一步

- 用正式训练器实现 M1 的 span/role/entity 头和 M2 的 label/issue/scope 头；
- 在 development 上做首次评估，不碰 sealed；
- 再比较 R0/R1/R2；训练前仍需要新的明确授权。
