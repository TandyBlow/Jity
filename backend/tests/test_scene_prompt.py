import pytest

from app.schemas import StoryOutput
from app.services.scenario_generator.scene_prompt import attach_scene_prompt


class FakeLLMClient:
    def __init__(self, result: str = "moonlit underground library, ancient stone arches, drifting dust"):
        self.result = result
        self.calls: list[dict] = []

    async def generate_text(self, prompt: str, **kwargs) -> str:
        self.calls.append({"prompt": prompt, **kwargs})
        return self.result


def story_output(location: str, scene_prompt: str = "narrator should be ignored") -> StoryOutput:
    return StoryOutput(
        narration="你沿着楼梯进入地下图书馆，四周只剩昏暗的壁灯。",
        current_location=location,
        scene_prompt=scene_prompt,
    )


@pytest.mark.asyncio
async def test_scene_prompt_is_reused_without_location_change():
    client = FakeLLMClient()
    output = story_output("")

    await attach_scene_prompt(
        client,
        output,
        {"current_location": "学院大厅", "_scene_prompt": "existing hall background"},
        "test-model",
    )

    assert output.scene_prompt == "existing hall background"
    assert client.calls == []


@pytest.mark.asyncio
async def test_scene_prompt_is_generated_only_for_new_location():
    client = FakeLLMClient('"moonlit underground library, ancient stone arches"\n')
    output = story_output("地下图书馆")

    await attach_scene_prompt(
        client,
        output,
        {"current_location": "学院大厅", "_scene_prompt": "existing hall background"},
        "test-model",
    )

    assert output.scene_prompt == "moonlit underground library, ancient stone arches"
    assert len(client.calls) == 1
    assert "New location: 地下图书馆" in client.calls[0]["prompt"]
    assert client.calls[0]["max_tokens"] == 80


@pytest.mark.asyncio
async def test_memory_location_takes_precedence_when_detecting_change():
    client = FakeLLMClient()
    output = story_output("")
    output.memory_updates.current_location = "钟楼顶部"

    await attach_scene_prompt(
        client,
        output,
        {"current_location": "学院大厅", "_scene_prompt": "existing hall background"},
        "test-model",
    )

    assert len(client.calls) == 1
    assert "New location: 钟楼顶部" in client.calls[0]["prompt"]
