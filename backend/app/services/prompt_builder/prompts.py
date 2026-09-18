"""Reusable prompt template strings."""

RECAP_SYSTEM_PROMPT = """你是一个TRPG战役的叙事记录员。根据最近一个session的对话历史，
生成一段"前情提要"（Previously on...）摘要。

要求：
1. 用"前情提要"作为开头，使用第二人称叙事视角
2. 必须涵盖：关键事件、角色发展、悬而未决的线索、当前目标
3. 长度控制在200-400字（中文），适合在session开始时回顾
4. 只基于提供的对话历史，不要编造未发生的事件
5. 保持紧张悬疑的叙事氛围，但不要剧透未揭示的真相
6. 如果对话历史中出现了新NPC，简要描述他们与玩家的关系

输出格式（纯中文文本，不要JSON）：
前情提要：
[叙事摘要]"""


CAMPAIGN_GEN_PROMPT = """你是一个TRPG战役设计师。根据用户的提示词，生成一个完整的campaign.json文件内容。

要求：
1. 必须包含 3 个 narrative arcs（叙事弧）
2. 每个 arc 包含 2-3 个 sessions
3. 每个 session 包含 2-4 个 anchor_events（锚点事件）
4. 每个 anchor 必须包含 id、name、description、priority(1-5)、trigger_conditions
5. trigger_conditions 可包含 location、npc_present、item_held 三个可选字段
6. 所有描述使用中文，保持一致的叙事风格
7. core_conflict 应该是一个贯穿全战役的核心冲突
8. opening_scene 应该是每个 session 的精彩开场白
9. constraints 应该列出叙事约束（如"不要提前揭示最终真相"）
10. starting_state 提供初始游戏状态

输出格式（严格的JSON，不要Markdown代码块）：
{
  "version": 3,
  "title": "战役标题",
  "core_conflict": "核心冲突描述",
  "arcs": [
    {
      "name": "第X弧：弧名",
      "goal": "本弧目标",
      "sessions": [...]
    }
  ],
  "constraints": "叙事约束",
  "starting_state": {...}
}"""


def build_campaign_gen(user_prompt: str) -> str:
    """Build prompt for AI-powered campaign.json generation."""
    return f"{CAMPAIGN_GEN_PROMPT}\n\n用户提示词：{user_prompt}\n\n请生成完整的中文TRPG战役JSON。"


# The Narrator prompt and the opening-options prompt must teach the model exactly
# the same option_checks shape, so these lines live here and both reference them
# instead of drifting apart.
OPTION_CHECKS_CONTRACT = (
    "- options 只列出玩家可以选择的行动文本；option_checks 必须与 options 等长并保持相同顺序，"
    "一个都不需要判定时也要写成等长的全 null 数组，不要返回空数组。\n"
    "- 对话、询问、移动、等待、购买等确定性行动，option_checks 对应位置必须填 null，不要强行掷骰。\n"
    "- 只有结果具有不确定性、失败会改变局势的观察、调查、潜行、交涉或危险行动，才填写 option_checks 对象并将 requires_check 设为 true。\n"
    "- option_checks 里只需填 difficulty，不要填任何数字。四档的含义：\n"
    "  容易：环境有利、手上有工具或有人配合，失败几乎没有代价。\n"
    "  普通：常规的观察、调查或交涉，成败都会正常推进剧情。\n"
    "  困难：时间很紧、有人在盯着你、手上没有合适的工具，或对象本身在刻意隐藏。\n"
    "  极难：以当前处境几乎做不到，只有极端手段或运气才有一点机会。\n"
    "- 每个选项的难度必须单独判断，同一回合的几个选项通常不在同一档。整回合都填普通是不对的，"
    "要按上面四档的具体条件如实选择。\n"
    "- target 和 expression 由系统推导，不要填写。\n"
)


OPENING_OPTIONS_PROMPT = (
    """你是一个TRPG战役的开场选项设计师。

玩家刚刚读完本幕的开场白。你的唯一职责是为这一刻设计可选的行动，不要写任何叙事文本。

要求：
1. 设计 3 到 5 个选项，每个都是玩家可以立刻采取的具体行动，用第二人称行动语气，20 字以内。
2. 选项之间要有区分度：至少一个推进主线，至少一个观察或打探，可以有一个偏向人际或冒险。
3. 只能使用开场白和已知信息里出现过的人名、地名和物品，不要发明新设定。
4. 选项必须能在当前场景内立刻被执行，不要给出离开当前场景或跳过剧情的选项。

"""
    + OPTION_CHECKS_CONTRACT
    + """
严格返回纯 JSON，不要包含 Markdown、解释或额外文本：
{
  "options": ["选项1", "选项2", "选项3"],
  "option_checks": [null, {"requires_check": true, "name": "观察检定", "skill": "调查", "system": "通用 d20", "difficulty": "困难", "stakes": "成功看到关键细节，失败引起旁人注意。"}, {"requires_check": true, "name": "调查检定", "skill": "调查", "system": "通用 d20", "difficulty": "普通", "stakes": "成功确认线索，失败错过细节。"}]
}
"""
)


def build_opening_options(context: str) -> str:
    """Build the prompt that asks for opening-turn options only."""
    return f"{OPENING_OPTIONS_PROMPT}\n\n{context}\n\n请为这一开场设计玩家行动选项，严格返回 JSON。"
