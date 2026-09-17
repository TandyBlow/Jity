# 本地 Examiner

战役回合现在按「Python Examiner → LLM Director → LLM Narrator」执行。Examiner 不持有 LLM 客户端，不调用 API。判定 blocked 时返回叙事内拒绝，不调用 Director 或 Narrator；自由模式仍使用原来的单次叙事生成路径。

规则位于 `backend/app/services/agents/examiner.py`，输入现有游戏状态，不改变状态，也不扣除资源。

| 检查 | 当前规则 |
| --- | --- |
| 物品 | 明确的“使用／用／拿出”等动作按名称精确检查 items，状态须为 owned、active、equipped 或相应中文状态；寻找物品不要求持有它。 |
| NPC | 明确的对话对象必须存在；已知 NPC 的攻击、询问等动作检查其状态及 current_location。following 状态视为同行，不受旧地点影响。代词等不明确目标交给叙事处理。 |
| 地点 | “在某地调查／搜索／休息”等明确原地动作与 current_location 比较；“前往某地”不要求玩家已经在那里。 |
| 资源 | 体力动作／战斗要求 health > 0；主动 SAN 风险动作或言灵要求 sanity > 0。当前没有动作消耗表，不臆造额外消耗和阈值。 |
| 检定 | 明确的恐怖遭遇、言灵或 SAN 检定触发 sanity_check；侦查、潜行、开锁等触发 skill_check；攻击、射击等触发 combat。物品使用单独标记 item_use。 |

`permissible` 表示未发现本地前置条件冲突，`conditional` 表示需要处理检定，`blocked` 表示明确的前置条件不满足。当前只识别规则触发，不掷骰、不计算命中或伤害；检定约束会传给 Director 和 Narrator。“继续”等纯续写直接允许。

自由文本识别采用有限的中文动作模板，不是通用语义解析器。不明确的表达不会被自动转换为新规则；长句、省略和别名仍有识别边界，后续可在此文件扩展模板。规则文本参数仅兼容旧调用，不再交给模型解释，也不因文本提到了 SAN 就触发检定。

独立的每 5 回合世界事实提取 API、提示词及 CampaignManager.extract_facts 已删除。世界事实仍由同次 Narrator 的 `memory_updates.world_facts_upserted` 和已有本地推断合并进状态；NPC 好感处理保持原有流程。

验证：在 `backend/` 中运行 `python -m pytest -q`。`tests/test_local_examiner.py` 覆盖规则判断、资源边界、调用链不请求 Examiner API，以及第 5／10／15 回合不再独立提取事实。
