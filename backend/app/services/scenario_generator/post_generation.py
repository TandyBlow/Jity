"""Hooks 4 & 5 — post-generation processing and record/finalize."""

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
        """Apply NPC affinity deltas from LLM output to the in-memory overlay.

        The overlay rides the progress snapshot into the node commit; a
        direct DB write here would persist increments that a failed commit
        would then re-apply on retry.
        """
        try:
            campaign_manager.apply_npc_relation_delta(
                output.npc_relations_delta, state.get("turn", 0)
            )
        except Exception:
            logger.warning(
                "NPC relations processing failed for campaign %s",
                campaign_manager.progress.campaign_id, exc_info=True,
            )

    async def _record_and_finalize(
        self, session_id, request, output, model, latency_ms, source, state,
        retrieved_for_storage, token_count, campaign_manager, meta=None
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
            retrieved_chunks=retrieved_for_storage,
            prompt_sections=getattr(meta, "sections", None),
            prompt_text=getattr(meta, "final_prompt", ""),
            **metrics,
        )

        # Unified advance — no duplication; all deferred to the node commit.
        # An ending turn still counts toward the whole-campaign budget
        # (turn_in_session + turns_total); only the session/arc advance is
        # skipped, since end_campaign closes the campaign instead.
        if output.game_over and campaign_manager is not None and campaign_manager.is_loaded():
            campaign_manager.commit_pending_anchors(persist=False)
            campaign_manager.advance_turn(persist=False)
            campaign_manager.end_campaign(persist=False)
        else:
            await self._advance_campaign(campaign_manager, [
                {"role": "user", "content": request.player_action},
                {"role": "assistant", "content": output.model_dump_json()},
            ])

        return output_id, metrics
