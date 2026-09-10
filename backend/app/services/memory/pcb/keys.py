"""Persona key categories and the extraction prompt."""

PCB_INTERVAL = 10

_REPLACE_KEYS: set[str] = {
    "name", "age", "birthday", "gender", "ethnicity", "zodiac_sign",
    "chinese_zodiac", "mbti", "current_school", "current_location", "hometown",
}

_ADD_KEYS: set[str] = {
    "liked_food", "liked_animal", "liked_activity", "liked_music", "liked_movie",
    "liked_book", "liked_video_game", "liked_artist", "disliked_food",
    "disliked_animal", "disliked_activity", "disliked_music", "disliked_movie",
    "disliked_book", "disliked_video_game", "disliked_artist", "other_liked",
    "other_disliked", "skills", "weaknesses",
}

_TRAJECTORY_KEYS: set[str] = {
    "schools_attended", "academic_majors", "past_experiences", "key_dates",
    "background_settings", "conceptual_terms", "other_information",
}

_CONTRADICTORY_KEYS: set[str] = {
    "liked_food", "liked_animal", "liked_music", "liked_movie",
    "disliked_food", "disliked_animal", "disliked_music", "disliked_movie",
}

_COMPLEX_KEYS: set[str] = {
    "family_related", "career", "economics", "health", "social_status",
    "lifestyle", "significant_events",
}

_EXTRACTION_PROMPT = """你是 TRPG 角色档案提取系统。请从下面的对话中提取玩家和在场 NPC 的明确角色特征。

输出严格 JSON：
{
  "characters": {
    "player": {"entries": {"name": [{"value": "...", "turn": 0}]}},
    "NPC 名称": {"entries": {"personality": [{"value": "...", "turn": 0}]}}
  }
}

player 可提取姓名、年龄、学校、位置、喜好、厌恶、技能、弱点、经历、家庭、职业、健康和重大事件。
NPC 可提取 personality、relationship_to_player、notable_traits、current_state。
只记录本轮明确出现或可以直接推出的信息，不要编造；没有信息的角色省略。turn 使用对话中的回合号。

对话内容：
{dialogue}"""
