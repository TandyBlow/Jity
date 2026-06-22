"""CampaignGenerator — AI-powered campaign.json generation (CAMP-06).

Uses deepseek-v4-pro for creative structured generation.
Single-shot with validation gate; staged pipeline as fallback.
"""

import asyncio
import copy
import json
import logging
import re
from pathlib import Path

import charset_normalizer
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

        # Ensure top-level required fields
        data.setdefault("core_conflict", data.get("core_conflict") or "未知冲突")
        data.setdefault("constraints", "")
        data.setdefault("starting_state", {})
        return data

    async def generate_from_novel(self, text: str) -> dict[str, Any]:
        """Full novel→campaign pipeline: detect chapters → extract anchors → assemble.

        Args:
            text: Full novel text (decoded to UTF-8 string).

        Returns:
            Validated campaign dict with _extraction_errors list.
        """
        chapters = NovelIngestor.split_chapters(text)
        logger.info("Novel pipeline: detected %d chapters", len(chapters))

        # Stage 1: Per-chapter anchor extraction
        extraction_results: list[dict] = []
        extraction_errors: list[str] = []
        all_lines = text.split("\n")

        for ch in chapters:
            chapter_text = "\n".join(all_lines[ch["start_line"]:ch["end_line"]])
            # Truncate very long chapters to ~3K chars for the extraction prompt
            chapter_snippet = chapter_text[:3000]
            for attempt in range(3):
                try:
                    result = await self.llm_client.generate_json(
                        (
                            "从以下小说章节中提取关键剧情事件、NPC（名称和简述）和地点变更。"
                            "返回JSON格式：{\"events\": [{\"name\": \"事件名\", \"description\": \"简述\", \"priority\": 1-5}], "
                            "\"npcs\": [{\"name\": \"NPC名\", \"description\": \"简述\"}], "
                            "\"locations\": [\"地点名\"]}\n\n"
                            f"章节：{ch['title']}\n\n{chapter_snippet}"
                        ),
                        model="deepseek-v4-pro",
                        max_tokens=1000,
                        temperature=0.3,
                    )
                    extraction_results.append({
                        "chapter_index": ch["index"],
                        "title": ch["title"],
                        "data": result,
                    })
                    break
                except Exception as e:
                    if attempt == 2:
                        extraction_errors.append(ch["title"])
                        logger.warning("Chapter extraction failed after 3 retries: %s — %s", ch["title"], e)
            # Brief delay to avoid rate limits
            await asyncio.sleep(0.1)

        # Stage 2: Cross-chapter assembly
        assembly_input = json.dumps(extraction_results, ensure_ascii=False)

        # Save intermediate extraction results for debugging/retry
        debug_path = self.output_dir / "_last_extraction_results.json"
        debug_path.write_text(assembly_input, encoding="utf-8")
        logger.info("Saved %d chapter extraction results to %s", len(extraction_results), debug_path)
        # Token budget guard: truncate if too long (>80K chars)
        if len(assembly_input) > 80000:
            assembly_input = assembly_input[:80000]
            logger.warning("Novel pipeline: assembly input truncated to 80K chars")

        assembly_prompt = (
            "将以下小说章节的剧情提取结果合并为一个完整的campaign.json文件（3-5个叙事弧arcs，每个arc含2-4个session）。\n"
            "请严格使用以下JSON结构：\n"
            "{\n"
            '  "title": "战役标题",\n'
            '  "core_conflict": "核心冲突（一句话）",\n'
            '  "description": "战役简介（50-100字）",\n'
            '  "arcs": [\n'
            '    {\n'
            '      "name": "弧名称",\n'
            '      "goal": "弧目标",\n'
            '      "sessions": [\n'
            '        {\n'
            '          "name": "幕名称",\n'
            '          "opening_scene": "开场叙事（中文，50-150字）",\n'
            '          "anchor_events": [\n'
            '            {\n'
            '              "id": "anchor-xxx",\n'
            '              "name": "锚点事件名",\n'
            '              "description": "事件简述",\n'
            '              "priority": 1,\n'
            '              "trigger_conditions": {"location": "地点名或null", "npc_present": "NPC名或null", "item_held": "物品名或null"}\n'
            '            }\n'
            '          ]\n'
            '        }\n'
            '      ]\n'
            '    }\n'
            '  ],\n'
            '  "constraints": "叙事约束说明",\n'
            '  "starting_state": {}\n'
            '}\n\n'
            "重要注意事项：\n"
            "1. 按时间顺序组织arc\n"
            "2. 每个session包含1-2个锚点事件\n"
            "3. 字段名必须使用 name（不是arc_title、session_title、event_name）\n"
            "4. 每个锚点事件必须有 id、name、description、priority、trigger_conditions 五个字段\n"
            "5. 返回纯JSON，不要包裹在 {\"campaign\": {...}} 中\n\n"
            f"## 章节提取结果\n{assembly_input}"
        )

        try:
            campaign_data = await self.llm_client.generate_json(
                assembly_prompt,
                model="deepseek-v4-pro",
                max_tokens=50000,
                temperature=0.7,
            )
        except Exception as e:
            raise CampaignGenerationError(f"Cross-chapter assembly failed: {e}") from e

        logger.info("Assembly raw keys: %s, arc count: %d",
                     list(campaign_data.keys()) if isinstance(campaign_data, dict) else type(campaign_data),
                     len(campaign_data.get("arcs", [])) if isinstance(campaign_data, dict) else -1)

        # Unwrap if LLM nests response under "campaign" key
        if isinstance(campaign_data, dict) and "campaign" in campaign_data:
            inner = campaign_data["campaign"]
            if isinstance(inner, dict) and inner.get("arcs"):
                logger.info("Unwrapping nested 'campaign' key with %d arcs", len(inner.get("arcs", [])))
                campaign_data = inner
        campaign_data = self._remap_schema(campaign_data)
        campaign_data = self._ensure_minimal_structure(campaign_data)

        # Guard: refuse to save empty campaigns (LLM assembly likely failed)
        if not campaign_data.get("arcs"):
            raise CampaignGenerationError(
                "Assembly produced an empty campaign (zero arcs). "
                "The LLM likely returned a non-campaign response. "
                "Check backend logs for assembly raw keys."
            )

        try:
            campaign_adapter.validate_python(campaign_data)
        except Exception as e:
            raise CampaignGenerationError(f"Assembled campaign validation failed: {e}") from e

        campaign_data["_extraction_errors"] = extraction_errors
        return campaign_data


