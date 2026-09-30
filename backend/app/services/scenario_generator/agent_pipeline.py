"""Hook 3 — execute the campaign agent pipeline."""

import logging

from app.schemas.agent_io import DirectorInstruction
from app.services.agents.director import DirectorAgent
from app.services.agents.examiner import ExaminerAgent, is_passive_continuation_action
from app.services.llm_client import LLMOutputParseError, LLMRequestError
from app.services.scenario_generator.errors import ScenarioGenerationError
from app.schemas import StoryOutput
from app.exceptions import CampaignRequiredError

logger = logging.getLogger(__name__)


class AgentPipelineMixin:
    async def _execute_llm_or_scripted(
        self, session_id, request, prompt, model, meta, retrieved_for_storage, _csi,
        state=None, campaign_manager=None,
    ) -> tuple[StoryOutput, int, str]:
        """Execute the campaign pipeline: Examiner → Director → Narrator."""
        if campaign_manager is None or not campaign_manager.is_loaded():
            raise CampaignRequiredError("请先创建战役会话，当前会话不支持继续生成。")

        state = state or {}

        # ── Agent pipeline ────────────────────────────────────────
        turn = int(state.get("turn", 0))

        # Stage 1: Examiner — action feasibility + rule identification
        from app.schemas.agent_io import ActionRuling
        if is_passive_continuation_action(request.player_action):
            ruling = ActionRuling()
        else:
            ruling = await ExaminerAgent().examine(
                player_action=request.player_action,
                game_state=state,
            )

        # If Examiner says blocked → return diegetic rejection
        if ruling.permissibility.value == "blocked" and ruling.rejection_reason:
            rejection_output = StoryOutput(
                narration=ruling.rejection_reason,
                dialogue=[],
                scene_prompt="",
                sanity_delta=0,
                health_delta=0,
                options=["重新尝试其他行动"],
                current_location=state.get("current_location", ""),
                game_over=False,
                game_over_reason="",
            ).replace_em_dashes()
            return rejection_output, 0, "examiner_blocked"

        # Stage 2: Director — narrative direction, anchor triggers, redirection
        direction = await self._run_director_stage(
            session_id, request, ruling, state, turn, campaign_manager
        )

        # Inject director instruction into prompt meta / campaign_context
        augmented_prompt = self._inject_direction(prompt, direction, ruling)

        # Stage 3: Narrator — the actual story generation (single LLM call)
        return await self._run_narrator_stage(
            session_id, request, augmented_prompt, model, meta,
            retrieved_for_storage, _csi, state, turn,
            campaign_manager=campaign_manager,
        )

    async def _run_director_stage(
        self, session_id, request, ruling, state, turn, campaign_manager
    ):
        """Stage 2: Director — narrative direction, anchor triggers, redirection."""
        director = DirectorAgent(self.llm_client)
        recap = (
            campaign_manager._load_recap_compressed()
            if hasattr(campaign_manager, "_load_recap_compressed")
            else ""
        )
        current_opening = campaign_manager.get_opening_scene() or ""
        current_session_index = getattr(campaign_manager.progress, "session_index", 0)
        current_messages = self.db.get_recent_messages(
            session_id,
            limit=4,
            campaign_session_index=current_session_index,
        )
        current_history = "\n".join(
            f"{msg.get('role', 'unknown')}: {msg.get('content', '')[:800]}"
            for msg in current_messages
        )
        narrative_parts = [
            f"当前地点：{state.get('current_location', '未知')}",
            "当前幕固定开场（最高优先级，必须从这里继续，不能回到上一幕）：\n"
            + current_opening,
        ]
        if current_history:
            narrative_parts.append("当前幕最近记录：\n" + current_history)
        if recap:
            narrative_parts.append(
                "上一幕回顾（仅作因果背景，不是当前场景，不得从其结尾续写）：\n" + recap
            )
        narrative_ctx = "\n\n".join(narrative_parts)
        anchor_progress = f"{len(campaign_manager.progress.revealed_anchors)}/{sum(len(s.anchor_events) for a in campaign_manager.campaign.arcs for s in a.sessions)}" if campaign_manager.progress else "0/0"
        candidates = self._describe_anchor_candidates(campaign_manager, state, turn)
        deviation = "偏差：连续3+回合无锚点触发" if campaign_manager.detect_deviation(state, turn) else "正常"
        item_states = self._format_score_item_states(campaign_manager, session_id, state)

        try:
            return await director.direct(
                player_action=request.player_action,
                ruling=ruling,
                narrative_context=narrative_ctx,
                anchor_progress=anchor_progress,
                candidate_anchors=candidates,
                deviation_status=deviation,
                item_states=item_states,
                context={"session_id": session_id, "turn": turn},
            )
        except Exception:
            logger.warning("Director failed, using fallback direction", exc_info=True)
            return DirectorInstruction(narrative_direction="继续叙事，回应玩家行动")

    async def _run_narrator_stage(
        self, session_id, request, augmented_prompt, model, meta,
        retrieved_for_storage, _csi, state, turn, campaign_manager=None,
    ) -> tuple[StoryOutput, int, str]:
        """Stage 3: Narrator — the actual story generation (single LLM call)."""
        try:
            output, latency_ms = await self.llm_client.generate(
                augmented_prompt,
                model,
                temperature=meta.temperature,
                purpose="story_narrator",
                context={"session_id": session_id, "turn": turn},
            )
            output.replace_em_dashes()
            source = "llm"
        except LLMRequestError as exc:
            output_id = self._store_error(
                session_id, request.player_action, model, exc.latency_ms,
                "request_error", exc.response_text, str(exc), retrieved_for_storage, _csi,
            )
            raise ScenarioGenerationError(f"{exc} model_output_id={output_id}", output_id) from exc
        except LLMOutputParseError as exc:
            output_id = self._store_error(
                session_id, request.player_action, model, exc.latency_ms,
                "parse_error", exc.raw_output, str(exc), retrieved_for_storage, _csi,
            )
            raise ScenarioGenerationError(f"{exc} model_output_id={output_id}", output_id) from exc

        return output, latency_ms, source
