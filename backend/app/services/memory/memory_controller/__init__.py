"""Memory Controller package — 3-layer memory orchestration.

Orchestrates the three memory layers:
  L0 Working Memory  (~3K tokens, always in context)
  L1 Narrative Memory (~2K tokens, vector retrieval via NSB)
  L2 World Memory    (~2K tokens, keyword trigger + semantic retrieval)

Modules:
  - controller:  MemoryController core (context assembly, per-turn hooks)
  - maintenance: async maintenance + state persistence mixin
"""

from app.services.memory.memory_controller.controller import MemoryController

__all__ = ["MemoryController"]
