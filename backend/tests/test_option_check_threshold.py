"""OptionCheck derives its success threshold from difficulty, not from the model."""

from app.schemas.game.story_output import OptionCheck, StoryOutput


def test_easy_check_uses_the_easy_band():
    check = OptionCheck(difficulty="容易")

    assert check.target == 8
    assert check.expression == "1d20 ≥ 8"


def test_ordinary_check_uses_the_ordinary_band():
    check = OptionCheck(difficulty="普通")

    assert check.target == 12
    assert check.expression == "1d20 ≥ 12"


def test_hard_check_raises_the_threshold():
    check = OptionCheck(difficulty="困难")

    assert check.target == 16


def test_extreme_check_uses_the_highest_band():
    check = OptionCheck(difficulty="极难")

    assert check.target == 19
    assert check.expression == "1d20 ≥ 19"


def test_model_supplied_target_is_overwritten():
    check = OptionCheck(difficulty="困难", target=12, expression="1d20 ≥ 12")

    assert check.target == 16
    assert check.expression == "1d20 ≥ 16"


def test_legacy_skill_value_is_ignored():
    check = OptionCheck(difficulty="普通", normal_target=4)

    assert check.target == 12


def test_story_output_normalizes_every_check():
    output = StoryOutput(
        narration="测试",
        options=["查看", "离开"],
        option_checks=[OptionCheck(difficulty="极难"), None],
    )

    assert output.option_checks[0] is not None
    assert output.option_checks[0].target == 19
    assert output.option_checks[1] is None
