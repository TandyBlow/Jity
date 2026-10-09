"""Full-campaign acceptance: 50-turn budget, ending inside it, consistent counters.

Drives the real generate loop against a stubbed narrator: repeated
continues, a mid-run branch restore, an injected commit failure with
retry, then run-to-end. The whole-campaign counter must follow every
restore exactly once and the ending must land on the cap turn.
"""

import pytest

from app.exceptions import ConcurrentModificationError
from app.services.campaign_endings import select_budget_ending

from tests.test_turn_commit_consistency import Harness


@pytest.mark.asyncio
async def test_budget_ending_classification(tmp_path):
    h = Harness(tmp_path)
    cap = h.manager.resolve_max_turns_per_campaign()
    assert cap == 50

    state = {"health": 80, "sanity": 60, "quests": [{"name": "任务", "status": "已完成"}]}
    route = select_budget_ending(h.manager.campaign, h.manager.progress, state, max_turns=50)
    assert route is None, "预算未到 49 回合不得触发"

    h.manager.progress.turns_total = 49
    route = select_budget_ending(h.manager.campaign, h.manager.progress, state, max_turns=50)
    assert route is not None and route.category in ("true", "good"), "有完成任务 → 成功档"

    state = {"health": 80, "sanity": 60, "quests": []}
    h.manager.progress.revealed_anchors = ["a-1"]
    route = select_budget_ending(h.manager.campaign, h.manager.progress, state, max_turns=50)
    assert route is not None and route.category in ("normal", "dark", "good"), "只有线索 → 未完成档"

    state = {"health": 80, "sanity": 60, "quests": []}
    h.manager.progress.revealed_anchors = []
    route = select_budget_ending(h.manager.campaign, h.manager.progress, state, max_turns=50)
    assert route is not None and route.category in ("bad", "dark"), "无任务无线索 → 失败档"

    empty = Harness(tmp_path / "no-routes").manager
    empty.campaign.ending_routes = []
    empty.progress.turns_total = 49
    route = select_budget_ending(empty.campaign, empty.progress, state, max_turns=50)
    assert route is not None and route.id == "budget-failure", "无配置路线时合成收束路线"


@pytest.mark.asyncio
async def test_full_campaign_runs_and_ends_within_budget(tmp_path):
    h = Harness(tmp_path)
    cap = h.manager.resolve_max_turns_per_campaign()
    totals: list[int] = []
    ended = None

    for step in range(cap + 5):
        # Mid-run chaos, once each: a branch restore and a failed commit+retry.
        if step == 5:
            with h.db.connect() as db:
                earlier = int(db.execute(
                    "SELECT id FROM story_turns WHERE session_id = ? ORDER BY id LIMIT 1 OFFSET 2",
                    (h.session_id,),
                ).fetchone()["id"])
            h.db.activate_story_turn(h.session_id, earlier)
            h.manager.reload_runtime_state()
        if step == 8:
            original = h.db.commit_story_turn

            def injected(*args, **kwargs):
                raise ConcurrentModificationError("injected")
            h.db.commit_story_turn = injected
            try:
                with pytest.raises(ConcurrentModificationError):
                    await h.generate()
            finally:
                h.db.commit_story_turn = original
            h.manager.reload_runtime_state()

        try:
            response = await h.generate()
        except ConcurrentModificationError:
            break
        total = response.campaign_progress["turns_total"]
        assert 1 <= total <= cap, f"整局计数越界：{total}"
        totals.append(total)
        if response.output.game_over:
            ended = response
            break

    assert ended is not None, "游戏必须在 50 回合内给出结局"
    # The branch restore at step 5 legitimately steps the counter back to the
    # restored node's snapshot; within each branch the count is +1 per turn.
    before, after = totals[:5], totals[5:]
    assert before == [1, 2, 3, 4, 5], f"前段逐回合 +1：{before}"
    assert after == list(range(after[0], after[0] + len(after))), f"恢复段逐回合 +1：{after}"
    assert after[0] <= 4, "恢复后计数必须回到快照附近而非继续旧值"
    assert ended.campaign_progress["turns_total"] == cap, "结局必须落在第 50 回合"
    assert ended.output.options == []
    assert ended.output.game_over_reason

    with pytest.raises(ConcurrentModificationError):
        await h.generate(), "结局之后后端必须拒绝继续推进"
