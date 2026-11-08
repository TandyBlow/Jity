# Build the round-composition case fixtures (deterministic JSON).
#
# The cases are POINTS over the registered pipeline world
# (narration_pipeline.make_pipeline_state), each with an explicit before
# point. N1 is run by the composer, not copied from here: the fixture holds
# the committed-state inputs (point/before/perspective) and the options for
# the perspective rule, so every fact the composer narrates can be traced
# back to an entity delta and a field path.
#
# The mock SELECTION / ORGANIZATION / SENTENCE responses live in mocks.json;
# they are scripted JSON, not model outputs. This script never writes them.
#
# Usage: python -X utf8 make_fixtures.py

import copy
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
WC = HERE.parent.parent
sys.path.insert(0, str(WC))

import narration_pipeline as np_  # noqa: E402

OUT = HERE / "fixtures" / "cases.json"

STATE = np_.make_pipeline_state()
BEFORE = {**np_.make_point(1, {}, None, state=copy.deepcopy(STATE)),
          "pointId": "pt-1", "version": 1}


def point(deltas, state=None, time_advance=None, version=2):
    return np_.make_point(version, deltas, time_advance,
                          state=state if state is not None
                          else copy.deepcopy(STATE), prev="pt-1")


def moved(eid, container):
    return np_.moved_delta(eid, container)


def with_char(**over):
    st = copy.deepcopy(STATE)
    for eid, fields in over.items():
        st["characters"][eid].update(fields)
    return st


def case(cid, title, expect, pt, perspective, mocks_ref,
         options=None, environment=None, fallback=True, notes=None):
    rec = {"caseId": cid, "title": title, "expect": expect,
           "mocksRef": mocks_ref,
           "before": BEFORE, "point": pt, "perspective": perspective,
           "options": {"mayPolicy": "select",
                       "visibleOtherActions": False, **(options or {})},
           "fallback": fallback}
    if environment is not None:
        rec["environment"] = environment
    if notes:
        rec["notes"] = notes
    return rec


