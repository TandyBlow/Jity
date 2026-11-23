# Design: goal-narr-dpo

## DPO

- 数据：84 条 sft 提示；chosen=手写目标；rejected=v3 采样（temp 0.45，84/84 非空）。
- 训练：policy=base+v3 LoRA，reference=同一权重禁用适配器（peft `disable_adapter`）；beta 0.1、lr 5e-6、2 epochs；logits 只取目标位（`logits_to_keep=T+1` 再去掉末位）。
- 踩坑：1D `input_ids` 会让 Qwen3 的 rotary 形状错位（16 vs 128），必须 `[1, seq]`。

## 归因变体工作流

- 7 条基础提示，每条生成 swap/unsettled 两类变体；每个变体由独立 agent 对抗校验。
- 结果：接受 9 条。复核发现 2 条不可用（给路明非加识别带、把芬格尔的相机写成诺诺的）。
- 教训：对抗校验没有世界登记表（谁拥有什么），拦不住物品归属错误；数据扩充要以世界文件为硬校验。

## 结果

- run97：10/10 ≤60 s；正文滑向否定复读，t2 主角持枪、t9 诺诺引语与「巷里没有诺诺」矛盾、t7/t10 凭空细节、t8 位置矛盾；检查器 5 命中。
- v4 不采用；评估臂恢复 v3。
