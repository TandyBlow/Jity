"""Regression tests for the candidate pack (pack v3).

Pins every defect an external reviewer found on 2026-11-08, plus the four
capability stages and the N2-based visibility pipeline:

  * R1/R2/R3 run on the FULL change set; the spoken subset has its own signature
  * invisible facts (N2) never reach input.json - they live in answer.json
  * a deferred entity is removed from the packet entirely (c8e06)
  * the page projection's numeric-cause rule is per character, not per point
  * item moves carry both ends and holder information (c8e05)
  * a reference object carries a readable name (c8e04)
  * a zero-valued standing number survives into currentState

Run: python -B tools/test_candidates_pack.py
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
import sys
import unittest

HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE.parent
IDS = ("c8e01", "c8e02", "c8e03", "c8e04", "c8e05", "c8e06")

_spec = importlib.util.spec_from_file_location("pack", HERE / "build_candidates_fresh.py")
pack = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pack)


def load(name):
    return json.loads((OUT / "candidates-fresh" / name).read_text(encoding="utf-8"))


class Exclusion(unittest.TestCase):
    def test_r3_uses_full_change_set(self):
        c8e02 = load("c8e02/screening.json")
        self.assertEqual(c8e02["v2"]["signature"], "moved*2|2|45s")
        self.assertEqual(c8e02["expressionSignature"], "moved*1|1|45s")
        c8e06 = load("c8e06/screening.json")
        self.assertEqual(c8e06["v2"]["signature"], "moved*2+task_achieved*1|2|120s")

    def test_r3_full_equals_all_change_facts(self):
        screening = importlib.util.module_from_spec(
            importlib.util.spec_from_file_location("screening", HERE / "screening.py"))
        screening.__spec__.loader.exec_module(screening)
        for cid in IDS:
            facts = load(f"{cid}/facts.json")["changeFacts"]
            data = load(f"{cid}/screening.json")
            expected = screening.change_signature(
                facts, load(f"{cid}/input.json")["timeAdvance"])
            self.assertEqual(data["v2"]["signature"], expected, cid)


class Visibility(unittest.TestCase):
    def test_c8e02_far_building_is_absent_from_input(self):
        data = load("c8e02/input.json")
        blob = json.dumps(data, ensure_ascii=False)
        self.assertNotIn("邵苇衡", blob)
        self.assertNotIn("穹榛中继室", blob)
        self.assertNotIn("fe_shao", blob)
        # the model must not even learn that something was withheld
        self.assertNotIn("withheld", blob)
        answer = load("c8e02/answer.json")
        self.assertEqual(len(answer["withheld"]), 1)

    def test_c8e02_withheld_fact_stays_in_the_answer(self):
        answer = load("c8e02/answer.json")
        withheld = answer["withheld"]
        self.assertEqual([w["entityId"] for w in withheld], ["fe_shao"])
        self.assertEqual(withheld[0]["n2Ground"], "other-location")

    def test_c8e06_deferred_entity_is_absent(self):
        data = load("c8e06/input.json")
        self.assertNotIn("fe_wen", {f["entityId"] for f in data["mustExpress"]})
        self.assertNotIn("fe_wen", {m["entityId"] for m in data["mayMention"]})
        self.assertNotIn("fe_wen", {c["entityId"] for c in data["currentState"]})

    def test_every_invisible_fact_is_reported(self):
        for cid in IDS:
            answer = load(f"{cid}/answer.json")
            invisible = [d for d in answer["n2"]["decisions"]
                         if d.get("class") == "invisible"]
            withheld = [w for w in answer["withheld"]
                        if w["expression"] == "withheld"]
            self.assertEqual(len(invisible), len(withheld), cid)

    def test_n2_was_actually_called(self):
        answer = load("c8e02/answer.json")
        self.assertEqual(answer["n2"]["status"], "ok")
        self.assertTrue(answer["n2"]["decisions"])
        self.assertIn("n2_perspective", answer["n2"]["module"])


class Capability(unittest.TestCase):
    def test_numeric_cause_is_checked_per_character(self):
        after = json.loads((OUT / "fresh/source/c8e01.after.json").read_text(encoding="utf-8"))
        split = [
            {"kind": "sanity_changed", "actor": "fe_nie", "entityId": "fe_nie"},
            {"kind": "task_achieved", "actor": "fe_pu", "entityId": "fe_pu"},
            {"kind": "personality_changed", "actor": "fe_yu", "entityId": "fe_yu"},
        ]
        caps = pack.capability("synthetic", split, [], after)
        rules = [f["rule"] for f in caps["flags"]]
        self.assertIn("P3-incomplete-numeric-cause", rules)
        self.assertFalse(caps["stages"]["pageProjectionAcceptsDelta"])

    def test_complete_trio_for_one_character_is_accepted(self):
        after = json.loads((OUT / "fresh/source/c8e03.after.json").read_text(encoding="utf-8"))
        same = [
            {"kind": "sanity_changed", "actor": "fe_wen", "entityId": "fe_wen"},
            {"kind": "task_achieved", "actor": "fe_wen", "entityId": "fe_wen"},
            {"kind": "personality_changed", "actor": "fe_wen", "entityId": "fe_wen"},
        ]
        caps = pack.capability("synthetic", same, [], after)
        self.assertTrue(caps["stages"]["pageProjectionAcceptsDelta"])

    def test_perspective_item_is_not_page_ready(self):
        row = next(r for r in load("candidates.json")["candidates"] if r["id"] == "c8e02")
        self.assertFalse(row["capability"]["pagePathSatisfiesExpectation"])
        self.assertIn("P5-no-perspective-filter",
                      [f["rule"] for f in row["capability"]["flags"]])

    def test_stages_are_separate(self):
        row = next(r for r in load("candidates.json")["candidates"] if r["id"] == "c8e06")
        stages = row["capability"]["stages"]
        self.assertTrue(stages["stateCommitted"])
        self.assertFalse(stages["perspectiveFilterEnforced"])
        self.assertFalse(stages["narrationGenerated"])


class Regeneration(unittest.TestCase):
    def test_pack_regenerates_byte_for_byte(self):
        """The committed pack must be what the generator produces today: the
        tests otherwise only read files that could have drifted."""
        import subprocess
        proc = subprocess.run([sys.executable, "-B", str(HERE / "build_candidates_fresh.py"),
                               "--check"], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stdout[-2000:] + proc.stderr[-2000:])


class RegenerationDetectsDrift(unittest.TestCase):
    def test_tampered_copy_fails_the_check(self):
        """A check that compares the fresh output with itself always passes;
        this proves the comparison actually reads the committed bytes."""
        import shutil
        import subprocess
        import tempfile
        tmp = pathlib.Path(tempfile.mkdtemp()) / "pack"
        shutil.copytree(OUT / "candidates-fresh", tmp)
        victim = tmp / "c8e03/input.json"
        data = json.loads(victim.read_text(encoding="utf-8"))
        data["note"] = "tampered"
        victim.write_text(json.dumps(data, ensure_ascii=False, indent=1) + chr(10),
                          encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, "-B", str(HERE / "build_candidates_fresh.py"),
             "--check", "--against", str(tmp)],
            capture_output=True, text=True)
        self.assertNotEqual(proc.returncode, 0, proc.stdout[-1000:])
        self.assertIn("c8e03/input.json", proc.stdout)

    def test_missing_file_fails_the_check(self):
        import shutil
        import subprocess
        import tempfile
        tmp = pathlib.Path(tempfile.mkdtemp()) / "pack"
        shutil.copytree(OUT / "candidates-fresh", tmp)
        (tmp / "c8e05/facts.json").unlink()
        proc = subprocess.run(
            [sys.executable, "-B", str(HERE / "build_candidates_fresh.py"),
             "--check", "--against", str(tmp)],
            capture_output=True, text=True)
        self.assertNotEqual(proc.returncode, 0, proc.stdout[-1000:])


class Projection(unittest.TestCase):
    def setUp(self):
        self.measured = load("projection-check.json")
        self.pack = load("candidates.json")

    def test_prediction_matches_the_real_projection(self):
        verdicts = {c["id"]: c for c in self.measured["cases"]}
        for row in self.pack["candidates"]:
            self.assertEqual(
                row["capability"]["stages"]["pageProjectionAcceptsDelta"],
                verdicts[row["id"]]["accepted"], row["id"])

    def test_perspective_item_really_leaks_in_the_page_path(self):
        verdicts = {c["id"]: c for c in self.measured["cases"]}
        self.assertTrue(verdicts["c8e02"]["accepted"])
        self.assertTrue(verdicts["c8e02"]["projectionNarratesWithheld"])
        row = next(r for r in self.pack["candidates"] if r["id"] == "c8e02")
        self.assertFalse(row["capability"]["pagePathSatisfiesExpectation"])

    def test_no_model_was_called(self):
        self.assertEqual(self.measured["modelCalls"], 0)


class Facts(unittest.TestCase):
    def test_item_move_keeps_both_ends_and_holder(self):
        facts = load("c8e05/facts.json")["changeFacts"]
        move = next(f for f in facts if f["kind"] == "moved_entity")
        self.assertEqual((move["fromId"], move["toId"]), ("fe_wen", "fe_nie"))
        self.assertEqual((move["from"], move["to"]), ("闻澈岑", "聂汀穗"))
        self.assertTrue(move["holderChanged"])

    def test_relative_position_has_readable_name(self):
        facts = load("c8e04/facts.json")["changeFacts"]
        move = next(f for f in facts if f["kind"] == "moved_entity")
        self.assertEqual(move["relativeTo"]["name"], "聂汀穗")

    def test_zero_survives_current_state(self):
        rows = pack.current_state_entries(
            "x", [{"kind": "sanity", "entityId": "x", "name": "甲", "value": 0}],
            json.loads((OUT / "fresh/source/c8e01.after.json").read_text(encoding="utf-8")),
            {"type": "omniscient", "entityId": None})
        self.assertEqual(rows, [{"entityId": "x", "name": "甲",
                                 "kind": "sanity", "value": 0}])


if __name__ == "__main__":
    unittest.main(verbosity=2)
