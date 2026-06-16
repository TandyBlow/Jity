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
        player_status = state.get("player_status", {})
        return f"""你是桌面 RPG 的中文 GM 辅助系统，负责根据玩家行动生成合理、连贯、可交互的下一段剧情。

当前状态：
- 当前地点：{state.get("current_location", "未知")}
- 血统稳定：{state.get("sanity", 80)}/100
- 体力：{state.get("health", 100)}/100
- 回合：{state.get("turn", 0)}
- 玩家状态：{self._compact_player_status(player_status)}

Context Memory / 长期记忆：
- 关键物品：{self._compact_list(state.get("items", []), kind="item")}
- NPC 记忆：{self._compact_list(state.get("npcs", []), kind="npc")}
- 任务记忆：{self._compact_list(state.get("quests", []), kind="quest")}
- 长期事实：{self._compact_list(state.get("world_facts", []), kind="world_fact")}

最近事件：
{self._bullet_list(state.get("recent_events", [])[-6:])}

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
- dialogue.text 和其他字符串字段不要包含未转义的英文双引号；需要引用原话时使用中文引号、英文单引号，或改写为间接叙述。
- 同时维护 memory_updates：只写本回合新增或变化的记忆，不要整段复述已有记忆。
- memory_updates.key_event 必须是一句不超过 80 字的关键事件摘要，用于最近事件，不要复制 narration。
- 系统会负责回合数、血统稳定、体力裁剪、每回合自动恢复 1 点血统稳定和记忆合并；你只提供剧情上能解释的记忆变化，不要把自动恢复写进 sanity_delta。

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
  "quests_updated": [{{"name": "任务名", "status": "active", "description": "任务说明"}}],
  "memory_updates": {{
    "current_location": "只在地点变化或需要确认当前位置时填写",
    "items_upserted": [{{"name": "物品名", "status": "owned|lost|observed|used", "description": "稳定说明", "location": "所在位置", "notes": "当前备注"}}],
    "items_removed": [{{"name": "物品名", "status": "lost", "description": "移除原因"}}],
    "npcs_upserted": [{{"name": "NPC名", "status": "present|following|away|unknown", "relationship": "与玩家关系或态度", "current_location": "当前位置", "description": "稳定身份", "notes": "本回合变化"}}],
    "quests_upserted": [{{"name": "任务名", "status": "active|completed|failed|paused", "description": "稳定说明", "objective": "当前目标", "notes": "本回合变化"}}],
    "world_facts_upserted": [{{"name": "事实名", "status": "known|suspected|resolved", "description": "长期事实", "source": "剧情来源", "notes": "备注"}}],
    "player_status_patch": {{"condition": "当前状态", "danger_level": "low|medium|high|critical", "current_goal": "当前目标", "notes": "短备注"}},
    "key_event": "本回合关键事件摘要，不超过80字"
  }}
}}"""

    @staticmethod
    def _compact_list(items: list[dict[str, Any]], *, kind: str) -> str:
        if not items:
            return "无"
        return "；".join(PromptBuilder._compact_item(item, kind=kind) for item in items[:8])

    @staticmethod
    def _compact_item(item: dict[str, Any], *, kind: str) -> str:
        name = item.get("name", "未命名")
        status = item.get("status") or item.get("disposition") or "已记录"
        if kind == "npc":
            detail = item.get("relationship") or item.get("description") or item.get("notes") or item.get("current_location")
        elif kind == "quest":
            detail = item.get("objective") or item.get("description") or item.get("notes")
        elif kind == "world_fact":
            detail = item.get("description") or item.get("notes")
        else:
            detail = item.get("description") or item.get("notes") or item.get("location")
        return f"{name}({status}{f'：{detail}' if detail else ''})"

    @staticmethod
    def _compact_player_status(player_status: dict[str, Any]) -> str:
        if not player_status:
            return "无"
        parts = [
            player_status.get("condition", ""),
            f"危险等级 {player_status.get('danger_level')}" if player_status.get("danger_level") else "",
            f"目标：{player_status.get('current_goal')}" if player_status.get("current_goal") else "",
            player_status.get("notes", ""),
        ]
        return "；".join(part for part in parts if part) or "无"

    @staticmethod
    def _bullet_list(items: list[str]) -> str:
        if not items:
            return "- 无"
        return "\n".join(f"- {item}" for item in items)
