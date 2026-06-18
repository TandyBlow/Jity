from __future__ import annotations

import json as json_module

from fastapi import FastAPI, HTTPException
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

from app.services.campaign_generator import CampaignGenerationError, CampaignGenerator
from app.services.campaign_manager import CampaignManager
from app.services.evaluation import EvaluationModule
from app.services.game_state import GameStateManager
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
retriever = RAGRetriever(chunks)
prompt_builder = PromptBuilder()
llm_client = LLMClient(settings)
scripted_story = ScriptedStoryService()
campaign_manager = CampaignManager(
    db=db,
    campaigns_dir=settings.campaigns_dir,
    scripted_story=scripted_story,
    prompt_builder=prompt_builder,
    llm_client=llm_client,
)
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
    campaign_manager=campaign_manager,
    default_model=settings.llm_model,
)

app = FastAPI(title="Jity RPG Scenario Generator API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin, "http://127.0.0.1:3000"],
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


@app.get("/campaigns")
def list_campaigns() -> dict[str, object]:
    """List all saved campaign.json files in campaigns_dir."""
    campaigns_dir = settings.campaigns_dir
    if not campaigns_dir.exists():
        return {"campaigns": []}

    campaign_files: list[dict[str, object]] = []
    for fpath in sorted(campaigns_dir.glob("*.json")):
        try:
            data = json_module.loads(fpath.read_text(encoding="utf-8"))
            campaign_files.append({
                "filename": fpath.name,
                "title": data.get("title", fpath.stem),
                "version": data.get("version", 1),
                "arc_count": len(data.get("arcs", [])),
            })
        except (json_module.JSONDecodeError, OSError):
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
    fpath.write_text(json_module.dumps(campaign_data, ensure_ascii=False, indent=2), encoding="utf-8")

    return {"status": "saved", "filename": filename, "path": str(fpath)}


@app.get("/campaigns/{filename}")
def get_campaign_file(filename: str) -> dict[str, object]:
    """Load a single campaign.json file by filename."""
    fpath = settings.campaigns_dir / filename
    if not fpath.exists():
        raise HTTPException(status_code=404, detail=f"Campaign file not found: {filename}")

    try:
        data = json_module.loads(fpath.read_text(encoding="utf-8"))
    except (json_module.JSONDecodeError, OSError) as exc:
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

    row = db.read_campaign_progress(session_id)
    if row:
        progress_data["revealed_anchors"] = json_module.loads(
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
    retriever = RAGRetriever(chunks)
    scenario_generator = ScenarioGenerator(
        db=db,
        state_manager=state_manager,
        retriever=retriever,
        prompt_builder=prompt_builder,
        llm_client=llm_client,
        scripted_story=scripted_story,
        campaign_manager=campaign_manager,
        default_model=settings.llm_model,
    )
    return {"status": "reloaded", "knowledge_chunks": len(chunks)}
