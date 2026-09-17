"""OptionCheck derives its success threshold from difficulty, not from the model."""

from app.schemas.game.story_output import OptionCheck, StoryOutput


def test_normal_check_keeps_the_skill_value_as_threshold():
    check = OptionCheck(normal_target=12, difficulty="普通")

    assert check.target == 12
    assert check.expression == "1d20 ≤ 12"


def test_hard_check_halves_the_threshold():
    check = OptionCheck(normal_target=12, difficulty="困难")

    assert check.target == 6
    assert check.expression == "1d20 ≤ 6"


def test_model_supplied_target_is_overwritten():
    check = OptionCheck(normal_target=12, difficulty="困难", target=12, expression="1d20 ≤ 12")

    assert check.target == 6
    assert check.expression == "1d20 ≤ 6"


def test_story_output_normalizes_every_check():
    output = StoryOutput(
        narration="测试",
        options=["查看", "离开"],
        option_checks=[
            OptionCheck(normal_target=10, difficulty="困难"),
            None,
        ],
    )

    assert output.option_checks[0] is not None
    assert output.option_checks[0].target == 5
    assert output.option_checks[1] is None
