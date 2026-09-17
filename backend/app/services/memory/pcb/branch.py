"""Persona Construction Branch (PCB).

The branch keeps one compact persona sketch per character.  The player
sketch uses the historical ``player`` key; NPC sketches use the character
name returned by the extractor.
"""

import logging
from typing import Any

from app.schemas.agent_io import PersonaSketch, PersonaSnapshot, PersonaValue
from app.services.embedding_client import EmbeddingClient
from app.services.llm_client import LLMClient

from app.services.memory.pcb.keys import PCB_INTERVAL, _EXTRACTION_PROMPT
from app.services.memory.pcb.merge import PersonaMergeMixin

logger = logging.getLogger(__name__)


class PersonaConstructionBranch(PersonaMergeMixin):
    """Extract and merge persona facts for the player and NPCs."""

    def __init__(
        self,
        llm_client: LLMClient,
        interval: int = PCB_INTERVAL,
        embedding_client: EmbeddingClient | None = None,
    ) -> None:
        self._llm = llm_client
        self.interval = interval
        self._embedding = embedding_client
        self._sketches: dict[str, PersonaSketch] = {"player": PersonaSketch()}
        self._turns_since_extraction = 0

    @property
    def _sketch(self) -> PersonaSketch:
        """Backward-compatible view of the player sketch."""
        return self._sketches.setdefault("player", PersonaSketch())

    def should_extract(self) -> bool:
        return self._turns_since_extraction >= self.interval

    def on_turn(self) -> None:
        self._turns_since_extraction += 1

    async def extract_snapshot(
        self, dialogue: str, current_turn: int
    ) -> dict[str, PersonaSnapshot] | None:
        """Extract snapshots from the new multi-character format or the old format."""
        prompt = _EXTRACTION_PROMPT.format(dialogue=dialogue)
        self._turns_since_extraction = 0
        try:
            raw = await self._llm.generate_json(
                prompt=prompt,
                max_tokens=2000,
                temperature=0.2,
                purpose="memory_pcb_extraction",
                context={"turn": current_turn},
            )
        except Exception:
            logger.warning("PCB persona extraction failed", exc_info=True)
            return None

        characters_raw = raw.get("characters", {})
        if isinstance(characters_raw, dict) and characters_raw:
            snapshots: dict[str, PersonaSnapshot] = {}
            for character_name, character_data in characters_raw.items():
                if not isinstance(character_data, dict):
                    continue
                entries = self._parse_entries(character_data.get("entries", {}), current_turn)
                if entries:
                    name = str(character_name)
                    snapshots[name] = PersonaSnapshot(
                        character_name=name,
                        entries=entries,
                        extracted_at_turn=current_turn,
                    )
            if snapshots:
                return snapshots

        entries = self._parse_entries(raw.get("entries", {}), current_turn)
        if entries:
            return {
                "player": PersonaSnapshot(
                    character_name="player",
                    entries=entries,
                    extracted_at_turn=current_turn,
                )
            }
        logger.warning("PCB extraction output not parseable: %s", str(raw)[:200])
        return None

    @staticmethod
    def _parse_entries(raw: Any, current_turn: int) -> dict[str, list[PersonaValue]]:
        if not isinstance(raw, dict):
            return {}
        entries: dict[str, list[PersonaValue]] = {}
        for key, values in raw.items():
            if not isinstance(values, list):
                continue
            parsed: list[PersonaValue] = []
            for value in values:
                if isinstance(value, dict) and "value" in value:
                    parsed.append(
                        PersonaValue(
                            value=str(value["value"]),
                            turn=int(value.get("turn", current_turn)),
                        )
                    )
                elif isinstance(value, str):
                    parsed.append(PersonaValue(value=value, turn=current_turn))
            if parsed:
                entries[str(key)] = parsed
        return entries

    def get_persona_text(self, top_k: int = 15, npc_names: list[str] | None = None) -> str:
        """Render player entries first, then up to three entries per relevant NPC."""
        if not any(sketch.entries for sketch in self._sketches.values()):
            return "角色档案：暂无记录"

        parts = ["## 角色档案"]
        count = 0
        player_limit = max(2, int(top_k * 0.6))
        player = self._sketches.get("player")
        if player:
            for key, values in player.entries.items():
                if count >= player_limit:
                    break
                rendered = "；".join(f"{value.value}(T{value.turn})" for value in values[-3:])
                parts.append(f"- {key}: {rendered}")
                count += 1

        ordered_npcs = list(npc_names or [])
        ordered_npcs.extend(
            name for name in self._sketches
            if name != "player" and name not in ordered_npcs
        )
        for name in ordered_npcs:
            if count >= top_k:
                break
            sketch = self._sketches.get(name)
            if not sketch or not sketch.entries:
                continue
            npc_lines = [f"### {name}"]
            npc_count = 0
            for key, values in sketch.entries.items():
                if npc_count >= 3 or count >= top_k:
                    break
                rendered = "；".join(f"{value.value}(T{value.turn})" for value in values[-2:])
                npc_lines.append(f"- {key}: {rendered}")
                npc_count += 1
                count += 1
            if npc_count:
                parts.extend(npc_lines)
        return "\n".join(parts)

    def export_state(self) -> dict[str, Any]:
        return {
            "sketches": {name: sketch.model_dump() for name, sketch in self._sketches.items()},
            "turns_since": self._turns_since_extraction,
        }

    def load_state(self, data: dict[str, Any]) -> None:
        sketches = data.get("sketches", {})
        if isinstance(sketches, dict) and sketches:
            self._sketches = {
                str(name): PersonaSketch(**sketch)
                for name, sketch in sketches.items()
                if isinstance(sketch, dict)
            }
        else:
            old_sketch = data.get("sketch", {})
            self._sketches = {"player": PersonaSketch(**old_sketch)} if old_sketch else {}
        self._sketches.setdefault("player", PersonaSketch())
        self._turns_since_extraction = int(data.get("turns_since", 0))
