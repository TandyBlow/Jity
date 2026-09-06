"""Thesis section: CHAPTER 5: 实验与评估 (Experiments & Evaluation). Appends to the shared document on import."""
from thesis.document import (
    add_heading,
    add_page_break,
    add_para,
    doc,
)

# ============================================================
# CHAPTER 5: 实验与评估 (Experiments & Evaluation)
# ============================================================

add_heading('5  实验与评估', level=1)

# 5.1
add_heading('5.1  实验设计', level=2)

add_para(
    '为验证Nyarlathotep记忆架构和prompt工程优化的有效性，本研究设计并执行了七轮正式实验（Run 1–7），'
    '实验记录保存于.pipeline/memory/experiment_ledger.md。'
    '实验在三个维度上系统比较系统配置：'
)

add_para(
    '实验条件设计：Baseline（8字段JSON输出，无记忆增强）、'
    'L0模式（8+5字段JSON输出，L0工作记忆卡片注入，状态追踪字段标记为可选）、'
    'L1-mix-k5模式（L0全量 + L1混合摘要语义检索Top-5）。'
    '测试场景包括场景A"调查失踪案"和场景B"码头疑云"，每个场景运行5轮。'
)

add_para(
    '关键消融变量包括：temperature（0.9 → 0.3）、JSON schema字段数（14 → 8）、'
    'L0记忆卡片注入位置（顶部 → 底部）、记忆摘要策略（纯叙事 → 混合 → 结构化）、'
    '系统提示措辞（DM → KP，删除冗余说明）。'
)

add_para(
    '评估方法采用三步模糊匹配：'
    '（1）文本规范化（去标点、统一数字格式、去停用词）；'
    '（2）关键词重叠分数（状态字段的实体级匹配）；'
    '（3）嵌入相似度（BAAI/bge-large-zh-v1.5余弦相似度，阈值>0.5视为匹配）。'
    '评测指标包括状态准确率（HP/SAN/位置/物品/NPC的一致性）、JSON格式合规率、'
    '叙事连贯性主观评分、以及每轮token消耗和延迟。'
)

# 5.2
add_heading('5.2  核心实验结果', level=2)

add_para(
    'Temperature消融：将temperature从0.9降至0.3后，非JSON输出频率从约15%显著降至约2%，'
    'JSON格式合规率从约85%提升至约98%。这一结果验证了在结构化输出场景中低temperature的必要性，'
    '与DeepSeek V4的官方benchmark建议一致。'
)

add_para(
    'JSON Schema精简：将输出字段从14个减至8个（移除5个状态追踪字段，标记为可选仅L0模式使用）后，'
    'JSON解析成功率提升约12个百分点。这表明过重的JSON schema是结构化输出失败的主要因素之一，'
    '与文献中关于"schema复杂度与LLM遵从度呈负相关"的发现一致。'
)

add_para(
    'L0卡片位置优化：经网格搜索实验验证，将记忆卡片放置在系统提示底部'
    '（叙事指令之后、JSON格式指令之前）比放置在顶部提升33个百分点（场景B：33% → 67%）。'
    '分析显示，顶部注入会污染叙事指令的有效上下文空间，使LLM将记忆卡片误读为叙事指令的一部分。'
    '这一发现与Lost-in-the-Middle效应的研究结论互补——不仅中间信息容易被遗忘，'
    '顶部信息的语义污染同样是一个被低估的问题。'
)

add_para(
    '记忆摘要策略对比：mixed策略（同时保留精确实体名称和叙事语境）在场景A上达到92%的checkpoint准确率，'
    '显著优于纯叙事摘要策略（narration，67%）。分析表明，实体名称后缀保留了用于checkpoint匹配的关键标识符，'
    '而纯叙事摘要虽然在语义上等价，但缺乏精确的实体锚点。'
)

# 5.3
add_heading('5.3  HaluMem幻觉评测', level=2)

add_para(
    '本研究实现了HaluMem（Chen et al., 2025）的四类幻觉检测框架，'
    '用于评测Nyarlathotep记忆系统的可靠性。具体实现见backend/app/services/memory/halumem_eval.py（270行）。'
)

add_para(
    '评测流程分为三个阶段：记忆提取阶段（Memory Extraction）检测LLM生成的状态变更JSON中'
    '是否存在fabrication（无中生有，编造不存在的物品/NPC/事件）、error（数值错误，如HP/SAN计算偏差）、'
    'conflict（与已知状态冲突，如声称物品在背包中但此前已消耗）、omission（遗漏，如应触发但未触发的规则）；'
    '记忆更新阶段（Memory Updating）检测GameStateManager合并后的状态是否存在conflict（合并冲突）、'
    'omission（遗漏更新）和error（合并逻辑错误）；'
    '记忆问答阶段（Memory QA）进行端到端的幻觉检测，通过LLM-as-judge（使用DeepSeek API）自动判定。'
)

add_para(
    '评测结果以结构化JSON报告输出，包含每类幻觉的计数、每个阶段的细目、'
    '以及聚合指标（总幻觉率、按类型分布、按阶段分布）。这些结果为后续记忆架构的迭代优化提供了数据驱动的决策依据。'
)

# 5.4
add_heading('5.4  系统规模与测试覆盖', level=2)

add_para(
    '截至2026年6月，Jity代码库包含69个Python模块（10,910行代码），'
    '其中服务层32个模块（6,095行）、记忆子系统8个模块（1,524行）、Agent层5个模块（1,249行）。'
    '测试套件包含19个测试文件（2,887行），共计221个自动化测试用例，'
    '覆盖Agent管线（test_agent_pipeline.py, 708行）、战役管理（test_campaign_manager.py, 303行）、'
    'token预算管理（test_token_budget.py, 232行）等核心模块。'
    'Git历史记录显示32次提交，开发周期约三周（2026-06-03至2026-06-24）。'
)

add_page_break()
