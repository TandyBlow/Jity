"""AI scene-background routes."""

from fastapi import APIRouter, HTTPException

from app.config import get_settings
from app.schemas.background import BackgroundGenerateRequest, BackgroundGenerateResponse
from app.services.background_generator import BackgroundGenerationError, BackgroundGenerator

router = APIRouter(prefix="/backgrounds", tags=["backgrounds"])


@router.post("/generate", response_model=BackgroundGenerateResponse)
async def generate_background(request: BackgroundGenerateRequest) -> BackgroundGenerateResponse:
    try:
        image_url, cached = await BackgroundGenerator(get_settings()).generate(
            request.scene_prompt,
            request.location,
        )
    except BackgroundGenerationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return BackgroundGenerateResponse(image_url=image_url, cached=cached)
