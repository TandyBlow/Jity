"""Knowledge reload must not reset an active game's runtime coordination."""

import asyncio
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.database import Database
from app.dependencies.knowledge_service import KnowledgeService
from app.schemas import GenerateRequest
from app.services.game_state import GameStateManager
from app.services.knowledge_base import KnowledgeBase
from app.services.prompt_builder import PromptBuilder


def test_startup_loads_knowledge_and_builds_retriever_once(tmp_path):
    """A fresh app import exercises the actual dependency wiring."""
    backend = Path(__file__).resolve().parents[1]
    code = """
from unittest.mock import patch
from app.services.knowledge_base import KnowledgeBase
from app.services.retriever import RAGRetriever

loads, builds = [], []
load_chunks, build_retriever = KnowledgeBase.load_chunks, RAGRetriever.__init__

def load(self):
    loads.append(self)
    return load_chunks(self)

def build(self, *args, **kwargs):
    builds.append(self)
    build_retriever(self, *args, **kwargs)

with patch.object(KnowledgeBase, 'load_chunks', load), patch.object(RAGRetriever, '__init__', build):
    from app.main import app
    from app.dependencies import knowledge_service
    assert len(loads) == len(builds) == 1, (len(loads), len(builds))
    assert builds[0] is knowledge_service.scenario_generator.retriever
    assert knowledge_service.chunks
"""
    env = {
        **os.environ,
        "PYTHONPATH": str(backend),
        "DATABASE_FILE": str(tmp_path / "startup.sqlite3"),
        "BACKGROUNDS_DIR": str(tmp_path / "backgrounds"),
        "KNOWLEDGE_DIR": str(backend.parent / "knowledge"),
        "DEEPSEEK_API_KEY": "",
        "IMAGE_API_KEY": "",
        "PROMPT_LOGGING_ENABLED": "false",
    }
    result = subprocess.run(
        [sys.executable, "-c", code], cwd=tmp_path, env=env,
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.fixture
def knowledge_runtime(tmp_path):
    knowledge_dir = tmp_path / "knowledge"
    knowledge_dir.mkdir()
    source = knowledge_dir / "world_lore.md"
    source.write_text("# 旧档案\n旧版本的学院资料。", encoding="utf-8")
    db = Database(tmp_path / "game.sqlite3")
    service = KnowledgeService(
        knowledge=KnowledgeBase(db, knowledge_dir, tmp_path / "missing.md"),
        embedding_client=None,
        db=db,
        state_manager=GameStateManager(db),
        prompt_builder=PromptBuilder(),
        llm_client=MagicMock(),
        settings=SimpleNamespace(llm_model="test"),
    )
    return service, source


@pytest.mark.asyncio
async def test_reload_preserves_active_turn_lock_memory_and_retrieval(knowledge_runtime, monkeypatch):
    service, source = knowledge_runtime
    generator = service.scenario_generator
    original_retriever = service.retriever
    entered, release, background_release = asyncio.Event(), asyncio.Event(), asyncio.Event()
    started = []

    async def delayed_retrieval(query):
        entered.set()
        await release.wait()
        return original_retriever.retrieve(query)

    async def retrieve_turn(session_id, request):
        started.append(request.player_action)
        return await generator.retriever.retrieve_async(request.player_action)

    monkeypatch.setattr(original_retriever, "retrieve_async", delayed_retrieval)
    monkeypatch.setattr(generator, "_generate_locked", retrieve_turn)
    controller = object()
    generator._memory_controllers["player"] = controller
    background = asyncio.create_task(background_release.wait())
    generator._memory_jobs["other-player"] = background
    generator._memory_tasks.add(background)
    first = asyncio.create_task(generator.generate("player", GenerateRequest(player_action="旧档案")))
    second = None
    try:
        await asyncio.wait_for(entered.wait(), timeout=2)
        lock = generator._generation_locks["player"]
        source.write_text("# 新档案\n新版本的学院资料。", encoding="utf-8")
        assert await asyncio.to_thread(service.reload) == 1
        assert service.scenario_generator is generator
        assert generator._generation_locks["player"] is lock
        assert generator._memory_controllers["player"] is controller
        assert generator._memory_jobs["other-player"] is background
        assert background in generator._memory_tasks and not background.done()

        second = asyncio.create_task(service.scenario_generator.generate(
            "player", GenerateRequest(player_action="新档案"),
        ))
        await asyncio.sleep(0)
        assert started == ["旧档案"]  # The replacement still uses the same session lock.
        release.set()
        old_result, new_result = await asyncio.wait_for(asyncio.gather(first, second), timeout=2)
        assert old_result[0]["title"] == "旧档案"
        assert new_result[0]["title"] == "新档案"
        assert service.chunks is service.retriever.chunks
        assert service.chunks[0]["title"] == "新档案"
    finally:
        release.set()
        background_release.set()
        tasks = [first, background] + ([second] if second is not None else [])
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


def test_failed_reload_keeps_live_retrieval(knowledge_runtime, monkeypatch):
    service, source = knowledge_runtime
    original_retriever = service.retriever
    source.write_text("# 新档案\n新版本的学院资料。", encoding="utf-8")

    def fail_build(*args, **kwargs):
        raise RuntimeError("retriever build failed")

    with monkeypatch.context() as patch:
        patch.setattr(sys.modules[KnowledgeService.__module__], "RAGRetriever", fail_build)
        with pytest.raises(RuntimeError, match="retriever build failed"):
            service.reload()
    assert service.retriever is original_retriever
    assert service.chunks[0]["title"] == "旧档案"
    assert service.retriever.retrieve("旧档案")[0]["title"] == "旧档案"
    assert service.reload() == 1
    assert service.chunks[0]["title"] == "新档案"
