"""Campaign entry_state merging for GameStateManager."""

from copy import deepcopy
from typing import Any


class EntryStateMixin:
    def merge_entry_state(
        self,
        base_state: dict[str, Any],
        campaign: Any,  # CampaignSchema (avoid circular import)
        arc_index: int,
        session_index: int,
        *,
        initialize: bool = False,
        reset_scene_context: bool = False,
    ) -> dict[str, Any]:
        """Merge entry_state from campaign session into base_state.

        Fresh entry uses neutral state → starting_state → session.entry_state.
        Chapter transitions preserve durable state, but may reset scene-local
        NPCs and recent events before applying the next session's entry_state.
        Deep copies keep the source state and campaign immutable.
        """
        result = deepcopy(base_state)
        if reset_scene_context:
            # ``npcs`` and ``recent_events`` describe the active scene and the
            # short-term narration window.  Carrying them over makes a new
            # scripted opening compete with the scene that just ended.  Durable
            # continuity remains in items/quests/world_facts, relations and the
            # campaign recap.
            result["npcs"] = []
            result["recent_events"] = []
            result.pop("_memory_controller", None)
            result["_scene_prompt"] = ""
        if initialize:
            # The free-play defaults describe a specific academy scene. A new
            # campaign (including timeline entry) must not inherit that story.
            result.update(
                current_location="", items=[], npcs=[], quests=[], world_facts=[],
                recent_events=[], _scene_prompt="",
                player_status={
                    "condition": "正常", "danger_level": "medium",
                    "current_goal": "了解当前处境", "notes": "",
                },
            )

        # Layer 1: campaign-level starting_state — only for campaign start (arc 0, session 0)
        if initialize and arc_index == 0 and session_index == 0:
            if getattr(campaign, "starting_state", None):
                for key, value in campaign.starting_state.items():
                    if key in result and key not in ("turn", "_scene_prompt") and value is not None:
                        if key == "player_status":
                            result[key].update(deepcopy(value))
                        else:
                            result[key] = deepcopy(value)

        # Layer 2: session-level entry_state (always applied if present)
        try:
            arc = campaign.arcs[arc_index]
            session = arc.sessions[session_index]
            result["player_status"]["current_goal"] = arc.goal or "了解当前处境"
            entry = session.entry_state
            if entry:
                if entry.get("location"):
                    if result.get("current_location") != entry["location"]:
                        result["_scene_prompt"] = ""
                        if not reset_scene_context:
                            for npc in result.get("npcs", []):
                                if npc.get("status") == "present":
                                    npc["status"] = "away"
                    result["current_location"] = entry["location"]
                if "npcs" in entry:
                    result["npcs"] = self.merge_by_name(
                        result.get("npcs", []), entry["npcs"], kind="npc",
                        default_location=result["current_location"],
                    )
                if entry.get("player_status"):
                    result["player_status"].update(deepcopy(entry["player_status"]))
                if entry.get("scene_prompt"):
                    result["_scene_prompt"] = entry["scene_prompt"]
                if entry.get("items"):
                    for item_name in entry["items"]:
                        if not any(i.get("name") == item_name for i in result.get("items", [])):
                            result.setdefault("items", []).append(
                                {"name": item_name, "status": "owned"}
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
            if not result.get("current_location"):
                # Older campaign files may lack entry metadata. Let the opening
                # establish the scene instead of inventing an academy location.
                result["current_location"] = session.name
        except (IndexError, AttributeError):
            pass

        return result
