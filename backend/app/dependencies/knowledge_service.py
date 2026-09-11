"""KnowledgeService — owns chunks, retriever and scenario_generator with atomic reload."""

import threading

from app.database import Database
from app.dependencies.campaign_cache import CampaignManagerCache, get_campaign_manager_for_session
from app.dependencies.singletons import state_manager
from app.services.embedding_client import EmbeddingClient
from app.services.game_state import GameStateManager
from app.services.knowledge_base import KnowledgeBase
from app.services.llm_client import LLMClient
from app.services.prompt_builder import PromptBuilder
from app.services.retriever import RAGRetriever
from app.services.scenario_generator import ScenarioGenerator
from app.services.scripted_story import ScriptedStoryService


class KnowledgeService:
    """Owns chunks, retriever, scenario_generator.  ``reload()`` swaps them atomically."""

    def __init__(
        self,
        knowledge: KnowledgeBase,
        embedding_client: EmbeddingClient | None,
        db: Database,
        state_manager: GameStateManager,
        prompt_builder: PromptBuilder,
        llm_client: LLMClient,
        scripted_story: ScriptedStoryService,
        cache: CampaignManagerCache,
        settings=None,
    ) -> None:
        self._lock = threading.Lock()
        self.knowledge = knowledge
        self.embedding_client = embedding_client
        self.db = db
        self.state_manager = state_manager
        self.prompt_builder = prompt_builder
        self.llm_client = llm_client
        self.scripted_story = scripted_story
        self.cache = cache
        self.settings = settings

        self.chunks = knowledge.load_chunks()
        self.retriever = RAGRetriever(self.chunks, embedding_client=embedding_client)
        self.scenario_generator = self._build_scenario_generator()

    def _build_scenario_generator(self) -> ScenarioGenerator:
        return ScenarioGenerator(
            db=self.db,
            state_manager=self.state_manager,
            retriever=self.retriever,
            prompt_builder=self.prompt_builder,
            llm_client=self.llm_client,
            scripted_story=self.scripted_story,
            campaign_manager_provider=get_campaign_manager_for_session,
            default_model=self.settings.llm_model,
        )

    def reload(self) -> int:
        """Atomically rebuild chunks → retriever → scenario_generator."""
        with self._lock:
            self.chunks = self.knowledge.load_chunks()
            self.retriever = RAGRetriever(
                self.chunks, embedding_client=self.embedding_client
            )
            self.scenario_generator = self._build_scenario_generator()
            return len(self.chunks)
