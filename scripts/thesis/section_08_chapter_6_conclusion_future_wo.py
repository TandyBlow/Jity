"""Thesis section: CHAPTER 6: 结论与展望 (Conclusion & Future Work). Appends to the shared document on import."""
from thesis.document import (
    add_heading,
    add_page_break,
    add_para,
    doc,
)

# ============================================================
# CHAPTER 6: 结论与展望 (Conclusion & Future Work)
# ============================================================

add_heading('6  结论与展望', level=1)

add_heading('6.1  工作总结', level=2)

add_para(
    '本研究针对AI驱动的TRPG长战役中的"AI失忆"问题，设计并实现了Jity系统——'
    '一个集成了三层记忆架构（Nyarlathotep）和多智能体叙事管线的网页端中文AI跑团平台。'
    '主要成果包括：'
)

conclusions = [
    '设计并实现了Nyarlathotep三层记忆架构，将MOOM的层次化摘要（三级NSB）、人格构建（PCB五类键三种合并策略）、'
    '竞争-抑制遗忘公式和SCORE的四态物品状态机集成到统一的内存编排控制器中，针对中文TRPG场景进行了工程适配；',
    '构建了三阶段多智能体叙事管线（Examiner → Director → Narrator），实现了SENNA的六种重定向策略和CoDi的目标驱动叙事模式，'
    '将行动判定、方向规划和文本生成解耦为独立Agent，有效降低了单次LLM调用的复杂度和失败风险；',
    '完成了全栈系统工程实现：Python/FastAPI后端（69模块/10,910行）、Next.js/React前端、'
    'SQLite WAL数据库、FAISS向量检索、221个自动化测试用例；',
    '集成并工程化落地了七个前沿框架（SENNA、MOOM、SCORE、CoDi、HaluMem、PAYADOR、Borawski管线），'
    '为学术框架的实际TRPG应用提供了可复现的参考实现；',
    '通过七轮正式实验验证了温度优化（0.9→0.3减少非JSON输出）、Schema精简（14→8字段提升解析成功率）、'
    '记忆注入位置优化（底部vs顶部+33pp）和摘要策略选择（mixed 92% vs narration 67%）的有效性；',
    '构建了包含113篇论文的文献库（覆盖15个研究方向），为TRPG上下文工程领域提供了系统性的文献基础。',
]
for c in conclusions:
    add_para(f'（{conclusions.index(c) + 1}）{c}')

add_heading('6.2  未来工作', level=2)

add_para('基于当前进展，未来工作将沿以下方向展开：')

future = [
    'TRPG-MemBench评测基准构建：设计包含规则记忆、状态记忆、关系记忆和剧情记忆四个维度的TRPG专用评测基准，'
    '参考LongMemEval（ICLR 2025）的五维度框架和LoCoMo（2024）的300轮长对话设计，'
    '填补中文TRPG评测的学术空白；',
    'L2规则知识图谱（RuleKG）实现：按Idea 2规划，使用PDF解析→LLM+SPIRES知识抽取→Neo4j图谱构建的管线，'
    '将克苏鲁神话TRPG规则书转化为可检索的结构化知识图谱，实现规则溯源到原文；',
    '软约束框架（SoftGuard）：按Idea 3规划，参考Codifying Character Logic（NeurIPS 2025）的方法论，'
    '将检定/战斗规则编译为可执行验证函数（硬约束层，JavaScript函数），同时维护偏差账簿（软约束层）'
    '记录NPC行为和剧情走向的允许偏差并在后续自动修正；',
    'MOOM复杂键LLM合并的完整实现：当前COMPLEX_KEYS（家庭、职业、健康）的LLM判断逻辑被简化为append+cap，'
    '需实现MOOM论文中的完整LLM判断流程以提升人格一致性；',
    'BGE重排序的激活接入：遗忘机制的BGE风格相似度重排序当前为可选功能，完整接入后预期提升记忆检索精度；',
    '长战役端到端测试：运行完整的270轮auto_play.py测试（3弧线×3会话×30轮），'
    '验证所有锚点事件的触发和记忆系统在极端长程场景下的稳定性；',
    '中文模型对比评测：在统一基准上对比DeepSeek-V4、Qwen3等中文模型在TRPG场景中的表现，'
    '产生首个系统性的中文AI跑团模型评测报告。',
]
for f in future:
    add_para(f'（{future.index(f) + 1}）{f}')

add_page_break()
