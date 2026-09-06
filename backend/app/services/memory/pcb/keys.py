"""PCB persona key categories and extraction prompt."""

PCB_INTERVAL = 10  # extract persona every N turns

# ── Persona key definitions (from MOOM Appendix B) ──────────────

_REPLACE_KEYS: set[str] = {
    "name", "age", "birthday", "gender", "ethnicity",
    "zodiac_sign", "chinese_zodiac", "mbti",
    "current_school", "current_location", "hometown",
}

_ADD_KEYS: set[str] = {
    "liked_food", "liked_animal", "liked_activity", "liked_music",
    "liked_movie", "liked_book", "liked_video_game", "liked_artist",
    "disliked_food", "disliked_animal", "disliked_activity",
    "disliked_music", "disliked_movie", "disliked_book",
    "disliked_video_game", "disliked_artist",
    "other_liked", "other_disliked", "skills", "weaknesses",
}

_TRAJECTORY_KEYS: set[str] = {
    "schools_attended", "academic_majors", "past_experiences",
    "key_dates", "background_settings", "conceptual_terms",
    "other_information",
}

_CONTRADICTORY_KEYS: set[str] = {
    "liked_food", "liked_animal", "liked_music", "liked_movie",
    "disliked_food", "disliked_animal", "disliked_music", "disliked_movie",
}

_COMPLEX_KEYS: set[str] = {
    "family_related", "career", "economics", "health",
    "social_status", "lifestyle", "significant_events",
}

_EXTRACTION_PROMPT = """你是TRPG角色档案提取系统。从以下对话片段中提取玩家的角色特征。

需要提取的特征键（按类别）：

替换类（取最新值）：姓名、年龄、生日、性别、民族、星座、生肖、MBTI、当前学校、当前位置、故乡
追加类（可多次追加）：喜欢的食物/动物/活动/音乐/电影/书籍/游戏/艺术家、讨厌的同类、其他喜欢/讨厌、擅长/短板
轨迹类（带时间戳追加）：就读学校、专业、经历、关键日期、背景设定、概念术语、其他信息
矛盾类（需要冲突检测）：喜欢/讨厌的食物/动物/音乐/电影
复杂类（需要LLM判断）：家庭、职业、经济、健康、社会地位、生活习惯、重大事件

输出格式（严格JSON）：
{
  "entries": {
    "name": [{"value": "名字", "turn": 0}],
    "age": [{"value": "18", "turn": 0}],
    "liked_food": [{"value": "寿司", "turn": 3}, {"value": "拉面", "turn": 7}],
    "family_related": [{"value": "父亲是军人", "turn": 5}],
    ...
  }
}

只提取本轮明确出现或推断出的信息，不要编造。

对话内容：
{dialogue}"""
