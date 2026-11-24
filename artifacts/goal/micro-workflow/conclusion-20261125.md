# micro-workflow 第二轮（2026-11-25）

## 定向补采与标签审计

- 五轮采集（one/two/three/ab/four）共 559 条语义记录：targets 68、results 147、updates 136、action 180、reaction 14、continuation 14。
- 定向两轮（「蹲墙角擦护目镜不出声」/「脱下外套检查血迹」）均 COMPLETED，首读 19.4 s / 29.7 s；`after` 无结算错误。
- **skip 标签 0 条**：五个文件全部 action 原始输出里 `kind` 只有 `act`（本轮 33/33、31/31），没有一次模型 `skip`。现有 skip 全部来自程序规则（`offscreenPolicy` 的零调用分支，`actions/index.ts` 223/240/255），本来就是零成本。
- **外貌变化 0 条**：55 次带 `appearances` 的 updates 回答全部为空数组；92 条实体行全负例。第二轮输入里「脱下外套」指向的 `外套` 不是世界登记物品（登记的是「演习背心」），但「擦护目镜」指向的 `goggles_lu` 也没有触发操作。
- 结论：act/skip 头与外貌文本头在当前数据上没有可训练的正例；这不是采样不足，而是 0.6B 在现有提示下的决策分布退化为单一类。四类头里可训练的是 results 与 movement（外加共享编码器），外貌只剩「是否变化」这个二分类，但没有正例同样无法训练。
- 人工抽查（`human-review.json`）：movement 6 条中 5 条可从事实文本直接确认、1 条可信；results 5 条中 3 条可信、2 条存疑（`admitted=false` 却标 partial；「拦下长椅」标 partial）。results 标签来自模型自己的 fact，无法用独立状态差复核，只能判「可信/存疑」。

## 已接入

- `microUpdates`：位置阶段先问移动头（74 条样本，16 正/58 负），只接受「实体自己的事实点名了登记地点」的移动；缺目的地、条目被校验拒绝、事实点名移动未覆盖时回退 LLM，原因写入 `stageDetail.microAbstain`。
- 分阶段调用的外貌半边改为跨调用复用（BatchMemory）：此前每点固定两次外貌提问（合并位置回答一次 + 外貌阶段一次，录音 6/7/23 点全部成对），现在外貌阶段直接复用合并回答，每点少一次约 7.8k 字调用。
- `?seed=N` 注入确定性 d20，用于受控 A/B；`semanticCalls.source` 记录 model/micro/program。
- 测试：settlement 111 通过、全量 1300 通过、tsc 干净。

## 待补

- 受控 A/B 数值与状态对比（固定 seed，两臂各一轮）。
- 移动头在真实回合里的命中/回退比例（本轮 only 单元测试与探针）。
