from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from app.database import Database


class KnowledgeBase:
    def __init__(self, db: Database, knowledge_dir: Path, legacy_rulebook: Path) -> None:
        self.db = db
        self.knowledge_dir = knowledge_dir
        self.legacy_rulebook = legacy_rulebook

    def load_chunks(self) -> list[dict[str, Any]]:
        files = [
            path
            for path in list(self.knowledge_dir.glob("**/*.md")) + list(self.knowledge_dir.glob("**/*.json"))
            if path.name.lower() != "readme.md"
        ]
        if self.legacy_rulebook.exists():
            files.append(self.legacy_rulebook)

        chunks: list[dict[str, Any]] = []
        for path in files:
            if path.suffix == ".json":
                chunks.extend(self._chunks_from_json(path))
            else:
                chunks.extend(self._chunks_from_markdown(path))
        self.db.replace_knowledge_chunks(chunks)
        return chunks

    def _chunks_from_markdown(self, path: Path) -> list[dict[str, Any]]:
        text = path.read_text(encoding="utf-8")
        sections = re.split(r"\n(?=##+ )", text)
        chunks = []
        for index, section in enumerate(sections):
            content = section.strip()
            if not content:
                continue
            title_match = re.search(r"^#+\s+(.+)$", content, re.MULTILINE)
            title = title_match.group(1).strip() if title_match else path.stem
            body, metadata = self._extract_markdown_metadata(content)
            if not self._has_substantive_content(body):
                continue
            source_type = str(metadata.get("source_type") or self._source_type_from_path(path))
            keywords = self._parse_keywords(metadata.get("keywords", ""))
            importance = self._parse_importance(metadata.get("importance"))
            chunks.append(self._chunk(source_type, title, body, path, index, keywords, importance))
        return chunks

    def _chunks_from_json(self, path: Path) -> list[dict[str, Any]]:
        data = json.loads(path.read_text(encoding="utf-8"))
        records = data if isinstance(data, list) else data.get("entries", [])
        chunks = []
        for index, record in enumerate(records):
            title = str(record.get("title") or record.get("name") or path.stem)
            source_type = str(record.get("source_type") or record.get("type") or "world_lore")
            content = str(record.get("content") or record.get("description") or "")
            keywords = record.get("keywords", [])
            importance = self._parse_importance(record.get("importance"))
            if content:
                chunks.append(self._chunk(source_type, title, content, path, index, keywords, importance))
        return chunks

    @staticmethod
    def _extract_markdown_metadata(content: str) -> tuple[str, dict[str, str]]:
        lines = content.splitlines()
        if not lines:
            return content, {}

        metadata: dict[str, str] = {}
        body_start = 1 if lines[0].lstrip().startswith("#") else 0
        cursor = body_start
        while cursor < len(lines) and not lines[cursor].strip():
            cursor += 1
        while cursor < len(lines):
            line = lines[cursor].strip()
            if not line:
                cursor += 1
                break
            if ":" not in line:
                break
            key, value = line.split(":", 1)
            key = key.strip().lower()
            if key not in {"source_type", "keywords", "importance"}:
                break
            metadata[key] = value.strip()
            cursor += 1

        body_lines = lines[:body_start] + lines[cursor:]
        return "\n".join(body_lines).strip(), metadata

    @staticmethod
    def _parse_keywords(value: Any) -> list[str]:
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, str):
            return [item.strip() for item in re.split(r"[,，]", value) if item.strip()]
        return []

    @staticmethod
    def _parse_importance(value: Any) -> int:
        try:
            importance = int(value)
        except (TypeError, ValueError):
            return 3
        return min(max(importance, 1), 5)

    @staticmethod
    def _has_substantive_content(content: str) -> bool:
        without_headings = re.sub(r"^#+\s+.+$", "", content, flags=re.MULTILINE)
        return bool(without_headings.strip())

    @staticmethod
    def _source_type_from_path(path: Path) -> str:
        mapping = {
            "npcs": "npc",
            "locations": "location",
            "quests": "quest",
            "rules": "rule",
            "world_lore": "world_lore",
        }
        return mapping.get(path.stem, "world_lore")

    @staticmethod
    def _chunk(
        source_type: str,
        title: str,
        content: str,
        path: Path,
        index: int,
        keywords: list[str] | None = None,
        importance: int = 3,
    ) -> dict[str, Any]:
        digest = hashlib.sha1(f"{path}:{index}:{title}".encode("utf-8")).hexdigest()[:16]
        return {
            "id": digest,
            "source_type": source_type,
            "title": title,
            "content": content,
            "keywords": keywords or [],
            "importance": importance,
            "source_path": str(path),
        }
