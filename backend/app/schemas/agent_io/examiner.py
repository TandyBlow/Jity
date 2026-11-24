"""Examiner Agent I/O schemas — action feasibility and triggered rules."""

from enum import Enum

from pydantic import BaseModel, Field


class ActionPermissibility(str, Enum):
    """Examiner verdict on player action feasibility."""

    PERMISSIBLE = "permissible"
    CONDITIONAL = "conditional"  # needs a dice roll / sanity check
    BLOCKED = "blocked"  # impossible given current state


class TriggeredRule(BaseModel):
    """A game rule that the Examiner identifies as relevant this turn."""

    rule_type: str = Field(description="e.g. 'sanity_check', 'skill_check', 'combat', 'item_use'")
    rule_name: str = Field(description="Human-readable rule name, e.g. 'SAN检定：遭遇神话生物'")
    rule_details: str = Field(default="", description="Brief rule mechanics, e.g. '1d100 ≤ SAN值，失败扣除1d6'")


class ActionRuling(BaseModel):
    """Examiner Agent output — action feasibility and triggered rules."""

    permissibility: ActionPermissibility = ActionPermissibility.PERMISSIBLE
    triggered_rules: list[TriggeredRule] = Field(default_factory=list)
    constraints: str = Field(
        default="",
        description="Narrative constraints for the Director, e.g. '玩家没有钥匙，无法开门'",
    )
    rejection_reason: str = Field(
        default="",
        description="If blocked, a diegetic reason to relay to the player",
    )
