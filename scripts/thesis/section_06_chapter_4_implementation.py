"""Thesis section: CHAPTER 4: 关键实现 (Implementation). Appends to the shared document on import."""
from thesis.document import (
    add_heading,
    add_page_break,
    add_para,
    doc,
)

# ============================================================
# CHAPTER 4: 关键实现 (Implementation)
# ============================================================

add_heading('4  关键实现', level=1)

add_para(
    '本章详细介绍Jity系统各核心组件的实现细节。系统单回合的完整数据处理流程如图4.1所示，'
    '涵盖从玩家输入到响应返回的九个处理阶段。以下各节按模块逐一展开。'
)

# 4.1
add_heading('4.1  记忆控制器（MemoryController）', level=2)

add_para(
    'MemoryController是Nyarlathotep架构的核心编排器，实现于backend/app/services/memory/memory_controller.py（227行）。'
    '其核心职责包括：上下文组装（三层记忆按优先级组装为prompt注入文本）、'
    '异步记忆维护（每轮后触发NSB摘要级联、PCB人格抽取、MOOM遗忘）、'
    '会话级持久化（每个session_id对应一个MemoryController实例，通过ScenarioGenerator的字典缓存，LRU淘汰上限50个）。'
)

add_para(
    'on_turn_generated()方法在每轮LLM生成后由ScenarioGenerator调用，异步触发维护任务：'
    '解析LLM的状态变更JSON → 提取新增事件 → 检查NSB阈值（turn % 6 === 0 → L1摘要，'
    'L1计数 % 5 === 0 → L2摘要，L2计数 % 5 === 0 → L3摘要） → '
    '检查PCB阈值（turn % 10 === 0 → 人格快照抽取） → 运行MOOM遗忘评分 → 提交数据库。'
    '维护任务通过asyncio.create_task()以fire-and-forget模式异步执行，不阻塞玩家等待。'
)

# 4.2
add_heading('4.2  MOOM子系统实现', level=2)

add_para(
    'NSB（Narrative Summarization Branch，nsb.py，286行）：实现MOOM的三级层次化摘要。'
    'generate_summary()方法调用LLM（temperature=0.2）对一组事件进行摘要，'
    '输出包含tags、entities_involved、causal_links、state_changes和importance的结构化JSON。'
    'retrieve_top_k()方法以query文本检索最相关摘要，计算关键词重叠分数、实体重叠分数和时序衰减因子的加权和。'
    '摘要持久化到knowledge_chunks表，使历史摘要可被RAGRetriever检索。'
)

add_para(
    'PCB（Persona Construction Branch，pcb.py，314行）：每10轮抽取玩家/NPC人格快照。'
    '维持累积的PersonaSketch，使用MOOM的五类键分类和三种合并策略：'
    'REPLACE_KEYS（name、age、gender、MBTI、location等）——规则替换，最新值覆盖；'
    'ADD_KEYS（liked/disliked foods、activities、music等）——追加并设上限；'
    'TRAJECTORY_KEYS（schools、majors、past experiences）——带时间戳追加；'
    'CONTRADICTORY_KEYS（preferences、beliefs、attitudes等）——嵌入判断：通过EmbeddingClient计算新旧值的余弦相似度，'
    '>0.85视为过时信息替换，<0.85视为真正变化追加；'
    'COMPLEX_KEYS（family、career、health、lifestyle等）——当前简化为追加+上限，'
    '完整LLM判断逻辑推迟至后续版本。'
    '当嵌入API不可用时，自动降级为字符级Jaccard相似度（>80%字符重叠视为相等）。'
)

add_para(
    'Forgetting（forgetting.py，172行）：精确实现MOOM论文的竞争-抑制公式。'
    '记忆重要性分数 S = α · 1/(exp(γ·(rc-b))+1-ε) + β · Σ(1/(rc-r+ε))，'
    '其中α=0.1（时间衰减权重），β=0.9（检索增强权重），γ=1.0（衰减陡度），b为偏置，ε为小常数防除零。'
    '每轮管线：评分所有记忆 → 相似度重排Top-2K → Top-K增强（记录本轮检索） → '
    'Next-K抑制（分数减半） → 未激活不变 → 修剪低于阈值（0.01）的记忆 → 上限200条。'
    'BGE风格相似度重排通过EmbeddingClient计算余弦相似度（可选功能，当前未完全接入）。'
)

