"""Campaign entry_state merging for GameStateManager."""

from typing import Any


class EntryStateMixin:
    def merge_entry_state(
        self,
        base_state: dict[str, Any],
        campaign: Any,  # CampaignSchema (avoid circular import)
        arc_index: int,
        session_index: int,
    ) -> dict[str, Any]:
        """Merge entry_state from campaign session into base_state.

        Merge order: default_state → campaign.starting_state → session.entry_state.
        Later values override earlier ones key-by-key.
        """
        result = dict(base_state)

        # Layer 1: campaign-level starting_state — only for campaign start (arc 0, session 0)
        if arc_index == 0 and session_index == 0:
            if getattr(campaign, "starting_state", None):
                for key, value in campaign.starting_state.items():
                    if value:  # non-empty override
                        if key in ("items", "npcs", "quests", "world_facts", "recent_events"):
                            continue
                        result[key] = value

        # Layer 2: session-level entry_state (always applied if present)
        try:
            arc = campaign.arcs[arc_index]
            session = arc.sessions[session_index]
            entry = session.entry_state
            if entry:
                if entry.get("location"):
                    result["current_location"] = entry["location"]
                if entry.get("items"):
                    for item_name in entry["items"]:
                        if not any(i.get("name") == item_name for i in result.get("items", [])):
                            result.setdefault("items", []).append(
                                {"name": item_name, "status": "初始"}
                            )
                if entry.get("quests"):
                    for quest_name in entry["quests"]:
                        if not any(q.get("name") == quest_name for q in result.get("quests", [])):
                            result.setdefault("quests", []).append(
                                {"name": quest_name, "objective": "", "status": "active"}
                            )
                if entry.get("world_facts_summary"):
                    for fact in entry["world_facts_summary"]:
                        result.setdefault("world_facts", []).append(
                            {"name": fact[:80], "description": fact, "status": "known", "source": "entry_state"}
                        )
        except (IndexError, AttributeError):
            pass

        return result
