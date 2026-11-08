"""Thesis section: CHAPTER 1: 引言 (Introduction). Appends to the shared document on import."""
from thesis.document import (
    add_heading,
    add_page_break,
    add_para,
    doc,
)

# ============================================================
# CHAPTER 1: 引言 (Introduction)
# ============================================================

add_heading('1  引言', level=1)

# 1.1
add_heading('1.1  选题动机', level=2)

add_para(
    '桌面角色扮演游戏（Tabletop Role-Playing Game, TRPG）是一种以玩家叙事为核心的社交游戏形式。'
    '在传统TRPG中，一名游戏主持人（Game Master, GM）负责推进剧情、扮演非玩家角色（NPC）、'
    '裁定规则并维护游戏世界的内部一致性。然而，找到一名经验丰富的GM并不容易，且单次跑团往往需要3–6小时的连续时间投入，'
    '这些门槛限制了TRPG的普及。'
)

add_para(
    '近年来，大语言模型（Large Language Model, LLM）在叙事生成、角色扮演和对话系统领域展现了卓越能力，'
    '使得AI具备成为GM的潜力。SillyTavern、ai_rpg、Chasm等开源项目进一步验证了AI跑团的技术可行性。'
    '然而，当前AI跑团面临一个核心瓶颈：长战役中的"AI失忆"问题。具体表现为：'
)

problems = [
    '状态遗忘：AI在10轮对话后开始遗忘玩家的生命值（HP）、理智值（SAN）、背包物品、当前所在位置等关键游戏状态；',
    'NPC关系断裂：此前建立的NPC好感度、敌对关系在多轮后被重置，角色互动失去连续性；',
    '剧情线索丢失：关键线索和任务目标在长对话中被淹没，导致叙事逻辑出现断裂；',
    '规则不一致：AI在检定判定的严格程度上前后矛盾，同一类型的技能检定在不同轮次中可能得到截然不同的裁决；',
    '物品连续性错误：已丢失或已消耗的物品在多轮后重新出现（SCORE论文报告基线GPT-4的物品状态追踪准确率为0%）。',
]
for prob in problems:
    add_para(f'（{problems.index(prob) + 1}）{prob}')

add_para(
    '这些问题根源于LLM的上下文窗口限制和"中间遗忘"（Lost-in-the-Middle）效应。'
    '对于一个持续30轮以上的TRPG战役，原始对话历史可能达到15K–20K tokens，全量注入不仅成本高昂，'
    '而且LLM对上下文中间部分的信息利用效率显著下降。Zhao等（2025）在覆盖1400余篇论文的综述中指出，'
    '上下文工程（Context Engineering）——即对LLM上下文窗口内信息的系统化设计、组织与优化——'
    '已成为解决此类问题的关键研究范式。'
)

add_para(
    '因此，本项目的核心研究问题是：如何通过上下文工程与记忆管理技术，确保AI在长TRPG战役中'
    '对游戏规则和动态状态保持完整、一致、可检索的记忆？'
)

# 1.2
add_heading('1.2  领域背景', level=2)

add_para(
    '本项目处于三个研究领域的交叉点：上下文工程、AI记忆系统、以及交互式AI叙事。'
)

add_para(
    '上下文工程（Context Engineering）是2024–2025年兴起的研究方向，区别于传统的提示工程（Prompt Engineering），'
    '上下文工程关注的是信息在上下文窗口中的空间分配和检索策略，而非单纯的措辞优化。'
    '其子方向包括提示压缩（LLMLingua系列、500xCompressor）、KV缓存管理（RocketKV实现400倍压缩比、'
    'DynamicKV在仅保留1.7% KV缓存的情况下维持任务性能）、以及记忆增强生成。'
)

add_para(
    'AI记忆系统源于检索增强生成（RAG）的泛化。从MemGPT（Packer et al., 2024）将操作系统概念引入LLM记忆管理开始，'
    '到EverMemOS的四层仿生架构在LoCoMo基准上达到92.3%的最高分，再到Zep的企业级时序知识图谱方案，'
    '记忆系统已经从简单的向量检索演进为多层次、多策略的记忆编排（Memory Orchestration）。'
    '在TRPG垂直领域，MOOM（Chen et al., 2025）针对超长角色扮演对话提出了包含叙事摘要分支（NSB）、'
    '人格构建分支（PCB）和竞争-抑制遗忘机制的完整记忆管理方案。'
)

add_para(
    '交互式AI叙事将LLM应用于文本冒险和TRPG场景。从CALYPSO（Zhu et al., 2023）的DM辅助工具到'
    'SENNA（Jorgensen et al., ACM IUI 2026）的多智能体叙事重定向系统，'
    '再到ITMO-Agentic-AI的8-Agent DM委员会，AI主持人的架构设计经历了从单模型到多智能体的范式转变。'
    'Song等（2024）在ACL Wordplay上发表的工作证明，结构化函数调用（4.38/5规则一致性）优于纯文本prompt；'
    'PANGeA（2024, AIIDE）的验证系统将程序化叙事的状态准确率从28%提升到98%，为规则执行可行性提供了关键证据。'
)

add_para(
    '值得注意的是，上述所有学术工作均在英文场景完成。CharacterEval（2024）是唯一的中文角色扮演评测基准，'
    '但尚未涵盖TRPG场景。中文模型在TRPG中的表现缺乏系统性学术评测，构成了明确的研究空白。'
)

# 1.3
add_heading('1.3  研究目标与贡献', level=2)

add_para('本项目的主要研究目标和贡献包括：')

contributions = [
    '设计并实现了一个三层记忆架构（Nyarlathotep），将MOOM的层次化摘要、SCORE的物品状态追踪、'
    '以及竞争-抑制遗忘机制集成到统一的记忆编排控制器中，针对中文TRPG场景进行了适配和优化；',
    '构建了一个三阶段多智能体叙事管线（Examiner → Director → Narrator），'
    '将行动可行性判定、叙事方向规划和文本生成解耦到三个独立Agent，各Agent采用不同的temperature和模型配置；',
    '实现了完整的TRPG全栈系统（Python/FastAPI后端 + Next.js/React前端），包含FSM驱动的多弧线战役引擎、'
    'FAISS向量检索、以及带三级修复策略的JSON输出管线；',
    '集成并工程化落地了七个已发表的前沿框架（SENNA、MOOM、SCORE、CoDi、HaluMem、PAYADOR、Borawski管线），'
    '为每个框架的实际TRPG应用提供了参考实现；',
    '完成了七轮正式实验，验证了记忆架构的有效性和prompt工程优化的效果，为后续TRPG-MemBench评测基准的构建奠定了基础。',
]
for c in contributions:
    add_para(f'（{contributions.index(c) + 1}）{c}')

# 1.4
add_heading('1.4  论文结构', level=2)

add_para(
    '本章介绍了本研究的选题动机、领域背景和研究目标。'
    '第二章综述了上下文工程、AI记忆系统、AI叙事、多智能体系统和评测基准五个方面的相关工作，'
    '并将本系统与现有方案进行了系统对比。'
    '第三章详细描述了Jity系统的总体架构、Nyarlathotep三层记忆系统、多智能体叙事管线、'
    '战役引擎和状态管理机制。'
    '第四章深入介绍了关键组件的实现细节，包括记忆控制器、MOOM子系统、SCORE追踪器、'
    'SENNA管线、LLM客户端和嵌入检索模块。'
    '第五章报告了七轮实验的设计、执行和结果分析。'
    '第六章总结全文并展望未来工作方向。'
)

add_page_break()
