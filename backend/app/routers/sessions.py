"""Session CRUD + history + progress routes."""

import json
import logging
import time
from datetime import datetime

from fastapi import APIRouter, HTTPException

from app.dependencies import (
    build_campaign_manager,
    campaign_manager_cache,
    db,
    knowledge_service,
    settings,
    state_manager,
)
from app.schemas import (
    CreateSessionRequest,
    SessionHistoryResponse,
    SessionResponse,
)
from app.services.game_state.defaults import (
    MAX_ITEMS,
    MAX_NPCS,
    MAX_QUESTS,
    MAX_WORLD_FACTS,
)

CAPS = {
    "items": MAX_ITEMS,
    "npcs": MAX_NPCS,
    "quests": MAX_QUESTS,
    "world_facts": MAX_WORLD_FACTS,
}

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
            slot_name = request.slot_name or f"auto_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
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
                initialize=True,
            )
            # Write merged state to DB so generate can read it
            state_manager.save_state(
                session_id, payload["game_name"],
                payload["model"], payload["state"]
            )
            payload["campaign_filename"] = request.campaign_filename
            progress = db.read_campaign_progress(session_id, slot_name)
            db.update_active_turn_snapshot(session_id, payload["state"], progress)
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


def _walk_active_path(rows: list[dict], active_id: object) -> set[int]:
    by_id = {int(row["id"]): row for row in rows}
    path: set[int] = set()
    cursor = int(active_id) if active_id else None
    while cursor is not None and cursor in by_id:
        path.add(cursor)
        parent = by_id[cursor].get("parent_turn_id")
        cursor = int(parent) if parent is not None else None
    return path


def _load_turns(session_id: str) -> tuple[dict, list[dict], object, set[int]] | None:
    """Every turn of a session decoded once, shared by the two read routes."""
    session = state_manager.get_session_payload(session_id)
    if not session:
        return None
    active_id = session.get("active_turn_id")
    rows = db.list_story_turns(session_id)
    turns = [
        {
            "row": row,
            "output": json.loads(row["output_json"]) if row.get("output_json") else None,
            "state": json.loads(row["state_json"]),
        }
        for row in rows
    ]
    return session, turns, active_id, _walk_active_path(rows, active_id)


@router.get("/{session_id}/timeline")
def get_session_timeline(session_id: str) -> dict[str, object]:
    """Return the complete branching tree with lightweight node summaries."""
    loaded = _load_turns(session_id)
    if not loaded:
        raise HTTPException(status_code=404, detail="Session not found")
    session, turns, active_id, active_path = loaded

    nodes: list[dict[str, object]] = []
    for turn in turns:
        row, output, state = turn["row"], turn["output"], turn["state"]
        action = row.get("player_action") or "会话起点"
        nodes.append({
            "id": row["id"],
            "parent_id": row["parent_turn_id"],
            "depth": row["depth"],
            "label": "会话起点" if row["parent_turn_id"] is None else action[:36],
            "player_action": row.get("player_action", ""),
            "narration_preview": (output or {}).get("narration", "")[:100],
            "location": state.get("current_location", ""),
            "turn": state.get("turn", row["depth"]),
            "source": row.get("source", "scripted"),
            "created_at": row["created_at"],
            "is_active": row["id"] == active_id,
            "is_on_active_path": row["id"] in active_path,
        })
    return {
        "session_id": session_id,
        "active_node_id": active_id,
        "nodes": nodes,
        "campaign_filename": session.get("campaign_filename"),
    }


@router.get("/{session_id}/memory-trace")
def get_memory_trace(session_id: str) -> dict[str, object]:
    """What each turn declared it remembered against what state actually kept.

    Name lists only. The prompts themselves live on the node detail route,
    which is fetched one turn at a time.
    """
    loaded = _load_turns(session_id)
    if not loaded:
        raise HTTPException(status_code=404, detail="Session not found")
    _session, turns, _active_id, active_path = loaded

    return {
        "session_id": session_id,
        "caps": CAPS,
        "nodes": [
            {
                "node_id": turn["row"]["id"],
                "parent_id": turn["row"]["parent_turn_id"],
                "depth": turn["row"]["depth"],
                "turn": turn["state"].get("turn", turn["row"]["depth"]),
                "is_on_active_path": turn["row"]["id"] in active_path,
                **state_manager.memory_trace_entry(turn["output"], turn["state"]),
            }
            for turn in turns
        ],
    }


def _turn_context(model_output_id: object) -> dict[str, object]:
    """What was injected into this turn's prompt, plus its cost.

    Always returns the same keys so the client can tell "nothing was recorded"
    apart from "an empty prompt was recorded".
    """
    empty: dict[str, object] = {
        "recorded": False,
        "retrieved_chunks": [],
        "token_count": 0,
        "latency_ms": 0,
        "word_count": 0,
        "prompt_sections": {},
        "prompt_text": "",
    }
    if model_output_id is None:
        return empty
    row = db.get_model_output(int(model_output_id))
    if not row:
        return empty
    sections = json.loads(row["prompt_sections_json"] or "{}")
    prompt_text = row["prompt_text"]
    return {
        # Turns stored before the prompt was recorded still have a row here.
        "recorded": bool(prompt_text or sections),
        "retrieved_chunks": json.loads(row["retrieved_chunks_json"] or "[]"),
        "token_count": row["token_count"],
        "latency_ms": row["latency_ms"],
        "word_count": row["word_count"],
        "prompt_sections": sections,
        "prompt_text": prompt_text,
    }


@router.get("/{session_id}/timeline/{node_id}")
def get_timeline_node(session_id: str, node_id: int) -> dict[str, object]:
    row = db.get_story_turn(session_id, node_id)
    if not row:
        raise HTTPException(status_code=404, detail="Timeline node not found")
    state = json.loads(row["state_json"])
    state_manager.sanitize_state(state)
    return {
        "context": _turn_context(row.get("model_output_id")),
        "id": row["id"],
        "session_id": session_id,
        "parent_id": row["parent_turn_id"],
        "depth": row["depth"],
        "player_action": row["player_action"],
        "output": json.loads(row["output_json"]) if row["output_json"] else None,
        "state": state,
        "campaign_progress": json.loads(row["campaign_progress_json"] or "{}"),
        "model": row["model"],
        "source": row["source"],
        "created_at": row["created_at"],
    }


@router.post("/{session_id}/timeline/{node_id}/activate")
def activate_timeline_node(session_id: str, node_id: int) -> dict[str, object]:
    snapshot = db.activate_story_turn(session_id, node_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail="Timeline node not found")

    progress = snapshot.get("campaign_progress") or {}
    slot_name = str(progress.get("slot_name") or "default")
    campaign_manager_cache.invalidate(session_id, slot_name)
    knowledge_service.scenario_generator.invalidate_timeline_caches(session_id, slot_name)

    state = dict(snapshot["state"])
    state_manager.sanitize_state(state)
    session = state_manager.get_session_payload(session_id)
    return {
        "status": "activated",
        "session_id": session_id,
        "active_turn_id": node_id,
        "state": state,
        "output": snapshot.get("output"),
        "model": snapshot.get("model"),
        "campaign_filename": session.get("campaign_filename") if session else None,
        "slot_name": slot_name,
    }
