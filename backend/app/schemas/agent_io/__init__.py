"""Pydantic schemas for multi-agent pipeline I/O package.

Examiner → Director → Narrator each consume/produce typed JSON.
Also includes SCORE item-state tracking and MOOM memory data structures.

Modules:
  - examiner:        ActionPermissibility, TriggeredRule, ActionRuling
  - director:        RedirectionStrategy, ItemContinuityCheck, DirectorInstruction
  - memory_branches: SCORE / NSB / PCB / MOOM / HaluMem models
"""

from app.schemas.agent_io.director import (
    DirectorInstruction,
    ItemContinuityCheck,
    RedirectionStrategy,
)
from app.schemas.agent_io.examiner import (
    ActionPermissibility,
    ActionRuling,
    TriggeredRule,
)
from app.schemas.agent_io.memory_branches import (
    EpisodeSummary,
    HallucinationFinding,
    HallucinationType,
    ItemState,
    ItemStateRecord,
    MemoryRecord,
    PersonaKey,
    PersonaSketch,
    PersonaSnapshot,
    PersonaValue,
)

__all__ = [
    "ActionPermissibility",
    "TriggeredRule",
    "ActionRuling",
    "RedirectionStrategy",
    "ItemContinuityCheck",
    "DirectorInstruction",
    "ItemState",
    "ItemStateRecord",
    "EpisodeSummary",
    "PersonaKey",
    "PersonaValue",
    "PersonaSnapshot",
    "PersonaSketch",
    "MemoryRecord",
    "HallucinationType",
    "HallucinationFinding",
]
