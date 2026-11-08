"""Thesis section: CHAPTER 3: 系统设计 (System Design). Appends to the shared document on import."""
from thesis.document import (
    add_heading,
    add_page_break,
    add_para,
    doc,
)


add_para(
    'SENNA的六种重定向策略仅在玩家偏离锚点超过3回合且无锚点触发时激活：'
    'more_information（提供额外线索或信息）、world_consequences（世界对玩家不作为做出反应）、'
    'npc_influence（NPC主动引导玩家方向）、environmental_cue（环境信号，如远处的钟声）、'
    'dramatic_timing（等待更合适的叙事时机）、hard_denial（显式阻止，仅作为最后手段使用）。'
)

add_para(
    '第三阶段——Narrator（传统LLM生成增强版）：负责生成最终叙事文本和结构化状态变更JSON。'
    '使用deepseek-v4-pro模型，temperature=0.35。'
    '其系统提示在原有基础上通过_inject_direction()函数注入了Director的叙事方向指令，'
    '使Narrator在保有叙事自由度的同时遵循高层叙事规划。'
    '输出包含narration（叙事文本）、npc_dialogue（NPC对话）、'
    'state_changes（状态变更JSON，含items_upserted/npcs_upserted/quests_updated/current_location等字段）、'
    'player_options（2–4个行动选项）和scene_description（场景图像生成提示）。'
)

# 3.4
add_heading('3.4  战役叙事引擎', level=2)

add_para(
    '战役叙事引擎采用层次化有限状态机（FSM）驱动，使用transitions库0.9.x实现。'
    '战役结构为有向无环图（DAG）：Campaign → Arc（弧线） → Session（会话） → Anchor Events（锚点事件）。'
    'FSM状态流转如图3.4所示。'
)

add_para(
    'FSM状态流转路径为：idle → active/session_active → active/session_recap → '
    'active/arc_transition → active/arc_intro → campaign_end。'
    '采用自定义"/"分隔符以避免与状态名中的下划线产生歧义。'
)

add_para(
    '每个锚点事件具有以下属性：trigger_conditions（触发条件，包括location/npc_present/item_held的硬性条件）、'
    'priority（优先级，1–5）、cooldown_turns（冷却轮数，≥3轮）、revealed标志。'
    'CampaignAnchorEvaluator每轮执行锚点评选：过滤未揭示的 → 检查硬性条件 → 检查冷却 → 按优先级排序 → 返回最高优先级候选。'
    '当玩家偏离锚点超过3回合且无锚点触发时，系统检测到偏离（deviation_detected），'
    '触发Director的六种重定向策略。同时，系统支持自适应锚点生成：基于当前位置动态生成临时锚点（上限3个），'
    '确保即使玩家探索未预期区域也能维持叙事结构。'
)

add_para(
    '战役上下文（CampaignContext）通过CampaignContextBuilder在每轮的系统提示前注入，包含：'
    '当前弧线和会话信息、最近的锚点完成记录、当前偏离状态、叙事健康指标（节奏分数、张力轨迹、对话密度、叙事吞吐量）。'
    '每5轮触发一次Fact Extraction：调用LLM从叙事文本和最近事件中提取新的世界观事实，'
    '保持L2世界记忆的动态更新。NPC关系追踪采用好感度系统（affinity），每次交互±1（上限±10），'
    '会话边界处向0自然衰减。'
)

# 3.5
add_heading('3.5  状态管理系统', level=2)

add_para(
    '状态管理系统遵循PAYADOR（arXiv:2504.07304）的"最小化LLM输出在结构化数据上的锚定"原则：'
    'LLM仅提议状态变更（deltas），确定性引擎（GameStateManager）负责验证和合并。'
    '这种架构确保了即使LLM产生幻觉，游戏状态的核心一致性仍由确定性代码保障。'
)

add_para(
    'GameStateManager的核心状态结构包含：sanity（理智值，0–100，每轮自动+1恢复）、'
    'health（生命值，0–100）、turn（当前轮数）、current_location（当前位置）、'
    'items（ItemMemory列表，按名称upsert合并）、npcs（NPCMemory列表，按名称upsert合并）、'
    'quests（QuestMemory列表，按名称upsert合并）、world_facts（WorldFactMemory列表）、'
    'player_status（PlayerStatus：condition/danger_level/current_goal）、'
    'recent_events（最近8个事件，每个≤120字符）。'
)

add_para(
    '防膨胀硬上限机制确保长战役（目标270轮）中状态不会无限增长：'
    '物品≤20个、NPC≤15个、任务≤10个、世界事实≤15个。'
    '当列表超过上限时，按重要性/时序优先级移除最旧的条目。'
    'SCORE物品状态机在状态合并后自动运行，检测并阻止丢失/销毁物品的非连续性"复活"。'
)

# 3.6
add_heading('3.6  数据存储设计', level=2)

add_para(
    '系统使用SQLite数据库（WAL模式，Write-Ahead Logging）作为主要关系型存储，包含以下表结构：'
)

add_para(
    'game_sessions表：存储游戏会话元数据（session_id、campaign_id、scenario_name、created_at、updated_at、state_snapshot）。'
    'session_messages表：存储每轮对话消息（session_id、turn、role、content、timestamp）。'
    'model_outputs表：存储LLM原始输出和结构化输出（session_id、turn、raw_output、parsed_output、model_name、temperature、tokens_used、latency_ms）。'
    'knowledge_chunks表：存储知识库块和NSB生成的摘要（chunk_id、content、source_type、keywords、importance、embedding_vector、created_at）。'
    'evaluations表：存储HaluMem评测结果（session_id、turn、hallucination_type、stage、severity、detail）。'
    'campaign_progress表：存储战役进度（session_id、campaign_id、arc_id、session_index、turn、revealed_anchors、fsm_state、npc_relations_json）。'
)

add_para(
    'FAISS向量索引（IndexFlatIP，内积相似度即归一化后的余弦相似度）用于L1记忆的语义检索。'
    'EmbeddingClient使用DeepSeek Embedding API（自动检测模型和维度），'
    '当API不可用时降级为SHA-256哈希嵌入（256维单位向量）。'
    '向量索引采用惰性初始化策略：首次调用retrieve_async()时批量计算所有知识块的API嵌入向量。'
)

add_page_break()
