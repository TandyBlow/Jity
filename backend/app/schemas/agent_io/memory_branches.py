"""Memory subsystem schemas — SCORE, NSB, PCB, MOOM forgetting, HaluMem."""

from enum import Enum

from pydantic import BaseModel, Field


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
