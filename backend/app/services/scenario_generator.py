import json
import logging
from collections.abc import Callable

from app.database import Database
from app.schemas import GenerateRequest, GenerateResponse, RetrievedChunk, StoryOutput
from app.services.campaign_manager import CampaignManager
from app.services.game_state import GameStateManager
from app.services.llm_client import LLMClient, LLMOutputParseError, LLMRequestError
from app.services.prompt_builder import PromptBuilder, PromptInput
from app.services.retriever import RAGRetriever

logger = logging.getLogger(__name__)
from app.services.scripted_story import ScriptedStoryService


class ScenarioGenerationError(RuntimeError):
    def __init__(self, message: str, model_output_id: int | None = None) -> None:
        super().__init__(message)
        self.model_output_id = model_output_id


class ScenarioGenerator:
    def __init__(
        self,
        db: Database,
        state_manager: GameStateManager,
        retriever: RAGRetriever,
        prompt_builder: PromptBuilder,
        llm_client: LLMClient,
        scripted_story: ScriptedStoryService,
        default_model: str,
        campaign_manager: CampaignManager | None = None,
        campaign_manager_provider: Callable[[str, str], CampaignManager | None] | None = None,
    ) -> None:
        self.db = db
        self.state_manager = state_manager
        self.retriever = retriever
        self.prompt_builder = prompt_builder
        self.llm_client = llm_client
        self.scripted_story = scripted_story
        self.campaign_manager = campaign_manager
        self.campaign_manager_provider = campaign_manager_provider
        self.default_model = default_model

    # ── Main orchestration (~50 lines) ────────────────────────────────

    async def generate(self, session_id: str, request: GenerateRequest) -> GenerateResponse | None:
        session = self.state_manager.get_session_payload(session_id)
        if not session:
            return None

        state = session["state"]
        model = request.model or session["model"] or self.default_model
        campaign_manager = self._campaign_manager_for(session_id, request.slot_name)
        _csi = self._campaign_session_index(campaign_manager)

        # Hook 1: Campaign opening scene (early return)
        opening_result = await self._handle_opening_scene(
            session_id, request, session, state, model, campaign_manager, _csi
        )
        if opening_result is not None:
            return opening_result

        # Hook 2: Build prompt (RAG + context injection + token truncation)
        prompt, meta, retrieved, retrieved_for_storage, token_count = await self._build_prompt(
            request, state, session_id, campaign_manager
        )

        # Hook 3: Execute generation (scripted story or LLM)
        output, latency_ms, source = await self._execute_llm_or_scripted(
            session_id, request, prompt, model, meta, retrieved_for_storage, _csi
        )

        next_state = self.state_manager.apply_output(state, request.player_action, output)

        # Hook 4: Post-generation processing (facts + NPC relations + state save)
        next_state = await self._apply_post_generation(
            output, next_state, state, session_id, session, model, campaign_manager
        )

        self.db.add_message(session_id, "user", request.player_action, _csi)
        self.db.add_message(session_id, "assistant", output.model_dump_json(), _csi)
        self.state_manager.save_state(session_id, session["game_name"], model, next_state)

        # Hook 5: Record + finalize (commit anchors, advance turn advance session — once)
        output_id, metrics = await self._record_and_finalize(
            session_id, request, output, model, latency_ms, source, state,
            retrieved_for_storage, token_count, campaign_manager
        )

        return GenerateResponse(
            session_id=session_id,
            state=next_state,
            output=output,
            retrieved_chunks=[
                RetrievedChunk(
                    id=chunk["id"],
                    title=chunk["title"],
                    source_type=chunk["source_type"],
                    content=chunk["content"][:700],
                    score=chunk["score"],
                    keywords=chunk.get("keywords", []),
                    importance=int(chunk.get("importance", 3)),
                )
                for chunk in retrieved
            ],
            model_output_id=output_id,
            used_model=model,
            source=source,
        )

    # ── Hook 1: Opening scene ────────────────────────────────────────

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
        )
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
            session_id=session_id, state=state, output=output,
            retrieved_chunks=[], model_output_id=output_id,
            used_model=model, source="scripted",
        )

    # ── Hook 2: Build prompt ────────────────────────────────────────

    async def _build_prompt(self, request, state, session_id, campaign_manager):
        """RAG retrieve → context injection → truncation → return prompt + metadata."""
        query = self._build_query(request.player_action, state)
        retrieved = await self.retriever.retrieve_async(query)
        retrieved_for_storage = self._serialize_retrieved_chunks(retrieved)

        campaign_context = ""
        if campaign_manager is not None and campaign_manager.is_loaded():
            turn = getattr(campaign_manager.progress, "turn_in_session", int(state.get("turn", 0)))
            campaign_context = campaign_manager.inject_context(state, turn)

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

    # ── Hook 3: Execute LLM or scripted ─────────────────────────────

    async def _execute_llm_or_scripted(
        self, session_id, request, prompt, model, meta, retrieved_for_storage, _csi
    ) -> tuple[StoryOutput, int, str]:
        """Return (output, latency_ms, source)."""
        scripted_output = self.scripted_story.generate(request.player_action, {})
        if scripted_output:
            return scripted_output, 0, "scripted"

        try:
            output, latency_ms = await self.llm_client.generate(prompt, model, temperature=meta.temperature)
            return output, latency_ms, "llm"
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

    # ── Hook 4: Post-generation ─────────────────────────────────────

    async def _apply_post_generation(
        self, output, next_state, state, session_id, session, model, campaign_manager
    ):
        """Fact extraction + NPC relations. Returns possibly-updated next_state."""
        if campaign_manager is not None and campaign_manager.is_loaded():
            # Fact extraction every 5 campaign turns
            upcoming_turn = getattr(campaign_manager.progress, "turn_in_session", 0) + 1
            if upcoming_turn > 0 and upcoming_turn % 5 == 0:
                facts = await campaign_manager.extract_facts(
                    output.narration,
                    next_state.get("recent_events", []),
                )
                if facts:
                    next_state["world_facts"] = self.state_manager.merge_by_name(
                        next_state.get("world_facts", []),
                        facts,
                        kind="world_fact",
                    )
                    next_state = self.state_manager.enforce_state_caps(next_state)

            # NPC relations delta processing
            if output.npc_relations_delta:
                self._process_npc_relations_delta(output, state, campaign_manager)

        return next_state

    # ── Hook 5: Record + finalize ──────────────────────────────────

    async def _record_and_finalize(
        self, session_id, request, output, model, latency_ms, source, state,
        retrieved_for_storage, token_count, campaign_manager
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
            retrieved_chunks=retrieved_for_storage, **metrics,
        )

        # Unified advance — no duplication
        await self._advance_campaign(campaign_manager)

        return output_id, metrics

    # ── Shared advance helper (eliminates duplicate cluster) ─────────

    async def _advance_campaign(self, campaign_manager: CampaignManager | None) -> None:
        """Commit anchors, advance turn, maybe advance session — exactly once."""
        if campaign_manager is None or not campaign_manager.is_loaded():
            return
        campaign_manager.commit_pending_anchors()
        turn_in_session = campaign_manager.advance_turn()
        max_turns = campaign_manager.resolve_max_turns()
        if turn_in_session >= max_turns:
            await campaign_manager.advance_session()

    # ── NPC relations helper ────────────────────────────────────────

    def _process_npc_relations_delta(self, output, state, campaign_manager) -> None:
        """Apply NPC affinity deltas from LLM output to campaign_progress."""
        try:
            progress = campaign_manager.progress
            row = self.db.read_campaign_progress(progress.campaign_id, campaign_manager.slot_name)
            existing_json = row.get("npc_relations", "[]") if row else "[]"
            relations = json.loads(existing_json) if isinstance(existing_json, str) else existing_json
            relations_by_name = {r["name"]: r for r in relations}
            for delta in output.npc_relations_delta:
                name = delta.get("name", "")
                sentiment = delta.get("sentiment", "neutral")
                if not name:
                    continue
                if name not in relations_by_name:
                    relations_by_name[name] = {
                        "name": name, "affinity": 0,
                        "last_interaction_turn": state.get("turn", 0), "note": ""
                    }
                entry = relations_by_name[name]
                if sentiment == "positive":
                    entry["affinity"] = min(entry.get("affinity", 0) + 1, 10)
                elif sentiment == "negative":
                    entry["affinity"] = max(entry.get("affinity", 0) - 1, -10)
                entry["last_interaction_turn"] = state.get("turn", 0)
                entry["note"] = delta.get("note", "") or entry.get("note", "")
            self.db.update_npc_relations(
                progress.campaign_id,
                json.dumps(list(relations_by_name.values()), ensure_ascii=False),
                campaign_manager.slot_name,
            )
        except Exception:
            logger.warning(
                "NPC relations processing failed for campaign %s",
                campaign_manager.progress.campaign_id, exc_info=True,
            )

    # ── Error storage helper ────────────────────────────────────────

    def _store_error(
        self, session_id, input_text, model, latency_ms, status,
        raw_output, error_text, retrieved_chunks, _csi
    ) -> int:
        """Store error details in model_outputs. Returns output_id."""
        self.db.add_message(session_id, "user", input_text, _csi)
        self.db.add_message(session_id, "assistant_error", raw_output if status == "parse_error" else error_text, _csi)
        return self.db.add_model_output(
            session_id=session_id, model=model,
            input_text=input_text, output={},
            latency_ms=latency_ms, source="llm", status=status,
            raw_output_text=raw_output, error_text=error_text,
            retrieved_chunks=retrieved_chunks,
        )

    # ── Utility helpers ─────────────────────────────────────────────

    def _campaign_manager_for(self, session_id: str, slot_name: str) -> CampaignManager | None:
        if self.campaign_manager_provider is not None:
            return self.campaign_manager_provider(session_id, slot_name)
        return self.campaign_manager

    @staticmethod
    def _campaign_session_index(campaign_manager: CampaignManager | None) -> int:
        if campaign_manager is not None and campaign_manager.is_loaded():
            return getattr(campaign_manager.progress, "session_index", 0)
        return 0

    @staticmethod
    def _build_query(player_action: str, state: dict) -> str:
        parts = [
            player_action,
            state.get("current_location", ""),
            " ".join(event for event in state.get("recent_events", [])[-4:]),
            " ".join(item.get("name", "") for item in state.get("npcs", [])),
            " ".join(item.get("name", "") for item in state.get("quests", [])),
        ]
        return "\n".join(part for part in parts if part)

    @staticmethod
    def _serialize_retrieved_chunks(chunks: list[dict]) -> list[dict]:
        return [
            {
                "id": chunk.get("id", ""),
                "source_type": chunk.get("source_type", ""),
                "title": chunk.get("title", ""),
                "score": chunk.get("score", 0),
                "keywords": chunk.get("keywords", []),
                "importance": int(chunk.get("importance", 3)),
                "content": str(chunk.get("content", ""))[:700],
            }
            for chunk in chunks
        ]
