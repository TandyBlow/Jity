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
        self.gen._apply_post_generation = AsyncMock(
            side_effect=lambda output, next_state, state, sid, sess, model, cm: next_state
        )
        memory_ctrl = MagicMock()
        memory_ctrl.export_state.return_value = {}
        memory_ctrl.maintain = AsyncMock()
        self.gen._get_memory_controller = MagicMock(return_value=memory_ctrl)

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
async def test_branch_restore_then_generate_keeps_progress_consistent(tmp_path):
    h = Harness(tmp_path)
    await h.generate()  # turn 1 on the active path

    root = h.db.ensure_timeline_root(h.session_id, {}, "test-model")
    snapshot = h.db.activate_story_turn(h.session_id, root)
    assert snapshot is not None
    # The root node carries no campaign_progress snapshot, so activation
    # leaves the progress row untouched (timeline.py: `if progress:` guard).
    # The activate endpoint invalidates the manager cache; the rebuilt
    # manager reloads progress from the persisted row.
    h.manager.reload_runtime_state()
    assert h.progress_row()["turn_in_session"] == 1

    response = await h.generate()
    row = h.progress_row()
    assert row["turn_in_session"] == 2
    assert h.node_count() == 3, "根、原分支一节点、新分支一节点"
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
