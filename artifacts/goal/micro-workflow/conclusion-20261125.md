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

## 重训结果（四轮数据）

- results 5 类（跨回合留出）：four 35/51（69%）、one 20/28（71%）、three 48/72（67%）、two 17/22（77%）；混淆集中在 achieved↔partial、not_achieved→no_change。输入中位 64 token（max 141），int8 10,552,059 B。
- movement 二分类：four 留出 tp4/fp0/fn1/tn17（95%），其余三折全对；合计 16 正例中 15 命中、58 负例全对；输入中位 54 token（max 84），int8 10,549,906 B。
- act 头在 124 条全 `act` 数据上仍是平凡 100%，不作为能力。
- 浏览器探针（ORT-WASM 1 线程，int8，新权重）：加载 999 ms；results 7/8（p50 10.4 ms）、movement 6/6（p50 14.7 ms）、act 4/4（p50 15.4 ms）。

## 外貌机会扫描

- 55 次带外貌段的 updates 提示共列出 1,382 个实体行，接受答案里 0 个 add/remove/replace。
- 用「事实点名实体核心名 + 变化动词」保守扫描，候选仅 16 行（来自 8 个提示实例），集中在「把护目镜擦干净」（goggles_lu / lu）与「拆下红色识别带」（shen / shen_band），且是否算外貌变化本身可争议。
- 结论：外貌阶段在当前语料里是纯开销；即使做「是否变化」二分类也没有足够正例，暂不训练第四个头，外貌继续由 LLM 回答（合并位置回答的半边已复用，见上）。

## 受控 A/B 状态

- `?seed=11` 的基线臂与 `micro=1&seed=11` 微型臂已启动，但 Claude Code 因系统内存过低杀掉了产品服务器与整个 A/B 后台进程（非实验失败）；`evidence-seed-llm.json` 只有启动记录，没有回合。
- 重新运行需要用户确认后再起服务器与两臂；命令与对比脚本已就绪（`ab_compare.py`，证据含 `after.place/nearby/tasks` 与 `source` 计数）。
- 因此本轮不宣称「LLM 调用减少量 / 完整回合耗时 / 状态正确率」的受控数值；分阶段复用外貌半边的省调用是代码与单元测试证据，未计入受控 A/B。
