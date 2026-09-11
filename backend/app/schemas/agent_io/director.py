"""Director Agent I/O schemas — narrative direction, anchors, continuity."""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class RedirectionStrategy(str, Enum):
    """SENNA's six narrative redirection strategies."""

    MORE_INFORMATION = "more_information"  # offer hints
    WORLD_CONSEQUENCES = "world_consequences"  # world reacts
    NPC_INFLUENCE = "npc_influence"  # NPC steers player
    ENVIRONMENTAL_CUE = "environmental_cue"  # environmental hints
    DRAMATIC_TIMING = "dramatic_timing"  # wait for better moment
    HARD_DENIAL = "hard_denial"  # explicit block (last resort)


class ItemContinuityCheck(BaseModel):
    """SCORE-style item state continuity check result."""

    item_name: str
    previous_state: str  # active / lost / destroyed / unknown
    current_state: str
    is_valid_transition: bool = True
    error_description: str = Field(default="")


class DirectorInstruction(BaseModel):
    """Director Agent output — narrative direction, anchors, continuity."""

    narrative_direction: str = Field(
        description="High-level instruction for the Narrator, e.g. '引导玩家进入钟楼，揭示第一个线索'"
    )
    anchor_triggered: str = Field(
        default="",
        description="ID of the anchor event to activate this turn, empty if none",
    )
    redirection_strategy: Optional[RedirectionStrategy] = Field(
        default=None,
        description="Set only when player deviates and needs redirecting",
    )
    redirection_hint: str = Field(
        default="",
        description="Concrete hint text for the Narrator to weave in, e.g. '远处的钟声再次响起'",
    )
    item_continuity_checks: list[ItemContinuityCheck] = Field(default_factory=list)
    health_guidance: str = Field(
        default="",
        description="CAMP-09 narrative health guidance (diegetic only)",
    )
