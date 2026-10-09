"""Full-campaign acceptance: 50-turn budget, ending inside it, consistent counters.

Drives the real generate loop against a stubbed narrator: repeated
continues, a mid-run branch restore, an injected commit failure with
retry, then run-to-end. The whole-campaign counter must follow every
restore exactly once and the ending must land on the cap turn.
"""

from types import SimpleNamespace

import pytest

from app.exceptions import ConcurrentModificationError
from app.services.campaign_endings import select_budget_ending

from tests.test_turn_commit_consistency import Harness


def _synthetic_campaign(routes: list) -> SimpleNamespace:
    """A campaign whose ending routes have checkable requirements."""
    return SimpleNamespace(
        arcs=[SimpleNamespace(sessions=[SimpleNamespace(anchor_events=[])])],
        ending_routes=routes,
    )


def _fake_route(id: str, category: str, requirements: list[str], phrases: list[str] | None = None):
    from app.schemas.campaign import EndingRoute
    return EndingRoute(
        id=id, name=id, category=category,
        requirements=requirements, trigger_phrases=phrases or [],
        resolution="收束。", epilogue="终。",
    )


def test_budget_ending_classification():
    # 证据 = 完成任务的名称/目标 + 世界事实 + 已揭示锚点。
    state = {
        "health": 80, "sanity": 60,
        "quests": [{"name": "查明钟摆声", "status": "已完成", "objective": "找到钟摆的来源"}],
        "world_facts": [{"name": "低频来自塔顶", "description": "钟摆与塔顶共振"}],
    }
    progress = SimpleNamespace(turns_total=0, revealed_anchors=[])

    # 预算未到不触发
    camp = _synthetic_campaign([_fake_route("r-true", "true", ["钟摆"])])
    assert select_budget_ending(camp, progress, state, max_turns=50) is None

    # 第 50 回合：要求在证据里 → 选中对应路线（requirements 参与判断）
    progress.turns_total = 49
    route = select_budget_ending(camp, progress, state, max_turns=50)
    assert route is not None and route.id == "r-true"

    # 完成了任务但证据对不上任何路线的要求 → 未完成收束，而不是按类别硬选
    camp2 = _synthetic_campaign([_fake_route("r-true", "true", ["找到塔顶的火种"])])
    route = select_budget_ending(camp2, progress, state, max_turns=50)
    assert route is not None and route.id == "budget-incomplete"

    # A matching closing action cannot waive unmet route requirements.
    camp3 = _synthetic_campaign([
        _fake_route("r-good", "good", ["不可能满足的要求"], phrases=["把怀表埋进盐里"]),
    ])
    route = select_budget_ending(
        camp3, progress, state, max_turns=50, player_action="我把怀表埋进盐里",
    )
    assert route is not None and route.id == "budget-incomplete"
    route = select_budget_ending(camp3, progress, state, max_turns=50, player_action="离开")
    assert route is not None and route.id == "budget-incomplete"

    # 只有线索没有完成任务 → 未完成档；空要求路线不再按类别裸选
    camp4 = _synthetic_campaign([_fake_route("r-empty", "good", [])])
    bare_state = {"health": 80, "sanity": 60, "quests": [], "world_facts": []}
    progress.revealed_anchors = ["a-1"]
    route = select_budget_ending(camp4, progress, bare_state, max_turns=50)
    assert route is not None and route.id == "budget-incomplete"

    # 死亡状态 → 失败档按存活统计走 bad/dark
    camp5 = _synthetic_campaign([_fake_route("r-bad", "bad", [])])
    dead = {"health": 0, "sanity": 0, "quests": [], "world_facts": []}
    progress.revealed_anchors = []
    route = select_budget_ending(camp5, progress, dead, max_turns=50)
    assert route is not None and route.id == "r-bad"

    # 无任何路线 → 合成收束
    route = select_budget_ending(_synthetic_campaign([]), progress, dead, max_turns=50)
    assert route is not None and route.id == "budget-failure"


@pytest.mark.asyncio
async def test_full_campaign_runs_and_ends_within_budget(tmp_path):
    h = Harness(tmp_path)
    cap = h.manager.resolve_max_turns_per_campaign()
    totals: list[int] = []
    chapters: list[tuple[int, int]] = []
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
        chapters.append((
            response.campaign_progress["arc_index"],
            response.campaign_progress["session_index"],
        ))
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

    distinct_chapters = sorted(set(chapters))
    assert distinct_chapters == [(0, 0), (0, 1), (1, 0), (2, 0), (2, 1)]
    assert (ended.campaign_progress["arc_index"], ended.campaign_progress["session_index"]) == (2, 1)

    with pytest.raises(ConcurrentModificationError):
        await h.generate(), "结局之后后端必须拒绝继续推进"
