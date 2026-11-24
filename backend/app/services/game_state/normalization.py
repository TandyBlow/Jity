"""Memory-entry normalization and name-keyed merging."""

from typing import Any


class MemoryNormalizationMixin:
    def merge_by_name(
        self,
        current: list[dict[str, Any]],
        updates: list[dict[str, Any]],
        *,
        kind: str,
        default_location: str = "",
    ) -> list[dict[str, Any]]:
        merged = {
            item.get("name"): item
            for item in (self._normalize_memory(item, kind, default_location=default_location) for item in current)
            if item and item.get("name")
        }
        for update in updates:
            normalized = self._normalize_memory(update, kind, default_location=default_location)
            if not normalized:
                continue
            name = normalized.get("name")
            if not name:
                continue
            existing = merged.get(name, {})
            existing.update({key: value for key, value in normalized.items() if value not in (None, "")})
            merged[name] = existing
        return list(merged.values())

    def _remove_by_name(self, current: list[dict[str, Any]], removed: list[dict[str, Any]]) -> list[dict[str, Any]]:
        removed_names = {
            normalized["name"]
            for normalized in (self._normalize_memory(item, "item") for item in removed)
            if normalized and normalized.get("name")
        }
        return [item for item in current if item.get("name") not in removed_names]

    def _normalize_memory(
        self,
        item: Any,
        kind: str,
        *,
        default_location: str = "",
    ) -> dict[str, Any]:
        if isinstance(item, str):
            raw: dict[str, Any] = {"name": item}
        elif isinstance(item, dict):
            raw = dict(item)
        else:
            return {}

        name = self._clean_text(str(raw.get("name", "")))
        if not name:
            return {}

        if kind == "item":
            return {
                "name": name,
                "status": self._normalize_status(str(raw.get("status") or "owned"), kind),
                "description": self._clean_text(str(raw.get("description") or "")),
                "location": self._clean_text(str(raw.get("location") or "")),
                "notes": self._clean_text(str(raw.get("notes") or "")),
            }
        if kind == "npc":
            return {
                "name": name,
                "status": self._normalize_status(str(raw.get("status") or "present"), kind),
                "relationship": self._clean_text(str(raw.get("relationship") or raw.get("disposition") or "")),
                "current_location": self._clean_text(str(raw.get("current_location") or default_location or "")),
                "description": self._clean_text(str(raw.get("description") or "")),
                "notes": self._clean_text(str(raw.get("notes") or "")),
            }
        if kind == "quest":
            return {
                "name": name,
                "status": self._normalize_status(str(raw.get("status") or "active"), kind),
                "description": self._clean_text(str(raw.get("description") or "")),
                "objective": self._clean_text(str(raw.get("objective") or "")),
                "notes": self._clean_text(str(raw.get("notes") or "")),
            }
        return {
            "name": name,
            "status": self._normalize_status(str(raw.get("status") or "known"), kind),
            "description": self._clean_text(str(raw.get("description") or "")),
            "source": self._clean_text(str(raw.get("source") or "")),
            "notes": self._clean_text(str(raw.get("notes") or "")),
        }

    @staticmethod
    def _normalize_status(status: str, kind: str) -> str:
        value = status.strip().lower()
        aliases = {
            "已解锁": "active",
            "进行中": "active",
            "活跃": "active",
            "完成": "completed",
            "已完成": "completed",
            "失败": "failed",
            "持有": "owned",
            "获得": "owned",
            "在场": "present",
            "同行": "following",
            "离开": "away",
            "已知": "known",
            "推测": "suspected",
        }
        if status in aliases:
            return aliases[status]
        if value:
            return value
        defaults = {"item": "owned", "npc": "present", "quest": "active", "world_fact": "known"}
        return defaults.get(kind, "known")