def main() -> int:
    cases = []

    # 1 normal: one actor moves and completes a tracked task.
    st = with_char(char_pa={"position": {"containerId": "loc_2",
                                         "slotId": None, "relativeTo": None},
                            "tasks": {**copy.deepcopy(
                                STATE["characters"]["char_pa"]["tasks"]),
                                "task_1": {**copy.deepcopy(
                                    STATE["characters"]["char_pa"]["tasks"]["task_1"]),
                                    "status": "achieved"}}})
    d = {"char_pa": {**moved("char_pa", "loc_2"),
                     "tasksAchieved": ["task_1"]}}
    cases.append(case(
        "normal-move-task", "移动 + 任务达成", "ok", point(d, st),
        {"type": "protagonist"}, "normal-move-task",
        environment={"weather": "细雨", "wind": "高", "light": "昏暗",
                     "time": "傍晚", "atmosphere": "海雾贴着塔壁"},
        notes="N4.0 scene overlay supplied explicitly; N5 has no time fact. "
              "The overlay values are appended to 地点外貌 without labels, so "
              "they must already match the scene (see README gaps)."))

    # 2 normal: the viewpoint sees another actor move (N4 visible-actions
    # arm). No task/goal of the other actor is selected.
    st = with_char(
        char_pa={"position": {"containerId": "loc_2", "slotId": None,
                              "relativeTo": None}},
        char_pb={"position": {"containerId": "loc_2", "slotId": None,
                              "relativeTo": None}})
    d = {"char_pa": moved("char_pa", "loc_2"),
         "char_pb": moved("char_pb", "loc_2")}
    cases.append(case(
        "normal-two-actors", "同地可见动作（他人移动）", "ok", point(d, st),
        {"type": "protagonist"}, "normal-two-actors",
        {"visibleOtherActions": True},
        notes="N2 visibleOtherActions=True; the other actor's move is may."))

    # 3 normal: inner changes of the viewpoint actor (appearance, personality,
    # sanity).
    ch = [{"id": "ch_a1", "text": "外袍被雨浸透", "supersedes": []}]
    ph = [{"id": "ch_p1", "text": "话少了许多", "supersedes": []}]
    st = with_char(char_pa={
        "sanity": 14,
        "appearanceChanges": copy.deepcopy(ch),
        "personalityChanges": copy.deepcopy(ph)})
    d = {"char_pa": {"entityId": "char_pa", "positionSet": None,
                     "appearanceChanges": copy.deepcopy(ch),
                     "personalityChanges": copy.deepcopy(ph),
                     "subtasksAdded": [], "tasksAchieved": [],
                     "sanitySet": 14}}
    cases.append(case(
        "normal-inner-change", "外貌 + 个性 + 理智", "ok", point(d, st),
        {"type": "protagonist"}, "normal-inner-change",
        notes="All three facts are selected; the text follows the frozen N5 "
              "frames."))

    # 4 N1 stop: a delta for an unregistered entity cannot become a fact.
    d = {"char_x": {"entityId": "char_x", "positionSet": None,
                    "appearanceChanges": [], "personalityChanges": [],
                    "subtasksAdded": [], "tasksAchieved": [],
                    "sanitySet": None}}
    cases.append(case(
        "fail-n1-unregistered", "N1 未注册实体", "incomplete",
        point(d), {"type": "protagonist"}, "normal-move-task",
        notes="N1 entity-unregistered is a blocking diagnostic."))

    # 5 perspective stop: the caller names a subject the state does not hold.
    st = with_char(char_pa={"position": {"containerId": "loc_2",
                                         "slotId": None, "relativeTo": None}})
    d = {"char_pa": moved("char_pa", "loc_2")}
    cases.append(case(
        "fail-perspective", "视角人物不在册", "incomplete", point(d, st),
        {"type": "protagonist", "entityId": "char_missing"},
        "normal-move-task",
        notes="resolve_perspective stops before N1."))

    # 6 N2 stop: the mock selection names a fact that does not exist.
    st = with_char(char_pa={"position": {"containerId": "loc_2",
                                         "slotId": None, "relativeTo": None},
                            "tasks": {**copy.deepcopy(
                                STATE["characters"]["char_pa"]["tasks"]),
                                "task_1": {**copy.deepcopy(
                                    STATE["characters"]["char_pa"]["tasks"]["task_1"]),
                                    "status": "achieved"}}})
    d = {"char_pa": {**moved("char_pa", "loc_2"),
                     "tasksAchieved": ["task_1"]}}
    normal_pt = point(d, st)
    cases.append(case(
        "fail-n2-invalid", "N2 未知事实引用", "stopped-at-selection",
        normal_pt, {"type": "protagonist"}, "fail-n2-invalid",
        notes="The composer validates the selection against N1 ids."))

    # 7 N2 stop: a must fact is omitted by the mock selection.
    cases.append(case(
        "fail-n2-missing-must", "N2 漏掉必述事实", "stopped-at-selection",
        normal_pt, {"type": "protagonist"}, "fail-n2-missing-must",
        notes="must (moved) is missing from selectedFactIds."))

    # 8 N2 stop: empty selection while facts exist.
    cases.append(case(
        "fail-n2-empty", "N2 空选择", "stopped-at-selection",
        normal_pt, {"type": "protagonist"}, "fail-n2-empty",
        notes="An empty narration is not success."))

    # 9 N3 stop: the plan drops a selected fact (coverage invariant).
    cases.append(case(
        "fail-n3-coverage", "N3 计划漏事实", "stopped-at-organization",
        normal_pt, {"type": "protagonist"}, "fail-n3-coverage",
        notes="check_plan_v3: plan ids != selected ids."))

    # 10 N3 stop: the plan cites an unknown fact id.
    cases.append(case(
        "fail-n3-unknown", "N3 计划未知引用", "stopped-at-organization",
        normal_pt, {"type": "protagonist"}, "fail-n3-unknown",
        notes="check_plan_v3: unknown factId in a sentence group."))

    # 11 retry: attempt 1 misses a fact, attempt 2 passes.
    cases.append(case(
        "retry-n5-success", "N5 失败后重生成功", "ok",
        normal_pt, {"type": "protagonist"}, "retry-n5-success",
        notes="Two sentence-mock attempts; the second is accepted."))

    # 12 reject: both attempts fail N5; the template fallback is recorded but
    # the status stays a failure.
    cases.append(case(
        "reject-n5", "N5 两次拒绝 + 回退", "n5-rejected",
        normal_pt, {"type": "protagonist"}, "reject-n5",
        notes="Attempt 1 uncovered; attempt 2 truncated. Fallback text is "
              "recorded separately and is not a model success."))

    # 13 N5 G2: a repeated registered actor outside the matched spans.
    cases.append(case(
        "fail-n5-extra-actor", "N5 额外行动者提及", "n5-rejected",
        normal_pt, {"type": "protagonist"}, "fail-n5-extra-actor",
        notes="G2 residue-name: the third sentence mentions the actor again "
              "outside any matched span."))

    # 14 sentence port failure: no text from the sentence module.
    cases.append(case(
        "fail-sentence-port", "成句端口超时", "sentence-port-failed",
        normal_pt, {"type": "protagonist"}, "fail-sentence-port",
        notes="Both attempts raise model-timeout; the fallback is recorded."))

    # 15 contract conflict: N4.0 input renders time vaguely ("过去了一会儿")
    # while the frozen v2 N5 G3 requires the exact value. A compliant N4.0
    # sentence therefore fails N5; this is a rule conflict, not a text defect.
    st = with_char(char_pa={"position": {"containerId": "loc_2",
                                         "slotId": None, "relativeTo": None},
                            "tasks": {**copy.deepcopy(
                                STATE["characters"]["char_pa"]["tasks"]),
                                "task_1": {**copy.deepcopy(
                                    STATE["characters"]["char_pa"]["tasks"]["task_1"]),
                                    "status": "achieved"}}})
    d = {"char_pa": {**moved("char_pa", "loc_2"),
                     "tasksAchieved": ["task_1"]}}
    time_advance = {"boundary": "elapsed",
                    "duration": {"amount": 8, "unit": "minute"}}
    cases.append(case(
        "contract-time-conflict", "N4.0 模糊时间 vs N5 精确时间", "n5-rejected",
        point(d, st, time_advance), {"type": "protagonist"},
        "contract-time-conflict", fallback=False,
        notes="The mock text follows N4.0 (no exact duration); the frozen v2 "
              "N5 G3 fails. Fallback disabled so the exact-time template is "
              "not presented as a compliant result."))

    # 16 false pass: the frozen v2 judge cannot see a brand-new named actor
    # (only registered names/goals are scanned). The fixture annotates the
    # defect; the composer records the disagreement instead of relaxing N5.
    cases.append(case(
        "n5-false-pass-unregistered-actor", "N5 漏掉新增具名人物", "n5-false-pass",
        normal_pt, {"type": "protagonist"},
        "n5-false-pass-unregistered-actor", fallback=False,
        notes="The sentence mock declares addsUnregisteredEntity; judge_row "
              "returns pass. Recorded as an N5 coverage failure."))

    # 17 empty generation: both attempts come back blank -> 'empty-output'
    # (its own failure class), never a success with a silent empty string.
    cases.append(case(
        "fail-sentence-empty", "成句返回空文本", "empty-output",
        normal_pt, {"type": "protagonist"}, "fail-sentence-empty",
        notes="Both attempts are empty; the template fallback is recorded "
              "separately."))

    # 18 selection names an invisible fact: the other actor completes a
    # non-tracked task two locations away. N2's rule says invisible; the
    # composer must refuse the selection rather than narrate a secret.
    st = with_char(
        char_pa={"position": {"containerId": "loc_2", "slotId": None,
                              "relativeTo": None}},
        char_pb={"tasks": {**copy.deepcopy(
            STATE["characters"]["char_pb"]["tasks"]),
            "task_3": {**copy.deepcopy(
                STATE["characters"]["char_pb"]["tasks"]["task_3"]),
                "status": "achieved"}}})
    d = {"char_pa": moved("char_pa", "loc_2"),
         "char_pb": {"entityId": "char_pb", "positionSet": None,
                     "appearanceChanges": [], "personalityChanges": [],
                     "subtasksAdded": [], "tasksAchieved": ["task_3"],
                     "sanitySet": None}}
    cases.append(case(
        "fail-n2-invisible", "N2 选了不可见事实", "stopped-at-selection",
        point(d, st), {"type": "protagonist"}, "fail-n2-invisible",
        notes="The other actor's non-tracked task is completed at 管线镇 "
              "while the viewpoint stands at 钟楼 -> invisible."))

    # 19 fallback unavailable: a subtask fact has no program template frame.
    st = with_char(char_pa={"position": {"containerId": "loc_2",
                                          "slotId": None,
                                          "relativeTo": None}})
    d = {"char_pa": {**moved("char_pa", "loc_2"),
                     "subtasksAdded": [{"id": "task_9",
                                         "ownerId": "char_pa",
                                         "parentTaskId": "task_1",
                                         "goal": "找梯子",
                                         "status": "pending"}]}}
    cases.append(case(
        "fallback-unsupported-kind", "回退不支持的新任务类型", "n5-rejected",
        point(d, st), {"type": "protagonist"},
        "fallback-unsupported-kind",
        notes="The text omits the subtask; the template has no subtask frame, "
              "so the fallback records unavailableReason and no text."))

    doc = {"version": "round-composition-cases-v0.1",
           "world": "narration_pipeline.make_pipeline_state (w_pipe)",
           "note": "Points over committed state; N1 is recomputed by the "
                   "composer. Mocks are scripted JSON, not model outputs.",
           "cases": cases}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8", newline="\n")
    print(f"wrote {len(cases)} cases -> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
