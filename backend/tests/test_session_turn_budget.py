"""A selected playthrough length survives loading and cannot leak into templates."""
import json
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.database import Database
from app.schemas import CreateSessionRequest
from app.services.campaign_manager import CampaignManager
from app.services.game_state import GameStateManager


@pytest.mark.parametrize("value", [0, 51, -1, 2.5, "30", True])
def test_reject_invalid_budget(value):
    with pytest.raises(ValidationError):
        CreateSessionRequest(max_turns_per_campaign=value)


def test_selected_budget_survives_restart_and_slots_without_changing_template(tmp_path, sample_campaign_json, monkeypatch):
    from app.routers import sessions

    db = Database(tmp_path / "sessions.db")
    state = GameStateManager(db)
    campaign_path = tmp_path / "default_campaign.json"
    sample_campaign_json["max_turns_per_campaign"] = 50
    campaign_path.write_text(json.dumps(sample_campaign_json))
    original = campaign_path.read_bytes()
    monkeypatch.setattr(sessions, "db", db)
    monkeypatch.setattr(sessions, "state_manager", state)
    monkeypatch.setattr(sessions, "settings", SimpleNamespace(campaigns_dir=tmp_path, llm_model="test"))
    monkeypatch.setattr(sessions, "build_campaign_manager", lambda: CampaignManager(db=db, campaigns_dir=tmp_path))
    monkeypatch.setattr(sessions, "campaign_manager_cache", SimpleNamespace(put=lambda *args: None))
    short = sessions.create_session(CreateSessionRequest(max_turns_per_campaign=20))
    normal = sessions.create_session(CreateSessionRequest(max_turns_per_campaign=50))
    legacy = sessions.create_session(CreateSessionRequest())

    # Reopen the database and create fresh managers, equivalent to cache eviction
    # or a server restart. Both existing and new slots inherit the same length.
    reopened = Database(tmp_path / "sessions.db")
    for session, budget in [(short, 20), (normal, 50), (legacy, 50)]:
        row = reopened.get_session(session.session_id)
        for slot in [row["active_slot_name"], "alternate"]:
            manager = CampaignManager(db=reopened, campaigns_dir=tmp_path)
            manager.load(campaign_path, campaign_id=session.session_id, slot_name=slot)
            assert manager.resolve_max_turns_per_campaign() == budget
    assert campaign_path.read_bytes() == original
