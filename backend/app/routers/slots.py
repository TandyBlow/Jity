"""Save-slot CRUD routes."""

import json
import logging

from fastapi import APIRouter, HTTPException

from app.dependencies import (
    campaign_manager_cache,
    db,
    get_campaign_manager_for_session,
    state_manager,
)
from app.repositories.campaign_progress import CampaignProgressRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/campaigns/slots", tags=["slots"])

_repo = CampaignProgressRepository(db)


@router.get("")
def list_slots(session_id: str | None = None) -> dict[str, object]:
    """List save slots, optionally limited to one game session."""
    return {"slots": _repo.list_slots(session_id)}


@router.post("")
def create_slot(request: dict[str, str]) -> dict[str, object]:
    """Create a named save slot for the current game session."""
    slot_name = request.get("slot_name", "").strip()
    if not slot_name:
        raise HTTPException(status_code=400, detail="slot_name is required")

    session_id = request.get("session_id") or request.get("campaign_id")
    if not session_id:
        raise HTTPException(status_code=400, detail="session_id is required")

    session_row = db.get_session(session_id)
    if not session_row:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")

    try:
        result = _repo.create_slot(session_row, slot_name, request.get("source_slot_name") or session_row["active_slot_name"] or "default")
    except ValueError as exc:
        # Map known business errors to proper HTTP status codes
        msg = str(exc)
        if "already exists" in msg:
            raise HTTPException(status_code=409, detail=msg) from exc
        if "invalid characters" in msg:
            raise HTTPException(status_code=400, detail=msg) from exc
        raise HTTPException(status_code=400, detail=msg) from exc

    return result


@router.post("/{slot_id}/load")
def load_slot(slot_id: int) -> dict[str, object]:
    """Switch the backend and UI to a persisted campaign slot."""
    progress = db.read_campaign_progress_by_id(slot_id)
    if not progress:
        raise HTTPException(status_code=404, detail=f"Slot '{slot_id}' not found")

    session_id = progress["campaign_id"]
    payload = state_manager.get_session_payload(session_id)
    if not payload:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")

    slot_name = progress["slot_name"]
    db.set_session_active_slot(session_id, slot_name)
    get_campaign_manager_for_session(session_id, slot_name)
    session_row = db.get_session(session_id)
    return {
        "status": "loaded",
        "slot": {
            "id": progress["id"],
            "campaign_id": progress["campaign_id"],
            "slot_name": slot_name,
            "arc_index": progress["arc_index"],
            "session_index": progress["session_index"],
            "turn_in_session": progress.get("turn_in_session", 0),
            "campaign_filename": session_row["campaign_filename"] if session_row else None,
            "is_active": True,
        },
        "session": payload,
    }


@router.delete("/{slot_name}")
def delete_slot(slot_name: str) -> dict[str, object]:
    """Delete a save slot by name."""
    if not _repo.delete_slot(slot_name):
        raise HTTPException(status_code=404, detail=f"Slot '{slot_name}' not found")
    return {"status": "deleted", "slot_name": slot_name}
