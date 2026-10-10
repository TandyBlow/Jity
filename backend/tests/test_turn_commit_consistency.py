"""Failure-injection tests for the turn-finalization commit sequence.

The seam under test: campaign advancement (turn counter, anchor marks,
session/arc boundaries) must reach the database only through the
commit_story_turn transaction, so that a failure there leaves progress,
session head and node count consistent — and a retried request advances
exactly once.

T1/T2 are red on the pre-fix ordering (advance persists before the node
commit); T3/T4 are regression guards for restore and boundary recap.
"""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.database import Database
from app.exceptions import ConcurrentModificationError
from app.schemas import StoryOutput
from app.schemas.game.requests_responses import GenerateRequest
from app.services.campaign_manager.facade import CampaignManager
from app.services.game_state import GameStateManager
from app.services.memory.memory_controller import MemoryController
from app.services.scenario_generator.generator import ScenarioGenerator

CAMPAIGN = Path(__file__).resolve().parents[1] / "data" / "campaigns" / "default_campaign.json"


def _story_output(text: str = "第一回合的旁白。") -> StoryOutput:
    return StoryOutput(
        narration=text,
        dialogue=[],
        scene_prompt="",
        sanity_delta=0,
        health_delta=0,
        options=["继续"],
        current_location="报到处大厅",
        game_over=False,
        game_over_reason="",
    )


class Harness:
    """Real database + real campaign manager; only LLM output and the
    prompt/opening/post hooks are stubbed, so the finalize seam runs for real."""

    def __init__(self, tmp_path: Path):
        self.db = Database(tmp_path / "consistency.sqlite3")
        self.state_manager = GameStateManager(self.db)
        self.llm = MagicMock()
        self.llm.generate = AsyncMock(return_value=(_story_output(), 5))
        self.llm.generate_json = AsyncMock(return_value={})
        self.manager = CampaignManager(
            db=self.db, campaigns_dir=tmp_path, scripted_story=None,
            prompt_builder=MagicMock(), llm_client=self.llm,
        )
        self.manager.load(CAMPAIGN, slot_name="default")
        session = self.state_manager.create_session("一致性测试局", "test-model")
        self.session_id = session["session_id"]

        self.gen = ScenarioGenerator(
            db=self.db, state_manager=self.state_manager, retriever=None,
            prompt_builder=None, llm_client=self.llm, scripted_story=None,
            default_model="test-model",
        )
        self.gen.campaign_manager_provider = lambda sid, slot: self.manager
        self.gen._handle_opening_scene = AsyncMock(return_value=None)
        self.gen._build_prompt = AsyncMock(return_value=(
            "P", SimpleNamespace(sections=None, final_prompt="", temperature=0.7), [], [], 0,
        ))
        # _apply_post_generation runs for real: the NPC relation overlay is
        # part of the consistency surface under test.
        # Exercise the actual versioned snapshot lifecycle, including fresh
        # controllers after failures/restores and independent maintenance workers.
        self.gen._memory_controllers[self.session_id] = MemoryController(
            self.llm, self.db, self.session_id,
        )

    def set_narration_delta(self, delta: list[dict]) -> None:
        """Make the stubbed narrator report an NPC relation delta this turn."""
        output = _story_output()
        output.npc_relations_delta = delta
        self.llm.generate = AsyncMock(return_value=(output, 5))

    async def generate(self):
        return await self.gen.generate(
            self.session_id, GenerateRequest(player_action="继续调查四周")
        )

    def stage_pending_anchor(self) -> None:
        self.manager._anchors.pending_anchor_triggers = [("dynamic-test-anchor", 0)]

    def progress_row(self) -> dict:
        row = self.db.read_campaign_progress(
            self.manager.progress.campaign_id, "default"
        )
        return dict(row) if row else {}

    def node_count(self) -> int:
        with self.db.connect() as db:
            row = db.execute(
                "SELECT COUNT(*) AS c FROM story_turns WHERE session_id = ?",
                (self.session_id,),
            ).fetchone()
            return int(row["c"])

    def head(self) -> int:
        with self.db.connect() as db:
            row = db.execute(
                "SELECT active_turn_id FROM game_sessions WHERE id = ?", (self.session_id,)
            ).fetchone()
            return int(row["active_turn_id"])


