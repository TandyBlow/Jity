"""JSON cleaning / repair helpers for LLM output."""

import re


class JSONRepairMixin:
    @staticmethod
    def _clean_json_text(text: str) -> str:
        cleaned = re.sub(r"<think>[\s\S]*?</think>", "", text).strip()
        return cleaned.replace("```json", "").replace("```", "").strip()

    def _repair_json_local(self, raw_text: str) -> str:
        """Attempt local JSON repair before falling back to LLM repair."""
        from json_repair import repair_json

        cleaned = self._clean_json_text(raw_text)
        return repair_json(cleaned)

    @staticmethod
    def _build_json_repair_prompt(raw_text: str, error_text: str) -> str:
        return f"""下面这段内容不是合法的剧情 JSON，可能原因包括字符串里有未转义的双引号、尾部被截断、字段类型不符合 schema。

请在不改变剧情含义和字段结构的前提下修复它。只返回严格合法 JSON，不要 Markdown，不要解释，不要额外文本。
如果 dialogue.text 里需要引用角色原话，不要使用裸双引号；改用中文引号、英文单引号，或改写为间接叙述。

解析错误：
{error_text}

原始输出：
{raw_text}"""

    @staticmethod
    def _format_failed_outputs(original_text: str, repaired_text: str) -> str:
        return f"原始输出：\n{original_text}\n\n修复输出：\n{repaired_text}"
