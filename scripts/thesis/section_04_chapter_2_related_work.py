"""Thesis section: CHAPTER 2: 相关工作 (Related Work). Appends to the shared document on import."""
from thesis.document import (
    add_heading,
    add_page_break,
    add_para,
    doc,
)
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt

# ============================================================
# CHAPTER 2: 相关工作 (Related Work)
# ============================================================

add_heading('2  相关工作', level=1)

# 2.1
add_heading('2.1  上下文工程与窗口管理', level=2)

add_para(
    '上下文工程作为独立研究方向，在2025年趋于成熟。Zhao等（2025）的综述覆盖1400余篇论文，'
    '提出了包含提示压缩、KV缓存管理、上下文选择和上下文组织四个维度的分类框架。'
    '本研究的L0工作记忆层可视为一种"语义级提示压缩"——将当前场景状态压缩为结构化模板（约150 tokens），'
    '而非依赖对话历史的完整重放。L1语义检索层则属于上下文选择策略——按需检索相关记忆而非全量注入。'
)

add_para(
    '提示压缩方面，LLMLingua系列（Jiang et al., 2023 EMNLP; 2024 ACL）提出了粗到细的token级压缩方法，'
    '500xCompressor（ACL 2025）实现了6–480倍的极端压缩比。KV缓存压缩方面，RocketKV（ICML 2025）'
    '实现了400倍压缩比和3.7倍加速，DynamicKV（arXiv:2412.14838）在仅保留1.7% KV缓存的情况下维持了任务性能，'
    'ZSMerge（arXiv:2503.10714）提出了零样本KV缓存合并方案。'
    '本研究采用token预算管理策略（SimpleTruncationStrategy，使用tiktoken的cl100k_base编码器），'
    '按优先级顺序裁剪上下文段落（RAG块 → 健康指引 → 战役上下文 → 摘要 → 消息历史），'
    '确保系统提示和玩家动作始终保留在上下文中。'
)

# 2.2
add_heading('2.2  AI记忆系统', level=2)

add_para(
    '通用记忆框架方面，MemGPT/Letta（Packer et al., 2024, arXiv:2310.08560）首次将操作系统概念'
    '（虚拟上下文管理、分页、中断）引入LLM记忆管理，但其为通用对话设计，缺乏TRPG所需的规则记忆和NPC关系追踪能力。'
    'EverMemOS（2025）以仿生四层架构在LoCoMo 300轮长对话基准上达到92.3%，是目前性能最高的通用记忆系统。'
    'Zep（arXiv:2501.13956, 2025）以时序知识图谱为核心，在LoCoMo上达到85.22%。'
    'Memoria（arXiv:2512.12686, 2025）提出混合记忆层次（会话摘要+知识图谱用户建模），'
    'SGMem（arXiv:2509.21212, 2025）使用句子级图记忆提升会话一致性。'
)

add_para(
    'TRPG相关记忆方案方面，SillyTavern生态中涌现了多个创新方案：NemoLore提供自动摘要+核心记忆+向量检索的组合方案；'
    'Memory Books（STMB）实现了场景→弧→章→书→史诗的多层记忆整合；Timeline Memory引入Agentic工具调用和自主lore编辑。'
    '开源方案中，NeverEndingQuest的Hub-and-Spoke模块架构实现了85–92%的token节约，Chasm使用向量数据库持久化角色事件和对话。'
    'ai_rpg（115★）实现了NPC记忆+技能检定+场景摘要的完整TRPG框架。'
)

