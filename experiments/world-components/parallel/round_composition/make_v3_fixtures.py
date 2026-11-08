# Build the v3-only sample fixtures: D1 (outcome + resultText) and the D5
# sample families (two-actor conflict, same-name entities, ordinary control).
#
# D5 ruling: register the samples FIRST, then move the gates to data
# triggers. The samples are program-plan cases (plan_v3), not scripted plans,
# except where the ruling explicitly needs a TAMPERED plan to prove a gate
# fires (same-name pronoun grant) — those are labelled `tampered`.
#
# Every sample carries the rowId aliases it must be judged under twice, so the
# archive can show that renaming a case does not change a verdict.
#
# Usage: python -X utf8 make_v3_fixtures.py

import copy
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
WC = HERE.parent.parent
sys.path.insert(0, str(WC))

import narration_pipeline as np_  # noqa: E402

OUT = HERE / "fixtures" / "cases-v3-extra.json"

STATE = np_.make_pipeline_state()
BEFORE = {**np_.make_point(1, {}, None, state=copy.deepcopy(STATE)),
          "pointId": "pt-1", "version": 1}


def point(deltas, state=None, time_advance=None, version=2):
    return np_.make_point(version, deltas, time_advance,
                          state=state if state is not None
                          else copy.deepcopy(STATE), prev="pt-1")


def with_state(**over):
    st = copy.deepcopy(STATE)
    for eid, fields in over.items():
        st["characters"][eid].update(fields)
    return st


def moved(eid, container):
    return np_.moved_delta(eid, container)


def base_case(cid, title, expect, pt, *, judge_only=False, gender_hints=None,
              narrative_outcome=False,
              plan_source="program", texts=None, counters=None,
              row_id_aliases=None, notes=None, plan_override=None):
    return {
        "caseId": cid, "title": title, "expect": expect,
        # judge-level samples skip the chain: the point is turned into N1
        # facts + a program plan, and only the gate is exercised. N2 visibility
        # is NOT applied, because these samples test the gate, not selection.
        "judgeOnly": judge_only,
        "genderHints": gender_hints,
        "before": BEFORE, "point": pt,
        "perspective": {"type": "protagonist"},
        "options": {"mayPolicy": "select", "visibleOtherActions": False},
        "selectionSource": "rule",
        "planSource": plan_source,
        "planOverride": plan_override,
        "sentenceTexts": texts or [],
        # counter-texts are expected to be REJECTED; each carries its own
        # expectation and the reason it exists, so a gate firing is archived
        "counterTexts": counters or [],
        "narrativeOutcome": narrative_outcome,
        "rowIdAliases": row_id_aliases or [f"comp:{cid}", f"alias:{cid}"],
        "notes": notes,
    }


