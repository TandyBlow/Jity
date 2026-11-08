"""Runtime pacing reads campaign data and Settings, never runner files."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from app.config import Settings
from app.services.campaign_advancer import CampaignSessionAdvancer


def advancer(**values):
    return CampaignSessionAdvancer(Mock(), Mock(), Settings(_env_file=None, **values))


def campaign(session_cap=None, campaign_session_cap=None, campaign_cap=None):
    session = SimpleNamespace(max_turns_per_session=session_cap)
    return SimpleNamespace(
        max_turns_per_session=campaign_session_cap,
        max_turns_per_campaign=campaign_cap,
        arcs=[SimpleNamespace(sessions=[session, session])],
    )


@pytest.mark.parametrize("session_cap,campaign_cap,expected", [(7, 10, 7), (None, 10, 10), (None, None, 12)])
def test_session_cap_precedence(session_cap, campaign_cap, expected):
    runtime = advancer(max_turns_per_session=12, max_turns_per_campaign=40)
    progress = SimpleNamespace(arc_index=0, session_index=0, turn_in_session=0, turns_total=0)
    assert runtime.resolve_max_turns(campaign(session_cap, campaign_cap), progress) == expected


@pytest.mark.parametrize("authored,expected", [(None, 24), (18, 18), (100, 50), (0, 1)])
def test_campaign_overrides_settings_with_existing_product_clamp(authored, expected):
    runtime = advancer(max_turns_per_campaign=24)
    assert runtime.resolve_max_turns_per_campaign(campaign(campaign_cap=authored)) == expected


def test_backend_environment_supplies_fallbacks(monkeypatch):
    monkeypatch.setenv("MAX_TURNS_PER_SESSION", "11")
    monkeypatch.setenv("MAX_TURNS_PER_CAMPAIGN", "22")
    runtime = advancer()
    assert runtime.resolve_max_turns(None, None) == 11
    assert runtime.resolve_max_turns_per_campaign(None) == 22


def test_settings_defaults_keep_existing_budgets(monkeypatch):
    monkeypatch.delenv("MAX_TURNS_PER_SESSION", raising=False)
    monkeypatch.delenv("MAX_TURNS_PER_CAMPAIGN", raising=False)
    runtime = advancer()
    assert runtime.resolve_max_turns(None, None) == 30
    assert runtime.resolve_max_turns_per_campaign(None) == 50


@pytest.mark.parametrize("values", [
    {"max_turns_per_session": 0}, {"max_turns_per_campaign": 0}, {"max_turns_per_campaign": 51},
])
def test_settings_reject_invalid_budgets(values):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **values)


def test_budget_resolution_does_not_read_files(monkeypatch):
    runtime = advancer(max_turns_per_session=9, max_turns_per_campaign=20)
    def unexpected_read(*args, **kwargs):
        raise AssertionError("Runtime pacing must not read runner configuration")
    monkeypatch.setattr(Path, "read_text", unexpected_read)
    assert runtime.resolve_max_turns(None, None) == 9
    assert runtime.resolve_max_turns_per_campaign(None) == 20


def test_allocation_still_reserves_turns_for_remaining_sessions():
    runtime = advancer(max_turns_per_session=30, max_turns_per_campaign=20)
    progress = SimpleNamespace(arc_index=0, session_index=0, turn_in_session=2, turns_total=2)
    assert runtime.resolve_max_turns(campaign(), progress) == 10
