import json

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.database import Database
from app.schemas import (
    CreateSessionRequest,
    GenerateRequest,
    GenerateResponse,
    SessionHistoryResponse,
    SessionResponse,
    StoryOutput,
)
from pathlib import Path

from app.services.campaign_generator import CampaignGenerationError, CampaignGenerator, NovelIngestor
from app.services.campaign_manager import CampaignManager
from app.services.embedding_client import EmbeddingClient
from app.services.evaluation import EvaluationModule
from app.services.game_state import GameStateManager
from app.services.health_monitor import HealthMonitor
from app.services.knowledge_base import KnowledgeBase
from app.services.llm_client import LLMClient, MissingAPIKeyError
from app.services.prompt_builder import PromptBuilder
from app.services.retriever import RAGRetriever
from app.services.scenario_generator import ScenarioGenerationError, ScenarioGenerator
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
campaign_managers: dict[tuple[str, str], CampaignManager] = {}


def build_campaign_manager() -> CampaignManager:
    return CampaignManager(
        db=db,
        campaigns_dir=settings.campaigns_dir,
        scripted_story=scripted_story,
        prompt_builder=prompt_builder,
        llm_client=llm_client,
        health_monitor=health_monitor,
    )


def get_campaign_manager_for_session(session_id: str, slot_name: str = "default") -> CampaignManager | None:
    """Return the manager for this session/slot, loading it from persisted metadata if needed."""
    session_row = db.get_session(session_id)
    if not session_row or not session_row["campaign_filename"]:
        return None
    active_slot = slot_name or session_row["active_slot_name"] or "default"
    key = (session_id, active_slot)
    if key in campaign_managers:
        return campaign_managers[key]

    campaign_path = settings.campaigns_dir / session_row["campaign_filename"]
    if not campaign_path.exists():
        return None
    manager = build_campaign_manager()
    manager.load(
        campaign_path,
        campaign_id=session_row["campaign_id"] or session_id,
        slot_name=active_slot,
    )
    campaign_managers[key] = manager
    return manager


campaign_generator = CampaignGenerator(
    llm_client=llm_client,
    prompt_builder=prompt_builder,
    db=db,
    output_dir=settings.campaigns_dir,
)
evaluation_module = EvaluationModule()
scenario_generator = ScenarioGenerator(
    db=db,
    state_manager=state_manager,
    retriever=retriever,
    prompt_builder=prompt_builder,
    llm_client=llm_client,
    scripted_story=scripted_story,
    campaign_manager_provider=get_campaign_manager_for_session,
    default_model=settings.llm_model,
)

app = FastAPI(title="Jity RPG Scenario Generator API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin, "http://127.0.0.1:3000", "http://localhost:3001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/campaigns/generate")
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


@app.post("/campaigns/generate-from-novel")
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


@app.get("/campaigns")
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
            continue
    return {"campaigns": campaign_files}


@app.post("/campaigns/save")
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


@app.get("/campaigns/slots")
def list_slots(session_id: str | None = None) -> dict[str, object]:
    """List save slots, optionally limited to one game session."""
    where_clause = ""
    params: tuple[str, ...] = ()
    if session_id:
        where_clause = "WHERE campaign_progress.campaign_id = ?"
        params = (session_id,)

    with db.connect() as conn:
        rows = conn.execute(
            f"""SELECT
                 campaign_progress.id,
                 campaign_progress.campaign_id,
                 campaign_progress.slot_name,
                 campaign_progress.arc_index,
                 campaign_progress.session_index,
                 campaign_progress.turn_in_session,
                 campaign_progress.updated_at,
                 game_sessions.campaign_filename,
                 game_sessions.active_slot_name
               FROM campaign_progress
               JOIN game_sessions ON game_sessions.id = campaign_progress.campaign_id
               {where_clause}
               ORDER BY campaign_progress.updated_at DESC""",
            params,
        ).fetchall()
        slots = [{
            "id": row["id"],
            "campaign_id": row["campaign_id"],
            "slot_name": row["slot_name"],
            "arc_index": row["arc_index"],
            "session_index": row["session_index"],
            "turn_in_session": row["turn_in_session"],
            "last_played": row["updated_at"],
            "campaign_filename": row["campaign_filename"],
            "is_active": row["slot_name"] == row["active_slot_name"],
        } for row in rows]
    return {"slots": slots}


@app.post("/campaigns/slots")
def create_slot(request: dict[str, str]) -> dict[str, object]:
    """Create a named save slot for the current game session."""
    slot_name = request.get("slot_name", "").strip()
    if not slot_name:
        raise HTTPException(status_code=400, detail="slot_name is required")
    import re
    if not re.match(r'^[a-zA-Z0-9_一-鿿]+$', slot_name):
        raise HTTPException(status_code=400, detail="slot_name contains invalid characters")
    session_id = request.get("session_id") or request.get("campaign_id")
    if not session_id:
        raise HTTPException(status_code=400, detail="session_id is required")

    session_row = db.get_session(session_id)
    if not session_row:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")

    campaign_id = session_row["campaign_id"] or session_id
    source_slot = request.get("source_slot_name") or session_row["active_slot_name"] or "default"
    if db.read_campaign_progress(campaign_id, slot_name):
        raise HTTPException(status_code=409, detail=f"Slot '{slot_name}' already exists")

    source = db.read_campaign_progress(campaign_id, source_slot) or {}
    db.write_campaign_progress(
        campaign_id=campaign_id,
        slot_name=slot_name,
        arc_index=int(source.get("arc_index", 0)),
        session_index=int(source.get("session_index", 0)),
        turn_in_session=int(source.get("turn_in_session", 0)),
        fsm_state=str(source.get("fsm_state", "active/session_active")),
        revealed_anchors=json.loads(source.get("revealed_anchors", "[]")) if source else [],
        completed_arcs=json.loads(source.get("completed_arcs", "[]")) if source else [],
        recap_compressed=str(source.get("recap_compressed", "")),
        recap_full=str(source.get("recap_full", "")),
    )
    if source.get("npc_relations"):
        db.update_npc_relations(campaign_id, source["npc_relations"], slot_name)
    db.set_session_active_slot(session_id, slot_name)
    return {"status": "created", "slot_name": slot_name, "campaign_id": campaign_id}


@app.post("/campaigns/slots/{slot_id}/load")
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


@app.delete("/campaigns/slots/{slot_name}")
def delete_slot(slot_name: str) -> dict[str, object]:
    """Delete a save slot by name."""
    with db.connect() as conn:
        result = conn.execute(
            "DELETE FROM campaign_progress WHERE slot_name = ?", (slot_name,)
        )
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail=f"Slot '{slot_name}' not found")
    return {"status": "deleted", "slot_name": slot_name}


