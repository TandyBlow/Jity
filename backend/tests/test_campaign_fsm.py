"""Tests for campaign FSM transitions and progress persistence."""

import json

import pytest

from app.services.campaign_fsm import CampaignStateMachine


class TestFSMTransitions:
    """Tests for HierarchicalMachine state transitions."""

    def test_initial_state_is_idle(self):
        """FSM should start in idle state."""
        fsm = CampaignStateMachine()
        assert str(fsm.state) == "idle"

    def test_start_campaign_transitions_to_session_active(self):
        """start_campaign: idle → active/session_active."""
        fsm = CampaignStateMachine()
        fsm.start_campaign()
        assert str(fsm.state) == "active/session_active"
        assert fsm.is_in_active_group() is True
        assert fsm.get_substate() == "session_active"

    def test_end_session_and_resume(self):
        """end_session → session_recap; resume_session → session_active."""
        fsm = CampaignStateMachine()
        fsm.start_campaign()
        fsm.end_session()
        assert str(fsm.state) == "active/session_recap"
        fsm.resume_session()
        assert str(fsm.state) == "active/session_active"

    def test_arc_transition_flow(self):
        """Full arc transition: session_active → session_recap → arc_transition → arc_intro → session_active."""
        fsm = CampaignStateMachine()
        fsm.start_campaign()
        fsm.end_session()
        fsm.arc_transition()
        assert str(fsm.state) == "active/arc_transition"
        assert fsm.get_substate() == "arc_transition"
        fsm.begin_arc()
        assert str(fsm.state) == "active/arc_intro"
        assert fsm.get_substate() == "arc_intro"
        fsm.session_active()
        assert str(fsm.state) == "active/session_active"

    def test_end_campaign_from_any_state(self):
        """end_campaign should work from any active substate."""
        fsm = CampaignStateMachine()
        fsm.start_campaign()
        fsm.end_campaign()
        assert str(fsm.state) == "campaign_end"

    def test_get_substate_returns_leaf(self):
        """get_substate() should return only the leaf state name."""
        fsm = CampaignStateMachine()
        assert fsm.get_substate() == "idle"
        fsm.start_campaign()
        assert fsm.get_substate() == "session_active"

    def test_is_in_active_group(self):
        """is_in_active_group() should return True only when in active/*."""
        fsm = CampaignStateMachine()
        assert fsm.is_in_active_group() is False
        fsm.start_campaign()
        assert fsm.is_in_active_group() is True
        fsm.end_campaign()
        assert fsm.is_in_active_group() is False

    def test_separator_is_slash(self):
        """State names should use '/' not '_' to separate hierarchy levels."""
        fsm = CampaignStateMachine()
        fsm.start_campaign()
        state_name = str(fsm.state)
        assert "/" in state_name
        # 'session_active' contains '_' — but the hierarchy separator is '/'
        assert "active/session_active" == state_name


class TestProgressPersistence:
    """Tests for progress save/load via Database."""

    def test_write_and_read_progress(self):
        """write_campaign_progress should persist and read_campaign_progress should load."""
        from app.database import Database
        from pathlib import Path
        import tempfile
        import os

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = Database(db_path)
            db.write_campaign_progress(
                "test-camp",
                arc_index=1,
                session_index=2,
                turn_in_session=5,
                fsm_state="active/session_active",
                revealed_anchors=["anchor-1"],
                completed_arcs=[0],
            )
            row = db.read_campaign_progress("test-camp")
            assert row is not None
            assert row["campaign_id"] == "test-camp"
            assert row["arc_index"] == 1
            assert row["session_index"] == 2
            assert row["turn_in_session"] == 5
            assert row["fsm_state"] == "active/session_active"

    def test_read_nonexistent_progress_returns_none(self):
        """read_campaign_progress for unknown ID should return None."""
        from app.database import Database
        from pathlib import Path
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            db = Database(Path(tmpdir) / "test.db")
            assert db.read_campaign_progress("nonexistent") is None

    def test_write_overwrites_existing(self):
        """Writing with same campaign_id should update existing row."""
        from app.database import Database
        from pathlib import Path
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            db = Database(Path(tmpdir) / "test.db")
            db.write_campaign_progress("test-camp", 0, 0, 0, "idle")
            db.write_campaign_progress("test-camp", 2, 1, 10, "active/session_recap")
            row = db.read_campaign_progress("test-camp")
            assert row["arc_index"] == 2
            assert row["fsm_state"] == "active/session_recap"

    def test_campaign_manager_init_fsm(self):
        """CampaignManager.load() should init FSM to active/session_active after first load."""
        from app.services.campaign_manager import CampaignManager
        from pathlib import Path
        from unittest.mock import MagicMock
        import tempfile
        import os

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            campaign_path = tmp / "test_campaign.json"
            campaign_path.write_text(json.dumps({
                "version": 3,
                "title": "FSM测试",
                "core_conflict": "冲突",
                "arcs": [],
            }, ensure_ascii=False), encoding="utf-8")

            db = MagicMock()
            db.read_campaign_progress.return_value = None
            mgr = CampaignManager(
                db=db,
                campaigns_dir=tmp,
                scripted_story=MagicMock(),
            )
            mgr.load(campaign_path)
            assert mgr.is_loaded() is True
            assert str(mgr.fsm.state) == "active/session_active"

    def test_campaign_manager_load_progress_persists_fsm(self):
        """After load(), progress should persist FSM state to DB."""
        from app.services.campaign_manager import CampaignManager
        from app.database import Database
        from pathlib import Path
        from unittest.mock import MagicMock
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            db_path = tmp / "test.db"
            db = Database(db_path)

            campaign_path = tmp / "test_campaign.json"
            campaign_path.write_text(json.dumps({
                "version": 3,
                "title": "FSM持久化测试",
                "core_conflict": "冲突",
                "arcs": [],
            }, ensure_ascii=False), encoding="utf-8")

            mgr = CampaignManager(
                db=db,
                campaigns_dir=tmp,
                scripted_story=MagicMock(),
            )
            mgr.load(campaign_path)
            mgr.save_progress()

            # Verify DB has the FSM state
            row = db.read_campaign_progress(mgr.progress.campaign_id)
            assert row is not None
            assert row["fsm_state"] == "active/session_active"
