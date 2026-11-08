"""Knowledge resources with a stable, session-owning scenario generator."""

import threading

from app.database import Database
from app.dependencies.campaign_cache import get_campaign_manager_for_session
from app.services.embedding_client import EmbeddingClient
from app.services.game_state import GameStateManager
from app.services.knowledge_base import KnowledgeBase
from app.services.llm_client import LLMClient
from app.services.prompt_builder import PromptBuilder
from app.services.retriever import RAGRetriever
from app.services.scenario_generator import ScenarioGenerator


class KnowledgeService:
    """Load knowledge once; reload retrieval without replacing session runtime."""

    def __init__(
        self,
        knowledge: KnowledgeBase,
        embedding_client: EmbeddingClient | None,
        db: Database,
        state_manager: GameStateManager,
        prompt_builder: PromptBuilder,
        llm_client: LLMClient,
        settings=None,
    ) -> None:
        self._lock = threading.Lock()
        self.knowledge = knowledge
        self.embedding_client = embedding_client
        self.db = db
        self.state_manager = state_manager
        self.prompt_builder = prompt_builder
        self.llm_client = llm_client
        self.settings = settings

        chunks = knowledge.load_chunks()
        retriever = RAGRetriever(chunks, embedding_client=embedding_client)
        self.scenario_generator = self._build_scenario_generator(retriever)

    def _build_scenario_generator(self, retriever: RAGRetriever) -> ScenarioGenerator:
        return ScenarioGenerator(
            db=self.db,
            state_manager=self.state_manager,
            retriever=retriever,
            prompt_builder=self.prompt_builder,
            llm_client=self.llm_client,
            campaign_manager_provider=get_campaign_manager_for_session,
            default_model=self.settings.llm_model,
        )

    @property
    def retriever(self) -> RAGRetriever:
        return self.scenario_generator.retriever

    @property
    def chunks(self) -> list[dict]:
        return self.retriever.chunks

    def reload(self) -> int:
        """Publish a complete retriever while preserving locks and memory jobs.

        An in-flight retrieval keeps its existing retriever; subsequent calls
        use the replacement. Failed construction leaves the live instance intact.
        """
        with self._lock:
            chunks = self.knowledge.load_chunks()
            retriever = RAGRetriever(
                chunks, embedding_client=self.embedding_client
            )
            self.scenario_generator.retriever = retriever
            return len(chunks)
