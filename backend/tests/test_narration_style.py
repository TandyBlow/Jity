"""Simile counting for the narration style rule."""

from app.schemas import StoryOutput
from app.services.evaluation import EvaluationModule, count_similes


def test_counts_simile_markers():
    assert count_similes("雨点像鼓点一样砸下来，走廊仿佛在呼吸。") == 2


def test_ignores_words_that_merely_contain_the_character():
    assert count_similes("他盯着那幅肖像画像，想象着图像里的像素") == 0


def test_clean_narration_has_no_similes():
    assert count_similes("你蹲下检查柜脚，发现了一道被灰尘掩盖的拖痕。") == 0


def test_style_discipline_penalises_repeated_similes():
    module = EvaluationModule()
    clean = StoryOutput(narration="你蹲下检查柜脚，发现了一道被灰尘掩盖的拖痕。")
    noisy = StoryOutput(narration="雨点像鼓点，灯光仿佛在呼吸，走廊宛如喉咙，风好似在低语。")

    assert module.score(clean)["style_discipline"] == 5
    assert module.score(noisy)["style_discipline"] < 5