@pytest.mark.asyncio
async def test_commit_failure_leaves_progress_head_and_nodes_unchanged(tmp_path):
    h = Harness(tmp_path)
    h.stage_pending_anchor()
    root = h.head()
    original = h.db.commit_story_turn

    def injected(*args, **kwargs):
        raise ConcurrentModificationError("injected commit failure")

    h.db.commit_story_turn = injected
    try:
        with pytest.raises(ConcurrentModificationError):
            await h.generate()
    finally:
        h.db.commit_story_turn = original

    row = h.progress_row()
    assert row["turn_in_session"] == 0, "进度在节点提交失败后不得已推进"
    assert "dynamic-test-anchor" not in str(row["revealed_anchors"]), "锚点不得在节点提交失败后被标记"
    assert h.node_count() == 1, "只应存在根节点"
    assert h.head() == root, "会话头不得移动"


@pytest.mark.asyncio
async def test_retry_after_commit_failure_advances_exactly_once(tmp_path):
    h = Harness(tmp_path)
    original = h.db.commit_story_turn

    def injected(*args, **kwargs):
        raise ConcurrentModificationError("injected commit failure")

    h.db.commit_story_turn = injected
    try:
        with pytest.raises(ConcurrentModificationError):
            await h.generate()
    finally:
        h.db.commit_story_turn = original

    response = await h.generate()
    row = h.progress_row()
    assert row["turn_in_session"] == 1, "重试只允许推进一次"
    assert h.node_count() == 2, "重试只允许追加一个节点"
    assert h.head() == response.timeline_node_id
    with h.db.connect() as db:
        node = db.execute(
            "SELECT campaign_progress_json FROM story_turns WHERE id = ?",
            (response.timeline_node_id,),
        ).fetchone()
    import json as _json
    assert _json.loads(node["campaign_progress_json"])["turn_in_session"] == 1


@pytest.mark.asyncio
async def test_branch_restore_to_root_resets_turn_session_and_anchors(tmp_path):
    h = Harness(tmp_path)
    h.stage_pending_anchor()
    await h.generate()  # turn 1 on the active path, anchor marked
    assert "dynamic-test-anchor" in str(h.progress_row()["revealed_anchors"])

    with h.db.connect() as db:
        root = int(db.execute(
            "SELECT id FROM story_turns WHERE session_id = ? AND parent_turn_id IS NULL",
            (h.session_id,),
        ).fetchone()["id"])
    snapshot = h.db.activate_story_turn(h.session_id, root)
    assert snapshot is not None
    # The root predates the campaign and carries no progress snapshot; the
    # activate endpoint resets to the campaign's initial state instead of
    # letting the previous branch's progress leak into the new branch.
    assert not snapshot.get("campaign_progress")
    h.manager.reset_to_initial()

    row = h.progress_row()
    assert row["turn_in_session"] == 0, "回合必须随开局快照一起恢复"
    assert row["session_index"] == 0, "章节必须随开局快照一起恢复"
    assert "dynamic-test-anchor" not in str(row["revealed_anchors"]), "事件记录必须随开局快照一起恢复"

    h.manager.reload_runtime_state()
    response = await h.generate()
    row = h.progress_row()
    assert row["turn_in_session"] == 1
    assert h.node_count() == 3, "根、原分支一节点、新分支一节点"
    assert h.head() == response.timeline_node_id


@pytest.mark.asyncio
async def test_boundary_recap_failure_keeps_turn_count_unchanged(tmp_path):
    """At a budget-forced session boundary the recap must not write counters
    ahead of the node — and the recap itself must not survive a failed
    commit (it travels with the node, so a retry cannot append twice)."""
    h = Harness(tmp_path)
    h.manager.progress.turn_in_session = 29
    h.manager.progress.turns_total = 45  # allocation is exhausted → boundary
    h.manager.save_progress()
    assert h.progress_row()["turn_in_session"] == 29

    original = h.db.commit_story_turn

    def injected(*args, **kwargs):
        raise ConcurrentModificationError("injected commit failure")

    h.db.commit_story_turn = injected
    try:
        with pytest.raises(ConcurrentModificationError):
            await h.generate()
    finally:
        h.db.commit_story_turn = original

    row = h.progress_row()
    assert row["turn_in_session"] == 29, "前情提要写入不得夹带回合数推进"
    assert row["session_index"] == 0, "前情提要写入不得夹带章节推进"
    assert row["recap_compressed"] == "", "前情提要必须随节点提交，失败不得留在历史里"

    h.manager.reload_runtime_state()
    response = await h.generate()
    row = h.progress_row()
    assert row["session_index"] == 1 and row["turn_in_session"] == 0
    assert row["recap_compressed"], "重试成功后前情提要随节点出现"
    assert h.head() == response.timeline_node_id
    with h.db.connect() as db:
        node = db.execute(
            "SELECT campaign_progress_json FROM story_turns WHERE id = ?",
            (response.timeline_node_id,),
        ).fetchone()
    import json as _json
    node_progress = _json.loads(node["campaign_progress_json"])
    assert node_progress["recap_compressed"] == row["recap_compressed"], "行与节点快照一致"


