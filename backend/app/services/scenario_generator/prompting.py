"""Hook 2 — prompt assembly (RAG retrieve → context injection → truncation)."""

import inspect

from app.services.prompt_builder import PromptInput
from app.services.campaign_endings import ending_instruction, select_ending


class PromptBuildMixin:
    async def _build_prompt(self, request, state, session_id, campaign_manager):
        """RAG retrieve → context injection → truncation → return prompt + metadata."""
        query = self._build_query(request.player_action, state)
        retrieved = await self.retriever.retrieve_async(query)
        retrieved_for_storage = self._serialize_retrieved_chunks(retrieved)

        campaign_context = ""
        if campaign_manager is not None and campaign_manager.is_loaded():
            turn = getattr(campaign_manager.progress, "turn_in_session", int(state.get("turn", 0)))
            campaign_context = campaign_manager.inject_context(state, turn)
            selected_ending = select_ending(
                campaign_manager.campaign, campaign_manager.progress, state, request.player_action
            )
            if selected_ending is not None:
                campaign_context += "\n" + ending_instruction(selected_ending)

            # Keep memory in the campaign context channel so token truncation
            # accounts for it.  The controller's async variant is used when
            # available; the synchronous API remains compatible with tests
            # and lightweight callers.
            memory_ctrl = self._get_memory_controller(session_id, state, campaign_manager)
            async_assemble = getattr(memory_ctrl, "assemble_context_async", None)
            if inspect.iscoroutinefunction(async_assemble):
                campaign_context = await async_assemble(
                    state,
                    int(state.get("turn", 0)),
                    campaign_context=campaign_context,
                    player_action=request.player_action,
                )
            else:
                campaign_context = memory_ctrl.assemble_context(
                    state,
                    int(state.get("turn", 0)),
                    campaign_context=campaign_context,
                    player_action=request.player_action,
                )

        current_campaign_session = None
        if campaign_manager is not None and campaign_manager.is_loaded():
            current_campaign_session = getattr(campaign_manager.progress, "session_index", 0)

        prompt_input = PromptInput(
            player_action=request.player_action,
            game_state=state,
            retrieved_chunks=retrieved,
            style=request.style,
            constraints=request.constraints,
            campaign_context=campaign_context,
            # Previous sessions are represented by the campaign recap.  Mixing
            # their raw turns into "最近对话" after a scripted opening can pull
            # Narrator back into the scene that just ended.
            recent_messages=self.db.get_recent_messages(
                session_id,
                campaign_session_index=current_campaign_session,
            ),
        )
        prompt_sections, meta = self.prompt_builder.build_sections(prompt_input)
        prompt = "\n\n".join(prompt_sections.values())
        token_count = 0

        if campaign_manager is not None and campaign_manager.is_loaded():
            prompt, token_count, _ = campaign_manager.truncate_prompt_sections(prompt_sections)

        return prompt, meta, retrieved, retrieved_for_storage, token_count
