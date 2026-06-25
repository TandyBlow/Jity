"""Pydantic schemas for multi-agent pipeline I/O.

Examiner → Director → Narrator each consume/produce typed JSON.
Also includes SCORE item-state tracking and MOOM memory data structures.
"""

from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


# ── Examiner Agent ──────────────────────────────────────────────


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


# ── Director Agent ──────────────────────────────────────────────


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


# ── SCORE Item State Tracker ────────────────────────────────────


class ItemState(str, Enum):
    """SCORE item state machine values."""

    ACTIVE = "active"
    LOST = "lost"
    DESTROYED = "destroyed"
    UNKNOWN = "unknown"


class ItemStateRecord(BaseModel):
    """Tracked item state for SCORE continuity validation."""

    item_name: str
    state: ItemState = ItemState.ACTIVE
    last_seen_turn: int = 0
    notes: str = ""


# ── MOOM Narrative Summarization Branch (NSB) ──────────────────


class EpisodeSummary(BaseModel):
    """One episode summary produced by NSB hierarchical summarization."""

    episode_id: str
    turn_start: int
    turn_end: int
    summary: str
    tags: list[str] = Field(default_factory=list)
    entities_involved: list[str] = Field(default_factory=list)
    causal_links: list[str] = Field(default_factory=list, description="e.g. 'scene_041→scene_042: 玩家跟踪老汤姆'" "")
    state_changes: dict[str, str] = Field(default_factory=dict, description="e.g. {'线索.神秘信件': 'found'}")
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    level: int = Field(default=1, ge=1, le=3, description="1=raw对话, 2=一级摘要, 3=二级摘要")


# ── MOOM Persona Construction Branch (PCB) ──────────────────────


class PersonaKey(str, Enum):
    """Categories for persona key-value tracking."""

    NAME = "name"
    AGE = "age"
    GENDER = "gender"
    LIKED = "liked"
    DISLIKED = "disliked"
    SKILLS = "skills"
    WEAKNESSES = "weaknesses"
    BACKGROUND = "background"
    TRAJECTORY = "trajectory"
    OTHER = "other"


class PersonaValue(BaseModel):
    """A single value entry for a persona key, with timestamp metadata."""

    value: str
    turn: int = 0


class PersonaSnapshot(BaseModel):
    """Snapshot of persona extracted at a given interval by PCB."""

    character_name: str = "player"
    entries: dict[str, list[PersonaValue]] = Field(default_factory=dict)
    extracted_at_turn: int = 0


class PersonaSketch(BaseModel):
    """Cumulative persona sketch maintained by PCB merging logic."""

    entries: dict[str, list[PersonaValue]] = Field(default_factory=dict)


# ── MOOM Forgetting ─────────────────────────────────────────────


class MemoryRecord(BaseModel):
    """A single memory entry in the MOOM competition-inhibition pool."""

    memory_id: str
    content: str
    created_round: int = 0
    retrieved_rounds: list[int] = Field(default_factory=list)
    score: float = 0.0
    memory_type: str = Field(default="narrative", description="'narrative' or 'persona'")


# ── HaluMem Evaluation ──────────────────────────────────────────


class HallucinationType(str, Enum):
    """HaluMem four-class hallucination taxonomy."""

    FABRICATION = "fabrication"  # fabricated information
    ERROR = "error"  # incorrect recording of existing info
    CONFLICT = "conflict"  # new-old memory contradiction
    OMISSION = "omission"  # should-have-recorded but missing


class HallucinationFinding(BaseModel):
    """Single hallucination finding from HaluMem evaluation."""

    hallucination_type: HallucinationType
    memory_id: str = ""
    description: str
    ground_truth: str = Field(default="", description="Correct value if known")
