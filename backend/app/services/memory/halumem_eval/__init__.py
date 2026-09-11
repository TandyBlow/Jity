"""HaluMem evaluation package — operation-level hallucination evaluation.

Modules:
  - prompts:   evaluation prompt templates
  - parsing:   findings parsing and aggregate metrics
  - evaluator: HaluMemEvaluator runner
"""

from app.services.memory.halumem_eval.evaluator import HaluMemEvaluator
from app.services.memory.halumem_eval.parsing import _parse_findings

__all__ = ["HaluMemEvaluator", "_parse_findings"]
