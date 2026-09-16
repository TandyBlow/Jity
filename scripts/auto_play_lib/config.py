"""Auto-play defaults and option-strategy keyword configuration."""

import json
from pathlib import Path
from typing import Any


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

# Load optional config from backend/scripts/option_config.json
def _load_option_config() -> dict[str, Any]:
    config_path = Path(__file__).resolve().parents[2] / "backend" / "scripts" / "option_config.json"
    try:
        if config_path.exists():
            return json.loads(config_path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}

_OPTION_CONFIG = _load_option_config()

PROGRESSION_KEYWORDS = _OPTION_CONFIG.get("progression_keywords", {
    "推进": 12,
    "继续": 10,
    "前往": 10,
    "进入": 9,
    "调查": 9,
    "询问": 8,
    "确认": 7,
    "检查": 7,
    "追问": 7,
    "观察": 6,
    "打开": 6,
    "寻找": 6,
    "跟随": 6,
    "接受": 5,
    "核验": 5,
    "听证": 5,
    "取件": 5,
    "档案": 5,
    "图书馆": 5,
    "钟楼": 5,
    "任务": 5,
    "线索": 5,
    "通行卡": 4,
    "诺诺": 4,
})

PASSIVE_KEYWORDS = _OPTION_CONFIG.get("passive_keywords", {
    "等待": -8,
    "拒绝": -7,
    "离开学院": -7,
    "回宿舍睡觉": -6,
    "开玩笑": -4,
    "装傻": -4,
    "沉默": -4,
    "逃跑": -4,
    "什么都不做": -10,
})