def main() -> int:
    cases = []

    # ---- D1: task completion via outcome + resultText -------------------
    st = with_state(char_pa={
        "position": {"containerId": "loc_2", "slotId": None,
                     "relativeTo": None},
        "tasks": {**copy.deepcopy(STATE["characters"]["char_pa"]["tasks"]),
                  "task_1": {**copy.deepcopy(
                      STATE["characters"]["char_pa"]["tasks"]["task_1"]),
                      "status": "achieved",
                      "resultText": "把铜铃挂回了钟楼"}}})
    d = {"char_pa": {**moved("char_pa", "loc_2"),
                     "tasksAchieved": ["task_1"]}}
    cases.append(base_case(
        "d1-outcome-result", "任务达成用结果表述", "n5-pass",
        point(d, st), narrative_outcome=True,
        texts=["管线甲从管线镇来到了钟楼。管线甲把铜铃挂回了钟楼。"],
        notes="N1 emits outcome+resultText from the state's task.resultText; "
              "the text repeats that result. The goal never appears."))

    # D1 negative at chain level: achieved task with no resultText must block
    # in N1 (task-outcome-unavailable), never fall back to the goal.
    st2 = with_state(char_pa={
        "position": {"containerId": "loc_2", "slotId": None,
                     "relativeTo": None},
        "tasks": {**copy.deepcopy(STATE["characters"]["char_pa"]["tasks"]),
                  "task_1": {**copy.deepcopy(
                      STATE["characters"]["char_pa"]["tasks"]["task_1"]),
                      "status": "achieved"}}})
    cases.append(base_case(
        "d1-outcome-missing", "缺 resultText 必须阻断", "incomplete",
        point(d, st2), narrative_outcome=True, texts=[],
        notes="No resultText in the committed state -> N1 blocking "
              "diagnostic; the goal is not used as a substitute."))

    # ---- D5-a: two actors, one shared goal (different names) -----------
    st3 = with_state(
        char_pa={"tasks": {**copy.deepcopy(
            STATE["characters"]["char_pa"]["tasks"]),
            "task_2": {**copy.deepcopy(
                STATE["characters"]["char_pa"]["tasks"]["task_2"]),
                "goal": "合力抬钟", "status": "achieved"}}},
        char_pb={"tasks": {**copy.deepcopy(
            STATE["characters"]["char_pb"]["tasks"]),
            "task_3": {**copy.deepcopy(
                STATE["characters"]["char_pb"]["tasks"]["task_3"]),
                "goal": "合力抬钟", "status": "achieved"}}})
    d3 = {"char_pa": {"entityId": "char_pa", "positionSet": None,
                      "appearanceChanges": [], "personalityChanges": [],
                      "subtasksAdded": [], "tasksAchieved": ["task_2"],
                      "sanitySet": None},
          "char_pb": {"entityId": "char_pb", "positionSet": None,
                      "appearanceChanges": [], "personalityChanges": [],
                      "subtasksAdded": [], "tasksAchieved": ["task_3"],
                      "sanitySet": None}}
    cases.append(base_case(
        "d5-conflict-two-actors", "双人同目标（不同名）", "n5-pass",
        point(d3, st3), judge_only=True,
        texts=["管线甲完成了任务「合力抬钟」。管线乙完成了任务「合力抬钟」。"],
        counters=[{"text": "管线甲完成了任务「合力抬钟」。",
                   "expect": "n5-rejected",
                   "why": "one actor named: the second fact is uncovered"}],
        notes="plan_v3 merges both facts into one group (same goal, same "
              "place). Naming both actors passes; naming one leaves the "
              "other fact uncovered. G4 is NOT triggered (different names)."))

    # ---- D5-b: two entities with the SAME display name -----------------
    st4 = copy.deepcopy(STATE)
    st4["initial"]["characters"]["char_pc"] = {
        "id": "char_pc", "name": "管线乙",
        "initialPosition": {"containerId": "loc_1", "slotId": None,
                            "relativeTo": None},
        "initialAppearance": "常态", "initialPersonality": "沉默",
        "initialSanity": 9,
        "tasks": {"task_9": {"id": "task_9", "ownerId": "char_pc",
                             "parentTaskId": None, "goal": "合力抬钟",
                             "status": "achieved"}}}
    st4["characters"]["char_pc"] = {
        "id": "char_pc",
        "position": {"containerId": "loc_1", "slotId": None,
                     "relativeTo": None},
        "appearanceChanges": [], "personalityChanges": [], "sanity": 9,
        "tasks": {"task_9": {"id": "task_9", "ownerId": "char_pc",
                             "parentTaskId": None, "goal": "合力抬钟",
                             "status": "achieved"}}}
    st4["characters"]["char_pb"]["tasks"]["task_3"]["goal"] = "合力抬钟"
    st4["characters"]["char_pb"]["tasks"]["task_3"]["status"] = "achieved"
    d4 = {"char_pb": {"entityId": "char_pb", "positionSet": None,
                      "appearanceChanges": [], "personalityChanges": [],
                      "subtasksAdded": [], "tasksAchieved": ["task_3"],
                      "sanitySet": None},
          "char_pc": {"entityId": "char_pc", "positionSet": None,
                      "appearanceChanges": [], "personalityChanges": [],
                      "subtasksAdded": [], "tasksAchieved": ["task_9"],
                      "sanitySet": None}}
    cases.append(base_case(
        "d5-same-name-actors", "同名两名角色", "n5-pass",
        point(d4, st4), judge_only=True,
        texts=["管线乙完成了任务「合力抬钟」。管线乙完成了任务「合力抬钟」。"],
        counters=[{"text": "管线乙完成了任务「合力抬钟」。",
                   "expect": "n5-rejected",
                   "why": "one mention collapses two same-name people"}],
        notes="Two entities share the display name 管线乙. plan_v3 keeps them "
              "in separate groups and grants no pronoun. G4 is triggered by "
              "DATA (same display name, two entity ids) and requires one "
              "mention per actor."))

    # same-name + tampered plan that grants a pronoun: G5 must fire
    cases.append(base_case(
        "d5-same-name-grant", "同名角色获得代词授权（篡改计划）", "n5-rejected",
        point(d4, st4), judge_only=True, plan_source="tampered",
        plan_override={
            "sentences": [{"index": 0, "factIds": ["f0", "f1"],
                           "coreference": [{"mention": "他",
                                            "refersTo": "char_pb",
                                            "pronoun": "他"}],
                           "time": None}],
            "edges": {"consecutive-time": False}},
        texts=["管线乙完成了任务「合力抬钟」。管线乙完成了任务「合力抬钟」。"],
        notes="A tampered plan grants a pronoun to one of two same-name "
              "entities. G5 is data-triggered and must fail, even though the "
              "text itself names both actors."))

    # ---- D5-c: ordinary control ---------------------------------------
    st5 = with_state(char_pa={
        "position": {"containerId": "loc_2", "slotId": None,
                     "relativeTo": None},
        "tasks": {**copy.deepcopy(STATE["characters"]["char_pa"]["tasks"]),
                  "task_1": {**copy.deepcopy(
                      STATE["characters"]["char_pa"]["tasks"]["task_1"]),
                      "status": "achieved",
                      "resultText": "把铜铃挂回了钟楼"}}})
    cases.append(base_case(
        "d5-control-single-actor", "普通对照：单人", "n5-pass",
        point({"char_pa": {**moved("char_pa", "loc_2"),
                           "tasksAchieved": ["task_1"]}}, st5),
        narrative_outcome=True,
        texts=["管线甲从管线镇来到了钟楼。管线甲把铜铃挂回了钟楼。"],
        notes="Ordinary single-actor case: G4/G5 must NOT be triggered, so "
              "no conflict gate value is recorded."))

    # ---- D2 regressions (reviewer counter-examples, archived) ----------
    f8 = [{"factId": "f0", "kind": "moved", "entityId": "char_pa",
           "name": "管线甲", "from": "管线镇", "to": "钟楼",
           "entityGroup": "characters"},
          {"factId": "f1", "kind": "task_achieved", "entityId": "char_pa",
           "name": "管线甲", "goal": "把铜铃挂回钟楼",
           "entityGroup": "characters"},
          {"factId": "f2", "kind": "time", "amount": 8, "unit": "minute"}]
    base = "管线甲从管线镇来到了钟楼。管线甲完成了任务「把铜铃挂回钟楼」。"
    cases.append({
        "caseId": "d2-time-value-strict", "title": "时长数值必须完整比对",
        "expect": "n5-pass", "judgeOnly": True,
        "facts": f8, "mustExpress": ["f0", "f1", "f2"],
        "plan": {"sentences": [{"index": 0, "factIds": ["f0", "f1", "f2"],
                                "coreference": [],
                                "time": {"amount": 8, "unit": "minute"}}]},
        "sentenceTexts": [base + "约八分钟过去了。"],
        "counterTexts": [
            {"text": base + "8.8分钟过去了。", "expect": "n5-rejected",
             "why": "decimal truncated to 8 by the first scanner"},
            {"text": base + "负八分钟过去了。", "expect": "n5-rejected",
             "why": "negative sign dropped by the first scanner"},
            {"text": base + "过了一会儿，八分半钟过去了。",
             "expect": "n5-rejected",
             "why": "half-minute value hidden behind a vague clause"},
            {"text": base + "几分钟过去了。", "expect": "n5-rejected",
             "why": "explicit but unparseable duration"},
            {"text": base + "过了一会儿，八点八分钟过去了。",
             "expect": "n5-rejected",
             "why": "second review: only 八分钟 was matched inside a Chinese "
                    "decimal expression"},
            {"text": base + "过了一会儿，八分钟半过去了。",
             "expect": "n5-rejected",
             "why": "second review: trailing 半 was left outside the match"},
            {"text": base + "一百分钟过去了。", "expect": "n5-rejected",
             "why": "second review: cn_to_int returned None above 99, the "
                    "first build raised TypeError instead of judging"},
        ],
        "rowIdAliases": ["comp:d2-time-value-strict",
                         "alias:d2-time-value-strict"],
        "notes": "Same authoritative value 8 minutes throughout. The first "
                 "version passed 8.8 / 负八分钟 / 八分半钟 / 几分钟; all four "
                 "must now fail, while 约八分钟 and a pure vague clause pass.",
    })

    # ---- unit forms and cross-unit equality ----------------------------
    f90 = [{"factId": "f0", "kind": "moved", "entityId": "char_pa",
            "name": "管线甲", "from": "管线镇", "to": "钟楼",
            "entityGroup": "characters"},
           {"factId": "f2", "kind": "time", "amount": 90, "unit": "minute"}]
    cases.append({
        "caseId": "d2-time-units", "title": "时长单位与复合表达",
        "expect": "n5-pass", "judgeOnly": True,
        "facts": f90, "mustExpress": ["f0", "f2"],
        "plan": {"sentences": [{"index": 0, "factIds": ["f0", "f2"],
                                "coreference": [],
                                "time": {"amount": 90, "unit": "minute"}}]},
        "sentenceTexts": ["管线甲从管线镇来到了钟楼。一个半小时过去了。"],
        "counterTexts": [
            {"text": "管线甲从管线镇来到了钟楼。一小时四十分钟过去了。",
             "expect": "n5-rejected",
             "why": "compound duration: 一小时 + 四十分钟, neither equals 90 "
                    "minutes; compound expressions are not summed"},
            {"text": "管线甲从管线镇来到了钟楼。一百分钟过去了。",
             "expect": "n5-rejected",
             "why": "100 minutes != 90 minutes; also proves 百 does not crash"},
        ],
        "rowIdAliases": ["comp:d2-time-units", "alias:d2-time-units"],
        "notes": "Exact-length units (second/minute/hour/day) are compared in "
              "seconds, so 一个半小时 equals 90 minutes; months/years stay "
              "unit-for-unit because their length is not fixed. Compound "
              "expressions are not summed and therefore fail.",
    })

    # ---- grant regression: legal pronoun must be matched ----------------
    st6 = with_state(char_pa={
        "position": {"containerId": "loc_2", "slotId": None,
                     "relativeTo": None}})
    cases.append(base_case(
        "d2-pronoun-grant", "合法代词授权必须命中", "n5-pass",
        point({"char_pa": moved("char_pa", "loc_2")}, st6), judge_only=True,
        gender_hints={"char_pa": "male"},
        texts=["他从管线镇来到了钟楼。"],
        counters=[{"text": "他从管线镇来到了桥头。",
                   "expect": "n5-rejected",
                   "why": "wrong destination still fails"}],
        notes="genderHints licenses 他 for char_pa (single entity, unique "
              "name). v2 accepts this; the first v3 build reported "
              "uncovered:f0:moved because it always passed pronoun=None."))

    # ---- D1 judge-level block (no chain; the row is built by the runner) --
    cases.append({
        "caseId": "d1-outcome-judge-block", "title": "判定器缺 resultText 阻断",
        "expect": "blocked-at-judge", "judgeOnly": True,
        "facts": [{"factId": "f0", "kind": "outcome", "entityId": "char_pa",
                   "name": "管线甲", "goal": "把铜铃挂回钟楼",
                   "entityGroup": "characters"}],
        "mustExpress": ["f0"],
        "plan": {"sentences": [{"index": 0, "factIds": ["f0"],
                                "coreference": [], "time": None}]},
        "text": "管线甲完成了任务「把铜铃挂回钟楼」。",
        "rowIdAliases": ["comp:d1-outcome-judge-block",
                         "alias:d1-outcome-judge-block"],
        "notes": "A judge-level row whose outcome fact has no resultText must "
                 "block; the text quoting the goal is not accepted instead.",
    })

    doc = {"version": "round-composition-cases-v3-extra-v1",
           "world": "narration_pipeline.make_pipeline_state (w_pipe), plus a "
                    "second 管线乙 entity (char_pc) for the same-name family",
           "note": "D1/D5 samples. Program plan unless planSource=tampered. "
                   "Texts are scripted; no model ran.",
           "cases": cases}
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8", newline="\n")
    print(f"wrote {len(cases)} v3 sample cases -> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
