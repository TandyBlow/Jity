"""Regressions for durable, branch-local campaign memory without network calls."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pytest
from httpx import ASGITransport, AsyncClient

from app.database import Database
from app.exceptions import CampaignRequiredError
from app.schemas import GenerateRequest, StoryOutput
from app.schemas.agent_io import EpisodeSummary, ItemState, MemoryRecord
from app.schemas.game.memory import ItemMemory, MemoryUpdates
from app.services.game_state import GameStateManager
from app.services.memory.forgetting import compute_score, forget_step
from app.services.memory.memory_controller import MemoryController
from app.services.memory.nsb import NarrativeSummarizationBranch
from app.services.memory.score_tracker import ScoreTracker
from app.services.scenario_generator import ScenarioGenerator
from tests.test_campaign_openings import runtime  # noqa: F401


def episode(identifier="ep", **kwargs):
    return EpisodeSummary(episode_id=identifier, turn_start=1, turn_end=6, summary="找到密室钥匙", **kwargs)


@pytest.mark.asyncio
async def test_failed_summary_retains_input_and_retries():
    llm = MagicMock(generate_json=AsyncMock(side_effect=[RuntimeError("offline"), {"summary": "六回合摘要"}]))
    nsb = NarrativeSummarizationBranch(llm)
    for turn in range(1, 7):
        nsb.add_turn("观察", "线索", turn)
    assert await nsb.summarize_level1(0, 6) is None
    assert len(nsb._turn_buffer) == 6
    summary = await nsb.summarize_level1(0, 6)
    assert (summary.turn_start, summary.turn_end) == (1, 6)
    assert nsb._turn_buffer == []


@pytest.mark.asyncio
async def test_failed_promotion_keeps_children_and_retries_without_new_l1():
    llm = MagicMock(generate_json=AsyncMock(side_effect=[RuntimeError("offline"), {"summary": "大事记"}]))
    mc = MemoryController(llm, MagicMock(), "s")
    for i in range(5):
        mc.nsb.accept_level1(episode(str(i), protected=True))
    await mc.maintain("s", 30, dialogues="")
    assert len(mc.nsb._level1) == 5 and mc.pending
    await mc.maintain("s", 31, dialogues="")
    assert not mc.nsb._level1
    assert mc.nsb._level2[0].protected
    assert len(mc.nsb._level2[0].source_ids) == 5


@pytest.mark.asyncio
async def test_restore_rebuilds_vectors_in_batch_and_deduplicates():
    embed = MagicMock(embed=AsyncMock(side_effect=[np.array([[1., 0.], [0., 1.]]), np.array([[1., 0.]])]))
    nsb = NarrativeSummarizationBranch(None, embedding_client=embed)
    nsb.accept_level1(episode("child", entities_involved=["钥匙"]))
    nsb.accept_level2(episode("parent", level=2, source_ids=["child"]))
    saved = nsb.export_state()
    nsb.load_state(saved)
    hits = await nsb.retrieve_hits("钥匙", turn=10)
    assert len(hits) == 1
    assert hits[0].memory_id == "child"
    assert hits[0].semantic_score > .99
    assert "entity:钥匙" in hits[0].reasons
    assert len(embed.embed.call_args_list[0].args[0]) == 2


@pytest.mark.asyncio
async def test_embedding_failure_has_keyword_fallback():
    embed = MagicMock(embed=AsyncMock(side_effect=RuntimeError("offline")))
    nsb = NarrativeSummarizationBranch(None, embedding_client=embed)
    nsb.accept_level1(episode(entities_involved=["钥匙"]))
    assert (await nsb.retrieve_hits("钥匙"))[0].entity_match > 0


def test_real_hits_only_and_persistent_inhibition():
    records = [MemoryRecord(memory_id=name, content=name, created_round=10) for name in ("a", "b", "c")]
    first = forget_step(records, 11, retrieved_ids=["a"], suppressed_ids=["b"])
    by_id = {r.memory_id: r for r in first}
    assert by_id["a"].retrieved_rounds == [11]
    assert by_id["b"].retrieved_rounds == []
    assert by_id["b"].inhibition == .5
    assert compute_score(by_id["b"], 12) < compute_score(by_id["c"], 12)
    again = forget_step(first, 11, retrieved_ids=["a"])
    assert next(r for r in again if r.memory_id == "a").retrieved_rounds == [11]


def test_protected_memory_survives_and_long_campaign_does_not_overflow():
    record = MemoryRecord(memory_id="clue", content="未解决线索", protected=True)
    assert forget_step([record], 10000)[0].memory_id == "clue"
    assert compute_score(record, 10000) >= 0


@pytest.mark.asyncio
async def test_only_full_post_truncation_hit_is_reinforced():
    mc = MemoryController(None, None, "s")
    mc.nsb.accept_level1(episode())
    mc._record_episode_memory(mc.nsb._level1[0], 6)
    prompt = await mc.assemble_context_async({}, 7, player_action="钥匙")
    assert mc.record_injected(prompt[:prompt.index("找到")], 7) == []
    assert mc._narrative_pool[0].retrieved_rounds == []
    trace = mc.record_injected(prompt, 7)
    assert trace[0]["memory_id"] == "ep"
    assert mc._narrative_pool[0].retrieved_rounds == [7]


def test_score_covers_legacy_and_structured_channels_and_recovery():
    tracker = ScoreTracker()
    tracker.seed([{"name": "通行卡", "aliases": ["门卡"]}], 0)
    removed = StoryOutput(narration="你弄丢了通行卡", items_lost=[{"name": "门卡"}])
    tracker.validate_output(removed, 1)
    assert tracker.get_record("门卡").state == ItemState.LOST
    invented = StoryOutput(narration="使用门卡", items_gained=[{"name": "门卡"}],
                           memory_updates=MemoryUpdates(items_upserted=[ItemMemory(name="通行卡")]))
    assert len(tracker.validate_output(invented, 2)) == 2
    assert not invented.items_gained and not invented.memory_updates.items_upserted
    restored = StoryOutput(narration="你重新找回通行卡", memory_updates=MemoryUpdates(
        items_upserted=[ItemMemory(name="门卡", transition="recovered")]))
    assert not tracker.validate_output(restored, 3)
    assert restored.memory_updates.items_upserted[0].name == "通行卡"
    assert tracker.get_record("门卡").state == ItemState.ACTIVE


def test_destroyed_item_requires_repair_and_removal_wins():
    tracker = ScoreTracker()
    tracker.propose_transition("key", ItemState.DESTROYED, 0)
    assert tracker.propose_transition("key", ItemState.ACTIVE, 1, "recovered")[1]
    assert not tracker.propose_transition("key", ItemState.ACTIVE, 1, "repaired")[1]
    output = StoryOutput(narration="交出钥匙", items_gained=[{"name": "key"}],
                         memory_updates=MemoryUpdates(items_removed=[ItemMemory(name="key")]))
    tracker.validate_output(output, 2)
    assert not output.items_gained
    assert tracker.get_record("key").state == ItemState.LOST


def test_aliases_and_unknown_updates_cannot_bypass_destruction():
    tracker = ScoreTracker()
    tracker.seed([{"name": "key"}, {"name": "another"}], 0)
    tracker.propose_transition("key", ItemState.DESTROYED, 1)
    tracker.propose_transition("key", ItemState.UNKNOWN, 2)
    tracker.propose_transition("key", ItemState.LOST, 3)
    output = StoryOutput(narration="拿出钥匙", items_gained=[{"name": "KEY", "aliases": ["another"]}])
    assert tracker.validate_output(output, 4)
    assert not output.items_gained
    assert tracker.get_record("key").state == ItemState.DESTROYED
    assert tracker.get_record("another").state == ItemState.ACTIVE


def test_snapshot_is_not_aliased_and_legacy_rounds_migrate():
    mc = MemoryController(None, None, "s")
    mc.on_turn_generated("a", "b", 1)
    snapshot = mc.export_state()
    mc.on_turn_generated("c", "d", 2)
    assert len(snapshot["nsb"]["turn_buffer"]) == 1
    mc.load_state({"narrative_pool": [{"memory_id": "old", "content": "x", "created_round": 5, "retrieved_rounds": [6]}]})
    assert mc._narrative_pool[0].created_round == 10
    assert mc._narrative_pool[0].retrieved_rounds == [12]


def db_session(tmp_path):
    db = Database(tmp_path / "memory.db")
    states = GameStateManager(db)
    session = states.create_session("test", "test")
    mc = MemoryController(None, db, session["session_id"])
    mc.on_turn_generated("a", "b", 1)
    state = {**session["state"], "_memory_controller": mc.export_state()}
    db.update_active_turn_snapshot(session["session_id"], state)
    states.save_state(session["session_id"], "test", "test", state)
    return db, states, session, mc


def test_memory_cas_publishes_both_snapshots_and_rejects_wrong_version(tmp_path):
    db, states, session, mc = db_session(tmp_path)
    sid, root = session["session_id"], session["active_turn_id"]
    completed = mc.export_state()
    completed["pending"] = False
    assert not db.commit_memory_snapshot(sid, root, "wrong", completed)
    assert db.commit_memory_snapshot(sid, root, mc.version, completed)
    persisted = states.get_session_payload(sid)["state"]["_memory_controller"]
    assert persisted == json.loads(db.get_story_turn(sid, root)["state_json"])["_memory_controller"]
    assert not persisted["pending"]


@pytest.mark.asyncio
async def test_late_worker_cannot_pollute_restored_branch(tmp_path):
    db, states, session, mc = db_session(tmp_path)
    sid, root = session["session_id"], session["active_turn_id"]
    child = db.commit_story_turn(session_id=sid, expected_parent_id=root, player_action="child", output={},
                                 state={**session["state"], "_memory_controller": mc.export_state()},
                                 campaign_progress={}, model="test", source="llm", model_output_id=None)
    started, release = asyncio.Event(), asyncio.Event()
    async def summarize(**kwargs):
        started.set()
        await release.wait()
        return {"summary": "只属于子分支的秘密"}
    llm = MagicMock(generate_json=AsyncMock(side_effect=summarize))
    gen = ScenarioGenerator(db, states, None, None, llm, None, "test")
    for i in range(5):
        mc.nsb.add_turn("a", "b", i + 2)
    job = asyncio.create_task(gen._maintain_memory_snapshot(sid, child, 6, mc.export_state(), ""))
    await started.wait()
    db.activate_story_turn(sid, root)
    release.set()
    await job
    assert "只属于子分支" not in str(states.get_session_payload(sid))
    assert sid not in gen._memory_controllers


@pytest.mark.asyncio
async def test_campaign_pipeline_state_snapshot_and_director_agree(runtime):
    async with AsyncClient(transport=ASGITransport(app=runtime.app), base_url="http://test") as client:
        session = (await client.post("/sessions", json={})).json()
    sid = session["session_id"]
    await runtime.generator.generate(sid, GenerateRequest(player_action="入场"))
    runtime.llm.generate.return_value = (StoryOutput(narration="获得钥匙", items_gained=[{"name": "钥匙"}]), 1)
    await runtime.generator.generate(sid, GenerateRequest(player_action="观察"))
    runtime.llm.generate.return_value = (StoryOutput(narration="钥匙被毁坏", memory_updates=MemoryUpdates(
        items_removed=[ItemMemory(name="钥匙", status="destroyed")])), 1)
    await runtime.generator.generate(sid, GenerateRequest(player_action="继续"))
    runtime.llm.generate.return_value = (StoryOutput(narration="又拥有钥匙", items_gained=[{"name": "钥匙"}]), 1)
    result = await runtime.generator.generate(sid, GenerateRequest(player_action="继续"))
    await runtime.generator._wait_memory(sid)
    assert not any(i["name"] == "钥匙" for i in result.state["items"])
    assert not result.output.items_gained
    from app.services.agents.director import DirectorAgent
    assert "钥匙: destroyed" in DirectorAgent.direct.call_args.kwargs["item_states"]
    persisted = runtime.states.get_session_payload(sid)["state"]["_memory_controller"]
    assert any(r["item_name"] == "钥匙" and r["state"] == "destroyed" for r in persisted["score_tracker"])
    assert len(persisted["nsb"]["turn_buffer"]) == 4


@pytest.mark.asyncio
async def test_campaign_only_validation_and_legacy_history(runtime):
    async with AsyncClient(transport=ASGITransport(app=runtime.app), base_url="http://test") as client:
        for value in (None, "", "../escape.json"):
            assert (await client.post("/sessions", json={"campaign_filename": value})).status_code == 422
    old = runtime.states.create_session("legacy", "test")
    runtime.generator.campaign_manager_provider = lambda sid, slot: None
    with pytest.raises(CampaignRequiredError):
        await runtime.generator.generate(old["session_id"], GenerateRequest(player_action="继续"))
    assert runtime.states.get_session_payload(old["session_id"])


@pytest.mark.asyncio
async def test_restart_resumes_pending_summary_before_next_prompt(runtime):
    async with AsyncClient(transport=ASGITransport(app=runtime.app), base_url="http://test") as client:
        session = (await client.post("/sessions", json={})).json()
    sid = session["session_id"]
    opening = await runtime.generator.generate(sid, GenerateRequest(player_action="入场"))
    await runtime.generator._wait_memory(sid)
    state = runtime.states.get_session_payload(sid)["state"]
    mc = MemoryController(runtime.llm, runtime.db, sid)
    mc.load_state(state["_memory_controller"])
    for turn in range(2, 7):
        mc.on_turn_generated("调查", "密室密码是青铜", turn)
    saved = mc.export_state()
    assert runtime.db.commit_memory_snapshot(sid, opening.timeline_node_id, state["_memory_controller"]["version"], saved)
    runtime.generator.invalidate_timeline_caches(sid)
    runtime.llm.generate_json.return_value = {"summary": "密室密码是青铜", "entities_involved": ["密室"]}
    runtime.llm.generate.return_value = (StoryOutput(narration="你走近密室"), 1)
    result = await runtime.generator.generate(sid, GenerateRequest(player_action="前往密室"))
    await runtime.generator._wait_memory(sid)
    assert "密室密码是青铜" in runtime.llm.generate.call_args.args[0]
    node = runtime.db.get_story_turn(sid, opening.timeline_node_id)
    assert json.loads(node["state_json"])["_memory_controller"]["nsb"]["level1"]
    with runtime.db.connect() as db:
        row = db.execute("SELECT retrieved_chunks_json FROM model_outputs WHERE id = ?", (result.model_output_id,)).fetchone()
    assert any(h.get("memory_id") and h.get("reasons") for h in json.loads(row[0]))


@pytest.mark.asyncio
async def test_two_hundred_turns_promote_and_keep_protected_consequences():
    llm = MagicMock(generate_json=AsyncMock(return_value={"summary": "长期事件摘要", "state_changes": {"钥匙": "destroyed"}}))
    mc = MemoryController(llm, MagicMock(), "s")
    for turn in range(1, 201):
        mc.on_turn_generated("观察", "发现一条线索", turn)
        await mc.maintain("s", turn, dialogues="")
    assert mc.nsb._level3
    assert len(mc.nsb._level3) < mc.nsb.theta3
    assert mc.nsb._level3[0].state_changes["钥匙"] == "destroyed"
    assert mc.nsb._level3[0].protected
    assert len(mc.nsb._turn_buffer) < 6
    assert len(mc._narrative_pool) < 5


def test_memory_cas_does_not_overwrite_new_live_state(tmp_path):
    db, states, session, mc = db_session(tmp_path)
    state = states.get_session_payload(session["session_id"])["state"]
    state["health"] = 31
    states.save_state(session["session_id"], "test", "test", state)
    assert db.commit_memory_snapshot(session["session_id"], session["active_turn_id"], mc.version, mc.export_state())
    assert states.get_session_payload(session["session_id"])["state"]["health"] == 31


@pytest.mark.asyncio
async def test_completed_worker_advances_version_and_rejects_duplicate(tmp_path):
    db, states, session, mc = db_session(tmp_path)
    sid, root = session["session_id"], session["active_turn_id"]
    gen = ScenarioGenerator(db, states, None, None, None, None, "test")
    await gen._maintain_memory_snapshot(sid, root, 1, mc.export_state(), "")
    current = states.get_session_payload(sid)["state"]["_memory_controller"]
    assert current["version"] != mc.version
    assert not db.commit_memory_snapshot(sid, root, mc.version, mc.export_state())
