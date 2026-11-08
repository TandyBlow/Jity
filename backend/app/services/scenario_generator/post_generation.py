"""Shared settlement and commit path for opening and narrated turns."""

import logging

from app.schemas import GenerateRequest, GenerateResponse, RetrievedChunk, StoryOutput
from app.services.campaign_endings import is_final_session
from app.services.campaign_manager import CampaignManager
from app.services.game_state.defaults import STATE_CAPS
from app.services.memory.memory_controller import MemoryController
from app.services.prompt_builder import PromptMeta

logger = logging.getLogger(__name__)


class PostGenerationMixin:
    async def _finalize_turn(
        self,
        *,
        session_id: str,
        request: GenerateRequest,
        output: StoryOutput,
        state: dict,
        model: str,
        campaign_manager: CampaignManager,
        memory_ctrl: MemoryController,
        parent_turn_id: int,
        campaign_session_index: int,
        source: str,
        latency_ms: int = 0,
        token_count: int = 0,
        retrieved: list[dict] | None = None,
        retrieved_for_storage: list[dict] | None = None,
        meta: PromptMeta | None = None,
    ) -> GenerateResponse:
        """Settle the final output and publish one turn for either generation path.

        Narrated turns finish any ending preview/rewrite before entering here.
        State, memory and campaign progress reach storage through the same node
        transaction. Background maintenance starts only after that commit;
        generate() owns failure/cancellation recovery for both paths.
        """
        memory_ctrl.score_tracker.validate_output(output, int(state.get("turn", 0)) + 1)
        next_state = self.state_manager.apply_output(state, request.player_action, output)
        next_state["items"] = memory_ctrl.score_tracker.reconcile_inventory(next_state.get("items", []))
        campaign_manager.confirm_pending_anchors(output, next_state)
        self._apply_npc_relations(output, state, campaign_manager)
        self._feed_memory(session_id, next_state, output, request.player_action, campaign_manager)

        output_id = await self._record_output_and_advance(
            session_id, request, output, model, latency_ms, source, state,
            retrieved_for_storage or [], token_count, campaign_manager, meta=meta,
        )
        progress_snapshot = self._campaign_progress_snapshot(session_id, campaign_manager)
        serialized = output.model_dump()
        timeline_node_id = self.db.commit_story_turn(
            session_id=session_id,
            expected_parent_id=parent_turn_id,
            player_action=request.player_action,
            output=serialized,
            state=next_state,
            campaign_progress=progress_snapshot,
            model=model,
            source=source,
            model_output_id=output_id,
            campaign_session_index=campaign_session_index,
        )
        campaign_manager.flush_deferred_effects()
        self._schedule_memory(session_id, timeline_node_id, next_state, campaign_manager)

        sanitized = self.state_manager.sanitize_state(dict(next_state))
        return GenerateResponse(
            memory=self.state_manager.memory_trace_entry(serialized, sanitized),
            declared=self.state_manager.declared_updates(serialized.get("memory_updates") or {}, serialized),
            caps=STATE_CAPS,
            campaign_progress=campaign_manager.campaign_view(sanitized) or None,
            session_id=session_id,
            state=sanitized,
            output=output,
            retrieved_chunks=[
                RetrievedChunk(
                    id=chunk["id"], title=chunk["title"], source_type=chunk["source_type"],
                    content=chunk["content"][:700], score=chunk["score"],
                    keywords=chunk.get("keywords", []), importance=int(chunk.get("importance", 3)),
                )
                for chunk in retrieved or []
            ],
            model_output_id=output_id,
            used_model=model,
            source=source,
            timeline_node_id=timeline_node_id,
            parent_timeline_node_id=parent_turn_id,
        )

    def _apply_npc_relations(self, output, state, campaign_manager) -> None:
        """Stage relation deltas in the overlay persisted with the turn snapshot."""
        if campaign_manager is None or not campaign_manager.is_loaded() or not output.npc_relations_delta:
            return
        try:
            campaign_manager.apply_npc_relation_delta(
                output.npc_relations_delta, state.get("turn", 0)
            )
        except Exception:
            logger.warning(
                "NPC relations processing failed for campaign %s",
                campaign_manager.progress.campaign_id, exc_info=True,
            )

    async def _record_output_and_advance(
        self, session_id, request, output, model, latency_ms, source, state,
        retrieved_for_storage, token_count, campaign_manager, meta=None
    ) -> int:
        """Record output and advance only in memory; the node commit persists progress."""
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
        if source == "examiner_blocked":
            # A rejected action is feedback, not a story beat. It stays in the
            # timeline but cannot consume campaign pacing or cross a boundary.
            pass
        elif output.game_over and campaign_manager is not None and campaign_manager.is_loaded():
            campaign_manager.commit_pending_anchors(persist=False)
            campaign_manager.advance_turn(persist=False)
            campaign_manager.end_campaign(persist=False)
        else:
            await self._advance_campaign(campaign_manager, [
                {"role": "user", "content": request.player_action},
                {"role": "assistant", "content": output.model_dump_json()},
            ])

        return output_id

    async def _advance_campaign(
        self,
        campaign_manager: CampaignManager | None,
        pending_messages: list[dict[str, str]] | None = None,
    ) -> None:
        """Commit anchors, advance turn, maybe advance session — exactly once.

        All advancement is in-memory only: the turn path persists progress
        inside the commit_story_turn transaction, so a failed node commit
        leaves nothing advanced on disk.
        """
        if campaign_manager is None or not campaign_manager.is_loaded():
            return
        closing_pending = campaign_manager.is_closing_pending()
        should_begin_closing = campaign_manager.should_begin_closing_after_next_turn()
        campaign_manager.commit_pending_anchors(persist=False)
        campaign_manager.advance_turn(persist=False)
        if closing_pending and not is_final_session(
            campaign_manager.campaign, campaign_manager.progress
        ):
            await campaign_manager.advance_session(pending_messages, persist=False)
        elif should_begin_closing and not is_final_session(
            campaign_manager.campaign, campaign_manager.progress
        ):
            campaign_manager.begin_closing()

    def _campaign_progress_snapshot(
        self, session_id: str, campaign_manager: CampaignManager | None
    ) -> dict:
        if campaign_manager is None or not campaign_manager.is_loaded() or campaign_manager.progress is None:
            return {}
        # In-memory values: on the deferred path they are ahead of the row
        # until commit_story_turn writes them.
        return campaign_manager.progress_snapshot()
