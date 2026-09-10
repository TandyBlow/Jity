"""CampaignManager package — thin facade over focused campaign services.

Modules:
  - fact_prompts:   fact-extraction prompt template + builder
  - facade:         CampaignManager core (lifecycle, properties, persistence)
  - facades:        anchor/context passthrough mixin
  - recap_advancer: recap + turn/session/arc advancement mixin
  - metrics:        token budget, fact extraction, per-turn metrics mixin
"""

from app.services.campaign_manager.facade import CampaignManager
from app.services.campaign_manager.fact_prompts import (
    _FACT_EXTRACTION_PROMPT,
    build_fact_extraction,
)

__all__ = [
    "CampaignManager",
    "build_fact_extraction",
    "_FACT_EXTRACTION_PROMPT",
]
