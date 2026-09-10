"""CampaignGenerator package — AI campaign generation and novel ingestion.

Modules:
  - errors:          CampaignGenerationError
  - generator:       single-shot generation with validation gate
  - novel_pipeline:  novel→campaign extraction and assembly
  - novel_ingestor:  TXT encoding detection and chapter splitting
"""

from app.services.campaign_generator.errors import CampaignGenerationError
from app.services.campaign_generator.generator import (
    CAMPAIGN_GEN_FALLBACK,
    CAMPAIGN_GEN_MODEL,
    CampaignGenerator,
)
from app.services.campaign_generator.novel_ingestor import NovelIngestor

__all__ = [
    "CampaignGenerator",
    "CampaignGenerationError",
    "NovelIngestor",
    "CAMPAIGN_GEN_MODEL",
    "CAMPAIGN_GEN_FALLBACK",
]
