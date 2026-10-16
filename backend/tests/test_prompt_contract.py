"""The option_checks contract is shared, so both prompts must keep carrying it."""

from app.services.prompt_builder.builder import _style_and_rules
from app.services.prompt_builder.input import PromptInput
from app.services.prompt_builder.prompts import (
    FINAL_TURNS_OPTION_CONTRACT,
    HARD_TURNS_OPTION_CONTRACT,
    OPTION_CHECKS_CONTRACT,
    OPTION_IMPACT_CONTRACT,
    SOFT_TURNS_OPTION_CONTRACT,
    build_opening_options,
)


def _narrator_rules() -> str:
    return _style_and_rules(PromptInput(player_action="x", game_state={}, retrieved_chunks=[]))


def test_narrator_prompt_carries_the_shared_contract():
    assert OPTION_CHECKS_CONTRACT in _narrator_rules()


def test_opening_options_prompt_carries_the_same_contract():
    assert OPTION_CHECKS_CONTRACT in build_opening_options("上下文")


def test_all_option_prompts_require_story_impact():
    assert OPTION_IMPACT_CONTRACT in _narrator_rules()
    assert OPTION_IMPACT_CONTRACT in build_opening_options("上下文")


def test_opening_options_prompt_asks_for_options_only():
    prompt = build_opening_options("上下文")

    assert "options" in prompt
    assert "option_checks" in prompt
    assert "不要写任何叙事文本" in prompt


def test_soft_turns_contract_forbids_every_idle_option_class():
    assert "所有选项都必须直接推进" in SOFT_TURNS_OPTION_CONTRACT
    assert "等待、休息、闲逛" in SOFT_TURNS_OPTION_CONTRACT
    assert "重复观察、重复询问" in SOFT_TURNS_OPTION_CONTRACT
    assert "2 到 4 个推进选项" in SOFT_TURNS_OPTION_CONTRACT
    assert "不能提前宣告本幕结束" in SOFT_TURNS_OPTION_CONTRACT


def test_hard_turns_contract_requires_core_story_before_transition():
    assert "强制补齐核心剧情的起点" in HARD_TURNS_OPTION_CONTRACT
    assert "核心锚点没有完成前不得转场" in HARD_TURNS_OPTION_CONTRACT
    assert "必须在本回合正文中完整发生" in HARD_TURNS_OPTION_CONTRACT


def test_final_turns_contract_separates_local_hard_cap_from_global_budget():
    assert "hard_turns 只表示必须把冲突推到最终抉择" in FINAL_TURNS_OPTION_CONTRACT
    assert "不代表整局回合预算耗尽" in FINAL_TURNS_OPTION_CONTRACT
    assert "原样包含下方某条结局触发短语" in FINAL_TURNS_OPTION_CONTRACT
    assert "真正到达整局回合上限" in FINAL_TURNS_OPTION_CONTRACT
