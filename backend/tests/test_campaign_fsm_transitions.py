"""Tests for campaign FSM transitions and progress persistence."""

import json

import pytest

from app.services.campaign_fsm import CampaignStateMachine

def _leaf(state_name: str) -> str:
    """Extract leaf state from hierarchical state name."""
    return state_name.split("/")[-1] if "/" in state_name else state_name


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
        assert _leaf(str(fsm.state)) == "session_active"

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
        assert _leaf(str(fsm.state)) == "arc_transition"
        fsm.begin_arc()
        assert str(fsm.state) == "active/arc_intro"
        assert _leaf(str(fsm.state)) == "arc_intro"
        fsm.session_active()
        assert str(fsm.state) == "active/session_active"

    def test_end_campaign_from_any_state(self):
        """end_campaign should work from any active substate."""
        fsm = CampaignStateMachine()
        fsm.start_campaign()
        fsm.end_campaign()
        assert str(fsm.state) == "campaign_end"

    def test_separator_is_slash(self):
        """State names should use '/' not '_' to separate hierarchy levels."""
        fsm = CampaignStateMachine()
        fsm.start_campaign()
        state_name = str(fsm.state)
        assert "/" in state_name
        assert "active/session_active" == state_name
