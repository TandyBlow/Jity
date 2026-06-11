from __future__ import annotations

from app.database import Database
from app.schemas import GenerateRequest, GenerateResponse, RetrievedChunk
from app.services.game_state import GameStateManager
from app.services.llm_client import LLMClient
from app.services.prompt_builder import PromptBuilder
from app.services.retriever import RAGRetriever


class ScenarioGenerator:
    def __init__(
        self,
        db: Database,
        state_manager: GameStateManager,
        retriever: RAGRetriever,
        prompt_builder: PromptBuilder,
        llm_client: LLMClient,
        default_model: str,
    ) -> None:
        self.db = db
        self.state_manager = state_manager
        self.retriever = retriever
        self.prompt_builder = prompt_builder
        self.llm_client = llm_client
        self.default_model = default_model

    async def generate(self, session_id: str, request: GenerateRequest) -> GenerateResponse | None:
        session = self.state_manager.get_session_payload(session_id)
        if not session:
            return None

        state = session["state"]
        query = self._build_query(request.player_action, state)
        retrieved = self.retriever.retrieve(query)
        prompt = self.prompt_builder.build(
            user_action=request.player_action,
            state=state,
            retrieved_chunks=retrieved,
            narrative_profile=request.narrative_profile,
            style=request.style,
            constraints=request.constraints,
        )
        model = request.model or session["model"] or self.default_model
        output, latency_ms = await self.llm_client.generate(prompt, model)
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
                )
                for chunk in retrieved
            ],
            model_output_id=output_id,
            used_model=model,
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
