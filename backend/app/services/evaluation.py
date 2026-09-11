
from app.schemas import StoryOutput


class EvaluationModule:
    """Small automatic heuristic scorer; human scoring lives in the database."""

    def score(self, output: StoryOutput) -> dict[str, int]:
        option_score = min(5, max(1, len(output.options) + 1))
        dialogue_score = 4 if output.dialogue else 2
        state_score = 5 if output.current_location or output.quests_updated or output.npcs_encountered else 3
        return {
            "coherence": 4 if len(output.narration) > 30 else 2,
            "lore_consistency": state_score,
            "npc_consistency": dialogue_score,
            "action_relevance": 4,
            "creativity": 4,
            "controllability": 4 if abs(output.sanity_delta) <= 20 and abs(output.health_delta) <= 30 else 2,
            "playability": option_score,
        }
