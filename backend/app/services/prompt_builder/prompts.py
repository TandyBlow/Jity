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


OPTION_IMPACT_CONTRACT = (
    "- 每个选项执行后必须至少改变一项剧情状态：获得或验证线索、推进或改变目标、改变 NPC 关系、"
    "改变位置或控制权、改变危险、消耗资源换取优势、开启或排除路线。若什么都不改变，就不要生成该选项。\n"
    "- 至少一个选项必须直接推进当前主线目标；其他选项可以用风险、关系、资源或调查等不同方式推进。\n"
    "- 各选项必须产生实质不同的后果，禁止把“观察、仔细观察、继续查看”之类同义行动拆成多个选项。\n"
    "- 玩家即使失败也要得到新信息或造成新局势，不能得到“什么也没发生，请重试”的死回合。\n"
    "- 如果最近行动已经反复观察或询问，本回合选项必须要求决定、介入、付出代价或选择路线，不能继续原地打转。\n"
)


SOFT_TURNS_OPTION_CONTRACT = (
    "软回合阈值后的选项规则（最高优先级）：\n"
    "- 从本回合结尾开始，所有选项都必须直接推进至少一个下方列出的本幕收束目标；这不是建议，而是硬性约束。\n"
    "- 只生成 2 到 4 个推进选项。不得提供等待、休息、闲逛、纯气氛互动、重复观察、重复询问、"
    "留在原地继续看看或与本幕目标无关的支线。\n"
    "- 调查选项只有在本次行动必然验证或排除关键线索、锁定目标或开启路线时才允许；单纯查看更多细节不算推进。\n"
    "- 每个选项要写明具体行动对象，并让玩家分别通过直接介入、证据验证、人物交涉、承担风险或资源取舍等不同方式推进。"
    "不得把同一种推进方式改写成多个近义选项。\n"
    "- 如果玩家当前行动仍在闲逛或重复调查，先用关键线索、NPC 介入、时间压力或危险升级打断空转，"
    "再给出全部指向本幕收束目标的选项。\n"
    "- 软阈值只负责聚焦选择，不能提前宣告本幕结束、强行传送或替玩家作出转场决定。\n"
)


FINAL_TURNS_OPTION_CONTRACT = (
    "最终幕硬回合阈值后的收束规则（最高优先级）：\n"
    "- hard_turns 只表示必须把冲突推到最终抉择，不代表整局回合预算耗尽；不得因此返回 game_over，"
    "不得使用‘回合预算耗尽’或‘未完成的调查’作为结局。\n"
    "- 当前行动后必须让最终危机产生不可逆变化，并生成 3 到 4 个能够立刻结束战役的明确选择。\n"
    "- 每个选择必须原样包含下方某条结局触发短语，使玩家下一次提交后端能够确定性选中对应结局；"
    "不要把触发短语改写成近义句。\n"
    "- 各选择必须代表实质不同的代价与立场；不得提供继续调查、等待、重复交涉、暂不决定或离开以后再说。\n"
    "- 只有玩家已经提交了明确结局选择，或真正到达整局回合上限时，才能返回 game_over=true。\n"
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
    + OPTION_IMPACT_CONTRACT
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
