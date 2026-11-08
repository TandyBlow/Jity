"""Runtime review regressions: real state/transactions, no network models."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.database import Database
from app.repositories.campaign_progress import CampaignProgressRepository
from app.schemas import GenerateRequest, StoryOutput
from app.schemas.campaign import AnchorEvent, EndingRoute
from app.services.game_state import GameStateManager
from app.services.prompt_builder import PromptBuilder
from tests.test_turn_commit_consistency import Harness


@pytest.fixture(autouse=True)
def no_embeddings(monkeypatch):
    from app import dependencies
    monkeypatch.setattr(dependencies, "embedding_client", None)


def slot_history(tmp_path):
    db = Database(tmp_path / "slots.sqlite3")
    states = GameStateManager(db)
    session = states.create_session("存档回归", "mock")
    sid = session["session_id"]
    db.set_session_campaign_id(sid, sid, "default_campaign.json", "A")

    def commit(parent, turn, slot="A"):
        return db.commit_story_turn(
            session_id=sid, expected_parent_id=parent, player_action=f"行动{turn}",
            output={"narration": f"剧情{turn}"}, state={**session["state"], "turn": turn},
            campaign_progress={
                "campaign_id": sid, "slot_name": slot, "arc_index": 0, "session_index": 0,
                "turn_in_session": turn, "turns_total": turn,
                "revealed_anchors": json.dumps([f"anchor-{turn}"]),
                "npc_relations": json.dumps([{"name": "诺诺", "affinity": turn}]),
                "recap_compressed": f"回顾{turn}",
            }, model="mock", source="llm", model_output_id=None,
        )

    first = commit(session["active_turn_id"], 1)
    CampaignProgressRepository(db).create_slot(db.get_session(sid), "B", "A")
    db.set_session_active_slot(sid, "A")
    second = commit(first, 2)
    return db, states, sid, first, second, commit


def test_loading_copied_slot_does_not_rewind_source_slot(tmp_path, monkeypatch):
    from app.routers import slots
    db, states, sid, first, second, commit = slot_history(tmp_path)
    monkeypatch.setattr(slots, "db", db)
    monkeypatch.setattr(slots, "state_manager", states)
    monkeypatch.setattr(slots, "campaign_manager_cache", SimpleNamespace(invalidate=Mock()))
    monkeypatch.setattr(slots, "knowledge_service", SimpleNamespace(
        scenario_generator=SimpleNamespace(invalidate_timeline_caches=Mock())))
    monkeypatch.setattr(slots, "get_campaign_manager_for_session", Mock())
    app = FastAPI()
    app.include_router(slots.router)
    client = TestClient(app)
    source = dict(db.read_campaign_progress(sid, "A"))
    copied = db.read_campaign_progress(sid, "B")
    original_node = db.get_story_turn(sid, first)

    response = client.post(f"/campaigns/slots/{copied['id']}/load")
    assert response.status_code == 200
    assert response.json()["session"]["active_turn_id"] == first
    assert db.get_session(sid)["active_slot_name"] == "B"
    assert dict(db.read_campaign_progress(sid, "A")) == source
    assert db.get_story_turn(sid, first) == original_node
    assert db.read_campaign_progress(sid, "B")["recap_compressed"] == "回顾1"

    branch = commit(first, 2, "B")
    assert db.get_story_turn(sid, branch)["parent_turn_id"] == first
    assert db.read_campaign_progress(sid, "A")["head_turn_id"] == second
    loaded_a = client.post(f"/campaigns/slots/{source['id']}/load")
    assert loaded_a.json()["session"]["active_turn_id"] == second
    assert db.read_campaign_progress(sid, "B")["head_turn_id"] == branch


def test_timeline_restore_uses_active_slot(tmp_path):
    db, _, sid, first, _, _ = slot_history(tmp_path)
    db.set_session_active_slot(sid, "B")
    source = dict(db.read_campaign_progress(sid, "A"))
    snapshot = db.activate_story_turn(sid, first)
    assert snapshot["campaign_progress"]["slot_name"] == "B"
    assert dict(db.read_campaign_progress(sid, "A")) == source


def test_restore_empty_root_reports_active_slot_without_inventing_progress(tmp_path):
    db, _, sid, _, _, _ = slot_history(tmp_path)
    db.set_session_active_slot(sid, "B")
    root = next(node for node in db.list_story_turns(sid) if node["parent_turn_id"] is None)
    source = dict(db.read_campaign_progress(sid, "A"))
    snapshot = db.activate_story_turn(sid, root["id"])
    assert snapshot["slot_name"] == "B"
    assert snapshot["campaign_progress"] == {}
    assert dict(db.read_campaign_progress(sid, "A")) == source


def test_slot_restore_rolls_back_state_and_progress_together(tmp_path):
    db, _, sid, first, _, _ = slot_history(tmp_path)
    source = dict(db.read_campaign_progress(sid, "A"))
    db.set_session_active_slot(sid, "A")
    before = dict(db.get_session(sid))
    with db.connect() as conn:
        conn.execute("""CREATE TRIGGER reject_restore BEFORE UPDATE ON campaign_progress
                        WHEN NEW.slot_name = 'B' BEGIN SELECT RAISE(ABORT, 'injected'); END""")
    import sqlite3
    with pytest.raises(sqlite3.IntegrityError, match="injected"):
        db.activate_story_turn(sid, first, slot_name="B")
    assert dict(db.get_session(sid)) == before
    assert dict(db.read_campaign_progress(sid, "A")) == source


EVIDENCE = "你在门边看见了清晰的红色标记。"


def anchor_output(**overrides):
    fields = dict(
        narration=EVIDENCE, options=["继续"],
        anchor_completions=[{"anchor_id": "clue", "evidence": EVIDENCE}],
        memory_updates={"world_facts_upserted": [
            {"name": "发现红色标记", "status": "known", "description": EVIDENCE},
        ]},
    )
    fields.update(overrides)
    return StoryOutput(**fields)


def anchor_runtime(tmp_path, output):
    h = Harness(tmp_path)
    scene = h.manager.campaign.arcs[0].sessions[0]
    scene.anchor_events = [AnchorEvent(id="clue", name="发现红色标记", description=EVIDENCE)]
    scene.completion_anchors = ["clue"]
    del h.gen._build_prompt
    h.gen.prompt_builder = PromptBuilder()
    h.gen.retriever = SimpleNamespace(retrieve_async=AsyncMock(return_value=[]))
    h.llm.generate = AsyncMock(side_effect=lambda *a, **k: (output.model_copy(deep=True), 1))
    return h


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid", ["missing", "quote", "fact", "suspected", "unknown_id"])
async def test_unfulfilled_anchor_does_not_advance_and_can_retry(tmp_path, invalid):
    output = anchor_output()
    if invalid == "missing":
        output.anchor_completions = []
    elif invalid == "quote":
        output.narration = "你在大厅休息，尚未进行调查。"
    elif invalid == "fact":
        output.memory_updates.world_facts_upserted = []
    elif invalid == "suspected":
        output.memory_updates.world_facts_upserted[0].status = "suspected"
    else:
        output.anchor_completions[0].anchor_id = "unoffered-anchor"
    h = anchor_runtime(tmp_path, output)
    first = await h.generate()
    await h.gen._wait_memory(h.session_id)
    assert h.manager.progress.revealed_anchors == []
    assert first.output.anchor_completions == []
    assert not h.manager.is_closing_pending()

    h.llm.generate = AsyncMock(return_value=(anchor_output(), 1))
    second = await h.generate()
    await h.gen._wait_memory(h.session_id)
    node = h.db.get_story_turn(h.session_id, second.timeline_node_id)
    assert h.manager.progress.revealed_anchors == ["clue"]
    assert json.loads(json.loads(node["campaign_progress_json"])["revealed_anchors"]) == ["clue"]
    assert json.loads(node["output_json"])["anchor_completions"][0]["evidence"] == EVIDENCE


@pytest.mark.asyncio
async def test_confirmed_anchor_rolls_back_with_failed_commit(tmp_path, monkeypatch):
    h = anchor_runtime(tmp_path, anchor_output())
    before = h.progress_row()
    with monkeypatch.context() as patch:
        patch.setattr(h.db, "commit_story_turn", Mock(side_effect=RuntimeError("injected")))
        with pytest.raises(RuntimeError, match="injected"):
            await h.generate()
    assert h.progress_row() == before
    assert h.manager.progress.revealed_anchors == []
    assert h.manager._anchors.pending_anchor_triggers == []
    assert h.manager._anchors._confirmed_anchor_ids == set()
    response = await h.generate()
    await h.gen._wait_memory(h.session_id)
    assert h.manager.progress.revealed_anchors == ["clue"]
    assert response.output.anchor_completions


async def finale_runtime(tmp_path, action, required_items=()):
    h = Harness(tmp_path)
    await h.generate()
    await h.gen._wait_memory(h.session_id)
    h.manager.progress.arc_index = len(h.manager.campaign.arcs) - 1
    h.manager.progress.session_index = len(h.manager.campaign.arcs[-1].sessions) - 1
    h.manager.progress.turn_in_session = 3
    h.manager.progress.turns_total = 30
    h.manager.campaign.ending_routes = [EndingRoute(
        id="success", name="封印关闭", category="good", requirements=[],
        required_items=list(required_items), trigger_phrases=[action], resolution="封印关闭，众人安全离开。",
    )]
    h.manager.save_progress()
    return h


@pytest.mark.asyncio
@pytest.mark.parametrize("budget", [False, True])
async def test_blocked_action_cannot_select_success_but_budget_can_close(tmp_path, budget):
    action = "使用古钥匙打开封印"
    h = await finale_runtime(tmp_path, action)
    if budget:
        h.manager.progress.turns_total = h.manager.resolve_max_turns_per_campaign() - 1
        h.manager.save_progress()
    h.llm.generate.reset_mock()
    response = await h.gen.generate(h.session_id, GenerateRequest(
        player_action=action, timeline_node_id=h.head(),
    ))
    await h.gen._wait_memory(h.session_id)
    assert response.output.game_over_reason != "封印关闭"
    assert response.output.game_over is budget
    if not budget:
        assert response.source == "examiner_blocked"
        assert "古钥匙" in response.output.narration
        h.llm.generate.assert_not_awaited()


@pytest.mark.asyncio
async def test_ending_rewrite_keeps_the_consequences_that_qualified_it(tmp_path):
    action = "决定关闭封印"
    h = await finale_runtime(tmp_path, action, required_items=["终局钥匙"])
    before = h.state_manager.get_session_payload(h.session_id)["state"]
    before["items"] = [{"name": "旧通行卡", "status": "owned"}]
    h.state_manager.save_state(h.session_id, "测试", "mock", before)
    h.llm.generate = AsyncMock(return_value=(StoryOutput(
        narration="你付出旧通行卡的代价，在密室找到终局钥匙并关闭封印。",
        current_location="密室", health_delta=-5,
        items_gained=[{"name": "终局钥匙", "status": "owned"}],
        items_lost=[{"name": "旧通行卡", "status": "consumed"}],
        quests_updated=[{"name": "关闭封印", "status": "completed"}],
        memory_updates={"world_facts_upserted": [{"name": "封印已关闭", "description": "密室恢复安全"}]},
        npc_relations_delta=[{"name": "诺诺", "sentiment": "positive"}],
    ), 1))
    response = await h.gen.generate(h.session_id, GenerateRequest(player_action=action, timeline_node_id=h.head()))
    await h.gen._wait_memory(h.session_id)
    assert response.output.game_over_reason == "封印关闭"
    assert {item["name"] for item in response.state["items"]} == {"终局钥匙"}
    assert response.state["current_location"] == "密室"
    assert response.state["health"] == before["health"] - 5
    assert any(q["name"] == "关闭封印" and q["status"] == "completed" for q in response.state["quests"])
    assert any(f["name"] == "封印已关闭" for f in response.state["world_facts"])
    rewrite = next(c for c in h.llm.generate_text.await_args_list if c.kwargs.get("purpose") == "ending_narrative")
    assert "终局钥匙" in rewrite.args[0] and "密室" in rewrite.args[0]
    node = h.db.get_story_turn(h.session_id, response.timeline_node_id)
    assert h.state_manager.sanitize_state(json.loads(node["state_json"])) == response.state
    assert json.loads(node["output_json"])["items_gained"] == response.output.items_gained
    progress = json.loads(node["campaign_progress_json"])
    relations = json.loads(progress["npc_relations"])
    assert next(r["affinity"] for r in relations if r["name"] == "诺诺") == 1
    h.db.activate_story_turn(h.session_id, response.timeline_node_id)
    restored = h.state_manager.get_session_payload(h.session_id)["state"]
    assert restored["items"] == response.state["items"]


@pytest.mark.asyncio
async def test_new_facts_npcs_and_quests_survive_caps_commit_and_restore(tmp_path):
    h = Harness(tmp_path)
    state = h.state_manager.get_session_payload(h.session_id)["state"]
    for kind, count in [("npcs", 15), ("quests", 10), ("world_facts", 15)]:
        state[kind] = [{"name": f"旧{kind}{i}"} for i in range(count)]
    h.state_manager.save_state(h.session_id, "测试", "mock", state)
    h.llm.generate = AsyncMock(return_value=(StoryOutput(
        narration="你遇见守门人，得知新线索，并接下新任务。",
        memory_updates={
            "npcs_upserted": [{"name": "新守门人"}],
            "quests_upserted": [{"name": "新任务"}],
            "world_facts_upserted": [{"name": "新线索", "description": "最终钥匙在地下室"}],
        },
    ), 1))
    response = await h.generate()
    await h.gen._wait_memory(h.session_id)
    for kind, count, name in [("npcs", 16, "新守门人"), ("quests", 11, "新任务"), ("world_facts", 16, "新线索")]:
        assert len(response.state[kind]) == count
        assert name in response.memory[kind]["held"]
        assert response.caps[kind] is None
    h.db.activate_story_turn(h.session_id, response.timeline_node_id)
    restored = h.state_manager.get_session_payload(h.session_id)["state"]
    for kind in ("npcs", "quests", "world_facts"):
        assert restored[kind] == response.state[kind]
