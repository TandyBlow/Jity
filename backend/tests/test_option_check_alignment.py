"""option_checks must stay index-aligned with options, whatever the model returns."""

from app.schemas.game.story_output import OptionCheck, StoryOutput


def _output(options: list[str], option_checks: list) -> StoryOutput:
    return StoryOutput(narration="测试", options=options, option_checks=option_checks)


def test_empty_array_is_padded_so_every_option_index_resolves():
    output = _output(["查看", "离开"], [])

    assert output.option_checks == [None, None]


def test_short_array_is_padded():
    check = OptionCheck(normal_target=12)
    output = _output(["查看", "离开", "等待"], [check])

    assert output.option_checks[0] is check
    assert output.option_checks[1] is None
    assert output.option_checks[2] is None


def test_long_array_is_truncated():
    checks = [OptionCheck(normal_target=12), OptionCheck(normal_target=10), None]
    output = _output(["查看", "离开"], checks)

    assert len(output.option_checks) == 2
    assert output.option_checks[1] is checks[1]


def test_matching_length_is_untouched():
    check = OptionCheck(normal_target=12)
    output = _output(["查看", "离开"], [None, check])

    assert output.option_checks[0] is None
    assert output.option_checks[1] is check


def test_no_options_means_no_checks():
    output = _output([], [])

    assert output.option_checks == []
