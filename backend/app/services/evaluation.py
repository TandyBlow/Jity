
import re

from app.schemas import StoryOutput

# Words that contain 像 without forming a simile.
_NON_SIMILE_WORDS = (
    "想象", "想像", "图像", "影像", "肖像", "画像", "雕像", "塑像",
    "录像", "像素", "偶像", "像样", "像话", "好像",
)

_SIMILE_MARKERS = re.compile(r"像|仿佛|好似|宛如|犹如|如同")


def count_similes(text: str) -> int:
    """Count simile constructions, ignoring words that merely contain 像."""
    stripped = text
    for word in _NON_SIMILE_WORDS:
        stripped = stripped.replace(word, "")
    return len(_SIMILE_MARKERS.findall(stripped))


class EvaluationModule:
    """Small automatic heuristic scorer; human scoring lives in the database."""

    def score(self, output: StoryOutput) -> dict[str, int]:
        option_score = min(5, max(1, len(output.options) + 1))
        dialogue_score = 4 if output.dialogue else 2
        state_score = 5 if output.current_location or output.quests_updated or output.npcs_encountered else 3
        similes = count_similes(output.narration)
        return {
            "coherence": 4 if len(output.narration) > 30 else 2,
            "lore_consistency": state_score,
            "npc_consistency": dialogue_score,
            "action_relevance": 4,
            "creativity": 4,
            "controllability": 4 if abs(output.sanity_delta) <= 20 and abs(output.health_delta) <= 30 else 2,
            "playability": option_score,
            "style_discipline": 5 if similes <= 1 else max(1, 5 - (similes - 1)),
        }
