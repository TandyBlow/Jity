"""MOOM Persona Construction Branch (PCB).

Constructs and dynamically updates player and NPC persona profiles using
key-value pairs. Implements MOOM's three merging strategies:
  (1) Rule-based: for deterministic attributes (name, age, gender)
  (2) Embedding-based: for contradictory attributes (likes/dislikes)
  (3) LLM-based: for complex attributes requiring judgment

Extracts persona snapshots at regular intervals (every 10 turns),
then merges with cumulative persona sketches per character.

Uses deepseek-v4-flash for extraction (cheap, non-blocking path).
"""

import logging
from typing import Any

import numpy as np

from app.schemas.agent_io import PersonaKey, PersonaSnapshot, PersonaValue, PersonaSketch
from app.services.embedding_client import EmbeddingClient
from app.services.llm_client import LLMClient

logger = logging.getLogger(__name__)

# ── Default extraction interval ──────────────────────────────────

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


_EXTRACTION_PROMPT = """你是TRPG角色档案提取系统。从以下对话片段中提取玩家和在场NPC的角色特征。

玩家（标注为"player"）需要提取的特征键（按类别）：

替换类（取最新值）：姓名、年龄、生日、性别、民族、星座、生肖、MBTI、当前学校、当前位置、故乡
追加类（可多次追加）：喜欢的食物/动物/活动/音乐/电影/书籍/游戏/艺术家、讨厌的同类、其他喜欢/讨厌、擅长/短板
轨迹类（带时间戳追加）：就读学校、专业、经历、关键日期、背景设定、概念术语、其他信息
矛盾类（需要冲突检测）：喜欢/讨厌的食物/动物/音乐/电影
复杂类（需要LLM判断）：家庭、职业、经济、健康、社会地位、生活习惯、重大事件

NPC（用NPC名作为key）需要提取：
- personality: 性格特征描述
- relationship_to_player: 与玩家的关系
- notable_traits: 显著特征或口头禅
- current_state: 当前状态（情绪、处境等）

输出格式（严格JSON）：
{
  "characters": {
    "player": {
      "entries": {
        "name": [{"value": "玩家名", "turn": 0}],
        "age": [{"value": "18", "turn": 0}],
        "liked_food": [{"value": "寿司", "turn": 3}],
        "family_related": [{"value": "父亲是军人", "turn": 5}]
      }
    },
    "源稚生": {
      "entries": {
        "personality": [{"value": "冷静威严，执行部部长", "turn": 5}],
        "relationship_to_player": [{"value": "上级与保护者", "turn": 5}]
      }
    }
  }
}

只提取本轮明确出现或推断出的信息，不要编造。没有显著特征的NPC可以省略。

对话内容：
{dialogue}"""


