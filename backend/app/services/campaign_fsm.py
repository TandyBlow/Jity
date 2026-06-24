"""Campaign state machine using transitions library.

Defines the arc → session → scene state hierarchy.
Uses HierarchicalMachine with '/' separator to avoid underscore ambiguity
in state names like 'arc_intro'.
"""
from transitions.extensions.nesting import HierarchicalMachine, NestedState


class _SlashSeparatedState(NestedState):
    """NestedState with '/' separator to avoid '_' ambiguity in state names."""
    separator = "/"


class _CampaignHierarchicalMachine(HierarchicalMachine):
    """HierarchicalMachine pre-configured with '/' separator for nested states."""
    state_cls = _SlashSeparatedState


class CampaignStateMachine:
    """State machine for campaign arc/session/scene progression.

    States (hierarchical with '/' separator):
      - idle               — no campaign active
      - active/arc_intro    — new arc intro sequence
      - active/session_active — mid-session gameplay
      - active/session_recap  — end-of-session recap
      - active/arc_transition — between-arc transition
      - campaign_end         — campaign complete

    Transitions:
      - start_campaign: idle → active/session_active
      - arc_intro: active/session_active → active/arc_intro
      - session_active: active/arc_intro → active/session_active
      - end_session: active/session_active → active/session_recap
      - resume_session: active/session_recap → active/session_active
      - arc_transition: active/session_recap → active/arc_transition
      - begin_arc: active/arc_transition → active/arc_intro
      - end_campaign: * → campaign_end
    """

    states = [
        "idle",
        {
            "name": "active",
            "children": [
                "arc_intro",
                "session_active",
                "session_recap",
                "arc_transition",
            ],
            "initial": "session_active",
        },
        "campaign_end",
    ]

    transitions = [
        {"trigger": "start_campaign", "source": "idle", "dest": "active/session_active"},
        {"trigger": "arc_intro", "source": "active/session_active", "dest": "active/arc_intro"},
        {"trigger": "session_active", "source": "active/arc_intro", "dest": "active/session_active"},
        {"trigger": "end_session", "source": "active/session_active", "dest": "active/session_recap"},
        {"trigger": "resume_session", "source": "active/session_recap", "dest": "active/session_active"},
        {"trigger": "arc_transition", "source": "active/session_recap", "dest": "active/arc_transition"},
        {"trigger": "begin_arc", "source": "active/arc_transition", "dest": "active/arc_intro"},
        {"trigger": "end_campaign", "source": "*", "dest": "campaign_end"},
    ]

    def __init__(self) -> None:
        self.machine = _CampaignHierarchicalMachine(
            model=self,
            states=CampaignStateMachine.states,
            transitions=CampaignStateMachine.transitions,
            initial="idle",
        )
