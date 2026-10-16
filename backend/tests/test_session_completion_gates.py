"""Session boundaries follow story milestones, with turn caps as fallback."""

from types import SimpleNamespace
from unittest.mock import MagicMock

from app.services.campaign_advancer import CampaignSessionAdvancer
from app.services.scenario_generator.prompting import PromptBuildMixin


def _runtime(*, turn=0, revealed=None, required=None, minimum=7, soft=5, hard=10):
    session = SimpleNamespace(
        min_turns_per_session=minimum,
        soft_turns_per_session=soft,
        max_turns_per_session=hard,
        completion_anchors=required or [],
    )
    campaign = SimpleNamespace(
        arcs=[SimpleNamespace(sessions=[session])],
        max_turns_per_session=None,
        max_turns_per_campaign=50,
    )
    progress = SimpleNamespace(
        arc_index=0,
        session_index=0,
        turn_in_session=turn,
        turns_total=turn,
        revealed_anchors=revealed or [],
    )
    return CampaignSessionAdvancer(MagicMock(), MagicMock()), campaign, progress


def test_milestone_cannot_close_session_before_minimum_length():
    advancer, campaign, progress = _runtime(
        turn=4, revealed=["truth"], required=["truth"], minimum=7,
    )
    assert advancer.should_begin_closing_after_next_turn(campaign, progress) is False


def test_milestone_closes_session_once_minimum_length_is_reached():
    advancer, campaign, progress = _runtime(
        turn=6, revealed=["truth"], required=["truth"], minimum=7,
    )
    assert advancer.should_begin_closing_after_next_turn(campaign, progress) is True


def test_missing_milestone_waits_until_hard_cap():
    advancer, campaign, progress = _runtime(
        turn=8, revealed=[], required=["truth"], minimum=7, hard=10,
    )
    assert advancer.should_begin_closing_after_next_turn(campaign, progress) is False
    progress.turn_in_session = 9
    assert advancer.should_begin_closing_after_next_turn(campaign, progress) is True


def test_soft_limit_requests_forward_pressure_before_hard_cap():
    advancer, campaign, progress = _runtime(turn=4, soft=5, hard=10)
    assert advancer.is_soft_limit_reached(campaign, progress) is True
    assert advancer.should_begin_closing_after_next_turn(campaign, progress) is False


def test_soft_limit_focus_uses_only_unrevealed_completion_anchors():
    required = SimpleNamespace(
        id="required", name="揭示核心真相", description="确认冒充者真正身份",
    )
    optional = SimpleNamespace(
        id="optional", name="调查旁支", description="检查无关房间",
    )
    session = SimpleNamespace(
        name="档案室之谜",
        completion_anchors=["required"],
        anchor_events=[required, optional],
    )
    campaign = SimpleNamespace(
        arcs=[SimpleNamespace(goal="查明档案异常", sessions=[session])],
    )
    manager = SimpleNamespace(
        campaign=campaign,
        progress=SimpleNamespace(
            arc_index=0, session_index=0, revealed_anchors=[],
        ),
    )

    focus = PromptBuildMixin._soft_turns_focus(manager)

    assert "揭示核心真相" in focus
    assert "确认冒充者真正身份" in focus
    assert "调查旁支" not in focus


def test_soft_limit_focus_falls_back_to_arc_goal_when_anchors_are_complete():
    anchor = SimpleNamespace(id="done", name="已完成", description="已经发生")
    session = SimpleNamespace(
        name="钟楼听证", completion_anchors=["done"], anchor_events=[anchor],
    )
    manager = SimpleNamespace(
        campaign=SimpleNamespace(
            arcs=[SimpleNamespace(goal="完成听证并作出决定", sessions=[session])],
        ),
        progress=SimpleNamespace(
            arc_index=0, session_index=0, revealed_anchors=["done"],
        ),
    )

    focus = PromptBuildMixin._soft_turns_focus(manager)

    assert "完成听证并作出决定" in focus
