"""MOOM Persona Construction Branch (PCB) — main branch class."""

import logging
from typing import Any

from app.schemas.agent_io import PersonaSketch, PersonaSnapshot, PersonaValue
from app.services.embedding_client import EmbeddingClient
from app.services.llm_client import LLMClient

from app.services.memory.pcb.keys import PCB_INTERVAL, _EXTRACTION_PROMPT
from app.services.memory.pcb.merge import PersonaMergeMixin

logger = logging.getLogger(__name__)


class PersonaConstructionBranch(PersonaMergeMixin):
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

        return self._parse_entries(raw, current_turn)

    def _parse_entries(self, raw: dict, current_turn: int) -> PersonaSnapshot | None:
        """Parse raw LLM JSON into a PersonaSnapshot."""
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

    def get_persona_text(self, top_k: int = 15) -> str:
        """Build a compact text representation of the persona for prompt injection."""
        if not self._sketch.entries:
            return ""
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
