# Synthetic fixture for the CPU mechanism test. NOT training data.
#
# Every row says source="fixture", so it can never be fed
# to a real run (train.py refuses rows whose split is not train/validation, and
# the fixture file names carry `fixture`). The purpose is to exercise the
# serializer, the masks, the pointer with a variable candidate list and the
# masked weighted loss on a laptop CPU with a 32-dim encoder.
#
# Usage: python tests/make_fixture.py

from __future__ import annotations

import json
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE / "fixture"

LOW = {"id": "lu", "name": "路明非", "type": "人物"}
NONO = {"id": "nono", "name": "诺诺", "type": "人物"}
FIN = {"id": "fingel", "name": "芬格尔", "type": "人物"}
GOGGLES = {"id": "goggles_lu", "name": "护目镜", "type": "物品", "place": "lu/slot_body"}
HALL = {"id": "west_arcade", "name": "西回廊", "type": "地点"}
CAGE = {"id": "cage_lock", "name": "笼门挂锁", "type": "物品"}


def row(row_id: str, split: str, goal: str, *, place: str, present: list, items: list,
        recent: list, sanity: int, personality: str, candidates: list, steps: list,
        acceptable: list | None = None) -> dict:
    payload = {
        "rowId": row_id,
        "source": "fixture",
        "worldId": "world_fixture",
        "characterId": "lu",
        "split": split,
        "goalId": goal,
        "x": {
            "character": LOW,
            "goals": [goal_text(goal)],
            "place": place,
            "present": present,
            "items": items,
            "recent": recent,
            "sanity": sanity,
            "personality": personality,
            "candidates": candidates,
        },
        "y": {"steps": steps},
        "yGroup": None,
        "yRationale": "fixture",
        "labelSource": "fixture",
        "skipReason": None if steps else "fixture skip",
    }
    if acceptable:
        payload["acceptableGroups"] = acceptable
    return payload


def goal_text(key: str) -> str:
    return {
        "goal_route": "在庭院正路、西回廊和地下检修通道之间选一条有掩护的路线",
        "goal_goggles": "把胸前护目镜戴好并确认镜片没有裂纹",
        "goal_ask": "向诺诺问清当前红蓝两方局势",
        "goal_route_v": "验证用：在两条有掩护的通道之间选一条",
        "goal_goggles_v": "验证用：确认护目镜能挡住碎片",
        "goal_ask_v": "验证用：问清谁能带他离开交火区",
        "goal_route_v2": "验证用：找一条能绕开正路的通道",
    }.get(key, key)


def build() -> tuple[list, list]:
    train = [
        row("fx-t-01", "train", "goal_route", place="西回廊", present=[NONO], items=[GOGGLES],
            recent=["诺诺说红蓝两方在西回廊交火"], sanity=55, personality="犹豫，怕被卷进麻烦",
            candidates=[NONO, HALL], steps=[{"action": "观察", "object": "west_arcade"}]),
        row("fx-t-02", "train", "goal_route", place="西回廊", present=[NONO], items=[GOGGLES],
            recent=["走廊尽头传来脚步声"], sanity=55, personality="犹豫，怕被卷进麻烦",
            candidates=[NONO, HALL], steps=[{"action": "移动", "object": "west_arcade"}]),
        row("fx-t-03", "train", "goal_goggles", place="器材棚", present=[], items=[GOGGLES],
            recent=["护目镜挂在胸前"], sanity=60, personality="怕疼，先顾自己",
            candidates=[GOGGLES], steps=[{"action": "检查", "object": "goggles_lu"}]),
        row("fx-t-04", "train", "goal_goggles", place="器材棚", present=[FIN], items=[GOGGLES],
            recent=["芬格尔在门口张望"], sanity=60, personality="怕疼，先顾自己",
            candidates=[FIN, GOGGLES], steps=[{"action": "装备", "object": "goggles_lu"}]),
        row("fx-t-05", "train", "goal_ask", place="庭院正路", present=[NONO], items=[],
            recent=["诺诺站在路口"], sanity=40, personality="怕惹事，能不开口就不开口",
            candidates=[NONO], steps=[]),
        row("fx-t-06", "train", "goal_route", place="西回廊", present=[NONO, FIN], items=[CAGE],
            recent=["笼门挂锁被人动过"], sanity=48, personality="谨慎，先看清楚再动",
            candidates=[NONO, FIN, CAGE, HALL],
            steps=[{"action": "检查", "object": "cage_lock"}, {"action": "倾听", "object": None}]),
    ]
    validation = [
        row("fx-v-01", "validation", "goal_route_v", place="庭院正路", present=[], items=[GOGGLES],
            recent=["正路上没有掩体"], sanity=52, personality="犹豫，怕被卷进麻烦",
            candidates=[HALL, GOGGLES], steps=[{"action": "潜行", "object": "west_arcade"}]),
        row("fx-v-02", "validation", "goal_goggles_v", place="器材棚", present=[FIN], items=[GOGGLES],
            recent=["芬格尔问护目镜有没有裂"], sanity=58, personality="怕疼，先顾自己",
            candidates=[FIN, GOGGLES], steps=[{"action": "核实", "object": "goggles_lu"}]),
        row("fx-v-03", "validation", "goal_ask_v", place="庭院正路", present=[NONO], items=[],
            recent=["诺诺看了他一眼"], sanity=42, personality="怕惹事，能不开口就不开口",
            candidates=[NONO], steps=[{"action": "提问", "object": "nono"}]),
        row("fx-v-04", "validation", "goal_route_v2", place="器材棚", present=[], items=[],
            recent=["门外有人在喊"], sanity=46, personality="谨慎，先看清楚再动",
            candidates=[], steps=[]),
    ]
    return train, validation


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    train, validation = build()
    for name, rows in (("train.jsonl", train), ("validation.jsonl", validation)):
        path = OUT / name
        path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")
        print(f"{path} {len(rows)} rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
