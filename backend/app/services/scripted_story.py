
import json
from pathlib import Path
from typing import Any

from app.schemas import StoryOutput


class ScriptedStoryService:
    """Loads scripted story scenes from JSON data files.

    Scenes are keyword-matched against the player action.
    Turn-0 scenes come from opening_scenes.json.
    Turn-1+ and location scenes come from branch_scenes.json.
    """

    def __init__(self, scenes_dir: Path | None = None) -> None:
        if scenes_dir is None:
            scenes_dir = Path(__file__).parent.parent.parent / "data" / "scripted_story"
        self._opening_scenes = self._load_scenes(scenes_dir / "opening_scenes.json")
        self._branch_scenes = self._load_scenes(scenes_dir / "branch_scenes.json")

    @staticmethod
    def _load_scenes(path: Path) -> list[dict]:
        if not path.exists():
            return []
        return json.loads(path.read_text(encoding="utf-8")).get("scenes", [])

    def generate(self, action: str, state: dict[str, Any]) -> StoryOutput | None:
        normalized_action = action.strip()
        turn = int(state.get("turn", 0))

        scenes_to_check = []
        if turn == 0:
            scenes_to_check = self._opening_scenes
        elif turn <= 1:
            scenes_to_check = self._branch_scenes + self._opening_scenes  # branch first, then opening fallback
        else:
            # After turn 1, only check location-based branch scenes
            scenes_to_check = self._branch_scenes

        for scene in scenes_to_check:
            keywords = scene.get("keywords", [])
            if any(kw in normalized_action for kw in keywords):
                return self._scene_to_output(scene)
        return None

    @staticmethod
    def _scene_to_output(scene: dict) -> StoryOutput:
        return StoryOutput(
            narration=scene["narration"].strip(),
            dialogue=scene.get("dialogue", []),
            scene_prompt=scene.get("scene_prompt", ""),
            sanity_delta=0,
            health_delta=0,
            options=scene.get("options", []),
            current_location=scene.get("current_location", ""),
            items_gained=scene.get("items_gained", []),
            quests_updated=scene.get("quests_updated", []),
            npcs_encountered=scene.get("npcs_encountered", []),
        ).replace_em_dashes()
