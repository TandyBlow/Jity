from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.database import Database
from app.schemas import CreateSessionRequest, GenerateRequest, GenerateResponse, SessionResponse, StoryOutput
from app.services.evaluation import EvaluationModule
from app.services.game_state import GameStateManager
from app.services.knowledge_base import KnowledgeBase
from app.services.llm_client import LLMClient
from app.services.prompt_builder import PromptBuilder
from app.services.retriever import RAGRetriever
from app.services.scenario_generator import ScenarioGenerator

settings = get_settings()
db = Database(settings.database_file)
knowledge = KnowledgeBase(db, settings.knowledge_dir, settings.rulebook_file)
chunks = knowledge.load_chunks()
state_manager = GameStateManager(db)
retriever = RAGRetriever(chunks)
prompt_builder = PromptBuilder()
llm_client = LLMClient(settings)
evaluation_module = EvaluationModule()
scenario_generator = ScenarioGenerator(
    db=db,
    state_manager=state_manager,
    retriever=retriever,
    prompt_builder=prompt_builder,
    llm_client=llm_client,
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


@app.post("/sessions/{session_id}/generate", response_model=GenerateResponse)
async def generate(session_id: str, request: GenerateRequest) -> GenerateResponse:
    response = await scenario_generator.generate(session_id, request)
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
        default_model=settings.llm_model,
    )
    return {"status": "reloaded", "knowledge_chunks": len(chunks)}
