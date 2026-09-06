"""Novel → campaign pipeline: per-chapter extraction and cross-chapter assembly."""

import asyncio
import json
import logging

logger = logging.getLogger(__name__)


class NovelPipelineMixin:
    async def generate_from_novel(self, text: str) -> dict:
        """Full novel→campaign pipeline: detect chapters → extract anchors → assemble.

        Args:
            text: Full novel text (decoded to UTF-8 string).

        Returns:
            Validated campaign dict with _extraction_errors list.
        """
        from app.services.campaign_generator.novel_ingestor import NovelIngestor
        from app.services.campaign_generator.errors import CampaignGenerationError
        from app.schemas.campaign import campaign_adapter

        chapters = NovelIngestor.split_chapters(text)
        logger.info("Novel pipeline: detected %d chapters", len(chapters))

        extraction_results, extraction_errors = await self._extract_chapters(
            text, chapters
        )

        campaign_data = await self._assemble_campaign(extraction_results)

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

    async def _extract_chapters(self, text: str, chapters: list[dict]) -> tuple[list[dict], list[str]]:
        """Stage 1: per-chapter anchor extraction with retries."""
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

        return extraction_results, extraction_errors

    async def _assemble_campaign(self, extraction_results: list[dict]) -> dict:
        """Stage 2: cross-chapter assembly into one validated campaign dict."""
        from app.services.campaign_generator.errors import CampaignGenerationError
        from app.services.campaign_generator.generator import CAMPAIGN_GEN_MODEL

        assembly_input = json.dumps(extraction_results, ensure_ascii=False)

        # Save intermediate extraction results for debugging/retry
        debug_path = self.output_dir / "_last_extraction_results.json"
        debug_path.write_text(assembly_input, encoding="utf-8")
        logger.info("Saved %d chapter extraction results to %s", len(extraction_results), debug_path)
        # Token budget guard: truncate if too long (>80K chars)
        if len(assembly_input) > 80000:
            assembly_input = assembly_input[:80000]
            logger.warning("Novel pipeline: assembly input truncated to 80K chars")

        assembly_prompt = _build_assembly_prompt(assembly_input)

        try:
            campaign_data = await self.llm_client.generate_json(
                assembly_prompt,
                model=CAMPAIGN_GEN_MODEL,
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
        return campaign_data


def _build_assembly_prompt(assembly_input: str) -> str:
    return (
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
