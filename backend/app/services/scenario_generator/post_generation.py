"""Hooks 4 & 5 — post-generation processing and record/finalize."""

import json
import logging

logger = logging.getLogger(__name__)


class PostGenerationMixin:
    async def _apply_post_generation(
        self, output, next_state, state, session_id, session, model, campaign_manager
    ):
        """NPC relations (world facts already merged from StoryOutput). Returns possibly-updated next_state."""
        if campaign_manager is not None and campaign_manager.is_loaded():
            # NPC relations delta processing
            if output.npc_relations_delta:
                self._process_npc_relations_delta(output, state, campaign_manager)

        return next_state

    def _process_npc_relations_delta(self, output, state, campaign_manager) -> None:
        """Apply NPC affinity deltas from LLM output to campaign_progress."""
        try:
            progress = campaign_manager.progress
            row = self.db.read_campaign_progress(progress.campaign_id, campaign_manager.slot_name)
            existing_json = row.get("npc_relations", "[]") if row else "[]"
            relations = json.loads(existing_json) if isinstance(existing_json, str) else existing_json
            relations_by_name = {r["name"]: r for r in relations}
            for delta in output.npc_relations_delta:
                name = delta.get("name", "")
                sentiment = delta.get("sentiment", "neutral")
                if not name:
                    continue
                if name not in relations_by_name:
                    relations_by_name[name] = {
                        "name": name, "affinity": 0,
                        "last_interaction_turn": state.get("turn", 0), "note": ""
                    }
                entry = relations_by_name[name]
                if sentiment == "positive":
                    entry["affinity"] = min(entry.get("affinity", 0) + 1, 10)
                elif sentiment == "negative":
                    entry["affinity"] = max(entry.get("affinity", 0) - 1, -10)
                entry["last_interaction_turn"] = state.get("turn", 0)
                entry["note"] = delta.get("note", "") or entry.get("note", "")
            self.db.update_npc_relations(
                progress.campaign_id,
                json.dumps(list(relations_by_name.values()), ensure_ascii=False),
                campaign_manager.slot_name,
            )
        except Exception:
            logger.warning(
                "NPC relations processing failed for campaign %s",
                campaign_manager.progress.campaign_id, exc_info=True,
            )

    async def _record_and_finalize(
        self, session_id, request, output, model, latency_ms, source, state,
        retrieved_for_storage, token_count, campaign_manager
    ) -> tuple[int, dict]:
        """Record metrics, store model output, advance campaign. Returns (output_id, metrics)."""
        metrics: dict = {}
        if campaign_manager is not None and campaign_manager.is_loaded():
            metrics = campaign_manager.record_turn(output, state, latency_ms)
            metrics["token_count"] = token_count

        output_id = self.db.add_model_output(
            session_id=session_id, model=model,
            input_text=request.player_action, output=output.model_dump(),
            latency_ms=latency_ms, source=source, status="ok",
            raw_output_text=output.model_dump_json(),
            retrieved_chunks=retrieved_for_storage, **metrics,
        )

        # Unified advance — no duplication
        if output.game_over and campaign_manager is not None and campaign_manager.is_loaded():
            campaign_manager.end_campaign()
        else:
            await self._advance_campaign(campaign_manager, [
                {"role": "user", "content": request.player_action},
                {"role": "assistant", "content": output.model_dump_json()},
            ])

        return output_id, metrics
