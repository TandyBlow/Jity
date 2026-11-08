"""Selection configuration cannot silently carry backend gameplay rules."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from auto_play_lib.config import load_auto_play_config
from auto_play_lib.options import score_option


def test_default_weights_preserve_option_scores():
    assert score_option("继续调查") == 19
    assert score_option("等待") == -8


def test_custom_keyword_weights_load_from_runner_config(tmp_path):
    path = tmp_path / "runner.json"
    expected = {"progression_keywords": {"调查": 3}, "passive_keywords": {"等待": -2}}
    path.write_text(json.dumps(expected))
    assert load_auto_play_config(path) == expected


@pytest.mark.parametrize("extra", [{"max_turns_per_campaign": 1}, {"max_turns_per_session": 1}])
def test_gameplay_budgets_are_rejected_in_runner_config(tmp_path, extra):
    path = tmp_path / "runner.json"
    path.write_text(json.dumps({"progression_keywords": {}, "passive_keywords": {}, **extra}))
    with pytest.raises(ValueError, match="only"):
        load_auto_play_config(path)
