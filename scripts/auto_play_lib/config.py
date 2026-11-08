"""Auto-play defaults and option-strategy keyword configuration."""

import json
from pathlib import Path


DEFAULT_API_BASE_URL = "http://localhost:8000"
DEFAULT_FRONTEND_URL = "http://localhost:3000"
DEFAULT_MODEL = "deepseek-v4-flash"
DEFAULT_CAMPAIGN = "龙族Ⅰ_火之晨曦_campaign.json"
DEFAULT_STORY_STYLE = "黑暗学院奇幻，带一点黑色幽默，强调 NPC 反应。"
DEFAULT_CONSTRAINTS = "关键 NPC 不能突然死亡；不要跳出当前入学调查。"
CAMPAIGN_STORY_STYLE = "延续当前战役的叙事风格、时代背景和人物处境。"
CAMPAIGN_CONSTRAINTS = "遵循当前战役及本幕设定，承接最近剧情和玩家行动，保持人物与物品连续。"
INITIAL_ACTION = '愣住两秒，然后硬着头皮打招呼：“学姐好……那个，这里到底有什么不普通的？”'
CAMPAIGN_ENTRY_ACTION = "（入场）环顾四周，了解当前处境。"
INITIAL_OPTIONS = [
    INITIAL_ACTION,
    "下意识后退半步，抓紧行李箱拉杆：“等等，你怎么知道我的名字？这是什么整蛊节目吗？”",
    "试图挤出个笑脸，但声音有点抖：“照片？什么照片？我那张高考准考证上的照片可丑了……”",
]

# Runner-only selection weights. Gameplay budgets belong to campaign JSON and
# backend Settings; the server never imports or reads this file.
AUTO_PLAY_CONFIG_PATH = Path(__file__).resolve().parents[1] / "auto_play_config.json"


def load_auto_play_config(path: Path = AUTO_PLAY_CONFIG_PATH) -> dict[str, dict[str, int]]:
    config = json.loads(path.read_text(encoding="utf-8"))
    expected = {"progression_keywords", "passive_keywords"}
    if not isinstance(config, dict) or set(config) != expected:
        raise ValueError("Auto-play config must contain only progression_keywords and passive_keywords")
    for weights in config.values():
        if not isinstance(weights, dict) or any(
            not isinstance(word, str) or type(weight) is not int
            for word, weight in weights.items()
        ):
            raise ValueError("Auto-play keyword weights must be string-to-integer mappings")
    return config


_AUTO_PLAY_CONFIG = load_auto_play_config()
PROGRESSION_KEYWORDS = _AUTO_PLAY_CONFIG["progression_keywords"]
PASSIVE_KEYWORDS = _AUTO_PLAY_CONFIG["passive_keywords"]
