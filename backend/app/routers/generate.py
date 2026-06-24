"""Generate + evaluate routes."""

from fastapi import APIRouter, HTTPException

from app.dependencies import (
    evaluation_module,
    knowledge_service,
)
from app.schemas import GenerateRequest, GenerateResponse, StoryOutput
from app.services.llm_client import MissingAPIKeyError
from app.services.scenario_generator import ScenarioGenerationError

router = APIRouter(tags=["generate"])


@router.post("/sessions/{session_id}/generate", response_model=GenerateResponse)
async def generate(session_id: str, request: GenerateRequest) -> GenerateResponse:
    try:
        response = await knowledge_service.scenario_generator.generate(session_id, request)
    except MissingAPIKeyError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ScenarioGenerationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if not response:
        raise HTTPException(status_code=404, detail="Session not found")
    return response


@router.post("/evaluate")
def evaluate(output: StoryOutput) -> dict[str, int]:
    return evaluation_module.score(output)
