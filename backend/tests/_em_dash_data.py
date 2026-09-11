"""Shared StoryOutput fixture for em dash tests."""

from app.schemas import StoryOutput
from app.schemas.game import (
    DialogueLine,
    ItemMemory,
    MemoryUpdates,
    NPCMemory,
    PlayerStatus,
    QuestMemory,
    WorldFactMemory,
)


def _output_with_em_dashes() -> StoryOutput:
    """Return a StoryOutput where every text field contains em dashes."""
    return StoryOutput(
        narration="你走进——大厅——看见——红色标记。",
        dialogue=[
            DialogueLine(speaker="诺——诺", text="你——终于——来了。"),
            DialogueLine(speaker="古德里安", text="欢迎——来到——卡塞尔。"),
        ],
        scene_prompt="dark — academy — hall",
        sanity_delta=-5,
        health_delta=0,
        options=["向前——走一步", "后退——观察", "大声——喊叫"],
        game_over=False,
        game_over_reason="",
        current_location="卡塞尔——学院——报到处",
        items_gained=[
            {"name": "临——时通行卡", "description": "一张——印有——火漆纹的——通行卡"},
        ],
        items_lost=[
            {"name": "旧——行李箱", "description": "在——慌乱中——丢失"},
        ],
        npcs_encountered=[
            {"name": "诺——诺", "disposition": "友好——但——审视", "notes": "红发——女生"},
        ],
        quests_updated=[
            {"name": "入——学报到", "status": "active", "description": "完成——新生——注册"},
        ],
        memory_updates=MemoryUpdates(
            current_location="卡塞尔——学院——报到处",
            key_event="玩家——进入——报到大厅——遇见——诺诺",
            items_upserted=[
                ItemMemory(name="临——时通行卡", status="owned", description="通行卡——有火漆纹", location="口袋", notes=""),
            ],
            items_removed=[
                ItemMemory(name="旧——行李箱", status="lost", description="丢失——在报到大厅", location="", notes=""),
            ],
            npcs_upserted=[
                NPCMemory(name="诺——诺", status="present", relationship="审视——好奇", current_location="报到大厅", description="红发——女生——高年级", notes=""),
            ],
            quests_upserted=[
                QuestMemory(name="入——学报到", status="active", description="完成——注册手续", objective="找到——教务处", notes=""),
            ],
            world_facts_upserted=[
                WorldFactMemory(name="卡塞尔——秘密", status="known", description="学院——隐藏着——古老秘密", source="诺诺——暗示", notes=""),
            ],
            player_status_patch=PlayerStatus(
                condition="紧张——不安",
                danger_level="medium",
                current_goal="找到——诺诺——问清楚",
                notes="刚——入学——一切——陌生",
            ),
        ),
        npc_relations_delta=[
            {"name": "诺——诺", "sentiment": "positive", "note": "对玩家——产生——兴趣"},
        ],
    )
