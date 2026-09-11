"""Create a background prompt only when the effective story location changes."""

import logging
import re

from app.schemas import StoryOutput

logger = logging.getLogger(__name__)


def effective_location(output: StoryOutput, state: dict) -> str:
    """Resolve location using the same precedence as GameStateManager."""
    return (
        output.memory_updates.current_location
        or output.current_location
        or str(state.get("current_location", ""))
    ).strip()


async def attach_scene_prompt(llm_client, output: StoryOutput, state: dict, model: str) -> None:
    """Attach a fresh prompt on location change; otherwise carry the saved prompt."""
    previous_location = str(state.get("current_location", "")).strip()
    next_location = effective_location(output, state)
    previous_prompt = str(state.get("_scene_prompt", "")).strip()

    # Ignore scene_prompt emitted by the narrator. It is no longer part of its job.
    output.scene_prompt = ""

    if not next_location or next_location == previous_location:
        output.scene_prompt = previous_prompt
        return

    context = re.sub(r"\s+", " ", output.narration).strip()[:900]
    prompt = (
        "Create one concise English image prompt for a cinematic game background. "
        "Return only the prompt, no label, quotes, or explanation. Use at most 30 words. "
        "Describe environment, time, weather, lighting, and atmosphere; do not describe UI or text.\n"
        f"New location: {next_location}\n"
        f"Current scene: {context}"
    )

    try:
        generated = await llm_client.generate_text(
            prompt,
            model=model,
            max_tokens=80,
            temperature=0.2,
        )
        output.scene_prompt = generated.strip().strip('"\'').replace("\n", " ")[:500]
    except Exception:
        logger.warning("Scene prompt generation failed for location %s", next_location, exc_info=True)
