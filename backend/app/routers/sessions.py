"""Session CRUD + history + progress routes."""

import json
import logging
import time

from fastapi import APIRouter, HTTPException

from app.dependencies import (
    build_campaign_manager,
    campaign_manager_cache,
    db,
    settings,
    state_manager,
)
from app.schemas import (
    CreateSessionRequest,
    SessionHistoryResponse,
    SessionResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.post("", response_model=SessionResponse)
def create_session(request: CreateSessionRequest) -> SessionResponse:
    payload = state_manager.create_session(request.game_name, request.model or settings.llm_model)
    session_id = payload["session_id"]

    # ── Campaign wiring: load campaign if filename provided ──
    if request.campaign_filename:
        campaign_path = settings.campaigns_dir / request.campaign_filename
        if not campaign_path.exists():
            raise HTTPException(
                status_code=404,
                detail=f"Campaign file not found: {request.campaign_filename}",
            )
        try:
            slot_name = request.slot_name or "default"
            manager = build_campaign_manager()
            manager.load(
                campaign_path,
                campaign_id=session_id,
                start_arc_index=request.arc_index,
                start_session_index=request.session_index,
                slot_name=slot_name,
            )
            campaign_manager_cache.put(session_id, slot_name, manager)
            db.set_session_campaign_id(
                session_id,
                session_id,
                request.campaign_filename,
                slot_name,
            )
            # Merge entry_state (includes campaign starting_state for fresh starts)
            payload["state"] = state_manager.merge_entry_state(
                payload["state"],
                manager.campaign,
                request.arc_index,
                request.session_index,
            )
            # Write merged state to DB so generate can read it
            state_manager.save_state(
                session_id, payload["game_name"],
                payload["model"], payload["state"]
            )
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    state_manager.sanitize_state(payload["state"])
    return SessionResponse(**payload)


@router.get("/{session_id}", response_model=SessionResponse)
def get_session(session_id: str) -> SessionResponse:
    payload = state_manager.get_session_payload(session_id)
    if not payload:
        raise HTTPException(status_code=404, detail="Session not found")
    state_manager.sanitize_state(payload["state"])
    return SessionResponse(**payload)


@router.get("/{session_id}/history", response_model=SessionHistoryResponse)
def get_session_history(session_id: str) -> SessionHistoryResponse:
    payload = state_manager.get_session_payload(session_id)
    if not payload:
        raise HTTPException(status_code=404, detail="Session not found")
    return SessionHistoryResponse(session_id=session_id, messages=db.get_messages(session_id))


@router.get("/{session_id}/progress")
def get_session_progress(session_id: str) -> dict[str, object]:
    """Return campaign progress data for timeline UI.

    Returns revealed_anchors, arc_index, session_index, world_facts
    from campaign_progress table and current game state.
    """
    session = state_manager.get_session_payload(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    state = session["state"]
    progress_data: dict[str, object] = {
        "session_id": session_id,
        "revealed_anchors": [],
        "arc_index": 0,
        "session_index": 0,
        "world_facts": state.get("world_facts", []),
    }

    session_row = db.get_session(session_id)
    slot_name = session_row["active_slot_name"] if session_row else "default"
    campaign_id = session_row["campaign_id"] if session_row and session_row["campaign_id"] else session_id
    row = db.read_campaign_progress(campaign_id, slot_name or "default")
    if row:
        progress_data["revealed_anchors"] = json.loads(
            row.get("revealed_anchors", "[]")
        )
        progress_data["arc_index"] = row.get("arc_index", 0)
        progress_data["session_index"] = row.get("session_index", 0)

    return progress_data
