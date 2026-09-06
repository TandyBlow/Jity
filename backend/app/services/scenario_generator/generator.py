"""ScenarioGenerator — orchestrates one generation turn through five hooks."""

from collections.abc import Callable

from app.database import Database
from app.schemas import GenerateRequest, GenerateResponse, RetrievedChunk, StoryOutput
from app.services.campaign_manager import CampaignManager
from app.services.game_state import GameStateManager
from app.services.llm_client import LLMClient
from app.services.memory.memory_controller import MemoryController
from app.services.prompt_builder import PromptBuilder
from app.services.retriever import RAGRetriever
from app.services.scripted_story import ScriptedStoryService

from app.services.scenario_generator.agent_pipeline import AgentPipelineMixin
from app.services.scenario_generator.director_support import DirectorSupportMixin
from app.services.scenario_generator.errors import ScenarioGenerationError
from app.services.scenario_generator.opening_scene import OpeningSceneMixin
from app.services.scenario_generator.post_generation import PostGenerationMixin
from app.services.scenario_generator.prompting import PromptBuildMixin


class ScenarioGenerator(
    OpeningSceneMixin,
    PromptBuildMixin,
    AgentPipelineMixin,
    DirectorSupportMixin,
    PostGenerationMixin,
):
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
        # session_id → MemoryController (persistent across turns)
        self._memory_controllers: dict[str, MemoryController] = {}

    # ── Main orchestration ────────────────────────────────────────────

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

        # Hook 3: Execute generation (multi-agent pipeline or legacy single call)
        output, latency_ms, source = await self._execute_llm_or_scripted(
            session_id, request, prompt, model, meta, retrieved_for_storage, _csi,
            state=state, campaign_manager=campaign_manager,
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

    # ── Shared advance helper ─────────────────────────────────────────

    async def _advance_campaign(self, campaign_manager: CampaignManager | None) -> None:
        """Commit anchors, advance turn, maybe advance session — exactly once."""
        if campaign_manager is None or not campaign_manager.is_loaded():
            return
        campaign_manager.commit_pending_anchors()
        turn_in_session = campaign_manager.advance_turn()
        max_turns = campaign_manager.resolve_max_turns()
        if turn_in_session >= max_turns:
            await campaign_manager.advance_session()

    # ── Error storage helper ──────────────────────────────────────────

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

    # ── Utility helpers ───────────────────────────────────────────────

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


__all__ = ["ScenarioGenerator", "ScenarioGenerationError"]
