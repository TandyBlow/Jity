"""NovelIngestor — TXT preprocessing and chapter detection."""

import re
from typing import Any

import charset_normalizer


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
            return cls._chapters_from_matches(matches, all_lines)

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

    @classmethod
    def _chapters_from_matches(cls, matches: list, all_lines: list[str]) -> list[dict[str, Any]]:
        text_line_count = len(all_lines)
        chapters = []
        for i, match in enumerate(matches):
            start_line = match.string[:match.start()].count("\n")
            if i + 1 < len(matches):
                end_line = match.string[: matches[i + 1].start()].count("\n")
            else:
                end_line = text_line_count
            title = match.group(0).strip()
            if start_line < end_line:
                chapters.append({
                    "index": i, "title": title,
                    "start_line": start_line, "end_line": end_line,
                })
        return chapters