add_para(
    'MOOM（Chen et al., 2025, arXiv:2509.11860）是针对超长角色扮演对话设计的记忆管理系统，'
    '包含叙事摘要分支（NSB，三级层次化摘要，阈值θ₁=6, θ₂=5, θ₃=5）、'
    '人格构建分支（PCB，五类键的三种合并策略：规则替换、嵌入判断、LLM合并）、'
    '以及竞争-抑制遗忘机制（公式 S = α · decay + β · reinforcement）。'
    '本研究直接实现了MOOM的三个子系统，并将其集成到统一的Nyarlathotep记忆控制器中。'
    'SCORE（Yi et al., 2025, arXiv:2503.23512）的实证研究表明基线GPT-4的物品状态追踪准确率为0%，'
    '其结构化记忆+检索框架将准确率提升至98%，同时减少41.8%的幻觉和提升23.6%的连贯性。'
    '本研究实现了SCORE的四态物品状态机（active/lost/destroyed/unknown）并集成到每回合的生成管线中。'
)

# 2.3
add_heading('2.3  AI叙事与交互式小说', level=2)

add_para(
    '主持人架构研究方面，Song等（2024）在ACL Wordplay上发表的Function Calling方案（4.38/5规则一致性）'
    '证明了结构化函数调用优于纯文本prompt。"Static vs. Agentic Game Master AI"（2025, ACM CUI）'
    '的系统性对比表明，多Agent架构在规则遵循度和叙事质量上全面优于单模型方案。'
    'CALYPSO（Zhu et al., 2023, AIIDE）作为DM辅助工具，验证了场景摘要和线索追踪的实用价值。'
)

add_para(
    '验证与约束系统方面，PANGeA（2024, AIIDE）引入的验证系统将程序化叙事的状态准确率从28%提升到98%，'
    '是规则执行可行性的关键证据。Codifying Character Logic（NeurIPS 2025）将角色逻辑编译为可执行函数，'
    '为游戏规则的类似处理提供了方法论参考。STORY2GAME（2025, Georgia Tech, arXiv:2505.03547）'
    '从交互式小说自动生成游戏状态机，展示了结构化状态表示的可能性。'
    'SNAP（2025, arXiv:2601.11529）提出了基于计划的控制性叙事生成框架。'
)

add_para(
    '多智能体方面，ITMO-Agentic-AI的8-Agent DM委员会（基于LangGraph实现）代表了多智能体DM的最激进探索。'
    'ST-RPG Chatbot的双模型方案（小模型做状态追踪+大模型做叙事生成）实现了86%的token节约。'
    'LoreKraft提出了多智能体AI MMORPG引擎。'
    'Latitude Voyage（行业方案）展示了确定性世界引擎与LLM并行的架构在数千轮追踪中的可行性。'
)

# 2.4
add_heading('2.4  多智能体系��与叙事管线', level=2)

add_para(
    'SENNA系统（Jorgensen et al., ACM IUI 2026, DOI: 10.1145/3742413.3789218）是目前与本研究最直接相关的学术工作。'
    'SENNA提出了一个多智能体叙事重定向系统，核心包含：Examiner agent（判定行动可行性并识别触发的游戏规则）、'
    'Navigator agent（基于有向无环图DAG的叙事结构管理锚点事件触发）、以及六种重定向策略'
    '（more_information、world_consequences、npc_influence、environmental_cue、dramatic_timing、hard_denial）。'
    '本研究直接实现了SENNA的Examiner和核心重定向机制，并将其与CoDi（AAAI AIIDE 2025）的Director-Actor框架'
    '以及SCORE的物品连续性验证集成到统一的三阶段叙事管线中。'
)

add_para(
    'CoDi框架（AAAI AIIDE 2025, DOI: 10.1609/aiide.v21i1.36811）提出了目标驱动的交互式故事生成模式，'
    '其中Director agent负责高层叙事方向规划，Actor负责文本生成。'
    '本研究的Director agent继承了CoDi的目标驱动指令类型，'
    '输出包含narrative_direction、anchor_triggered、redirection_strategy、item_continuity_checks和health_guidance的结构化指令。'
)

add_para(
    'HaluMem框架（Chen et al., 2025, arXiv:2511.03506）提供了记忆系统幻觉检测的方法论基础。'
    '其研究显示记忆系统在长对话中的失败率超过50%，Mem0的召回率从43%骤降至3.2%。'
    'HaluMem提出了四类幻觉分类法（fabrication、error、conflict、omission）和三阶段评估流程'
    '（记忆提取→记忆更新→问答评测）。本研究实现了HaluMem的评估框架，用于检测Nyarlathotep记忆系统的幻觉输出。'
)