@pytest.mark.asyncio
async def test_boundary_decay_deferred_until_commit(tmp_path):
    h = Harness(tmp_path)
    h.db.update_npc_relations(
        h.manager.progress.campaign_id, '[{"name": "诺诺", "affinity": 3}]'
    )
    h.manager.progress.turn_in_session = 29
    h.manager.progress.turns_total = 45
    h.manager.save_progress()

    original = h.db.commit_story_turn

    def injected(*args, **kwargs):
        raise ConcurrentModificationError("injected commit failure")

    h.db.commit_story_turn = injected
    try:
        with pytest.raises(ConcurrentModificationError):
            await h.generate()
    finally:
        h.db.commit_story_turn = original

    relations = h.progress_row()["npc_relations"]
    assert '"affinity": 3' in relations, "好感衰减不得先于节点提交落库"

    h.manager.reload_runtime_state()
    response = await h.generate()
    relations = h.progress_row()["npc_relations"]
    assert '"affinity": 2' in relations, "节点提交后衰减落库"
    with h.db.connect() as db:
        node = db.execute(
            "SELECT campaign_progress_json FROM story_turns WHERE id = ?",
            (response.timeline_node_id,),
        ).fetchone()
    import json as _json
    node_progress = _json.loads(node["campaign_progress_json"])
    assert '"affinity": 2' in str(node_progress["npc_relations"]), "节点快照与行一致，恢复不再回跳"


@pytest.mark.asyncio
async def test_relation_increment_applies_exactly_once_across_retry(tmp_path):
    """Relation increments ride the overlay: a failed commit must not leave
    the +1 in the database, and the retry must not double-apply it."""
    h = Harness(tmp_path)
    h.db.update_npc_relations(
        h.manager.progress.campaign_id, '[{"name": "诺诺", "affinity": 3}]'
    )
    h.set_narration_delta([{"name": "诺诺", "sentiment": "positive", "note": "帮忙"}])

    original = h.db.commit_story_turn

    def injected(*args, **kwargs):
        raise ConcurrentModificationError("injected commit failure")

    h.db.commit_story_turn = injected
    try:
        with pytest.raises(ConcurrentModificationError):
            await h.generate()
    finally:
        h.db.commit_story_turn = original

    relations = h.progress_row()["npc_relations"]
    assert '"affinity": 3' in relations, "增量不得先于节点提交落库"

    h.manager.reload_runtime_state()
    await h.generate()
    relations = h.progress_row()["npc_relations"]
    assert '"affinity": 4' in relations, "重试恰好应用一次增量"
    assert '"affinity": 5' not in relations, "重试不得叠加第二次增量"


@pytest.mark.asyncio
async def test_reset_to_initial_from_later_chapter(tmp_path):
    h = Harness(tmp_path)
    h.manager.progress.arc_index = 2
    h.manager.progress.session_index = 1
    h.manager.progress.turn_in_session = 7
    h.manager.progress.turns_total = 25
    h.manager.progress.revealed_anchors = ["a-1", "a-2"]
    h.manager.save_progress()
    h.db.update_recap_fields(h.manager.progress.campaign_id, "旧提要", "旧提要全文")
    h.db.update_npc_relations(h.manager.progress.campaign_id, '[{"name": "旧NPC", "affinity": -3}]')

    h.manager.reset_to_initial()

    row = h.progress_row()
    assert row["arc_index"] == 0 and row["session_index"] == 0, "章节索引必须一起重置"
    assert row["turn_in_session"] == 0 and row["turns_total"] == 0
    assert row["revealed_anchors"] == "[]", "事件记录必须清空"
    assert row["recap_compressed"] == "" and row["recap_full"] == "", "旧提要必须清空"
    assert row["npc_relations"] == "[]", "旧好感必须清空"

    h.manager.reload_runtime_state()
    response = await h.generate()
    row = h.progress_row()
    assert row["turns_total"] == 1 and row["arc_index"] == 0
    assert h.head() == response.timeline_node_id


@pytest.mark.asyncio
async def test_session_boundary_recap_failure_still_commits(tmp_path):
    h = Harness(tmp_path)
    h.manager.progress.turn_in_session = 29  # next advance crosses max_turns=30
    h.manager._recap.generate_recap = AsyncMock(side_effect=RuntimeError("recap down"))

    response = await h.generate()
    row = h.progress_row()
    assert row["session_index"] == 1, "边界跨越必须发生"
    assert row["turn_in_session"] == 0
    assert h.head() == response.timeline_node_id
    assert h.node_count() == 2, "recap 失败走结构化回退，节点照常提交"
