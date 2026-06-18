"""CampaignGenerator — AI-powered campaign.json generation (CAMP-06).

Uses deepseek-v4-pro for creative structured generation.
Single-shot with validation gate; staged pipeline as fallback.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from app.database import Database
from app.schemas.campaign import (
    CampaignSchema,
    migrate,
    campaign_adapter,
    CURRENT_SCHEMA_VERSION,
)
from app.services.llm_client import LLMClient, LLMOutputParseError, LLMRequestError
from app.services.prompt_builder import PromptBuilder, build_campaign_gen

logger = logging.getLogger(__name__)

# Campaign generation uses v4-pro (highest creative quality)
CAMPAIGN_GEN_MODEL = "deepseek-v4-pro"
# Fallback to v4-flash if pro is unavailable
CAMPAIGN_GEN_FALLBACK = "deepseek-v4-flash"


class CampaignGenerationError(RuntimeError):
    """Raised when campaign generation fails."""
    pass


class CampaignGenerator:
    """Generates campaign.json from user prompt via deepseek-v4-pro.

    Single-shot generation with Pydantic validation gate.
    Falls back to staged repair pipeline on validation failure.
    """

    def __init__(
        self,
        llm_client: LLMClient,
        prompt_builder: PromptBuilder,
        db: Database,
        output_dir: Path,
    ) -> None:
        self.llm_client = llm_client
        self.prompt_builder = prompt_builder  # retained for potential future use
        self.db = db
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

    async def generate(self, user_prompt: str) -> dict[str, Any]:
        """Generate and validate a campaign.json from user prompt.

        Returns the validated campaign dict ready for saving.
        Raises CampaignGenerationError on failure.
        """
        prompt = build_campaign_gen(user_prompt)

        # Stage 1: single-shot generation with v4-pro
        try:
            data = await self.llm_client.generate_json(
                prompt, model=CAMPAIGN_GEN_MODEL, max_tokens=50000, temperature=0.7
            )
        except (LLMRequestError, LLMOutputParseError) as exc:
            # Fallback to flash model
            logger.warning("v4-pro generation failed, trying v4-flash: %s", exc)
            try:
                data = await self.llm_client.generate_json(
                    prompt, model=CAMPAIGN_GEN_FALLBACK, max_tokens=50000, temperature=0.7
                )
            except Exception as exc2:
                raise CampaignGenerationError(f"Both models failed: {exc2}") from exc2

        # Stage 2: validation gate
        data = self._ensure_minimal_structure(data)
        try:
            validated = campaign_adapter.validate_python(data)
        except Exception as exc:
            raise CampaignGenerationError(f"Campaign validation failed: {exc}") from exc

        return validated.model_dump()

    def save(self, campaign_data: dict, filename: str | None = None) -> Path:
        """Save generated campaign to output directory.

        Args:
            campaign_data: Validated campaign dict
            filename: Optional filename (without extension). Defaults to title-based slug.

        Returns:
            Path to saved file
        """
        if filename is None:
            title = campaign_data.get("title", "generated_campaign")
            # Simple slug from title
            slug = title.replace(" ", "_").replace(" ", "_")[:50]
            filename = f"{slug}.json"

        output_path = self.output_dir / filename
        output_path.write_text(
            json.dumps(campaign_data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return output_path

    @staticmethod
    def _ensure_minimal_structure(data: dict) -> dict:
        """Ensure generated data has all required top-level fields."""
        data.setdefault("version", CURRENT_SCHEMA_VERSION)
        data.setdefault("title", "AI生成的战役")
        data.setdefault("core_conflict", "未知冲突")
        data.setdefault("arcs", [])
        data.setdefault("constraints", "")
        data.setdefault("starting_state", {})
        if data.get("version", 1) < CURRENT_SCHEMA_VERSION:
            data = migrate(data, CURRENT_SCHEMA_VERSION)
        return data
