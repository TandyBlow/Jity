from __future__ import annotations

from app.database import Database
from app.schemas import GenerateRequest, GenerateResponse, RetrievedChunk
from app.services.game_state import GameStateManager
from app.services.llm_client import LLMClient, LLMOutputParseError, LLMRequestError
from app.services.prompt_builder import PromptBuilder
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
    ) -> None:
        self.db = db
        self.state_manager = state_manager
        self.retriever = retriever
        self.prompt_builder = prompt_builder
        self.llm_client = llm_client
        self.scripted_story = scripted_story
        self.default_model = default_model

    async def generate(self, session_id: str, request: GenerateRequest) -> GenerateResponse | None:
        session = self.state_manager.get_session_payload(session_id)
        if not session:
            return None

        state = session["state"]
        query = self._build_query(request.player_action, state)
        retrieved = self.retriever.retrieve(query)
        retrieved_for_storage = self._serialize_retrieved_chunks(retrieved)
        prompt = self.prompt_builder.build(
            user_action=request.player_action,
            state=state,
            retrieved_chunks=retrieved,
            style=request.style,
            constraints=request.constraints,
        )
        model = request.model or session["model"] or self.default_model
        scripted_output = self.scripted_story.generate(request.player_action, state)
        if scripted_output:
            output = scripted_output
            latency_ms = 0
            source = "scripted"
        else:
            try:
                output, latency_ms = await self.llm_client.generate(prompt, model)
            except LLMRequestError as exc:
                self.db.add_message(session_id, "user", request.player_action)
                self.db.add_message(session_id, "assistant_error", str(exc))
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
                self.db.add_message(session_id, "user", request.player_action)
                self.db.add_message(session_id, "assistant_error", exc.raw_output)
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

        self.db.add_message(session_id, "user", request.player_action)
        self.db.add_message(session_id, "assistant", output.model_dump_json())
        self.state_manager.save_state(session_id, session["game_name"], model, next_state)
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
