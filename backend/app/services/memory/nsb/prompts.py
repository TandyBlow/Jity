"""NSB summarization prompts and MOOM thresholds."""

# ── MOOM default thresholds ──────────────────────────────────────

THETA_1 = 6  # turns per first-level summary
THETA_2 = 5  # first-level summaries per second-level summary
THETA_3 = 5  # second-level summaries per third-level summary


_LEVEL1_PROMPT = """你是TRPG叙事摘要系统。将以下{theta1}轮对话压缩为一段结构化摘要。

要求：
1. 捕获关键事件、冲突和转折点
2. 列出涉及的实体（NPC、物品、地点）
3. 记录状态变化（新获得的物品、关系变化等）
4. 添加因果链接（这个场景如何从前一个场景演化而来）
5. 添加叙事标签（悬疑/战斗/社交/探索/平静）
6. 评估重要性（0-1，1=关键剧情转折）

输出格式（严格JSON）：
{{
  "summary": "场景摘要，100-200字",
  "tags": ["悬疑", "战斗"],
  "entities_involved": ["角色名", "物品名"],
  "causal_links": ["scene_prev→scene_curr: 因果描述"],
  "state_changes": {{"实体名": "变化描述"}},
  "importance": 0.7
}}

对话内容：
{dialogue}"""

_LEVEL2_PROMPT = """你是TRPG叙事摘要系统。将以下{theta2}个一级场景摘要整合为一段二级摘要。

二级摘要关注更宏观的叙事弧线：中期目标进展、角色发展轨迹、主要冲突的演变。

输出格式（严格JSON，同上结构）：
{schema}

一级摘要列表：
{summaries}"""

_LEVEL3_PROMPT = """你是TRPG叙事摘要系统。将以下{theta3}个二级摘要整合为一段三级摘要。

三级摘要关注故事主题层面：核心冲突的哲学意义、阵营格局变化、整个叙事阶段的宏观走势。

输出格式（严格JSON，同上结构）：
{schema}

二级摘要列表：
{summaries}"""
