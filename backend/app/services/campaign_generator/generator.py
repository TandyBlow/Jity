"""CampaignGenerator — single-shot campaign.json generation with validation gate."""

import copy
import json
import logging
from pathlib import Path
from typing import Any

from app.database import Database
from app.schemas.campaign import (
    CURRENT_SCHEMA_VERSION,
    campaign_adapter,
    migrate,
)
from app.services.llm_client import LLMClient, LLMOutputParseError, LLMRequestError
from app.services.prompt_builder import PromptBuilder, build_campaign_gen

from app.services.campaign_generator.errors import CampaignGenerationError
from app.services.campaign_generator.novel_pipeline import NovelPipelineMixin

logger = logging.getLogger(__name__)

# Campaign generation uses v4-pro (highest creative quality)
CAMPAIGN_GEN_MODEL = "deepseek-v4-pro"
# Fallback to v4-flash if pro is unavailable
CAMPAIGN_GEN_FALLBACK = "deepseek-v4-flash"


class CampaignGenerator(NovelPipelineMixin):
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

    @staticmethod
    def _remap_schema(data: dict) -> dict:
        """Defensive field remapping for LLM output deviations.

        Handles common LLM naming variations:
        - arc_title / session_title / event_name / title → name
        - String anchor events → auto-convert to dicts
        - Missing anchor ids → auto-generated
        - Extra per-session fields stripped
        """
        data = copy.deepcopy(data)
        for ai, arc in enumerate(data.get("arcs", [])):
            # Remap arc fields: try multiple possible name sources
            for src in ("arc_title", "title"):
                if src in arc and "name" not in arc:
                    arc["name"] = arc.pop(src)
                    break
            if "name" not in arc:
                arc["name"] = f"第{ai + 1}弧"
            if "goal" not in arc:
                arc["goal"] = ""
            arc.pop("arc_id", None)

            for si, session in enumerate(arc.get("sessions", [])):
                _remap_session(session, ai, si)

        # Ensure top-level required fields
        data.setdefault("core_conflict", data.get("core_conflict") or "未知冲突")
        data.setdefault("constraints", "")
        data.setdefault("starting_state", {})
        return data


def _remap_session(session: dict, ai: int, si: int) -> None:
    """Normalize a single session dict emitted by the LLM."""
    # Remap session fields: try multiple possible name sources
    for src in ("session_title", "title"):
        if src in session and "name" not in session:
            session["name"] = session.pop(src)
            break
    if "name" not in session:
        session["name"] = f"第{si + 1}幕"
    if "opening_scene" not in session:
        session["opening_scene"] = session.pop("opening", "")
    session.pop("session_id", None)

    # Normalize anchor_events: strings → dicts
    raw_anchors = session.get("anchor_events", [])
    normalized = []
    for ani, anchor in enumerate(raw_anchors):
        if isinstance(anchor, str):
            anchor = {"name": anchor, "id": f"anchor-gen-{ai}-{si}-{ani}"}
        for src in ("event_name", "title"):
            if isinstance(anchor, dict) and src in anchor and "name" not in anchor:
                anchor["name"] = anchor.pop(src)
                break
        if isinstance(anchor, dict) and "name" not in anchor:
            anchor["name"] = f"锚点{ani + 1}"
        if isinstance(anchor, dict):
            if "id" not in anchor or not anchor.get("id"):
                anchor["id"] = f"anchor-gen-{ai}-{si}-{ani}"
            if "priority" not in anchor:
                anchor["priority"] = min(ani + 1, 5)
            if "trigger_conditions" not in anchor:
                anchor["trigger_conditions"] = {"location": None, "npc_present": None, "item_held": None}
            if "description" not in anchor:
                anchor["description"] = anchor.get("name", "")
        normalized.append(anchor)
    session["anchor_events"] = normalized

    # Strip session-level fields not in schema
    for extra_key in ("core_conflict", "constraints", "npcs", "session_id", "opening"):
        session.pop(extra_key, None)
