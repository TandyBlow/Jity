"""Cross-branch regressions: budgets, identity masking, snapshots and slots."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.schemas import StoryOutput
from app.schemas.campaign import EndingRoute
from app.schemas.agent_io import ItemState, OpeningOptions
from app.services.memory.memory_controller import MemoryController
from app.services.agents.examiner import ExaminerAgent
from app.services.campaign_endings import select_budget_ending
from app.repositories.campaign_progress import CampaignProgressRepository
from tests.test_turn_commit_consistency import Harness


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["治疗药水", "恢复液"])
async def test_alias_mask_preserves_trailing_action(name):
    state = {"items": [{"name": "治疗药水", "aliases": ["恢复液"], "status": "owned"}],
             "health": 100, "sanity": 80}
    ruling = await ExaminerAgent().examine(f"使用{name}攀爬高墙", state)
    assert ruling.permissibility.value == "conditional"
    assert [r.rule_name for r in ruling.triggered_rules if r.rule_type == "skill_check"] == ["技能检定：运动"]


@pytest.mark.asyncio
async def test_full_identity_wins_shared_alias():
    state = {"items": [{"name": "古钥匙", "status": "owned"},
                       {"name": "银钥匙", "aliases": ["古钥匙"], "status": "lost"}]}
    ruling = await ExaminerAgent().examine("使用古钥匙开门", state)
    assert ruling.permissibility.value == "permissible"


@pytest.mark.parametrize("action", ["不要撤离", "如果选择撤离", "假设决定：撤离"])
def test_budget_does_not_treat_negation_or_hypothesis_as_choice(action):
    route = EndingRoute(id="leave", name="撤离", category="normal", requirements=[], trigger_phrases=["撤离"], resolution="撤离。")
    campaign = SimpleNamespace(arcs=[], ending_routes=[route])
    progress = SimpleNamespace(turns_total=4, revealed_anchors=["known"])
    selected = select_budget_ending(campaign, progress, {}, 5, action)
    assert selected.id.startswith("budget-")


def test_budget_checks_required_item_and_anchor_even_with_fact_evidence():
    route = EndingRoute(id="truth", name="真相", category="true", requirements=["真相"],
                        required_items=["钥匙"], required_anchors=["door"], resolution="真相大白。")
    campaign = SimpleNamespace(arcs=[], ending_routes=[route])
    progress = SimpleNamespace(turns_total=4, revealed_anchors=[])
    state = {"quests": [{"name": "真相", "status": "completed"}]}
    assert select_budget_ending(campaign, progress, state, 5).id != "truth"


@pytest.mark.asyncio
async def test_replaced_ending_captures_only_final_consequences(tmp_path):
    h = Harness(tmp_path)
    h.manager.progress.arc_index = 2
    h.manager.progress.session_index = 1
    h.manager.save_progress()
    h.llm.generate.return_value = (StoryOutput(
        narration="应该被替换的原始旁白", health_delta=-100,
        items_gained=[{"name": "虚构奖励", "aliases": ["奖牌"]}],
        npc_relations_delta=[{"name": "同伴", "delta": 5}],
    ), 1)
    response = await h.generate()
    await h.gen._wait_memory(h.session_id)
    assert response.output.game_over
    assert not response.output.items_gained and not response.output.npc_relations_delta
    saved = json.loads(h.db.get_story_turn(h.session_id, response.timeline_node_id)["state_json"])
    memory = saved["_memory_controller"]
    assert "应该被替换" not in json.dumps(memory, ensure_ascii=False)
    assert "虚构奖励" not in json.dumps(memory, ensure_ascii=False)
    assert "奖牌" not in memory["item_aliases"]
    assert len(memory["nsb"]["turn_buffer"]) == 1
    assert response.output.narration in memory["nsb"]["turn_buffer"][0]
    assert response.caps["items"] is None


@pytest.mark.asyncio
async def test_slot_copy_keeps_budget_and_delete_keeps_shared_history(tmp_path):
    h = Harness(tmp_path)
    # Harness uses a separate campaign id; real sessions are bound before routing.
    h.db.set_session_campaign_id(h.session_id, h.session_id, "default_campaign.json", "default")
    h.manager.progress.campaign_id = h.session_id
    h.manager.save_progress()
    response = await h.generate()
    await h.gen._wait_memory(h.session_id)
    repo = CampaignProgressRepository(h.db)
    repo.create_slot(h.db.get_session(h.session_id), "copy", "default")
    copied = h.db.read_campaign_progress(h.session_id, "copy")
    assert copied["turns_total"] == 1
    original = h.db.read_campaign_progress(h.session_id, "default")
    before = h.db.list_story_turns(h.session_id)
    assert repo.delete_slot_by_id(original["id"])
    assert h.db.list_story_turns(h.session_id) == before
    assert h.db.get_session(h.session_id)
    assert h.db.get_story_turn(h.session_id, response.timeline_node_id)
    assert repo.delete_slot_by_id(original["id"]) is None
    with pytest.raises(ValueError, match="当前存档不可删除"):
        repo.delete_slot_by_id(copied["id"])


@pytest.mark.asyncio
async def test_chapter_opening_does_not_revive_consumed_entry_item(tmp_path):
    h = Harness(tmp_path)
    h.manager.progress.session_index = 1
    h.manager.campaign.arcs[0].sessions[1].entry_state = {"location": "新的场景", "items": ["药剂"]}
    h.manager.save_progress()
    state = h.state_manager.get_session_payload(h.session_id)["state"]
    state["turn"] = 2
    memory = MemoryController(h.llm, h.db, h.session_id)
    memory.score_tracker.seed([{"name": "药剂"}], 1)
    memory.score_tracker.propose_transition("药剂", ItemState.CONSUMED, 2)
    state["_memory_controller"] = memory.export_state()
    h.state_manager.save_state(h.session_id, "test", "test", state)
    h.db.update_active_turn_snapshot(h.session_id, state)
    del h.gen._handle_opening_scene
    h.gen._generate_opening_options = AsyncMock(return_value=OpeningOptions(
        options=["观察", "继续", "等待"], option_checks=[None, None, None],
    ))
    response = await h.generate()
    await h.gen._wait_memory(h.session_id)
    assert response.source == "scripted"
    assert all(item["name"] != "药剂" for item in response.state["items"])
    saved = json.loads(h.db.get_story_turn(h.session_id, response.timeline_node_id)["state_json"])
    assert saved["_memory_controller"]["score_tracker"][0]["state"] == "consumed"


@pytest.mark.asyncio
async def test_examiner_rejection_is_saved_once_in_memory(tmp_path):
    from app.schemas import GenerateRequest
    h = Harness(tmp_path)
    response = await h.gen.generate(h.session_id, GenerateRequest(player_action="使用不存在的水晶球"))
    await h.gen._wait_memory(h.session_id)
    assert response.source == "examiner_blocked"
    saved = json.loads(h.db.get_story_turn(h.session_id, response.timeline_node_id)["state_json"])
    buffer = saved["_memory_controller"]["nsb"]["turn_buffer"]
    assert len(buffer) == 1 and response.output.narration in buffer[0]
    assert h.progress_row()["turns_total"] == 1
