"""Hook 1 — campaign opening scene handling (early return path)."""

from app.schemas import GenerateResponse, StoryOutput
from app.schemas.agent_io import OpeningOptions
from app.schemas.campaign import AnchorEvent
from app.services.agents.opening_options import OpeningOptionsAgent
from app.services.llm_client import LLMOutputParseError, LLMRequestError, MissingAPIKeyError
from app.services.scenario_generator.errors import ScenarioGenerationError


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
        is_session_transition = int(state.get("turn", 0)) > 0
        state = self.state_manager.merge_entry_state(
            state, campaign_manager.campaign,
            campaign_manager.progress.arc_index, campaign_manager.progress.session_index,
            reset_scene_context=is_session_transition,
        )
        if is_session_transition:
            # The controller contains raw turns, summaries and persona sketches
            # from the previous scene.  The campaign recap is the deliberate
            # cross-session continuity channel; start a fresh short-term cache.
            self.invalidate_timeline_caches(session_id, campaign_manager.slot_name)

        # Asked for before anything is written, so a failure below leaves the turn
        # uncommitted and the retry lands back on the turn-0 guard.
        opening_options = await self._generate_opening_options(
            session_id, request, model, opening, state, campaign_manager, _csi
        )

        output = StoryOutput(
            narration=opening,
            dialogue=[],
            scene_prompt=state.get("_scene_prompt", ""),
            sanity_delta=0,
            health_delta=0,
            options=opening_options.options,
            option_checks=opening_options.option_checks,
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
            session_id=session_id, state=state, output=output,
            retrieved_chunks=[], model_output_id=output_id,
            used_model=model, source="scripted",
            timeline_node_id=timeline_node_id,
            parent_timeline_node_id=parent_turn_id,
        )

    # ── Opening options ────────────────────────────────────────────────

    @staticmethod
    def _current_session_anchors(campaign_manager) -> list[AnchorEvent]:
        """The anchors of the session being opened, most important first."""
        try:
            progress = campaign_manager.progress
            session = campaign_manager.campaign.arcs[progress.arc_index].sessions[
                progress.session_index
            ]
            anchors = list(session.anchor_events or [])
        except (AttributeError, IndexError, TypeError):
            return []
        return sorted(anchors, key=lambda anchor: anchor.priority, reverse=True)[:3]

    async def _generate_opening_options(
        self, session_id, request, model, opening, state, campaign_manager, _csi
    ) -> OpeningOptions:
        """Ask the model for this opening's options; fail loudly if it cannot.

        There is deliberately no fallback option: silently dropping back to a
        single continue button is the behaviour this call was added to remove.
        """
        agent = OpeningOptionsAgent(self.llm_client)
        try:
            return await agent.propose(
                opening=opening,
                state=state,
                anchors=self._current_session_anchors(campaign_manager),
                constraints=campaign_manager.campaign.constraints or "",
            )
        except MissingAPIKeyError:
            # Already carries actionable advice and maps to 503 in the router.
            raise
        except (LLMRequestError, LLMOutputParseError) as exc:
            status = "request_error" if isinstance(exc, LLMRequestError) else "parse_error"
            raw = getattr(exc, "response_text", "") or getattr(exc, "raw_output", "")
            output_id = self._store_error(
                session_id, request.player_action, model, exc.latency_ms,
                status, raw, str(exc), [], _csi,
            )
            raise ScenarioGenerationError(
                f"开场行动选项生成失败，请重试。{exc}", output_id
            ) from exc
