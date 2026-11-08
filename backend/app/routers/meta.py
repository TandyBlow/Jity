"""Health, models, and knowledge-reload routes."""

from fastapi import APIRouter

from app.dependencies import (
    knowledge_service,
    settings,
)

router = APIRouter(tags=["meta"])


@router.get("/health")
def health() -> dict[str, object]:
    return {
        "status": "ok",
        "database": str(settings.database_file),
        "knowledge_chunks": len(knowledge_service.chunks),
        "retriever": "numpy",
    }


@router.get("/models")
def models() -> dict[str, list[str]]:
    return {"models": [settings.llm_model, settings.llm_model_pro, "deepseek-reasoner"]}


@router.post("/knowledge/reload")
def reload_knowledge() -> dict[str, object]:
    count = knowledge_service.reload()
    return {"status": "reloaded", "knowledge_chunks": count}
