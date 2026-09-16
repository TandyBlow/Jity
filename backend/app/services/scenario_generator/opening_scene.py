"""Hook 1 — campaign opening scene handling (early return path)."""

from app.schemas import GenerateResponse, StoryOutput


class OpeningSceneMixin:
    async def _handle_opening_scene(
        self, session_id, request, session, state, model, campaign_manager, _csi,
        parent_turn_id=None,
    ) -> GenerateResponse | None:
        """Return GenerateResponse for campaign opening scene, or None to continue."""
        if campaign_manager is None or not campaign_manager.is_loaded():
            return None

        opening = campaign_manager.get_opening_scene()
        turn = campaign_manager.progress.turn_in_session
        if turn != 0 or not opening:
            return None
        if parent_turn_id is None:
            parent_turn_id = self.db.get_active_turn_id(session_id)

        # A chapter starts on the campaign-local clock, even when the global
        # game turn is already positive. Apply its scene without resetting stats.
        state = self.state_manager.merge_entry_state(
            state, campaign_manager.campaign,
            campaign_manager.progress.arc_index, campaign_manager.progress.session_index,
        )

        output = StoryOutput(
            narration=opening,
            dialogue=[],
            scene_prompt=state.get("_scene_prompt", ""),
            sanity_delta=0,
            health_delta=0,
            options=["继续"],
            current_location=state.get("current_location", ""),
        ).replace_em_dashes()
        state = self.state_manager.apply_output(state, request.player_action, output)

        metrics = campaign_manager.record_turn(output, session["state"], latency_ms=0)
        output_id = self.db.add_model_output(
            session_id=session_id, model=model,
            input_text=request.player_action, output=output.model_dump(),
            latency_ms=0, source="scripted", status="ok",
            raw_output_text=output.model_dump_json(),
            retrieved_chunks=[], **metrics,
        )

        # Unified advance — same path as normal turns
        await self._advance_campaign(campaign_manager, [
            {"role": "user", "content": request.player_action},
            {"role": "assistant", "content": output.model_dump_json()},
        ])
        progress_snapshot = self._campaign_progress_snapshot(session_id, campaign_manager)
        timeline_node_id = self.db.commit_story_turn(
            session_id=session_id,
            expected_parent_id=parent_turn_id,
            player_action=request.player_action,
            output=output.model_dump(),
            state=state,
            campaign_progress=progress_snapshot,
            model=model,
            source="scripted",
            model_output_id=output_id,
            campaign_session_index=_csi,
        )

        return GenerateResponse(
            session_id=session_id, state=self.state_manager.sanitize_state(state), output=output,
            retrieved_chunks=[], model_output_id=output_id,
            used_model=model, source="scripted",
            timeline_node_id=timeline_node_id,
            parent_timeline_node_id=parent_turn_id,
        )