# 2.5
add_heading('2.5  评测基准', level=2)

add_para(
    '记忆评测方面，LongMemEval（ICLR 2025）以五维度（信息提取、多会话推理、时间推理、知识更新、拒答）'
    '和500个嵌入题目成为目前最权威的长对话记忆评测基准。LoCoMo（2024）以300轮/35会话/平均9K tokens'
    '构建了超长程对话记忆基准。Evo-Memory（2025）提出了流式自演化记忆评测方案。'
)

add_para(
    '角色扮演评测方面，RPGBENCH（ICML 2025, arXiv:2502.00595）从游戏创建和模拟两个维度评测LLM作为RPG引擎的能力。'
    'CharacterBench包含22,859样本和11个评测维度。CharacterEval（2024）是唯一的中文角色扮演评测基准'
    '（1,785对话/11,376样本），但未覆盖TRPG场景。RoleRMBench & RoleRM（2025, arXiv:2512.10575）'
    '以七维度评测达到88.3%的判定准确率。PingPong（arXiv:2409.06820）对40余个模型进行了角色扮演一致性基准测试。'
)

add_para(
    '上述基准均未覆盖TRPG特有的记忆需求（规则记忆、状态追踪、NPC关系图维护）。'
    '本研究计划在后续阶段构建TRPG-MemBench评测基准，填补这一空白。'
)

# 2.6
add_heading('2.6  与现有工作的对比总结', level=2)

add_para('表2.1从六个维度将本系统（Nyarlathotep架构）与主要现有方案进行系统对比。')

# Create comparison table
table = doc.add_table(rows=7, cols=7, style='Table Grid')
table.autofit = True

headers = ['维度', 'MemGPT/Letta', 'SillyTavern\nMemory Books', 'SENNA', 'MOOM', 'SCORE', '本系统\n(Nyarlathotep)']
for i, h in enumerate(headers):
    cell = table.rows[0].cells[i]
    cell.text = h
    for p in cell.paragraphs:
        for run in p.runs:
            run.bold = True
            run.font.size = Pt(9)

data = [
    ['记忆架构', '通用OS式\n虚拟上下文', '手动配置\nWorld Book', 'DAG叙事图\n无长期记忆', '三层摘要+\n人格+遗忘', '物品状态机\n无长期记忆', '三层记忆+\n物品追踪+\n人格+遗忘'],
    ['检索策略', '语义检索', '关键词触发\n（手动编写）', '锚点条件\n匹配', '关键词+\n实体重叠', 'LLM解析\n结构化字段', '语义+时序+\n实体三维检索'],
    ['状态追踪', '依赖LLM\n隐式记忆', '手动维护\nWorld Book条目', '锚点触发\n状态', 'LLM输出\n摘要JSON', 'FSM+\nLLM解析', '确定性引擎+\nLLM提议deltas'],
    ['Agent架构', '单Agent', 'N/A', 'Examiner+\nNavigator', '单次调用', '单次调用', 'Examiner+\nDirector+\nNarrator'],
    ['中文支持', '无专门优化', '社区翻译', '无', 'ZH-4O\n中文数据集', '无', '字符级token\n预算控制'],
    ['评测体系', '通用对话', '无系统评测', '用户研究\nN=24', 'ZH-4O\n评测', '物品追踪\n准确率', 'HaluMem+\n7轮实验'],
]

for ri, row_data in enumerate(data):
    for ci, text in enumerate(row_data):
        cell = table.rows[ri + 1].cells[ci]
        cell.text = text
        for p in cell.paragraphs:
            for run in p.runs:
                run.font.size = Pt(8)

add_para('表2.1  本系统与现有方案的六维度对比', alignment=WD_ALIGN_PARAGRAPH.CENTER, font_size=10)

add_page_break()