# 4.3
add_heading('4.3  SCORE物品状态追踪', level=2)

add_para(
    'SCORE追踪器（score_tracker.py，159行）实现四态有限状态机。'
    '每个物品的状态转移规则为：active → lost（物品丢失/消耗）、active → destroyed（物品被摧毁）、'
    'lost → active（物品被找回，需通过连续性验证）、destroyed → active（禁止转移，自动拦截）。'
    'unknown状态用于LLM未明确提及的物品。'
)

add_para(
    'validate_item_transition()方法在每轮LLM的状态变更JSON解析后自动调用：'
    '检查LLM提议的物品状态转移 → 若从lost/destroyed到active，记录CONTINUITY_VIOLATION → '
    '阻止非法转移 → 维持物品在lost/destroyed状态。'
    'SCORE状态文本通过MemoryController注入Director和Narrator的系统提示，'
    '使两个Agent在生成时都能感知物品的当前状态和连续性约束。'
    '违规记录通过日志输出，用于后续分析和HaluMem评测。'
)

# 4.4
add_heading('4.4  SENNA多智能体管线', level=2)

add_para(
    'Examiner Agent（examiner.py，149行）：核心方法examine()构造包含玩家行动、当前游戏状态、'
    'NPC列表、物品列表和任务列表的提示。输出ActionRuling（Pydantic模型），包含verdict枚举值、'
    'ruling_reason（裁定理由文本）、triggered_rules（触发的游戏规则列表，每项含rule_name和rule_category）、'
    'suggested_difficulty（建议难度，1–20）。'
    '设置temperature=0.1以确保裁定的一致性。包含完整的fallback机制：任何异常或解析失败时默认返回PERMISSIBLE，'
    '确保单点故障不会中断游戏。'
)

add_para(
    'Director Agent（director.py，181行）：核心方法direct()的输入包括Examiner的ActionRuling、'
    'L1叙事记忆摘要（来自NSB.retrieve_top_k()）、当前锚点进度和候选项（来自CampaignAnchorEvaluator）、'
    '偏离状态和连续未触发轮数、以及SCORE物品状态列表。'
    '输出DirectorInstruction（Pydantic模型），包含narrative_direction（高层方向文本，≤150 tokens）、'
    'anchor_triggered（锚点事件ID或null）、redirection_strategy（六种枚举值之一或none）、'
    'redirection_hint（提示文本，≤80 tokens）、item_continuity_checks（SCORE验证结果列表）、'
    'health_guidance（节奏建议文本）。'
    'temperature=0.3平衡创造性和一致性。包含fallback机制：异常时返回通用叙事方向，不指定特殊策略。'
)

add_para(
    'ScenarioGenerator._execute_llm_or_scripted()方法（scenario_generator.py，第206–299行）'
    '编排完整的管线执行流程：1) 脚本化故事检查（turn ≤ 1时，ScriptedStoryService拦截）；'
    '2) Examiner判定；3) 若blocked，短路返回叙事拒绝；4) 检索L1记忆和锚点候选；'
    '5) Director生成指令；6) _inject_direction()将指令注入Narrator提示；7) Narrator生成最终输出。'
    '管线仅在战役加载时激活，确保向后兼容。'
)

# 4.5
add_heading('4.5  LLM客户端与JSON修复管线', level=2)

add_para(
    'LLMClient（llm_client.py，325行）基于openai SDK 2.41.x封装DeepSeek API调用。'
    '提供三种生成接口：generate()返回带Pydantic验证的StoryOutput类型对象、'
    'generate_json()返回原始dict（供Agent和事实抽取等调用方自行解析）、'
    'generate_text()返回自由文本（用于摘要生成）。'
)

