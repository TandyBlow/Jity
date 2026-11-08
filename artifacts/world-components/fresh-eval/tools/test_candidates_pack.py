"""Regression tests for the candidate pack (pack v2, after external review).

Each test pins one of the four defects the reviewer found on 2026-11-08, so a
later change cannot quietly reintroduce them:

  * out-of-scope facts must not sit in mustExpress (c8e02 perspective, c8e06
    player instruction);
  * item moves must carry both ends plus holder information (c8e05);
  * reference objects must carry a readable name (c8e04);
  * a zero-valued standing number must survive into currentState.

Run: python -B tools/test_candidates_pack.py
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
import unittest

HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE.parent

_spec = importlib.util.spec_from_file_location("pack", HERE / "build_candidates_fresh.py")
pack = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pack)


def load(name):
    return json.loads((OUT / "candidates-fresh" / name).read_text(encoding="utf-8"))


class Scope(unittest.TestCase):
    def test_c8e02_offscreen_move_is_not_must(self):
        data = load("c8e02/input.json")
        must = {f["entityId"] for f in data["mustExpress"]}
        may = {(m["fact"]["entityId"], m["reason"]) for m in data["mayMention"]}
        self.assertEqual(must, {"fe_wen"})
        self.assertIn(("fe_shao", "offstage-perspective"), may)

    def test_c8e06_deferred_move_is_not_must(self):
        data = load("c8e06/input.json")
        must = {f["entityId"] for f in data["mustExpress"]}
        may = {(m["fact"]["entityId"], m["reason"]) for m in data["mayMention"]}
        self.assertNotIn("fe_wen", must)
        self.assertIn(("fe_wen", "deferredByInstruction"), may)

    def test_no_fact_is_both_must_and_may(self):
        for cid in ("c8e01", "c8e02", "c8e03", "c8e04", "c8e05", "c8e06"):
            data = load(f"{cid}/input.json")
            must = {(f["kind"], f["entityId"], f.get("fieldPath"))
                    for f in data["mustExpress"]}
            may = {(m["fact"]["kind"], m["fact"]["entityId"],
                    m["fact"].get("fieldPath")) for m in data["mayMention"]}
            self.assertEqual(must & may, set(), cid)

    def test_visible_containers_include_the_building(self):
        after = json.loads((OUT / "fresh/source/c8e02.after.json").read_text(encoding="utf-8"))
        self.assertEqual(pack.visible_containers(after, "fe_wen"), {"fy_cal", "fy_yard"})


class Facts(unittest.TestCase):
    def test_item_move_keeps_both_ends_and_holder(self):
        facts = load("c8e05/facts.json")["changeFacts"]
        move = next(f for f in facts if f["kind"] == "moved_entity")
        self.assertEqual((move["fromId"], move["toId"]), ("fe_wen", "fe_nie"))
        self.assertEqual((move["from"], move["to"]), ("闻澈岑", "聂汀穗"))
        self.assertEqual((move["fromKind"], move["toKind"]), ("character", "character"))
        self.assertTrue(move["holderChanged"])

    def test_relative_position_has_readable_name(self):
        facts = load("c8e04/facts.json")["changeFacts"]
        move = next(f for f in facts if f["kind"] == "moved_entity")
        self.assertEqual(move["relativeTo"]["entityId"], "fe_nie")
        self.assertEqual(move["relativeTo"]["name"], "聂汀穗")

    def test_zero_survives_current_state(self):
        rows = pack.current_state_entries(
            [{"kind": "sanity", "entityId": "x", "name": "甲", "value": 0}])
        self.assertEqual(rows, [{"entityId": "x", "name": "甲",
                                 "kind": "sanity", "value": 0}])


class Capability(unittest.TestCase):
    def test_stages_are_separate(self):
        data = load("c8e06/input.json")
        caps = load("candidates.json")
        row = next(r for r in caps["candidates"] if r["id"] == "c8e06")
        stages = row["capability"]["stages"]
        self.assertTrue(stages["stateCommitted"])
        self.assertFalse(stages["perspectiveFilterEnforced"])
        self.assertFalse(stages["narrationGenerated"])
        self.assertFalse(row["capability"]["pagePathSatisfiesExpectation"])
        self.assertTrue(data["mustExpress"])

    def test_perspective_item_is_not_marked_page_ready(self):
        caps = load("candidates.json")
        row = next(r for r in caps["candidates"] if r["id"] == "c8e02")
        self.assertFalse(row["capability"]["pagePathSatisfiesExpectation"])
        self.assertIn("P5-no-perspective-filter",
                      [f["rule"] for f in row["capability"]["flags"]])


if __name__ == "__main__":
    unittest.main(verbosity=2)
