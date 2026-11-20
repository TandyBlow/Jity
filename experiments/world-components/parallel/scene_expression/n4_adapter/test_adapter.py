#!/usr/bin/env python3
"""Tests for the C6 N4 context adapter. Run: python -X utf8 test_adapter.py"""

from __future__ import annotations

import copy
import json
import pathlib
import unittest

HERE = pathlib.Path(__file__).resolve().parent
import sys
sys.path.insert(0, str(HERE))

from adapter import AdapterError, build_fixture, build_point_input  # noqa: E402


def load():
    return json.loads(
        (HERE / "fixtures" / "art-room-three-points.json").read_text(encoding="utf-8")
    )


class AdapterTest(unittest.TestCase):
    def setUp(self):
        self.fixture = load()
        self.world = self.fixture["world"]
        self.points = self.fixture["points"]

    def build(self, index):
        return build_point_input(self.world, self.points[index], index)

    def test_three_points_render(self):
        results = build_fixture(self.fixture)
        self.assertEqual([r["pointId"] for r in results], ["p1", "p2", "p3"])
        for r in results:
            self.assertIn("叙事任务。", r["input"])
            self.assertIn("玩家输入：", r["input"])
            self.assertIn("事件：", r["input"])
            self.assertIn("事实：", r["input"])
            self.assertTrue(r["input"].endswith("正文：\n"))

    def test_first_point_has_no_previous(self):
        text = self.build(0)["input"]
        self.assertIn("上一段正文：无（本点为首段）", text)
        self.assertIn("受阻原因：门锁着，杜衡不放行", text)

    def test_second_point_carries_previous_and_new_info(self):
        text = self.build(1)["input"]
        prior = self.points[1]["previousNarration"]
        self.assertIn(f"上一段正文：{prior}", text)
        self.assertIn("玩家输入：我问杜衡", text)
        self.assertIn("受阻原因：需登记；登记处 17:00 关门", text)
        # event order: D's rule, E's closing time, D leaves, form taken, E explains
        self.assertLess(text.index("清场到六点"), text.index("登记处五点就关门"))
        self.assertLess(text.index("登记处五点就关门"), text.index("我知道，我去拿登记表"))
        self.assertLess(text.index("我知道，我去拿登记表"), text.index("从墙上的登记表夹"))
        self.assertLess(text.index("从墙上的登记表夹"), text.index("他得把室内的东西都登记完"))
        self.assertIn("物品交接｜杜衡｜空白登记表", text)
        self.assertIn("移动｜杜衡｜三层走廊→楼梯间", text)

    def test_third_point_carries_previous(self):
        text = self.build(2)["input"]
        self.assertIn(f"上一段正文：{self.points[2]['previousNarration']}", text)
        self.assertIn("物品交接｜杜衡｜画夹", text)

    def test_deterministic(self):
        a = self.build(1)
        b = self.build(1)
        self.assertEqual(a["sha256"], b["sha256"])
        self.assertEqual(a["input"], b["input"])

    def test_offscreen_with_observable(self):
        point = copy.deepcopy(self.points[1])
        point["events"][4]["visible"] = False
        point["events"][4]["observable"] = "杜衡回来时，臂弯里夹着一张空白登记表"
        result = build_point_input(self.world, point, 1)
        self.assertIn("观察｜杜衡回来时，臂弯里夹着一张空白登记表", result["input"])
        self.assertNotIn("从墙上的登记表夹", result["input"])
        self.assertIn(
            {"code": "event-offscreen-observable", "eventId": "e5"},
            result["diagnostics"],
        )

    def test_offscreen_without_observable_is_dropped(self):
        point = copy.deepcopy(self.points[1])
        point["events"][4]["visible"] = False
        point["events"][4].pop("observable", None)
        result = build_point_input(self.world, point, 1)
        self.assertNotIn("从墙上的登记表夹", result["input"])
        self.assertIn(
            {"code": "event-offscreen-omitted", "eventId": "e5"},
            result["diagnostics"],
        )

    def _assert_code(self, point, index, code):
        with self.assertRaises(AdapterError) as ctx:
            build_point_input(self.world, point, index)
        self.assertEqual(ctx.exception.code, code)

    def test_missing_player_input(self):
        point = copy.deepcopy(self.points[0])
        point["playerInput"] = "  "
        self._assert_code(point, 0, "player-input-missing")

    def test_missing_previous_narration(self):
        point = copy.deepcopy(self.points[1])
        point["previousNarration"] = None
        self._assert_code(point, 1, "previous-narration-missing")

    def test_unknown_actor(self):
        point = copy.deepcopy(self.points[0])
        point["events"][0]["actor"] = "person_x"
        self._assert_code(point, 0, "unknown-entity")

    def test_unknown_event_kind(self):
        point = copy.deepcopy(self.points[0])
        point["events"][0]["kind"] = "explode"
        self._assert_code(point, 0, "unsupported-event-kind")

    def test_visibility_must_be_explicit(self):
        point = copy.deepcopy(self.points[0])
        point["events"][0].pop("visible")
        self._assert_code(point, 0, "event-visibility-missing")

    def test_achieved_task_cannot_have_blocked_reason(self):
        point = copy.deepcopy(self.points[2])
        point["task"]["status"] = "achieved"
        self._assert_code(point, 2, "achieved-task-with-blocked-reason")


if __name__ == "__main__":
    unittest.main(verbosity=2)
