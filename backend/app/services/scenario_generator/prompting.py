"""Hook 2 — prompt assembly (RAG retrieve → context injection → truncation)."""

from app.services.prompt_builder import PromptInput


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
            # Memory layers (L1 summaries, persona, SCORE states) ride in the
            # campaign_context channel so token truncation covers them too.
            memory_ctrl = self._get_memory_controller(session_id)
            campaign_context = memory_ctrl.assemble_context(
                state,
                int(state.get("turn", 0)),
                campaign_context=campaign_context,
                player_action=request.player_action,
            )

        prompt_input = PromptInput(
            player_action=request.player_action,
            game_state=state,
            retrieved_chunks=retrieved,
            style=request.style,
            constraints=request.constraints,
            campaign_context=campaign_context,
            recent_messages=self.db.get_recent_messages(session_id),
        )
        prompt_sections, meta = self.prompt_builder.build_sections(prompt_input)
        prompt = "\n\n".join(prompt_sections.values())
        token_count = 0

        if campaign_manager is not None and campaign_manager.is_loaded():
            prompt, token_count, _ = campaign_manager.truncate_prompt_sections(prompt_sections)

        return prompt, meta, retrieved, retrieved_for_storage, token_count
