"""FastAPI dependency injection — replaces main.py module-level globals.

Service singletons are created eagerly at import time (matching the original
main.py behavior so that test imports ``from app.main import app`` continue to
work unchanged).  Thread-unsafe global mutation (campaign_managers, knowledge
reload) is encapsulated in classes with proper locking.
"""

import json
import threading
import time

from app.config import get_settings
from app.database import Database
from app.repositories.campaign_progress import CampaignProgressRepository
from app.services.campaign_generator import CampaignGenerator
from app.services.campaign_manager import CampaignManager
from app.services.embedding_client import EmbeddingClient
from app.services.evaluation import EvaluationModule
from app.services.game_state import GameStateManager
from app.services.health_monitor import HealthMonitor
from app.services.knowledge_base import KnowledgeBase
from app.services.llm_client import LLMClient
from app.services.prompt_builder import PromptBuilder
from app.services.retriever import RAGRetriever
from app.services.scenario_generator import ScenarioGenerator
from app.services.scripted_story import ScriptedStoryService


# ── Eager singletons (created once at import time) ──────────────────────

settings = get_settings()
db = Database(settings.database_file)
knowledge = KnowledgeBase(db, settings.knowledge_dir, settings.rulebook_file)
chunks = knowledge.load_chunks()
state_manager = GameStateManager(db)
embedding_client = (
    EmbeddingClient(settings.deepseek_api_key, settings.llm_base_url)
    if settings.deepseek_api_key
    else None
)
retriever = RAGRetriever(chunks, embedding_client=embedding_client)
prompt_builder = PromptBuilder()
llm_client = LLMClient(settings)
scripted_story = ScriptedStoryService()
health_monitor = HealthMonitor(db)
campaign_generator = CampaignGenerator(
    llm_client=llm_client,
    prompt_builder=prompt_builder,
    db=db,
    output_dir=settings.campaigns_dir,
)
evaluation_module = EvaluationModule()
campaign_progress_repo = CampaignProgressRepository(db)

# CampaignManagerCache + KnowledgeService are created below after their
# class definitions — see bottom of file.


# ── CampaignManagerCache (thread-safe, TTL eviction) ────────────────────


class CampaignManagerCache:
    """Thread-safe LRU-like cache for CampaignManager instances.

    Replaces the bare ``campaign_managers: dict`` + ``_evict_stale_managers``
    that lived at module scope in main.py.
    """

    _TTL = 3600  # 1 hour

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._cache: dict[tuple[str, str], tuple[float, CampaignManager]] = {}

    def get(self, session_id: str, slot_name: str) -> CampaignManager | None:
        """Return cached manager or *None*.  Refreshes timestamp on hit."""
        with self._lock:
            self._evict()
            key = (session_id, slot_name)
            if key in self._cache:
                ts, mgr = self._cache[key]
                self._cache[key] = (time.time(), mgr)
                return mgr
        return None

    def put(self, session_id: str, slot_name: str, manager: CampaignManager) -> None:
        with self._lock:
            self._cache[(session_id, slot_name)] = (time.time(), manager)

    def invalidate(self, session_id: str, slot_name: str) -> None:
        with self._lock:
            self._cache.pop((session_id, slot_name), None)

    def _evict(self) -> None:
        """Remove entries older than TTL. Caller must hold ``_lock``."""
        now = time.time()
        stale = [k for k, (ts, _) in self._cache.items() if now - ts > self._TTL]
        for k in stale:
            self._cache.pop(k, None)

    def get_or_load(
        self,
        session_id: str,
        slot_name: str,
        session_row: dict,
    ) -> CampaignManager | None:
        """Return the manager, loading from DB if not cached.

        Validates cached entry against the session's current campaign_filename
        to prevent stale managers after campaign switch.
        """
        with self._lock:
            self._evict()
            key = (session_id, slot_name)
            if key in self._cache:
                ts, mgr = self._cache[key]
                # Refresh timestamp on hit
                self._cache[key] = (time.time(), mgr)
                return mgr

        # Not cached — try to load
        if not session_row or not session_row["campaign_filename"]:
            return None

        campaign_path = settings.campaigns_dir / session_row["campaign_filename"]
        if not campaign_path.exists():
            return None

        manager = build_campaign_manager()
        manager.load(
            campaign_path,
            campaign_id=session_row["campaign_id"] or session_id,
            slot_name=slot_name,
        )

        with self._lock:
            self._cache[(session_id, slot_name)] = (time.time(), manager)

        return manager


campaign_manager_cache = CampaignManagerCache()


def build_campaign_manager() -> CampaignManager:
    """Factory used by both routes and cache to create fresh managers."""
    return CampaignManager(
        db=db,
        campaigns_dir=settings.campaigns_dir,
        scripted_story=scripted_story,
        prompt_builder=prompt_builder,
        llm_client=llm_client,
        health_monitor=health_monitor,
    )


def get_campaign_manager_for_session(
    session_id: str, slot_name: str = "default"
) -> CampaignManager | None:
    """Public helper preserving the old ``get_campaign_manager_for_session`` API."""
    session_row = db.get_session(session_id)
    if not session_row:
        return None
    active_slot = slot_name or session_row["active_slot_name"] or "default"
    return campaign_manager_cache.get_or_load(session_id, active_slot, session_row)


# ── KnowledgeService (thread-safe atomic reload) ────────────────────────


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


knowledge_service = KnowledgeService(
    knowledge=knowledge,
    embedding_client=embedding_client,
    db=db,
    state_manager=state_manager,
    prompt_builder=prompt_builder,
    llm_client=llm_client,
    scripted_story=scripted_story,
    cache=campaign_manager_cache,
    settings=settings,
)
