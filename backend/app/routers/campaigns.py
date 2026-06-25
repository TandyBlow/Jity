"""Campaign generation, listing, saving, and file serving routes."""

import json
import logging

from fastapi import APIRouter, HTTPException

from app.dependencies import (
    build_campaign_manager,
    campaign_manager_cache,
    campaign_generator,
    db,
    settings,
    time,
)
from app.services.campaign_generator import CampaignGenerationError, NovelIngestor
from app.services.llm_client import MissingAPIKeyError
from fastapi import File, UploadFile

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/campaigns", tags=["campaigns"])


@router.post("/generate")
async def generate_campaign(request: dict[str, str]) -> dict[str, object]:
    """Generate campaign.json from user prompt using deepseek-v4-pro.

    Request body: {"prompt": "1920s 上海超自然侦探"}
    Returns: validated campaign JSON with saved file path.
    """
    user_prompt = request.get("prompt", "").strip()
    if not user_prompt:
        raise HTTPException(status_code=400, detail="prompt is required")

    try:
        campaign_data = await campaign_generator.generate(user_prompt)
    except CampaignGenerationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except MissingAPIKeyError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    filepath = campaign_generator.save(campaign_data)
    return {
        "status": "ok",
        "campaign": campaign_data,
        "saved_to": str(filepath),
    }


@router.post("/generate-from-novel")
async def generate_from_novel(file: UploadFile = File(...)) -> dict[str, object]:
    """Generate campaign.json from uploaded novel TXT file.

    Detects encoding, splits chapters, extracts anchors per chapter,
    assembles into campaign, and saves.
    """
    if not file.filename or not file.filename.lower().endswith(".txt"):
        raise HTTPException(status_code=400, detail="Only .txt files are supported")

    try:
        raw_bytes = await file.read()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Failed to read file: {exc}") from exc

    if not raw_bytes:
        raise HTTPException(status_code=400, detail="File is empty")

    # Detect encoding and decode
    encoding = NovelIngestor.detect_encoding(raw_bytes)
    try:
        text = raw_bytes.decode(encoding)
    except (UnicodeDecodeError, LookupError):
        text = raw_bytes.decode("utf-8", errors="replace")

    try:
        campaign_data = await campaign_generator.generate_from_novel(text)
    except CampaignGenerationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except MissingAPIKeyError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    filepath = campaign_generator.save(campaign_data)
    return {
        "status": "ok",
        "campaign": campaign_data,
        "saved_to": str(filepath),
        "extraction_errors": campaign_data.get("_extraction_errors", []),
    }


@router.get("")
def list_campaigns() -> dict[str, object]:
    """List all saved campaign.json files in campaigns_dir."""
    campaigns_dir = settings.campaigns_dir
    if not campaigns_dir.exists():
        return {"campaigns": []}

    campaign_files: list[dict[str, object]] = []
    for fpath in sorted(campaigns_dir.glob("*.json")):
        # Skip schema and debug files
        if fpath.name in ("campaign.schema.json",) or fpath.name.startswith("_"):
            continue
        try:
            data = json.loads(fpath.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                continue
            if not data.get("arcs"):
                continue
            campaign_files.append({
                "filename": fpath.name,
                "title": data.get("title", fpath.stem),
                "version": data.get("version", 1),
                "arc_count": len(data.get("arcs", [])),
                "description": data.get("description", ""),
                "tags": data.get("tags", []),
                "estimated_duration": data.get("estimated_duration", 0),
                "difficulty": data.get("difficulty", "normal"),
            })
        except (json.JSONDecodeError, OSError):
            logger.warning("Skipping corrupt campaign file: %s", fpath, exc_info=True)
            continue
    return {"campaigns": campaign_files}


@router.post("/save")
def save_campaign(request: dict[str, object]) -> dict[str, object]:
    """Save a campaign.json file (created or edited in curator).

    Request body: {"filename": "...", "campaign": {...}}
    """
    filename = str(request.get("filename", "")).strip()
    if not filename:
        raise HTTPException(status_code=400, detail="filename is required")
    if not filename.endswith(".json"):
        filename += ".json"

    campaign_data = request.get("campaign")
    if not isinstance(campaign_data, dict):
        raise HTTPException(status_code=400, detail="campaign data is required")

    campaigns_dir = settings.campaigns_dir
    campaigns_dir.mkdir(parents=True, exist_ok=True)
    fpath = campaigns_dir / filename
    fpath.write_text(json.dumps(campaign_data, ensure_ascii=False, indent=2), encoding="utf-8")

    return {"status": "saved", "filename": filename, "path": str(fpath)}


@router.get("/{filename}")
def get_campaign_file(filename: str) -> dict[str, object]:
    """Load a single campaign.json file by filename."""
    fpath = settings.campaigns_dir / filename
    if not fpath.exists():
        raise HTTPException(status_code=404, detail=f"Campaign file not found: {filename}")

    try:
        data = json.loads(fpath.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read campaign: {exc}") from exc

    return {"filename": filename, "campaign": data}
