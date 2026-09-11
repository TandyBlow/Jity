"""Knowledge chunk persistence."""

import json
from typing import Any


class KnowledgeStoreMixin:
    def add_knowledge_chunk(self, chunk_id: str, source_type: str, title: str, content: str, keywords: list[str] | None = None, importance: int = 3, source_path: str = "") -> None:
        """Insert a single knowledge chunk (upsert by id). Used by MemoryController for NSB episodes."""
        with self.connect() as db:
            db.execute(
                """
                INSERT INTO knowledge_chunks (id, source_type, title, content, keywords, importance, source_path)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    content = excluded.content,
                    keywords = excluded.keywords,
                    importance = excluded.importance
                """,
                (
                    chunk_id,
                    source_type,
                    title,
                    content,
                    json.dumps(keywords or [], ensure_ascii=False),
                    importance,
                    source_path,
                ),
            )

    def get_narrative_episodes(self) -> list[dict[str, Any]]:
        """Read persisted NSB episodes for memory restoration."""
        with self.connect() as db:
            rows = db.execute(
                """SELECT id, title, content, keywords, importance, updated_at
                   FROM knowledge_chunks
                   WHERE source_type = 'narrative_memory'
                   ORDER BY updated_at ASC"""
            ).fetchall()
        return [
            {
                "id": row["id"],
                "title": row["title"],
                "content": row["content"],
                "keywords": json.loads(row["keywords"])
                if isinstance(row["keywords"], str)
                else (row["keywords"] or []),
                "importance": row["importance"],
                "updated_at": row["updated_at"],
            }
            for row in rows
        ]

    def replace_knowledge_chunks(self, chunks: list[dict[str, Any]]) -> None:
        with self.connect() as db:
            db.execute("DELETE FROM knowledge_chunks")
            db.executemany(
                """
                INSERT INTO knowledge_chunks (id, source_type, title, content, keywords, importance, source_path)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        chunk["id"],
                        chunk["source_type"],
                        chunk["title"],
                        chunk["content"],
                        json.dumps(chunk.get("keywords", []), ensure_ascii=False),
                        int(chunk.get("importance", 3)),
                        chunk.get("source_path", ""),
                    )
                    for chunk in chunks
                ],
            )