class NovelIngestor:
    """TXT preprocessing and chapter detection for novel→campaign pipeline."""

    CHAPTER_PATTERN = re.compile(
        r'^\s*(?:第[零一二三四五六七八九十百千\d]+[章回卷节幕]|楔子|尾声|序[章言]|终[章章]|[第序][章幕])\s*[^\n]*$',
        re.MULTILINE,
    )

    # Fallback: if fewer than this many chapters detected, use size-based chunking
    MIN_CHAPTERS_FOR_REGEX = 3
    CHUNK_LINES = 3000

    @staticmethod
    def detect_encoding(file_bytes: bytes) -> str:
        """Detect text encoding using charset-normalizer."""
        result = charset_normalizer.from_bytes(file_bytes).best()
        return result.encoding if result else "utf-8"

    @classmethod
    def split_chapters(cls, text: str) -> list[dict[str, Any]]:
        """Split text into chapters based on regex pattern.

        Falls back to size-based chunking if fewer than MIN_CHAPTERS_FOR_REGEX detected.
        Returns:
            [{"index": 0, "title": "序章", "start_line": 0, "end_line": 42}, ...]
        """
        all_lines = text.split("\n")
        matches = list(cls.CHAPTER_PATTERN.finditer(text))

        if len(matches) >= cls.MIN_CHAPTERS_FOR_REGEX:
            chapters = []
            for i, match in enumerate(matches):
                start_line = text[:match.start()].count("\n")
                if i + 1 < len(matches):
                    end_line = text[: matches[i + 1].start()].count("\n")
                else:
                    end_line = len(all_lines)
                title = match.group(0).strip()
                if start_line < end_line:
                    chapters.append({
                        "index": i, "title": title,
                        "start_line": start_line, "end_line": end_line,
                    })
            return chapters

        # Fallback: size-based chunking
        chapters = []
        chunk_idx = 0
        for start in range(0, len(all_lines), cls.CHUNK_LINES):
            end = min(start + cls.CHUNK_LINES, len(all_lines))
            chapters.append({
                "index": chunk_idx,
                "title": f"第{chunk_idx + 1}段",
                "start_line": start,
                "end_line": end,
            })
            chunk_idx += 1
        return chapters
