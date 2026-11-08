"""Thesis section: CHAPTER 3: 系统设计 (System Design). Appends to the shared document on import."""
from thesis.document import (
    add_heading,
    add_page_break,
    add_para,
    doc,
)

# ============================================================
# CHAPTER 3: 系统设计 (System Design)
# ============================================================

add_heading('3  系统设计', level=1)

# 3.1
add_heading('3.1  系统总体架构', level=2)

add_para(
    'Jity系统采用前后端分离的全栈架构。后端基于Python/FastAPI框架，提供RESTful API；'
    '前端基于Next.js/React/TypeScript，提供GM控制台界面。系统整体架构如图3.1所示。'
)

add_para(
    '后端架构分为五个核心层次：'
)

layers = [
    'API层（FastAPI路由）：处理HTTP请求，包括会话管理（/sessions）、知识库重载（/knowledge/reload）、'
    '评测（/evaluate）和战役管理（/campaigns）等端点，通过手动依赖注入（DI）组装服务；',
    '服务层（12个核心服务模块）：ScenarioGenerator作为主编排器，协调LLM调用、RAG检索、'
    '状态更新和记忆维护；GameStateManager负责确定性状态验证与合并；PromptBuilder组装系统提示；'
    'LLMClient封装DeepSeek API调用和JSON修复；CampaignManager管理FSM驱动的多弧线战役；',
    'Agent层（Examiner + Director + Narrator）：三阶段多智能体叙事管线，将行动判定、'
    '叙事方向规划和文本生成解耦到独立Agent；',
    '记忆层（MemoryController + MOOM子系统）：Nyarlathotep三层记忆架构，包含'
    'NSB层次化摘要、PCB人格构建、SCORE物品追踪和竞争-抑制遗忘机制；',
    '数据层（SQLite WAL模式 + FAISS索引）：关系型数据存储游戏会话、消息、模型输出、'
    '知识块和评测结果；向量索引支持语义检索。',
]
for layer in layers:
    add_para(f'（{layers.index(layer) + 1}）{layer}')

add_para(
    '前端采用Next.js 16 + React 19 + Tailwind CSS v4 + shadcn/ui组件库，'
    '通过TypeScript REST客户端与后端API通信。'
    '前端组件包括GM控制台主页面（实时叙事打字机效果、状态面板、选项按钮）、'
    '知识库管理界面和评测报告仪表板。'
)

# 3.2
add_heading('3.2  Nyarlathotep三层记忆架构', level=2)

add_para(
    'Nyarlathotep是本系统的核心记忆管理架构，由三个层次的记忆模块组成，每层具有不同的存储方式、'
    '检索策略和上下文注入优先级。图3.2展示了三层架构的数据流。'
)

add_para(
    'L0工作记忆（Working Memory，约3K tokens）：始终在全量上下文中的紧凑结构化表示，包括：'
    '当前场景状态（位置、时间、天气等环境信息）、活跃NPC卡片（名称、外貌、态度、当前目标）、'
    '最近6轮对话摘要（每轮≤80 tokens）、活跃任务列表（名称、目标、进度）、'
    '以及PCB人格快照（玩家/NPC的人格特征）。L0记忆由GameStateManager在每轮LLM输出后自动更新，'
    '通过PromptBuilder注入系统提示，无需额外的检索步骤。'
)

add_para(
    'L1叙事记忆（Narrative Memory，约2K tokens）：通过NSB层次化摘要系统自动生成和维护。'
    'NSB采用三级摘要结构：L1级（微观情节，每6轮触发，捕获具体事件和实体交互）、'
    'L2级（叙事弧线，每30轮触发，合成冲突发展和解决模式）、'
    'L3级（宏大主题，每150轮触发，提取故事主题和角色弧线）。'
    '每个摘要包含标签（tags）、参与实体（entities_involved）、因果链接（causal_links）、'
    '状态变更（state_changes）和重要性分数（importance, 0–1）。'
    '检索时采用关键词+实体重叠评分结合时序衰减（recency bonus），返回Top-5最相关摘要。'
)

add_para(
    'L2世界记忆（World Memory，约2K tokens）：基于关键词触发和语义检索的静态与准静态知识。'
    '包括规则知识图谱（Rules KG）、世界书（World Book，地点/势力/历史背景）、'
    'NPC参考档案（固定属性、背景故事、关系网络）。'
    'L2内容由CampaignContextBuilder从知识库加载，通过RAGRetriever进行语义检索。'
)

add_para(
    '三层记忆的上下文注入遵循严格的优先级顺序：L0全量注入（不可裁剪） → '
    'L1检索Top-5注入（token预算允许时） → L2关键词触发注入（token预算允许时）。'
    '当token预算紧张时，SimpleTruncationStrategy按优先级裁剪：RAG块 → 健康指引 → 战役上下文 → L2摘要 → 消息历史，'
    '确保L0和玩家动作永不被裁剪。'
)

# 3.3
add_heading('3.3  多智能体叙事管线', level=2)

add_para(
    '本系统的多智能体叙事管线受SENNA和CoDi启发，将原来的单次LLM调用替换为三阶段流水线。'
    '管线仅在战役模式下激活；非战役模式下保留传统单次LLM调用路径。'
    '图3.3展示了管线的数据流。'
)

add_para(
    '第一阶段——Examiner Agent（SENNA）：负责判定玩家行动的可行性，但不生成叙事文本。'
    '使用deepseek-v4-flash模型，temperature=0.1以确保判定的一致性。'
    '输出ActionRuling结构，包含三类裁决：permissible（行动可行，无需检定）、'
    'conditional（需进行检定，标识触发的规则类型：SAN检定/技能检定/战斗/物品使用）、'
    'blocked（行动不可行）。若判定为blocked且提供了rejection_reason，'
    '管线立即短路返回叙事拒绝文本，不再调用Director和Narrator，从而避免不必要的LLM调用。'
)

add_para(
    '第二阶段——Director Agent（SENNA Navigator + CoDi Director）：负责产出高层叙事方向，但不撰写具体文本。'
    '使用deepseek-v4-flash模型，temperature=0.3以平衡创造性和一致性。'
    '输入包括Examiner裁决、L1叙事记忆摘要、当前锚点进度和候选项、玩家偏离状态、SCORE物品状态。'
    '输出DirectorInstruction结构，包含：narrative_direction（叙事方向文本）、'
    'anchor_triggered（本回合触发的锚点事件ID）、redirection_strategy（六种SENNA重定向策略之一）、'
    'redirection_hint（重定向提示文本）、item_continuity_checks（SCORE验证结果列表）、'
    'health_guidance（叙事健康指标和节奏建议）。'
)
