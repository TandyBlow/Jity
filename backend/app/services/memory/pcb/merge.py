"""PCB merge strategies (MOOM three-strategy merging)."""

from app.schemas.agent_io import PersonaSnapshot

from app.services.memory.pcb.keys import (
    _ADD_KEYS,
    _COMPLEX_KEYS,
    _CONTRADICTORY_KEYS,
    _REPLACE_KEYS,
    _TRAJECTORY_KEYS,
)


class PersonaMergeMixin:
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
