"""FastAPI dependency injection package.

Service singletons are created eagerly at import time (matching the original
main.py behavior so that test imports ``from app.main import app`` continue to
work unchanged).  Thread-unsafe global mutation (campaign_managers, knowledge
reload) is encapsulated in classes with proper locking.

Modules:
  - singletons:      eager service instances (db, retriever, llm_client, ...)
  - campaign_cache:  CampaignManagerCache + manager factory helpers
  - knowledge_service: KnowledgeService with atomic reload
"""

import time  # re-exported: routers/campaigns.py imports ``time`` from here

from app.dependencies.campaign_cache import (
    CampaignManagerCache,
    build_campaign_manager,
    campaign_manager_cache,
    get_campaign_manager_for_session,
)
from app.dependencies.knowledge_service import KnowledgeService
from app.dependencies.singletons import (
    campaign_generator,
    campaign_progress_repo,
    chunks,
    db,
    embedding_client,
    evaluation_module,
    health_monitor,
    knowledge,
    llm_client,
    prompt_builder,
    retriever,
    scripted_story,
    settings,
    state_manager,
)

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

__all__ = [
    "time",
    "settings",
    "db",
    "knowledge",
    "chunks",
    "state_manager",
    "embedding_client",
    "retriever",
    "prompt_builder",
    "llm_client",
    "scripted_story",
    "health_monitor",
    "campaign_generator",
    "evaluation_module",
    "campaign_progress_repo",
    "CampaignManagerCache",
    "campaign_manager_cache",
    "build_campaign_manager",
    "get_campaign_manager_for_session",
    "KnowledgeService",
    "knowledge_service",
]
