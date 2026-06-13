from __future__ import annotations

from typing import Any


class PromptBuilder:
    def build(
        self,
        user_action: str,
        state: dict[str, Any],
        retrieved_chunks: list[dict[str, Any]],
        style: str = "",
        constraints: str = "",
    ) -> str:
        knowledge = "\n\n".join(
            f"[{chunk['source_type']}] {chunk['title']}\n{chunk['content'][:1200]}"
            for chunk in retrieved_chunks
        )
        return f"""你是桌面 RPG 的中文 GM 辅助系统，负责根据玩家行动生成合理、连贯、可交互的下一段剧情。

当前游戏状态：
- 当前地点：{state.get("current_location", "未知")}
- 血统稳定：{state.get("sanity", 80)}/100
- 体力：{state.get("health", 100)}/100
- 回合：{state.get("turn", 0)}
- 物品：{self._compact_list(state.get("items", []))}
- NPC：{self._compact_list(state.get("npcs", []))}
- 任务：{self._compact_list(state.get("quests", []))}
- 最近事件：{"；".join(state.get("recent_events", [])[-6:]) or "无"}

RAG 检索到的相关知识：
{knowledge or "暂无额外知识。"}

用户输入：
{user_action}

风格要求：
{style or "延续当前故事风格，保持黑色幽默、校园悬疑和危险感。"}

特殊限制：
{constraints or "不要违反已有世界观，不要改变 NPC 核心性格，不要让玩家行动失去意义。"}

生成规则：
- 必须回应玩家刚才的行动，描述直接后果、NPC 反应和新的可行动局面。
- 不要复述原文长段落，不要突然跳到无关任务。
- 普通失败也应推动故事继续，而不是直接结束。
- 状态变化要能从剧情中解释。
- scene_prompt 必须是英文，少于 30 个词，用于生成背景图。
- items_gained、items_lost、npcs_encountered、quests_updated 必须是对象数组，不要返回字符串数组。

严格返回纯 JSON，不要包含 Markdown、解释或额外文本：
{{
  "narration": "第二人称沉浸叙事，2-4句",
  "dialogue": [{{"speaker": "角色名", "text": "对话内容"}}],
  "scene_prompt": "English scene description, max 30 words",
  "sanity_delta": 0,
  "health_delta": 0,
  "options": ["选项1", "选项2", "选项3"],
  "game_over": false,
  "game_over_reason": "",
  "current_location": "",
  "items_gained": [{{"name": "物品名", "description": "物品说明"}}],
  "items_lost": [{{"name": "物品名", "description": "失去原因"}}],
  "npcs_encountered": [{{"name": "角色名", "disposition": "态度", "notes": "当前记录"}}],
  "quests_updated": [{{"name": "任务名", "status": "状态", "description": "任务说明"}}]
}}"""

    @staticmethod
    def _compact_list(items: list[dict[str, Any]]) -> str:
        if not items:
            return "无"
        return "；".join(
            f"{item.get('name', '未命名')}({item.get('status') or item.get('disposition') or item.get('description') or '已记录'})"
            for item in items[:8]
        )
