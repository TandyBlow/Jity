
from app.database import Database
from app.schemas import GenerateRequest, GenerateResponse, RetrievedChunk, StoryOutput
from app.services.campaign_manager import CampaignManager
from app.services.game_state import GameStateManager
from app.services.llm_client import LLMClient, LLMOutputParseError, LLMRequestError
from app.services.prompt_builder import PromptBuilder, PromptInput
from app.services.retriever import RAGRetriever
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
    ) -> None:
        self.db = db
        self.state_manager = state_manager
        self.retriever = retriever
        self.prompt_builder = prompt_builder
        self.llm_client = llm_client
        self.scripted_story = scripted_story
        self.campaign_manager = campaign_manager
        self.default_model = default_model

    async def generate(self, session_id: str, request: GenerateRequest) -> GenerateResponse | None:
        session = self.state_manager.get_session_payload(session_id)
        if not session:
            return None

        state = session["state"]
        model = request.model or session["model"] or self.default_model

        # Get current campaign session index for message attribution
        _campaign_session_index = 0
        if self.campaign_manager is not None and self.campaign_manager.is_loaded():
            _campaign_session_index = getattr(self.campaign_manager.progress, "session_index", 0)

        # ── Injection Point #1: Campaign opening_scene override (turn 0 only) ──
        if self.campaign_manager is not None and self.campaign_manager.is_loaded():
            opening = self.campaign_manager.get_opening_scene()
            turn = int(state.get("turn", 0))
            if turn == 0 and opening:
                output = StoryOutput(
                    narration=opening,
                    dialogue=[],
                    scene_prompt="campaign opening",
                    sanity_delta=0,
                    health_delta=0,
                    options=["继续"],
                    current_location=state.get("current_location", ""),
                )
                self.db.add_message(session_id, "user", request.player_action, _campaign_session_index)
                self.db.add_message(session_id, "assistant", output.model_dump_json(), _campaign_session_index)
                state = self.state_manager.apply_output(state, request.player_action, output)
                self.state_manager.save_state(session_id, session["game_name"], model, state)
                output_id = self.db.add_model_output(
                    session_id=session_id,
                    model=model,
                    input_text=request.player_action,
                    output=output.model_dump(),
                    latency_ms=0,
                    source="scripted",
                    status="ok",
                    raw_output_text=output.model_dump_json(),
                    retrieved_chunks=[],
                )
                return GenerateResponse(
                    session_id=session_id,
                    state=state,
                    output=output,
                    retrieved_chunks=[],
                    model_output_id=output_id,
                    used_model=model,
                    source="scripted",
                )

        query = self._build_query(request.player_action, state)
        retrieved = self.retriever.retrieve(query)
        retrieved_for_storage = self._serialize_retrieved_chunks(retrieved)

        # ── Injection Point #2: Campaign context injection ──
        campaign_context = ""
        if self.campaign_manager is not None and self.campaign_manager.is_loaded():
            turn = int(state.get("turn", 0))
            campaign_context = self.campaign_manager.inject_context(state, turn)

        prompt, meta = self.prompt_builder.build(
            PromptInput(
                player_action=request.player_action,
                game_state=state,
                retrieved_chunks=retrieved,
                style=request.style,
                constraints=request.constraints,
                campaign_context=campaign_context,
            )
        )

        # ── Token budget check ──
        if self.campaign_manager is not None and self.campaign_manager.is_loaded():
            ok, token_count, warning = self.campaign_manager.check_token_budget(prompt)
            if not ok:
                # Log warning — token over budget
                pass
        scripted_output = self.scripted_story.generate(request.player_action, state)
        if scripted_output:
            output = scripted_output
            latency_ms = 0
            source = "scripted"
        else:
            try:
                output, latency_ms = await self.llm_client.generate(prompt, model, temperature=meta.temperature)
            except LLMRequestError as exc:
                self.db.add_message(session_id, "user", request.player_action, _campaign_session_index)
                self.db.add_message(session_id, "assistant_error", str(exc), _campaign_session_index)
                output_id = self.db.add_model_output(
                    session_id=session_id,
                    model=model,
                    input_text=request.player_action,
                    output={},
                    latency_ms=exc.latency_ms,
                    source="llm",
                    status="request_error",
                    raw_output_text=exc.response_text,
                    error_text=str(exc),
                    retrieved_chunks=retrieved_for_storage,
                )
                raise ScenarioGenerationError(f"{exc} model_output_id={output_id}", output_id) from exc
            except LLMOutputParseError as exc:
                self.db.add_message(session_id, "user", request.player_action, _campaign_session_index)
                self.db.add_message(session_id, "assistant_error", exc.raw_output, _campaign_session_index)
                output_id = self.db.add_model_output(
                    session_id=session_id,
                    model=model,
                    input_text=request.player_action,
                    output={},
                    latency_ms=exc.latency_ms,
                    source="llm",
                    status="parse_error",
                    raw_output_text=exc.raw_output,
                    error_text=str(exc),
                    retrieved_chunks=retrieved_for_storage,
                )
                raise ScenarioGenerationError(f"{exc} model_output_id={output_id}", output_id) from exc
            source = "llm"
        next_state = self.state_manager.apply_output(state, request.player_action, output)

        self.db.add_message(session_id, "user", request.player_action, _campaign_session_index)
        self.db.add_message(session_id, "assistant", output.model_dump_json(), _campaign_session_index)
        self.state_manager.save_state(session_id, session["game_name"], model, next_state)

        # ── NPC Relations delta processing ──
        if (self.campaign_manager is not None
            and self.campaign_manager.is_loaded()
            and output.npc_relations_delta):
            try:
                progress = self.campaign_manager.progress
                row = self.db.read_campaign_progress(progress.campaign_id)
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
                    json.dumps(list(relations_by_name.values()), ensure_ascii=False)
                )
            except Exception:
                pass

        # ── Injection Point #3: Session auto-advance check ──
        if self.campaign_manager is not None and self.campaign_manager.is_loaded():
            turn_in_session = getattr(self.campaign_manager.progress, "turn_in_session", 0)
            max_turns = self.campaign_manager._resolve_max_turns()
            if turn_in_session >= max_turns:
                await self.campaign_manager.advance_session()

        # ── Per-turn instrumentation ──
        metrics = {}
        if self.campaign_manager is not None and self.campaign_manager.is_loaded():
            metrics = self.campaign_manager.record_turn(output, state, latency_ms)

        output_id = self.db.add_model_output(
            session_id=session_id,
            model=model,
            input_text=request.player_action,
            output=output.model_dump(),
            latency_ms=latency_ms,
            source=source,
            status="ok",
            raw_output_text=output.model_dump_json(),
            retrieved_chunks=retrieved_for_storage,
            **metrics,
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
