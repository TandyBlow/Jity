"""Persona sketch merge strategies."""

from app.schemas.agent_io import PersonaSketch, PersonaSnapshot
from app.services.memory.pcb.keys import (
    _ADD_KEYS,
    _COMPLEX_KEYS,
    _CONTRADICTORY_KEYS,
    _REPLACE_KEYS,
    _TRAJECTORY_KEYS,
)


class PersonaMergeMixin:
    def _sketch_for(self, snapshot: PersonaSnapshot) -> PersonaSketch:
        name = snapshot.character_name or "player"
        sketch = self._sketches.setdefault(name, PersonaSketch())
        return sketch

    def merge_snapshot(self, snapshot: PersonaSnapshot) -> None:
        sketch = self._sketch_for(snapshot)
        for key, new_values in snapshot.entries.items():
            existing = sketch.entries.get(key, [])
            normalized_key = key.lower().replace(" ", "_")
            if normalized_key in _REPLACE_KEYS:
                if new_values:
                    sketch.entries[key] = [new_values[-1]]
            elif normalized_key in _TRAJECTORY_KEYS:
                sketch.entries[key] = (existing + new_values)[-20:]
            elif normalized_key in _CONTRADICTORY_KEYS:
                merged = list(existing)
                for new_value in new_values:
                    for index, old_value in enumerate(merged):
                        if _approx_equal(old_value.value, new_value.value):
                            merged[index] = new_value
                            break
                    else:
                        merged.append(new_value)
                sketch.entries[key] = merged[-15:]
            elif normalized_key in _COMPLEX_KEYS:
                sketch.entries[key] = (existing + new_values)[-10:]
            elif normalized_key in _ADD_KEYS:
                sketch.entries[key] = (existing + new_values)[-20:]
            else:
                sketch.entries[key] = (existing + new_values)[-10:]

    async def merge_snapshot_with_embedding(self, snapshot: PersonaSnapshot) -> None:
        sketch = self._sketch_for(snapshot)
        for key, new_values in snapshot.entries.items():
            normalized_key = key.lower().replace(" ", "_")
            if normalized_key not in _CONTRADICTORY_KEYS or self._embedding is None or not new_values:
                continue

            merged = list(sketch.entries.get(key, []))
            for new_value in new_values:
                if not merged:
                    merged.append(new_value)
                    continue
                existing_texts = [old_value.value for old_value in merged]
                try:
                    from app.services.memory.similarity import cosine_similarity

                    similarities = await cosine_similarity(
                        [new_value.value], existing_texts, self._embedding
                    )
                    maximum = float(similarities.max()) if similarities.size else 0.0
                except Exception:
                    maximum = 0.0
                    similarities = None
                if maximum > 0.85 and similarities is not None:
                    index = int(similarities.argmax())
                    if 0 <= index < len(merged):
                        merged[index] = new_value
                        continue
                merged.append(new_value)
            sketch.entries[key] = merged[-15:]

        non_contradictory = {
            key: values
            for key, values in snapshot.entries.items()
            if key.lower().replace(" ", "_") not in _CONTRADICTORY_KEYS
        }
        if non_contradictory:
            self.merge_snapshot(
                PersonaSnapshot(
                    character_name=snapshot.character_name,
                    entries=non_contradictory,
                    extracted_at_turn=snapshot.extracted_at_turn,
                )
            )


def _approx_equal(a: str, b: str) -> bool:
    a_lower = a.strip().lower()
    b_lower = b.strip().lower()
    if a_lower == b_lower:
        return True
    if not a_lower or not b_lower:
        return False
    common = sum(1 for character in a_lower if character in b_lower)
    return common / max(len(a_lower), len(b_lower)) > 0.8
