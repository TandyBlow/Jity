"""Hook 1 — campaign opening scene handling (early return path)."""

from app.schemas import GenerateResponse, StoryOutput


class OpeningSceneMixin:
    async def _handle_opening_scene(
        self, session_id, request, session, state, model, campaign_manager, _csi
    ) -> GenerateResponse | None:
        """Return GenerateResponse for campaign opening scene, or None to continue."""
        if campaign_manager is None or not campaign_manager.is_loaded():
            return None

        opening = campaign_manager.get_opening_scene()
        turn = int(state.get("turn", 0))
        if turn != 0 or not opening:
            return None

        output = StoryOutput(
            narration=opening,
            dialogue=[],
            scene_prompt="campaign opening",
            sanity_delta=0,
            health_delta=0,
            options=["继续"],
            current_location=state.get("current_location", ""),
        ).replace_em_dashes()
        self.db.add_message(session_id, "user", request.player_action, _csi)
        self.db.add_message(session_id, "assistant", output.model_dump_json(), _csi)
        state = self.state_manager.apply_output(state, request.player_action, output)
        self.state_manager.save_state(session_id, session["game_name"], model, state)

        metrics = campaign_manager.record_turn(output, session["state"], latency_ms=0)
        output_id = self.db.add_model_output(
            session_id=session_id, model=model,
            input_text=request.player_action, output=output.model_dump(),
            latency_ms=0, source="scripted", status="ok",
            raw_output_text=output.model_dump_json(),
            retrieved_chunks=[], **metrics,
        )

        # Unified advance — same path as normal turns
        await self._advance_campaign(campaign_manager)

        return GenerateResponse(
            session_id=session_id, state=self.state_manager.sanitize_state(state), output=output,
            retrieved_chunks=[], model_output_id=output_id,
            used_model=model, source="scripted",
        )
