"""Small synthetic world for the experiment's own unit tests.

It is deliberately tiny and hand-written: tests must prove the projection and
validation rules, not re-test the product world. Task ids here are test ids,
not the frozen goal vocabulary.
"""
from __future__ import annotations

import copy
from typing import Any


def small_world() -> dict[str, Any]:
    locations = {
        "hall": {
            "id": "hall",
            "name": "门厅",
            "parentLocationId": None,
            "initialAppearance": "门厅里有一张长桌。",
            "slots": [{"id": "slot_door", "label": "门口"}],
        },
        "yard": {
            "id": "yard",
            "name": "庭院",
            "parentLocationId": "hall",
            "initialAppearance": "庭院铺着碎石，远处有围墙。",
            "slots": [],
        },
    }
    characters = {
        "ann": {
            "id": "ann",
            "name": "安",
            "initialPosition": {"containerId": "hall", "slotId": None, "relativeTo": None},
            "initialAppearance": "穿着外套，手里空着。",
            "slots": [{"id": "slot_hand", "label": "手上"}, {"id": "slot_bag", "label": "背包"}],
            "initialPersonality": "谨慎，先看清再动。",
            "initialSanity": 50,
            "tasks": {
                "task_ann_a": {
                    "id": "task_ann_a",
                    "ownerId": "ann",
                    "parentTaskId": None,
                    "goal": "把桌上的钥匙收好",
                    "status": "pending",
                },
                "task_ann_b": {
                    "id": "task_ann_b",
                    "ownerId": "ann",
                    "parentTaskId": "task_ann_a",
                    "goal": "确认钥匙属于谁",
                    "status": "pending",
                },
                "task_ann_c": {
                    "id": "task_ann_c",
                    "ownerId": "ann",
                    "parentTaskId": None,
                    "goal": "已经完成的事",
                    "status": "achieved",
                },
            },
        },
        "bo": {
            "id": "bo",
            "name": "博",
            "initialPosition": {"containerId": "hall", "slotId": "slot_door", "relativeTo": None},
            "initialAppearance": "站在门口，靴子有泥。",
            "slots": [],
            "initialPersonality": "急躁。",
            "initialSanity": 61,
            "tasks": {
                "task_bo_a": {
                    "id": "task_bo_a",
                    "ownerId": "bo",
                    "parentTaskId": None,
                    "goal": "到庭院看看",
                    "status": "pending",
                }
            },
        },
        "cy": {
            "id": "cy",
            "name": "希",
            "initialPosition": {"containerId": "yard", "slotId": None, "relativeTo": None},
            "initialAppearance": "在庭院里走着。",
            "slots": [],
            "initialPersonality": "安静。",
            "initialSanity": 30,
            "tasks": {
                "task_cy_a": {
                    "id": "task_cy_a",
                    "ownerId": "cy",
                    "parentTaskId": None,
                    "goal": "在庭院里等消息",
                    "status": "pending",
                }
            },
        },
    }
    items = {
        "key": {
            "id": "key",
            "name": "铜钥匙",
            "initialPosition": {"containerId": "hall", "slotId": None, "relativeTo": None},
            "initialAppearance": "铜制钥匙，齿纹磨旧了。",
            "slots": [],
        },
        "bag": {
            "id": "bag",
            "name": "背包",
            "initialPosition": {"containerId": "ann", "slotId": "slot_bag", "relativeTo": None},
            "initialAppearance": "帆布背包。",
            "slots": [{"id": "slot_inner", "label": "内部"}],
        },
        "note": {
            "id": "note",
            "name": "纸条",
            "initialPosition": {"containerId": "bag", "slotId": "slot_inner", "relativeTo": None},
            "initialAppearance": "揉过的纸条。",
            "slots": [],
        },
        "shovel": {
            "id": "shovel",
            "name": "铁铲",
            "initialPosition": {"containerId": "yard", "slotId": None, "relativeTo": None},
            "initialAppearance": "沾着土的铁铲。",
            "slots": [],
        },
    }
    state = {
        "engineVersion": "world-engine-v1",
        "schemaVersion": 1,
        "worldId": "world_test",
        "protagonistId": "ann",
        "time": {"calendar": "gregorian", "dateTime": "2026-01-01T10:00:00", "instantOrdinal": 0},
        "initial": {
            "engineVersion": "world-engine-v1",
            "schemaVersion": 1,
            "worldId": "world_test",
            "protagonistId": "ann",
            "initialTime": {"calendar": "gregorian", "dateTime": "2026-01-01T10:00:00", "instantOrdinal": 0},
            "locations": locations,
            "items": items,
            "characters": characters,
        },
        "locations": {key: {"id": key, "appearanceChanges": []} for key in locations},
        "items": {key: {"id": key, "position": copy.deepcopy(value["initialPosition"]), "appearanceChanges": []} for key, value in items.items()},
        "characters": {
            key: {
                "id": key,
                "position": copy.deepcopy(value["initialPosition"]),
                "appearanceChanges": [],
                "personalityChanges": [],
                "sanity": value["initialSanity"],
                "tasks": copy.deepcopy(value["tasks"]),
            }
            for key, value in characters.items()
        },
    }
    return state
