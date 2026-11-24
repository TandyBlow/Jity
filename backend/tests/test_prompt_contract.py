"""The option_checks contract is shared, so both prompts must keep carrying it."""

from app.services.prompt_builder.builder import _style_and_rules
from app.services.prompt_builder.input import PromptInput
from app.services.prompt_builder.prompts import OPTION_CHECKS_CONTRACT, build_opening_options


def _narrator_rules() -> str:
    return _style_and_rules(PromptInput(player_action="x", game_state={}, retrieved_chunks=[]))


def test_narrator_prompt_carries_the_shared_contract():
    assert OPTION_CHECKS_CONTRACT in _narrator_rules()


def test_opening_options_prompt_carries_the_same_contract():
    assert OPTION_CHECKS_CONTRACT in build_opening_options("上下文")


def test_opening_options_prompt_asks_for_options_only():
    prompt = build_opening_options("上下文")

    assert "options" in prompt
    assert "option_checks" in prompt
    assert "不要写任何叙事文本" in prompt
