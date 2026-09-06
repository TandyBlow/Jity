"""MOOM Narrative Summarization Branch (NSB) package.

Modules:
  - prompts: MOOM thresholds and summarization prompt templates
  - parsing: safe type-coercion helpers for LLM output
  - branch:  NarrativeSummarizationBranch hierarchical summarizer
"""

from app.services.memory.nsb.branch import NarrativeSummarizationBranch
from app.services.memory.nsb.prompts import THETA_1, THETA_2, THETA_3

__all__ = ["NarrativeSummarizationBranch", "THETA_1", "THETA_2", "THETA_3"]