@app.get("/campaigns/{filename}")
def get_campaign_file(filename: str) -> dict[str, object]:
    """Load a single campaign.json file by filename."""
    fpath = settings.campaigns_dir / filename
    if not fpath.exists():
        raise HTTPException(status_code=404, detail=f"Campaign file not found: {filename}")

    try:
        data = json.loads(fpath.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read campaign: {exc}")

    return {"filename": filename, "campaign": data}


@app.get("/sessions/{session_id}/progress")
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


@app.get("/health")
def health() -> dict[str, object]:
    return {
        "status": "ok",
        "database": str(settings.database_file),
        "knowledge_chunks": len(chunks),
        "retriever": "faiss" if retriever.index is not None else "numpy",
    }


@app.get("/models")
def models() -> dict[str, list[str]]:
    return {"models": [settings.llm_model, "deepseek-chat", "deepseek-reasoner"]}


@app.post("/sessions", response_model=SessionResponse)
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
            campaign_managers[(session_id, slot_name)] = manager
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

    return SessionResponse(**payload)


@app.get("/sessions/{session_id}", response_model=SessionResponse)
def get_session(session_id: str) -> SessionResponse:
    payload = state_manager.get_session_payload(session_id)
    if not payload:
        raise HTTPException(status_code=404, detail="Session not found")
    return SessionResponse(**payload)


@app.get("/sessions/{session_id}/history", response_model=SessionHistoryResponse)
def get_session_history(session_id: str) -> SessionHistoryResponse:
    payload = state_manager.get_session_payload(session_id)
    if not payload:
        raise HTTPException(status_code=404, detail="Session not found")
    return SessionHistoryResponse(session_id=session_id, messages=db.get_messages(session_id))


@app.post("/sessions/{session_id}/generate", response_model=GenerateResponse)
async def generate(session_id: str, request: GenerateRequest) -> GenerateResponse:
    try:
        response = await scenario_generator.generate(session_id, request)
    except MissingAPIKeyError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ScenarioGenerationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if not response:
        raise HTTPException(status_code=404, detail="Session not found")
    return response


@app.post("/evaluate")
def evaluate(output: StoryOutput) -> dict[str, int]:
    return evaluation_module.score(output)


@app.post("/knowledge/reload")
def reload_knowledge() -> dict[str, object]:
    global chunks, retriever, scenario_generator
    chunks = knowledge.load_chunks()
    retriever = RAGRetriever(chunks, embedding_client=embedding_client)
    scenario_generator = ScenarioGenerator(
        db=db,
        state_manager=state_manager,
        retriever=retriever,
        prompt_builder=prompt_builder,
        llm_client=llm_client,
        scripted_story=scripted_story,
        campaign_manager_provider=get_campaign_manager_for_session,
        default_model=settings.llm_model,
    )
    return {"status": "reloaded", "knowledge_chunks": len(chunks)}
