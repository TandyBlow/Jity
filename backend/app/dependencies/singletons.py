"""Eager service singletons (created once at import time).

Matches the original main.py module-level globals so that test imports
``from app.main import app`` continue to work unchanged.
"""

from app.config import get_settings
from app.database import Database
from app.repositories.campaign_progress import CampaignProgressRepository
from app.services.campaign_generator import CampaignGenerator
from app.services.embedding_client import EmbeddingClient
from app.services.evaluation import EvaluationModule
from app.services.game_state import GameStateManager
from app.services.health_monitor import HealthMonitor
from app.services.knowledge_base import KnowledgeBase
from app.services.llm_client import LLMClient
from app.services.prompt_builder import PromptBuilder
from app.services.retriever import RAGRetriever
from app.services.scripted_story import ScriptedStoryService

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
