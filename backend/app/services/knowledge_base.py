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
        files = list(self.knowledge_dir.glob("**/*.md")) + list(self.knowledge_dir.glob("**/*.json"))
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
            chunks.append(self._chunk("rule", title, content, path, index))
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
            if content:
                chunks.append(self._chunk(source_type, title, content, path, index, keywords))
        return chunks

    @staticmethod
    def _chunk(
        source_type: str,
        title: str,
        content: str,
        path: Path,
        index: int,
        keywords: list[str] | None = None,
    ) -> dict[str, Any]:
        digest = hashlib.sha1(f"{path}:{index}:{title}".encode("utf-8")).hexdigest()[:16]
        return {
            "id": digest,
            "source_type": source_type,
            "title": title,
            "content": content,
            "keywords": keywords or [],
            "source_path": str(path),
        }
