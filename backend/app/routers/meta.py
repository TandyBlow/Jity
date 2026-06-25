"""Health, models, and knowledge-reload routes."""

from fastapi import APIRouter

from app.dependencies import (
    chunks,
    knowledge_service,
    retriever,
    settings,
)

router = APIRouter(tags=["meta"])


@router.get("/health")
def health() -> dict[str, object]:
    return {
        "status": "ok",
        "database": str(settings.database_file),
        "knowledge_chunks": len(knowledge_service.chunks),
        "retriever": "faiss" if knowledge_service.retriever.index is not None else "numpy",
    }


@router.get("/models")
def models() -> dict[str, list[str]]:
    return {"models": [settings.llm_model, "deepseek-v4-flash", "deepseek-reasoner"]}


@router.post("/knowledge/reload")
def reload_knowledge() -> dict[str, object]:
    count = knowledge_service.reload()
    return {"status": "reloaded", "knowledge_chunks": count}
