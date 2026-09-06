"""MOOM Persona Construction Branch (PCB) package.

Modules:
  - keys:    persona key categories and extraction prompt
  - merge:   MOOM three-strategy merge logic
  - branch:  PersonaConstructionBranch main class
"""

from app.services.memory.pcb.branch import PersonaConstructionBranch
from app.services.memory.pcb.keys import PCB_INTERVAL
from app.services.memory.pcb.merge import _approx_equal

__all__ = ["PersonaConstructionBranch", "PCB_INTERVAL", "_approx_equal"]
