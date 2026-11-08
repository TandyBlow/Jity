"""Hook 1 — campaign opening scene handling (early return path)."""

from app.schemas import GenerateResponse, StoryOutput
from app.schemas.agent_io import OpeningOptions
from app.schemas.campaign import AnchorEvent
from app.services.agents.opening_options import OpeningOptionsAgent
from app.services.llm_client import LLMOutputParseError, LLMRequestError, MissingAPIKeyError
from app.services.scenario_generator.errors import ScenarioGenerationError


class OpeningSceneMixin:
    async def _handle_opening_scene(
        self, session_id, request, state, model, campaign_manager, _csi,
        parent_turn_id,
    ) -> GenerateResponse | None:
        """Return GenerateResponse for campaign opening scene, or None to continue."""
        if campaign_manager is None or not campaign_manager.is_loaded():
            return None

        opening = campaign_manager.get_opening_scene()
        turn = campaign_manager.progress.turn_in_session
        if turn != 0 or not opening:
            return None

        # A chapter starts on the campaign-local clock, even when the global
        # game turn is already positive. Apply its scene without resetting stats.
        # ``turns_total`` distinguishes a real boundary from starting a new
        # timeline directly at a later chapter.
        is_session_transition = int(
            getattr(campaign_manager.progress, "turns_total", 0)
        ) > 0
        merged_state = self.state_manager.merge_entry_state(
            state, campaign_manager.campaign,
            campaign_manager.progress.arc_index, campaign_manager.progress.session_index,
            reset_scene_context=is_session_transition,
        )
        state.clear()
        state.update(merged_state)
        if is_session_transition:
            # Reload the preserved branch snapshot after resetting scene lists.
            # Past evidence remains available alongside the campaign recap.
            self.invalidate_timeline_caches(session_id, campaign_manager.slot_name)
            # Do not replace the player's transition choice with a scripted
            # opening.  The normal Director/Narrator path receives both the
            # authored opening premise and the chosen action, so it can bridge
            # the two chapters causally in one turn.
            return None

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
        return await self._finalize_turn(
            session_id=session_id, request=request, output=output, state=state,
            model=model, campaign_manager=campaign_manager,
            memory_ctrl=self._get_memory_controller(session_id, state, campaign_manager),
            parent_turn_id=parent_turn_id, campaign_session_index=_csi,
            source="scripted",
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
