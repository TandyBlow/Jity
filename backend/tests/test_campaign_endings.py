"""Campaign ending routes are loaded and injected only in the finale."""

import json
from pathlib import Path

from app.schemas.campaign import CampaignSchema, campaign_adapter, migrate
from app.services.campaign_context import CampaignContextBuilder


def test_default_campaign_has_seven_ending_routes():
    path = Path(__file__).parents[1] / "data" / "campaigns" / "default_campaign.json"
    campaign = campaign_adapter.validate_python(migrate(json.loads(path.read_text(encoding="utf-8"))))

    assert len(campaign.ending_routes) == 7
    assert {route.category for route in campaign.ending_routes} >= {"true", "good", "dark", "bad"}
    assert campaign.arcs[-1].sessions[-1].name == "钟楼零点"


def test_fire_dawn_campaign_has_seven_ending_routes():
    path = Path(__file__).parents[1] / "data" / "campaigns" / "龙族Ⅰ_火之晨曦_campaign.json"
    campaign = campaign_adapter.validate_python(migrate(json.loads(path.read_text(encoding="utf-8"))))

    assert len(campaign.ending_routes) == 7
    assert campaign.ending_routes[0].name == "火之晨曦"
    assert campaign.arcs[-1].sessions[-1].name == "Session 9: 青铜与火的葬礼"
    assert len(campaign.arcs[-1].sessions[-1].anchor_events) == 3


def test_mourner_eye_campaign_has_seven_ending_routes():
    path = Path(__file__).parents[1] / "data" / "campaigns" / "龙族Ⅱ_悼亡者之瞳_campaign.json"
    campaign = campaign_adapter.validate_python(migrate(json.loads(path.read_text(encoding="utf-8"))))

    assert len(campaign.ending_routes) == 7
    assert campaign.ending_routes[0].name == "悼亡者之瞳"
    assert campaign.arcs[-1].sessions[-1].name == "悼亡者之瞳"
    assert len(campaign.arcs[-1].sessions[-1].anchor_events) == 3


def test_black_moon_campaign_has_seven_ending_routes():
    path = Path(__file__).parents[1] / "data" / "campaigns" / "龙族Ⅲ_黑月之潮_campaign.json"
    campaign = campaign_adapter.validate_python(migrate(json.loads(path.read_text(encoding="utf-8"))))

    assert len(campaign.ending_routes) == 7
    assert campaign.ending_routes[0].name == "东京的黎明"
    assert campaign.arcs[-1].sessions[-1].name == "神葬所的黎明"
    assert len(campaign.arcs[-1].sessions[-1].anchor_events) == 3


def test_ending_director_prompt_contains_resolution_rules():
    campaign = CampaignSchema.model_validate({
        "title": "测试战役",
        "core_conflict": "测试",
        "ending_routes": [{
            "id": "ending-test",
            "name": "测试结局",
            "category": "true",
            "requirements": ["找到钥匙"],
            "resolution": "关闭大门",
            "epilogue": "黎明到来",
        }],
    })

    text = CampaignContextBuilder._describe_endings(campaign.ending_routes)

    assert "后端根据玩家的明确行动判定" in text
    assert "game_over=false" in text
    assert "测试结局" in text
    assert "找到钥匙" in text
    assert "可用于最终选项的明确行动" in text
