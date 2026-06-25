"""MOOM Narrative Summarization Branch (NSB).

Implements hierarchical multi-scale summarization from MOOM (Chen et al., 2025):
  θ₁ = 6 : every 6 turns → first-level summary I⁽¹⁾
  θ₂ = 5 : every 5 first-level summaries → second-level summary S⁽²⁾
  θ₃ = 5 : every 5 second-level summaries → third-level summary S⁽³⁾

Each summary captures plot conflicts at its respective temporal scale:
  Level 1: concrete events and micro-plot developments
  Level 2: intermediate narrative arcs and conflict resolution
  Level 3: high-level story themes and macro-plot progression

Summaries are stored with tags, entities, causal links, and state changes
for three-dimensional retrieval (semantic + temporal + entity).

Uses deepseek-v4-flash for summarization (cheap, non-blocking path).
"""

import json
import logging
from typing import Any

from app.schemas.agent_io import EpisodeSummary
from app.services.llm_client import LLMClient

logger = logging.getLogger(__name__)

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


class NarrativeSummarizationBranch:
    """Hierarchical summarization for long-term narrative memory."""

    def __init__(
        self,
        llm_client: LLMClient,
        theta1: int = THETA_1,
        theta2: int = THETA_2,
        theta3: int = THETA_3,
    ) -> None:
        self._llm = llm_client
        self.theta1 = theta1
        self.theta2 = theta2
        self.theta3 = theta3

        # Turn-level buffer (raw dialogue text)
        self._turn_buffer: list[str] = []
        # Hierarchical summary buffers
        self._level1: list[EpisodeSummary] = []
        self._level2: list[EpisodeSummary] = []
        self._level3: list[EpisodeSummary] = []

        # Monotonic counters
        self._episode_counter: int = 0

    # ── Public API ────────────────────────────────────────────────

    def add_turn(self, player_action: str, narration: str, turn: int) -> None:
        """Buffer one turn's dialogue. Does NOT trigger LLM call."""
        self._turn_buffer.append(f"[T{turn} 玩家]: {player_action}\n[T{turn} 主持人]: {narration}")

    def should_summarize_level1(self) -> bool:
        return len(self._turn_buffer) >= self.theta1

    def should_summarize_level2(self) -> bool:
        return len(self._level1) >= self.theta2

    def should_summarize_level3(self) -> bool:
        return len(self._level2) >= self.theta3

    async def summarize_level1(self, turn_start: int, turn_end: int) -> EpisodeSummary | None:
        """Produce a first-level summary from buffered turns. Consumes the buffer only on success."""
        if not self._turn_buffer:
            return None

        dialogue = "\n\n".join(self._turn_buffer)
        prompt = _LEVEL1_PROMPT.format(theta1=self.theta1, dialogue=dialogue)
        try:
            result = await self._generate_summary(prompt, level=1, turn_start=turn_start, turn_end=turn_end)
        except Exception:
            logger.warning("NSB level-1 LLM call failed, buffer retained for retry", exc_info=True)
            return None
        if result is None:
            return None
        self._turn_buffer.clear()
        return result

    async def summarize_level2(self, turn_start: int, turn_end: int) -> EpisodeSummary | None:
        """Produce a second-level summary from accumulated level-1 summaries. Consumes only on success."""
        if not self._level1:
            return None

        batch = self._level1[:self.theta2]

        summaries_text = "\n\n---\n\n".join(
            f"[摘要{i+1}]: {s.summary}" for i, s in enumerate(batch)
        )
        schema = '{"summary": "...", "tags": [...], "entities_involved": [...], "causal_links": [...], "state_changes": {...}, "importance": 0.7}'
        prompt = _LEVEL2_PROMPT.format(theta2=self.theta2, schema=schema, summaries=summaries_text)
        try:
            result = await self._generate_summary(prompt, level=2, turn_start=turn_start, turn_end=turn_end)
        except Exception:
            logger.warning("NSB level-2 LLM call failed, buffer retained for retry", exc_info=True)
            return None
        if result is None:
            return None
        self._level1 = self._level1[self.theta2:]
        return result

    async def summarize_level3(self, turn_start: int, turn_end: int) -> EpisodeSummary | None:
        """Produce a third-level summary from accumulated level-2 summaries. Consumes only on success."""
        if not self._level2:
            return None

        batch = self._level2[:self.theta3]

        summaries_text = "\n\n---\n\n".join(
            f"[摘要{i+1}]: {s.summary}" for i, s in enumerate(batch)
        )
        schema = '{"summary": "...", "tags": [...], "entities_involved": [...], "causal_links": [...], "state_changes": {...}, "importance": 0.7}'
        prompt = _LEVEL3_PROMPT.format(theta3=self.theta3, schema=schema, summaries=summaries_text)
        try:
            result = await self._generate_summary(prompt, level=3, turn_start=turn_start, turn_end=turn_end)
        except Exception:
            logger.warning("NSB level-3 LLM call failed, buffer retained for retry", exc_info=True)
            return None
        if result is None:
            return None
        self._level2 = self._level2[self.theta3:]
        return result

    def accept_level1(self, summary: EpisodeSummary) -> None:
        """Store a level-1 summary (called after successful LLM generation)."""
        self._level1.append(summary)

    def accept_level2(self, summary: EpisodeSummary) -> None:
        """Store a level-2 summary."""
        self._level2.append(summary)

    def accept_level3(self, summary: EpisodeSummary) -> None:
        """Store a level-3 summary."""
        self._level3.append(summary)

    def get_retrieval_context(self, query: str, top_k: int = 5) -> list[EpisodeSummary]:
        """Return the top-k most relevant summaries across all levels for context injection.

        Simple keyword + recency heuristic. Semantic retrieval via FAISS
        is handled externally by MemoryController combining NSB with the
        existing RAGRetriever.
        """
        all_summaries = self._level1 + self._level2 + self._level3
        # Score by recency (most recent first) combined with tag/entity overlap
        scored: list[tuple[EpisodeSummary, float]] = []
        query_lower = query.lower()
        for s in all_summaries:
            score = 0.0
            # Tag overlap
            for tag in s.tags:
                if tag.lower() in query_lower:
                    score += 2.0
            # Entity overlap
            for ent in s.entities_involved:
                if ent.lower() in query_lower:
                    score += 3.0
            # Recency bonus (more recent = higher score)
            score += s.importance
            scored.append((s, score))

        scored.sort(key=lambda x: x[1], reverse=True)
        return [s for s, _ in scored[:top_k]]

    def export_state(self) -> dict[str, Any]:
        """Serialize internal state for persistence."""
        return {
            "turn_buffer": self._turn_buffer,
            "level1": [s.model_dump() for s in self._level1],
            "level2": [s.model_dump() for s in self._level2],
            "level3": [s.model_dump() for s in self._level3],
            "episode_counter": self._episode_counter,
        }

    def load_state(self, data: dict[str, Any]) -> None:
        """Restore from persisted state."""
        self._turn_buffer = data.get("turn_buffer", [])
        self._level1 = [EpisodeSummary(**d) for d in data.get("level1", [])]
        self._level2 = [EpisodeSummary(**d) for d in data.get("level2", [])]
        self._level3 = [EpisodeSummary(**d) for d in data.get("level3", [])]
        self._episode_counter = data.get("episode_counter", 0)

    # ── Private ───────────────────────────────────────────────────

    async def _generate_summary(
        self, prompt: str, level: int, turn_start: int, turn_end: int
    ) -> EpisodeSummary | None:
        """Call LLM and parse into EpisodeSummary. Returns None on failure."""
        self._episode_counter += 1
        episode_id = f"ep_L{level}_{self._episode_counter}"

        try:
            raw = await self._llm.generate_json(
                prompt=prompt,
                model="deepseek-v4-flash",
                max_tokens=1000,
                temperature=0.3,
            )
        except Exception:
            logger.warning("NSB level-%d summarization LLM call failed", level, exc_info=True)
            return None

        return EpisodeSummary(
            episode_id=episode_id,
            turn_start=turn_start,
            turn_end=turn_end,
            summary=_safe_str(raw, "summary", ""),
            tags=_safe_list(raw, "tags"),
            entities_involved=_safe_list(raw, "entities_involved"),
            causal_links=_safe_list(raw, "causal_links"),
            state_changes=_safe_dict(raw, "state_changes"),
            importance=_safe_float(raw, "importance", 0.5),
            level=level,
        )


# ── Static parsing helpers ────────────────────────────────────────


def _safe_str(data: dict, key: str, default: str = "") -> str:
    v = data.get(key, default)
    return str(v) if v is not None else default


def _safe_list(data: dict, key: str) -> list[str]:
    v = data.get(key, [])
    if isinstance(v, list):
        return [str(x) for x in v]
    return []


def _safe_dict(data: dict, key: str) -> dict[str, str]:
    v = data.get(key, {})
    if isinstance(v, dict):
        return {str(k): str(val) for k, val in v.items()}
    return {}


def _safe_float(data: dict, key: str, default: float = 0.5) -> float:
    try:
        return float(data.get(key, default))
    except (TypeError, ValueError):
        return default
