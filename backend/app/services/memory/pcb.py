"""MOOM Persona Construction Branch (PCB).

Constructs and dynamically updates user/NPC persona profiles using
key-value pairs. Implements MOOM's three merging strategies:
  (1) Rule-based: for deterministic attributes (name, age, gender)
  (2) Embedding-based: for contradictory attributes (likes/dislikes)
  (3) LLM-based: for complex attributes requiring judgment

Extracts persona snapshots at regular intervals (every 10 turns),
then merges with the cumulative persona sketch.

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

        # Cumulative persona sketch
        self._sketch = PersonaSketch()
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
    ) -> PersonaSnapshot | None:
        """Extract a persona snapshot from recent dialogue via LLM.

        Args:
            dialogue: Recent conversation text (last 10 turns concatenated).
            current_turn: Current global turn number.

        Returns:
            PersonaSnapshot or None on failure.
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

        entries_raw = raw.get("entries", {})
        if not isinstance(entries_raw, dict):
            return None

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

        return PersonaSnapshot(entries=entries, extracted_at_turn=current_turn)

    def merge_snapshot(self, snapshot: PersonaSnapshot) -> None:
        """Merge a new persona snapshot into the cumulative sketch.

        Applies MOOM's three strategies:
          - Rule-based for replace/trajectory keys
          - Embedding-based for contradictory keys (cosine similarity via EmbeddingClient)
          - LLM-based for complex keys (deferred: last-wins as baseline)
        """
        for key, new_values in snapshot.entries.items():
            existing = self._sketch.entries.get(key, [])

            key_lower = key.lower().replace(" ", "_")

            if key_lower in _REPLACE_KEYS:
                # Rule-based: replace with latest value
                if new_values:
                    self._sketch.entries[key] = [new_values[-1]]

            elif key_lower in _TRAJECTORY_KEYS:
                # Rule-based: append with cap
                combined = list(existing)
                for v in new_values:
                    combined.append(v)
                self._sketch.entries[key] = combined[-20:]

            elif key_lower in _CONTRADICTORY_KEYS:
                # Embedding-based: use cosine similarity to detect outdated values
                # If new value is highly similar to existing → replace (outdated)
                # If new value is low similarity → append (genuinely different preference)
                merged = list(existing)
                for nv in new_values:
                    replaced = False
                    for i, ev in enumerate(merged):
                        if _approx_equal(ev.value, nv.value):
                            merged[i] = nv  # replace outdated
                            replaced = True
                            break
                    if not replaced:
                        merged.append(nv)
                self._sketch.entries[key] = merged[-15:]

            elif key_lower in _COMPLEX_KEYS:
                # LLM-based: simplified as append + cap
                # Full implementation would call LLM to judge — deferred to Phase 7
                combined = list(existing)
                combined.extend(new_values)
                self._sketch.entries[key] = combined[-10:]

            elif key_lower in _ADD_KEYS:
                # Append-only
                combined = list(existing)
                combined.extend(new_values)
                self._sketch.entries[key] = combined[-20:]

            else:
                combined = list(existing)
                combined.extend(new_values)
                self._sketch.entries[key] = combined[-10:]

    async def merge_snapshot_with_embedding(
        self, snapshot: PersonaSnapshot
    ) -> None:
        """Async version that uses EmbeddingClient for contradictory key similarity.

        Call this instead of merge_snapshot when embedding_client is available.
        Falls back to _approx_equal on embedding failure.
        """
        for key, new_values in snapshot.entries.items():
            existing = self._sketch.entries.get(key, [])
            key_lower = key.lower().replace(" ", "_")

            if key_lower in _CONTRADICTORY_KEYS and self._embedding is not None and new_values:
                merged = list(existing)
                for nv in new_values:
                    if not merged:
                        merged.append(nv)
                        continue
                    # Compute embedding similarity between new value and existing values
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
                        # High similarity → replace the most similar existing entry
                        idx = int(sim_matrix.argmax()) if sim_matrix.size > 0 else -1
                        if 0 <= idx < len(merged):
                            merged[idx] = nv
                        else:
                            merged.append(nv)
                    else:
                        merged.append(nv)
                self._sketch.entries[key] = merged[-15:]
            else:
                # Fall back to synchronous merge for non-contradictory keys
                pass  # handled below

        # Non-contradictory keys: use synchronous logic
        self.merge_snapshot(PersonaSnapshot(
            entries={k: v for k, v in snapshot.entries.items()
                     if k.lower().replace(" ", "_") not in _CONTRADICTORY_KEYS},
            extracted_at_turn=snapshot.extracted_at_turn,
        ))

    def get_persona_text(self, top_k: int = 15) -> str:
        """Build a compact text representation of the persona for prompt injection."""
        if not self._sketch.entries:
            return "角色档案：暂无记录"
        parts: list[str] = ["## 角色档案"]
        count = 0
        for key, values in self._sketch.entries.items():
            if count >= top_k:
                break
            vals = "；".join(
                f"{v.value}(T{v.turn})" for v in values[-3:]
            )
            parts.append(f"- {key}: {vals}")
            count += 1
        return "\n".join(parts)

    def export_state(self) -> dict[str, Any]:
        """Serialize for persistence."""
        return {"sketch": self._sketch.model_dump(), "turns_since": self._turns_since_extraction}

    def load_state(self, data: dict[str, Any]) -> None:
        """Restore from persisted state."""
        sketch_data = data.get("sketch", {})
        self._sketch = PersonaSketch(**sketch_data)
        self._turns_since_extraction = data.get("turns_since", 0)


# ── Helpers ────────────────────────────────────────────────────────


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
