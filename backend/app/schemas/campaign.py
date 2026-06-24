"""Campaign-related Pydantic schemas — campaign.json format, anchor events, progress.

Used by CampaignManager (Phase 2).
"""

from enum import Enum
from typing import Any, Callable, Literal, Optional

from pydantic import BaseModel, Field, TypeAdapter


class AnchorTriggerConditions(BaseModel):
    """Hard-filter conditions for anchor event activation."""
    location: Optional[str] = None
    npc_present: Optional[str] = None
    item_held: Optional[str] = None


class AnchorEvent(BaseModel):
    """A single narrative milestone with trigger conditions."""
    id: str
    name: str
    description: str
    priority: int = Field(ge=1, le=5, default=3)
    trigger_conditions: AnchorTriggerConditions = Field(default_factory=AnchorTriggerConditions)


class SessionSchema(BaseModel):
    """A single session within an arc."""
    name: str
    opening_scene: str = ""
    anchor_events: list[AnchorEvent] = Field(default_factory=list)
    entry_state: dict[str, Any] | None = None


class ArcSchema(BaseModel):
    """A narrative arc containing multiple sessions."""
    name: str
    goal: str = ""
    sessions: list[SessionSchema] = Field(default_factory=list)


class CampaignSchema(BaseModel):
    """Top-level campaign definition matching campaign.json format."""
    version: int = 1
    title: str
    core_conflict: str
    arcs: list[ArcSchema] = Field(default_factory=list)
    constraints: str = ""
    starting_state: dict[str, Any] = Field(default_factory=dict)
    # v4 additions
    difficulty: Literal["easy", "normal", "hard", "insane"] = "normal"
    difficulty_settings: dict[str, Any] | None = None
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    estimated_duration: int = 0


class CampaignProgress(BaseModel):
    """Runtime tracking of campaign progress (campaign_progress table row)."""
    campaign_id: str
    arc_index: int = 0
    session_index: int = 0
    turn_in_session: int = 0
    revealed_anchors: list[str] = Field(default_factory=list)
    completed_arcs: list[int] = Field(default_factory=list)


# ── Version migration chain (v1 → v2 → v3) ──


def _migrate_v1_to_v2(data: dict) -> dict:
    """v1 → v2: Add `constraints` field default if missing.

    v2 adds per-session constraints override support.
    """
    data = dict(data)  # shallow copy
    data.setdefault("constraints", "")
    data["version"] = 2
    return data


def _migrate_v2_to_v3(data: dict) -> dict:
    """v2 → v3: Add `starting_state` field default if missing.

    v3 adds campaign-level starting_state override for game session init.
    """
    data = dict(data)
    data.setdefault("starting_state", {})
    data["version"] = 3
    return data


def _migrate_v3_to_v4(data: dict) -> dict:
    """v3 → v4: Add difficulty, description, tags, estimated_duration defaults.

    v4 adds campaign-level difficulty settings and metadata.
    """
    data = dict(data)
    data.setdefault("difficulty", "normal")
    data.setdefault("difficulty_settings", None)
    data.setdefault("description", "")
    data.setdefault("tags", [])
    data.setdefault("estimated_duration", 0)
    data["version"] = 4
    return data


# Ordered: version N maps to function that transforms N → N+1
_MIGRATIONS: dict[int, Callable[[dict], dict]] = {
    1: _migrate_v1_to_v2,
    2: _migrate_v2_to_v3,
    3: _migrate_v3_to_v4,
}

CURRENT_SCHEMA_VERSION = 4


def migrate(data: dict, target_version: int = CURRENT_SCHEMA_VERSION) -> dict:
    """Chain migrations until data reaches target_version.

    Each migration function receives the output of the previous one.
    Returns the migrated dict (ready for Pydantic validation).
    """
    while data.get("version", 1) < target_version:
        current_ver = data.get("version", 1)
        if current_ver not in _MIGRATIONS:
            break
        data = _MIGRATIONS[current_ver](data)
    return data


# TypeAdapter for independent re-validation after migration
campaign_adapter = TypeAdapter(CampaignSchema)


# ── Recap (CAMP-08) ──


class RecapData(BaseModel):
    """Dual recap storage — compressed for prompt injection, full for historical preservation."""
    compressed: str = ""
    full: str = ""


# ── Health Monitoring (CAMP-09) ──


class HealthGuidanceHint(str, Enum):
    """Narrative health degradation categories — each maps to a diegetic hint."""
    PACING_SLOW = "pacing_slow"
    PACING_FAST = "pacing_fast"
    DIALOGUE_HEAVY = "dialogue_heavy"
    TENSION_PLATEAU = "tension_plateau"
    CLUE_STARVATION = "clue_starvation"


class HealthMetrics(BaseModel):
    """Per-turn narrative health metrics (CAMP-09).

    Pure computation from model_outputs instrumentation columns.
    No LLM calls needed.
    """
    pacing_score: float = Field(default=0.5, ge=0.0, le=1.0, description="Turns per meaningful event ratio")
    tension_trajectory: str = Field(default="stable", description="rising|falling|plateau|peak|valley|stable")
    clue_exposure_rate: float = Field(default=0.0, ge=0.0, description="New facts + revealed anchors per 10 turns")
    dialogue_density: float = Field(default=0.0, ge=0.0, le=1.0, description="dialogue_lines / word_count ratio")
    narrative_throughput: float = Field(default=0.0, description="word_count z-score vs baseline")
    needs_guidance: bool = Field(default=False, description="True if any metric exceeds degradation threshold")
    guidance_hints: list[HealthGuidanceHint] = Field(default_factory=list, description="Which guidance categories to inject")
    last_guidance_turn: dict[str, int] = Field(default_factory=dict, description="{hint_name: last_injected_turn} for throttling")
