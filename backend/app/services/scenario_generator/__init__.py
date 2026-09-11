"""ScenarioGenerator package — turn orchestration split by pipeline stage.

Modules:
  - errors:          ScenarioGenerationError
  - generator:       ScenarioGenerator core orchestration
  - opening_scene:   Hook 1 (campaign opening early-return)
  - prompting:       Hook 2 (RAG prompt assembly)
  - agent_pipeline:  Hook 3 (Examiner → Director → Narrator)
  - post_generation: Hooks 4 & 5 (facts, NPC relations, record/finalize)
  - director_support: rules/anchor/item-state helpers for the Director
"""

from app.services.scenario_generator.errors import ScenarioGenerationError
from app.services.scenario_generator.generator import ScenarioGenerator

__all__ = ["ScenarioGenerator", "ScenarioGenerationError"]