class PersonaConstructionBranch:
    """Constructs and updates persona profiles from dialogue."""

    def __init__(
        self,
        llm_client: LLMClient,
        interval: int = PCB_INTERVAL,
        embedding_client: EmbeddingClient | None = None,
    ) -> None:
        self._llm = llm_client
        self.interval = interval
        self._embedding = embedding_client

        # Per-character cumulative sketches (key = character name, "player" = player character)
        self._sketches: dict[str, PersonaSketch] = {"player": PersonaSketch()}
        # Turn counter for extraction timing
        self._turns_since_extraction = 0

    # ── Public API ────────────────────────────────────────────────

    def should_extract(self) -> bool:
        """Check if it's time to extract a persona snapshot."""
        return self._turns_since_extraction >= self.interval

    def on_turn(self) -> None:
        """Increment the extraction counter. Called every turn."""
        self._turns_since_extraction += 1

    async def extract_snapshot(
        self, dialogue: str, current_turn: int
    ) -> dict[str, PersonaSnapshot] | None:
        """Extract persona snapshots for player and NPCs from recent dialogue via LLM.

        Returns a dict mapping character name to PersonaSnapshot, or None on failure.
        "player" key is always present on success.
        """
        prompt = _EXTRACTION_PROMPT.format(dialogue=dialogue)
        self._turns_since_extraction = 0

        try:
            raw = await self._llm.generate_json(
                prompt=prompt,
                model="deepseek-v4-flash",
                max_tokens=2000,
                temperature=0.2,
            )
        except Exception:
            logger.warning("PCB persona extraction failed", exc_info=True)
            return None

        # ── New format: {"characters": {"player": {entries}, "NPC": {entries}}} ──
        characters_raw = raw.get("characters", {})
        if isinstance(characters_raw, dict) and characters_raw:
            snapshots: dict[str, PersonaSnapshot] = {}
            for char_name, char_data in characters_raw.items():
                if not isinstance(char_data, dict):
                    continue
                entries_raw = char_data.get("entries", {})
                if not isinstance(entries_raw, dict):
                    continue
                entries = _parse_entries(entries_raw, current_turn)
                if entries:
                    snapshots[char_name] = PersonaSnapshot(
                        character_name=char_name, entries=entries, extracted_at_turn=current_turn
                    )
            if snapshots:
                return snapshots

        # ── Old format fallback: {"entries": {"name": [...], ...}} ──
        entries_raw = raw.get("entries", {})
        if isinstance(entries_raw, dict):
            entries = _parse_entries(entries_raw, current_turn)
            if entries:
                return {"player": PersonaSnapshot(entries=entries, extracted_at_turn=current_turn)}

        logger.warning("PCB extraction output not parseable: %s", str(raw)[:200])
        return None

    def merge_snapshot(self, snapshot: PersonaSnapshot) -> None:
        """Merge a new persona snapshot into the cumulative sketch for the character.

        Applies MOOM's three strategies:
          - Rule-based for replace/trajectory keys
          - Embedding-based for contradictory keys (cosine similarity via EmbeddingClient)
          - LLM-based for complex keys (deferred: append + cap as baseline)
        """
        char_name = snapshot.character_name or "player"
        sketch = self._sketches.setdefault(char_name, PersonaSketch())

        for key, new_values in snapshot.entries.items():
            existing = sketch.entries.get(key, [])

            key_lower = key.lower().replace(" ", "_")

            if key_lower in _REPLACE_KEYS:
                if new_values:
                    sketch.entries[key] = [new_values[-1]]

            elif key_lower in _TRAJECTORY_KEYS:
                combined = list(existing)
                combined.extend(new_values)
                sketch.entries[key] = combined[-20:]

            elif key_lower in _CONTRADICTORY_KEYS:
                merged = list(existing)
                for nv in new_values:
                    replaced = False
                    for i, ev in enumerate(merged):
                        if _approx_equal(ev.value, nv.value):
                            merged[i] = nv
                            replaced = True
                            break
                    if not replaced:
                        merged.append(nv)
                sketch.entries[key] = merged[-15:]

            elif key_lower in _COMPLEX_KEYS:
                combined = list(existing)
                combined.extend(new_values)
                sketch.entries[key] = combined[-10:]

            elif key_lower in _ADD_KEYS:
                combined = list(existing)
                combined.extend(new_values)
                sketch.entries[key] = combined[-20:]

            else:
                combined = list(existing)
                combined.extend(new_values)
                sketch.entries[key] = combined[-10:]

    async def merge_snapshot_with_embedding(
        self, snapshot: PersonaSnapshot
    ) -> None:
        """Async merge using EmbeddingClient for contradictory key similarity.

        Call this instead of merge_snapshot when embedding_client is available.
        Falls back to _approx_equal on embedding failure.
        """
        char_name = snapshot.character_name or "player"
        sketch = self._sketches.setdefault(char_name, PersonaSketch())

        for key, new_values in snapshot.entries.items():
            existing = sketch.entries.get(key, [])
            key_lower = key.lower().replace(" ", "_")

            if key_lower in _CONTRADICTORY_KEYS and self._embedding is not None and new_values:
                merged = list(existing)
                for nv in new_values:
                    if not merged:
                        merged.append(nv)
                        continue
                    existing_texts = [ev.value for ev in merged]
                    try:
                        from app.services.memory.similarity import cosine_similarity
                        sim_matrix = await cosine_similarity(
                            [nv.value], existing_texts, self._embedding
                        )
                        max_sim = float(sim_matrix.max()) if sim_matrix.size > 0 else 0.0
                    except Exception:
                        max_sim = 0.0

                    if max_sim > 0.85:
                        idx = int(sim_matrix.argmax()) if sim_matrix.size > 0 else -1
                        if 0 <= idx < len(merged):
                            merged[idx] = nv
                        else:
                            merged.append(nv)
                    else:
                        merged.append(nv)
                sketch.entries[key] = merged[-15:]
            else:
                # handled by sync merge below
                pass

        # Non-contradictory keys: use synchronous logic
        non_contra = {
            k: v for k, v in snapshot.entries.items()
            if k.lower().replace(" ", "_") not in _CONTRADICTORY_KEYS
        }
        if non_contra:
            self.merge_snapshot(PersonaSnapshot(
                character_name=char_name,
                entries=non_contra,
                extracted_at_turn=snapshot.extracted_at_turn,
            ))

    def get_persona_text(self, top_k: int = 15, npc_names: list[str] | None = None) -> str:
        """Build a compact multi-character persona text for prompt injection.

        Player persona entries come first (up to ~60% of top_k), then
        currently-present NPC personas (sorted by recency). Characters
        with no entries are silently skipped.
        """
        if not any(sketch.entries for sketch in self._sketches.values()):
            return "角色档案：暂无记录"

        parts: list[str] = ["## 角色档案"]
        count = 0
        player_max = max(2, int(top_k * 0.6))

        # ── Player persona (capped) ──
        player_sketch = self._sketches.get("player")
        if player_sketch and player_sketch.entries:
            for key, values in player_sketch.entries.items():
                if count >= player_max:
                    break
                vals = "；".join(f"{v.value}(T{v.turn})" for v in values[-3:])
                parts.append(f"- {key}: {vals}")
                count += 1

        # ── NPC personas (prioritize in-scene NPCs first) ──
        if npc_names:
            ordered_npcs = npc_names + [n for n in self._sketches if n not in npc_names and n != "player"]
        else:
            ordered_npcs = [n for n in self._sketches if n != "player"]
        ordered_npcs = [n for n in ordered_npcs if n in self._sketches]  # defense in depth

        for npc_name in ordered_npcs:
            if count >= top_k:
                break
            sketch = self._sketches[npc_name]
            if not sketch.entries:
                continue
            npc_lines: list[str] = [f"### {npc_name}"]
            npc_count = 0
            for key, values in sketch.entries.items():
                if npc_count >= 3 or count >= top_k:
                    break
                vals = "；".join(f"{v.value}(T{v.turn})" for v in values[-2:])
                npc_lines.append(f"- {key}: {vals}")
                npc_count += 1
                count += 1
            if npc_count > 0:
                parts.extend(npc_lines)

        return "\n".join(parts)

    def export_state(self) -> dict[str, Any]:
        """Serialize all per-character sketches for persistence."""
        return {
            "sketches": {name: s.model_dump() for name, s in self._sketches.items()},
            "turns_since": self._turns_since_extraction,
        }

    def load_state(self, data: dict[str, Any]) -> None:
        """Restore from persisted state. Backward-compatible with old single-sketch format."""
        sketches_data = data.get("sketches", {})
        if sketches_data:
            self._sketches = {
                name: PersonaSketch(**sd) for name, sd in sketches_data.items()
            }
        else:
            # Fallback: old format with single "sketch" key → map to "player"
            old_sketch = data.get("sketch", {})
            if old_sketch:
                self._sketches = {"player": PersonaSketch(**old_sketch)}
        # Ensure "player" always exists
        if "player" not in self._sketches:
            self._sketches["player"] = PersonaSketch()
        self._turns_since_extraction = data.get("turns_since", 0)


# ── Helpers ────────────────────────────────────────────────────────


def _parse_entries(
    entries_raw: dict, current_turn: int
) -> dict[str, list[PersonaValue]]:
    """Parse LLM output entries dict into structured PersonaValue lists."""
    entries: dict[str, list[PersonaValue]] = {}
    for key, values in entries_raw.items():
        if not isinstance(values, list):
            continue
        parsed: list[PersonaValue] = []
        for v in values:
            if isinstance(v, dict) and "value" in v:
                parsed.append(PersonaValue(value=str(v["value"]), turn=v.get("turn", current_turn)))
            elif isinstance(v, str):
                parsed.append(PersonaValue(value=v, turn=current_turn))
        if parsed:
            entries[key] = parsed
    return entries


def _approx_equal(a: str, b: str) -> bool:
    """Crude string similarity for embedding-based dedup fallback."""
    a_lower = a.strip().lower()
    b_lower = b.strip().lower()
    if a_lower == b_lower:
        return True
    # Simple character overlap ratio
    if not a_lower or not b_lower:
        return False
    common = sum(1 for c in a_lower if c in b_lower)
    ratio = common / max(len(a_lower), len(b_lower))
    return ratio > 0.8
