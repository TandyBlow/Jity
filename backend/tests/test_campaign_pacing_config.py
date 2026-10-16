"""Production campaign pacing stays complete inside the 50-turn budget."""

import json
from pathlib import Path

import pytest

from app.schemas.campaign import CampaignSchema


CAMPAIGNS_DIR = Path(__file__).resolve().parents[1] / "data" / "campaigns"
PRODUCTION_CAMPAIGNS = [
    CAMPAIGNS_DIR / "default_campaign.json",
    CAMPAIGNS_DIR / "龙族Ⅰ_火之晨曦_campaign.json",
    CAMPAIGNS_DIR / "龙族Ⅱ_悼亡者之瞳_campaign.json",
    CAMPAIGNS_DIR / "龙族Ⅲ_黑月之潮_campaign.json",
]


def _load(path: Path) -> CampaignSchema:
    return CampaignSchema.model_validate(json.loads(path.read_text(encoding="utf-8")))


@pytest.mark.parametrize("path", PRODUCTION_CAMPAIGNS, ids=lambda path: path.stem)
def test_production_campaigns_have_complete_pacing_gates(path):
    campaign = _load(path)

    assert campaign.max_turns_per_campaign == 50
    assert campaign.max_turns_per_session is not None
    for arc in campaign.arcs:
        for session in arc.sessions:
            maximum = session.max_turns_per_session or campaign.max_turns_per_session
            assert session.soft_turns_per_session is not None
            assert session.hard_turns_per_session is not None
            assert 1 <= session.soft_turns_per_session <= session.hard_turns_per_session <= maximum
            assert session.completion_anchors
            authored = {anchor.id for anchor in session.anchor_events}
            assert set(session.completion_anchors).issubset(authored)


@pytest.mark.parametrize("path", PRODUCTION_CAMPAIGNS, ids=lambda path: path.stem)
def test_worst_case_core_completion_leaves_room_for_ending(path):
    campaign = _load(path)
    sessions = [session for arc in campaign.arcs for session in arc.sessions]
    spent_before_final = 0

    for session in sessions[:-1]:
        # From hard: one turn per required anchor, one closure turn and one
        # player-selected transition turn.  Natural early reveals only reduce
        # this worst-case estimate.
        required = len(session.completion_anchors)
        consumed = session.hard_turns_per_session + required + 1
        maximum = session.max_turns_per_session or campaign.max_turns_per_session
        spent_before_final += min(consumed, maximum)

    final = sessions[-1]
    final_required = len(final.completion_anchors)
    ending_turn = final.hard_turns_per_session + final_required + 1
    final_maximum = final.max_turns_per_session or campaign.max_turns_per_session

    assert final_maximum >= ending_turn
    assert spent_before_final + ending_turn <= campaign.max_turns_per_campaign
    assert campaign.max_turns_per_campaign - spent_before_final >= 7
