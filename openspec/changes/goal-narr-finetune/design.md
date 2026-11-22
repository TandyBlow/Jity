# Design: goal-narr-finetune

## 数据

- 来源：`.local/narr-train/prompts.jsonl`（111 条真实叙事提示，来自 run1–run80 的 `product.narration.prompt`），去重后 84 条唯一提示，id 1–84。
- 教师目标：`.local/narr-train/teacher-a.txt` / `teacher-b.txt`，按提示自身规则手写：只写已结算的动作、位置、外观和结果；不复述清单；不新增人物、物品、事件、数字、伤情、往事或心理活动；无引语不写对白；2–3 段短句。视角只写主角可见范围，其他区域的 NPC 结算不写入正文。
- 排除：id 6 与 38（结算把未知实体阿豹的交接写成完成，与场景矛盾）；id 72（结算文本损坏）。改以 3 条合成合法失败样本（S1–S3）：保留 run82 s06 的真实提示，把结算结果替换为「阿豹不在场，未能转交」。
- 过滤：把数据构造成 `check-prose-facts.mjs` 的 turn 形状跑门；当前 84 回合 0 命中（`input_echo`/`unknown_entity_claim`/`band_claim`/`invented_detail` 等全 0）。

## 编码等价

浏览器路径（builtin 候选，instruct 模式）：

1. `game-model.ts` 把 brief prompt 包成 `<|im_start|>user\n{prompt}<|im_end|>\n<|im_start|>assistant\n`；
2. `WllamaInferenceEngine.complete` 把它作为单条 user 消息交给 `createChatCompletion`；
3. wllama 用 GGUF 自带 Qwen3 模板渲染，传 `chat_template_kwargs: {enable_thinking: false}`。

训练用同一顺序：`apply_chat_template([{role:'user', content: chatml(prompt)}], add_generation_prompt=True, enable_thinking=False)`，只对教师目标计算 loss。渲染后确认模板尾部是空的 `<think></think>` 块（与浏览器一致），提示平均约 500 token。

## 结算门收紧

`assertKnownEntities` 原先只拒绝 `outcome === 'completed'` 的事实；run82 的答案省略了 outcome，交接被放行。改为：显式 `blocked` 放行；其余点名未登记实体的事实，只有正文含「不在场/没有/未能/没能/未被/没在/不在/无法/拒绝」时才放行。测试：`settlement.test.ts` 新增「缺省 outcome 被拒 / 显式 blocked 放行」两条断言。

## 训练

- 基座：`Qwen/Qwen3-1.7B`（HF safetensors，本地 `.local/qwen3-1.7b-hf`）。
- LoRA：r=16、alpha=32、dropout=0.05，全部线性层；bf16，gradient checkpointing，batch 1 × accum 8，lr 1e-4 OneCycle，5 epochs，max_len 1280。
- 机器：RTX 4060 Laptop 8 GB；不量化基座（1.7B bf16 ≈ 3.4 GB），LoRA 优化器只覆盖可训练参数。
- 产物：`.local/narr-train/lora-qwen3-1.7b/`（adapter）→ `merged-qwen3-1.7b/`（bf16）→ GGUF f16 → Q4_K_M。

## 转换与评估臂

- `convert_hf_to_gguf.py`（本地 llama.cpp 转换器，支持 `Qwen3ForCausalLM`）→ `llama-quantize.exe` Q4_K_M。
- 复用现有评估臂键 `qwen3-1.7b-narr-lora`，替换权重文件并更新 `page.tsx` 的 bytes/sha256；默认 `qwen3-1.7b` 不变。
- 评估顺序：transformers 留出提示生成 → 产品 s05/s06（`turns-semantics-s05-s06.json`，`schedHandback=player&offscreenPolicy=skip&narrationModel=qwen3-1.7b-narr-lora`）→ 检查器 + 人工读评 + 计时。
- 页面服务重启后再跑（`next start` 在启动时索引 `public/`）。

## 风险

- 84 条样本量小，可能过拟合到场景表层；留出提示与产品回合都不在训练文件里逐字重复，但场景类型重叠。证据里要如实写「训练集与评估集同世界、同投影」，不宣称跨世界泛化。
- 1.7B 能力上限可能仍然写不好长事实块；若微调后仍有硬错，按 D-022 记录失败，不改门槛。
- 不改变运行期契约：D-004 原样输出、D-007 默认模型、D-017/D-018 调度都不动。

## 验收

- 数据门：84/84 回合 0 命中。
- 训练：loss 下降、可复现（固定 seed）。
- 产品：s05/s06 驱动 0 问题、检查器 0 命中、人工读评无 4.2 硬错；记录计时。
- 未通过则如实登记，不进入默认。
