"""Hook 3 — execute the generation step (multi-agent pipeline or legacy call)."""

import asyncio
import logging

from app.schemas.agent_io import DirectorInstruction
from app.services.agents.director import DirectorAgent
from app.services.agents.examiner import ExaminerAgent, is_passive_continuation_action
from app.services.llm_client import LLMOutputParseError, LLMRequestError
from app.services.scenario_generator.errors import ScenarioGenerationError
from app.schemas import StoryOutput

logger = logging.getLogger(__name__)


class AgentPipelineMixin:
    async def _execute_llm_or_scripted(
        self, session_id, request, prompt, model, meta, retrieved_for_storage, _csi,
        state=None, campaign_manager=None,
    ) -> tuple[StoryOutput, int, str]:
        """Execute the multi-agent pipeline: Examiner → Director → Narrator.

        Falls back to the legacy single-call path when no campaign is loaded
        or when agents are not available.
        """
        # Legacy path: no campaign → single LLM call (unchanged behavior)
        if campaign_manager is None or not campaign_manager.is_loaded():
            return await self._execute_single_llm(request, prompt, model, meta)

        state = state or {}

        # ── Agent pipeline ────────────────────────────────────────
        turn = int(state.get("turn", 0))

        # Stage 1: Examiner — action feasibility + rule identification
        from app.schemas.agent_io import ActionRuling, ActionPermissibility
        if is_passive_continuation_action(request.player_action):
            # A scripted opening is itself valid narrative context.  The
            # Examiner only sees structured state, so it can falsely block the
            # UI's generic “继续” when the opening introduced characters that
            # are not duplicated in entry_state.
            ruling = ActionRuling(permissibility=ActionPermissibility.PERMISSIBLE)
        else:
            examiner = ExaminerAgent(self.llm_client)
            rules_texts = self._collect_relevant_rules(state, campaign_manager)
            try:
                ruling = await examiner.examine(
                    player_action=request.player_action,
                    game_state=state,
                    rules_texts=rules_texts,
                )
            except Exception:
                logger.warning("Examiner failed, defaulting to permissible", exc_info=True)
                ruling = ActionRuling(permissibility=ActionPermissibility.PERMISSIBLE)

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
        item_states = self._format_score_item_states(campaign_manager)

        try:
            return await director.direct(
                player_action=request.player_action,
                ruling=ruling,
                narrative_context=narrative_ctx,
                anchor_progress=anchor_progress,
                candidate_anchors=candidates,
                deviation_status=deviation,
                item_states=item_states,
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
                augmented_prompt, model, temperature=meta.temperature
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

        # Persistent per-session memory: feed the turn, then maintain in background
        memory_ctrl = self._get_memory_controller(session_id, state, campaign_manager)
        memory_ctrl.on_turn_generated(
            request.player_action, output.narration, turn,
            memory_updates=output.memory_updates,
        )
        task = asyncio.create_task(memory_ctrl.maintain(session_id, turn))
        self._memory_tasks.add(task)
        task.add_done_callback(self._log_memory_task_done)

        return output, latency_ms, source

    async def _execute_single_llm(
        self, request, prompt, model, meta
    ) -> tuple[StoryOutput, int, str]:
        """Fallback: single LLM call (original behavior, no multi-agent pipeline)."""
        try:
            output, latency_ms = await self.llm_client.generate(
                prompt, model, temperature=meta.temperature
            )
            output.replace_em_dashes()
            return output, latency_ms, "llm"
        except LLMRequestError:
            raise
        except LLMOutputParseError:
            raise