add_para(
    'JSON输出采用三层防御策略确保结构化输出的鲁棒性：'
    '第一层——直接解析：使用response_format: {"type": "json_object"}调用API，'
    '对返回内容进行json.loads() + Pydantic StoryOutput.model_validate()；'
    '第二层——本地修复：使用json_repair库0.61.x的repair_json()函数，'
    '处理未转义引号、尾随逗号、截断JSON等常见格式错误，无需额外API调用；'
    '第三层——LLM修复：若前两层均失败，以temperature=0调用LLM，'
    '传入修复提示要求其修正格式错误的JSON，再重新解析。'
)

add_para(
    '文本清洗（_clean_json_text）：剥离DeepSeek-R1风格的thinking标签、Markdown代码围栏标记，'
    '是应对DeepSeek模型偶尔将输出包裹在markdown中的实用响应策略。'
    '输出规范化（_normalize_output）：防御性字段规范化，将字符串类型的列表项强制转换为dict，'
    '填充缺失字段的默认值，是在JSON模式但无JSON Schema强制约束下的关键鲁棒性模式。'
)

add_para(
    '各调用场景的temperature策略：主叙事生成0.35（平衡质量和稳定性）、'
    'JSON修复0.0（确保修复确定性）、Examiner 0.1（确保裁定一致性）、'
    'Director 0.3（平衡创造性）、事实抽取0.2（确保准确性）、战役生成0.7（需要创造性）。'
    '经过7轮实验验证，主叙事temperature从最初的0.9降至0.35后，非JSON输出频率从约15%降至约2%。'
)

# 4.6
add_heading('4.6  嵌入与检索', level=2)

add_para(
    'EmbeddingClient（embedding_client.py，120行）封装DeepSeek Embedding API调用。'
    '初始化时自动探测可用模型（依次尝试deepseek-embed和deepseek-chat）和向量维度。'
    '实现惰性批量嵌入：首次调用retrieve_async()时遍历所有知识块，对未嵌入的块批量调用API。'
    '检测到API不可用时自动降级为SHA-256哈希嵌入（256维单位向量），'
    '通过CJK二元组/三元组/四元组展开处理中文文本，token → 哈希桶映射结合长度加权。'
    '但如系统文档所承认，哈希嵌入"对中文提供零语义匹配"，因此API路径不可用时会显著影响检索质量。'
)

add_para(
    'RAGRetriever（retriever.py，141行）实现混合检索策略。'
    '密集检索：通过EmbeddingClient获取查询向量，在FAISS IndexFlatIP索引中执行精确最近邻搜索。'
    '关键词增强（_keyword_boost方法）：六级增强策略——标题匹配（+1.2）、关键词匹配（+0.8）、'
    '标题作为词项（+0.5）、关键词-词项重叠（+0.18）、内容词项重叠（+0.05）、重要性缩放（+0.04）。'
    '查询构建（ScenarioGenerator._build_rag_query）：多字段拼接——玩家动作 + 当前位置 + 最近事件 + NPC名称 + 任务名称。'
)

# 4.7
add_heading('4.7  前端架构', level=2)

add_para(
    '前端采用Next.js 16.2 + React 19.0 + TypeScript，使用App Router模式。'
    '核心页面为GM控制台（app/page.tsx），包含以下功能区域：'
    '叙事显示区（打字机效果文本逐字输出、NPC对话淡入动画）、'
    '状态面板（HP/SAN进度条动画、物品列表、NPC列表、任务追踪、世界事实栏）、'
    '行动输入区（自由文本输入 + 2–4个快捷选项按钮）、'
    '战役进度显示（当前弧线/会话/轮数、锚点完成状态）、'
    '背景图像区（根据场景描述调用图像生成API，CSS过渡动画切换）。'
)

add_para(
    '前端通过REST客户端（app/api.ts）与后端通信，主要端点包括：'
    'POST /sessions（创建游戏会话）、POST /sessions/{id}/generate（提交玩家行动并获取叙事响应）、'
    'GET /sessions/{id}/state（获取当前状态快照）、POST /evaluate（提交评测数据）、'
    'POST /knowledge/reload（重载知识库）。'
)

add_page_break()
