"""Model output persistence."""

import json
from typing import Any


class ModelOutputStoreMixin:
    def add_model_output(
        self,
        session_id: str,
        model: str,
        input_text: str,
        output: dict[str, Any],
        latency_ms: int,
        source: str = "llm",
        status: str = "ok",
        raw_output_text: str = "",
        error_text: str = "",
        retrieved_chunks: list[dict[str, Any]] | None = None,
        word_count: int = 0,
        option_count: int = 0,
        sanity_delta: int = 0,
        health_delta: int = 0,
        dialogue_lines: int = 0,
        location_changed: int = 0,
        token_count: int = 0,
    ) -> int:
        with self.connect() as db:
            cursor = db.execute(
                """
                INSERT INTO model_outputs (
                  session_id,
                  model,
                  input_text,
                  output_json,
                  latency_ms,
                  source,
                  status,
                  raw_output_text,
                  error_text,
                  retrieved_chunks_json,
                  word_count,
                  option_count,
                  sanity_delta,
                  health_delta,
                  dialogue_lines,
                  location_changed,
                  token_count
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    model,
                    input_text,
                    json.dumps(output, ensure_ascii=False),
                    latency_ms,
                    source,
                    status,
                    raw_output_text,
                    error_text,
                    json.dumps(retrieved_chunks or [], ensure_ascii=False),
                    word_count,
                    option_count,
                    sanity_delta,
                    health_delta,
                    dialogue_lines,
                    location_changed,
                    token_count,
                ),
            )
            return int(cursor.lastrowid)
