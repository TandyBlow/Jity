# Build and PRE-REGISTER the first real-model batch (<=10 samples).
#
# Everything a reader needs to reproduce the batch is fixed here BEFORE any
# model runs: the 10 sample points, the selection/organization settings, the
# model identity, the decode parameters and the acceptance wording. The script
# dry-runs the program chain (N1 -> N2 rule -> plan_v3 -> scene -> N4.0) and
# refuses to register a case that would not reach the model, so "the model was
# asked to narrate" cannot be claimed for a case that actually stopped earlier.
#
# Outputs:
#   fixtures/batch-v1-cases.json   the 10 points + expected fact/selection/plan
#   fixtures/batch-v1.json         registration: model, decode, acceptance,
#                                  hashes of the cases file and of the chain code
#
# Usage: python -X utf8 make_real_batch.py

import copy
import hashlib
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
WC = HERE.parent.parent
for p in (str(WC), str(HERE)):
    if p not in sys.path:
        sys.path.insert(0, p)

import narration_pipeline as np_  # noqa: E402
import n2_perspective as n2p  # noqa: E402
import n3_organize as n3  # noqa: E402
from n4_input_renderer.packer import pack_narrative_input  # noqa: E402
from n4_input_renderer.scene_context import build_scene_context  # noqa: E402

CASES_OUT = HERE / "fixtures" / "batch-v1-cases.json"
REG_OUT = HERE / "fixtures" / "batch-v1.json"

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


def add_character(st, eid, name, goal="合力抬钟"):
    st["initial"]["characters"][eid] = {
        "id": eid, "name": name,
        "initialPosition": {"containerId": "loc_1", "slotId": None,
                            "relativeTo": None},
        "initialAppearance": "常态", "initialPersonality": "沉默",
        "initialSanity": 9,
        "tasks": {"task_9": {"id": "task_9", "ownerId": eid,
                             "parentTaskId": None, "goal": goal,
                             "status": "achieved"}}}
    st["characters"][eid] = {
        "id": eid, "position": {"containerId": "loc_1", "slotId": None,
                                "relativeTo": None},
        "appearanceChanges": [], "personalityChanges": [], "sanity": 9,
        "tasks": {"task_9": {"id": "task_9", "ownerId": eid,
                             "parentTaskId": None, "goal": goal,
                             "status": "achieved"}}}
    return st


def moved(eid, container):
    return np_.moved_delta(eid, container)


def case(cid, title, pt, *, options=None, narrative_outcome=False,
         perspective=None, notes=None, before=None):
    return {"caseId": cid, "title": title,
            "before": before if before is not None else BEFORE, "point": pt,
            "perspective": perspective or {"type": "protagonist"},
            "options": {"mayPolicy": "select", "visibleOtherActions": False,
                        **(options or {})},
            "selectionSource": "rule", "planSource": "program",
            "narrativeOutcome": narrative_outcome, "notes": notes}


def build_cases():
    cases = []

    # 1 moved + outcome (D1 path), no time
    st = with_state(char_pa={
        "position": {"containerId": "loc_2", "slotId": None,
                     "relativeTo": None},
        "tasks": {**copy.deepcopy(STATE["characters"]["char_pa"]["tasks"]),
                  "task_1": {**copy.deepcopy(
                      STATE["characters"]["char_pa"]["tasks"]["task_1"]),
                      "status": "achieved",
                      "resultText": "把铜铃挂回了钟楼"}}})
    cases.append(case(
        "rb-move-outcome", "移动 + 任务结果（outcome）",
        point({"char_pa": {**moved("char_pa", "loc_2"),
                           "tasksAchieved": ["task_1"]}}, st),
        narrative_outcome=True,
        notes="D1=C path: the task is narrated from resultText."))

    # 2 moved + outcome + time (8 minutes)
    cases.append(case(
        "rb-time-vague", "移动 + 结果 + 时间推进",
        point({"char_pa": {**moved("char_pa", "loc_2"),
                           "tasksAchieved": ["task_1"]}}, st,
              {"boundary": "elapsed",
               "duration": {"amount": 8, "unit": "minute"}}),
        narrative_outcome=True,
        notes="N4.0 hides the value; v3 accepts a vague expression and checks "
              "any stated duration."))

    # 3 self inner changes (appearance + personality + sanity)
    ch = [{"id": "ch_a1", "text": "外袍被雨浸透", "supersedes": []}]
    ph = [{"id": "ch_p1", "text": "话少了许多", "supersedes": []}]
    st3 = with_state(char_pa={"sanity": 14,
                              "appearanceChanges": copy.deepcopy(ch),
                              "personalityChanges": copy.deepcopy(ph)})
    cases.append(case(
        "rb-inner-change", "外貌 + 个性 + 理智",
        point({"char_pa": {"entityId": "char_pa", "positionSet": None,
                           "appearanceChanges": copy.deepcopy(ch),
                           "personalityChanges": copy.deepcopy(ph),
                           "subtasksAdded": [], "tasksAchieved": [],
                           "sanitySet": 14}}, st3),
        notes="Three visible self facts, no position change."))

    # 4 two different actors move to the same place
    st4 = with_state(
        char_pa={"position": {"containerId": "loc_2", "slotId": None,
                              "relativeTo": None}},
        char_pb={"position": {"containerId": "loc_2", "slotId": None,
                              "relativeTo": None}})
    cases.append(case(
        "rb-two-actors-move", "两人同地移动（他人动作可见）",
        point({"char_pa": moved("char_pa", "loc_2"),
               "char_pb": moved("char_pb", "loc_2")}, st4),
        options={"visibleOtherActions": True},
        notes="The other actor's move is a may fact; select arm includes it."))

    # 5 two same-name actors (G4)
    st5 = add_character(copy.deepcopy(STATE), "char_pc", "管线乙")
    st5["characters"]["char_pb"]["tasks"]["task_3"]["goal"] = "合力抬钟"
    st5["characters"]["char_pb"]["tasks"]["task_3"]["status"] = "achieved"
    st5["characters"]["char_pa"]["position"] = {"containerId": "loc_2",
                                               "slotId": None,
                                               "relativeTo": None}
    st5["characters"]["char_pb"]["position"] = {"containerId": "loc_2",
                                               "slotId": None,
                                               "relativeTo": None}
    st5["characters"]["char_pc"]["position"] = {"containerId": "loc_2",
                                               "slotId": None,
                                               "relativeTo": None}
    # the before point must contain char_pc too, otherwise its move has no
    # resolvable origin and N1 stops (this was caught by the dry run)
    before5_state = copy.deepcopy(st5)
    for eid in ("char_pa", "char_pb", "char_pc"):
        before5_state["characters"][eid]["position"] = {
            "containerId": "loc_1", "slotId": None, "relativeTo": None}
    before5 = {**np_.make_point(1, {}, None, state=before5_state),
               "pointId": "pt-1", "version": 1}
    cases.append(case(
        "rb-same-name", "两个同名角色同时移动（G4）",
        point({"char_pa": moved("char_pa", "loc_2"),
               "char_pb": moved("char_pb", "loc_2"),
               "char_pc": moved("char_pc", "loc_2")}, st5),
        before=before5, options={"visibleOtherActions": True},
        notes="char_pb and char_pc share the name 管线乙; G4 is data-triggered "
              "and needs one mention per actor."))

    # 6 moved + new subtask (no template frame for subtask)
    st6 = with_state(char_pa={
        "position": {"containerId": "loc_2", "slotId": None,
                     "relativeTo": None}})
    cases.append(case(
        "rb-subtask", "移动 + 新小任务",
        point({"char_pa": {**moved("char_pa", "loc_2"),
                           "subtasksAdded": [{"id": "task_9",
                                              "ownerId": "char_pa",
                                              "parentTaskId": "task_1",
                                              "goal": "找梯子",
                                              "status": "pending"}]}}, st6),
        notes="The program template has no subtask frame, so a rejection here "
              "cannot fall back to a template."))

    # 7 sanity + personality only
    ph2 = [{"id": "ch_p2", "text": "对雾天格外警觉", "supersedes": []}]
    st7 = with_state(char_pa={"sanity": 7,
                              "personalityChanges": copy.deepcopy(ph2)})
    cases.append(case(
        "rb-sanity-only", "理智下降 + 个性变化",
        point({"char_pa": {"entityId": "char_pa", "positionSet": None,
                           "appearanceChanges": [],
                           "personalityChanges": copy.deepcopy(ph2),
                           "subtasksAdded": [], "tasksAchieved": [],
                           "sanitySet": 7}}, st7),
        notes="No position or task fact."))

    # 8 pure time advance (no deltas)
    cases.append(case(
        "rb-time-only", "纯时间推进",
        point({}, None, {"boundary": "elapsed",
                         "duration": {"amount": 8, "unit": "minute"}}),
        notes="No entity delta: N1 yields no_change + time."))

    # 9 two different actors, one shared goal (different names)
    st9 = with_state(
        char_pa={"tasks": {**copy.deepcopy(
            STATE["characters"]["char_pa"]["tasks"]),
            "task_2": {**copy.deepcopy(
                STATE["characters"]["char_pa"]["tasks"]["task_2"]),
                "goal": "合力抬钟", "status": "achieved",
                "resultText": "合力把钟抬离了地面"}}},
        char_pb={"tasks": {**copy.deepcopy(
            STATE["characters"]["char_pb"]["tasks"]),
            "task_3": {**copy.deepcopy(
                STATE["characters"]["char_pb"]["tasks"]["task_3"]),
                "goal": "合力抬钟", "status": "achieved",
                "resultText": "抬钟时肩膀抵住了钟沿"}}})
    cases.append(case(
        "rb-conflict-two-actors", "双人同目标（不同名）",
        point({"char_pa": {"entityId": "char_pa", "positionSet": None,
                           "appearanceChanges": [], "personalityChanges": [],
                           "subtasksAdded": [], "tasksAchieved": ["task_2"],
                           "sanitySet": None},
               "char_pb": {"entityId": "char_pb", "positionSet": None,
                           "appearanceChanges": [], "personalityChanges": [],
                           "subtasksAdded": [], "tasksAchieved": ["task_3"],
                           "sanitySet": None}}, st9),
        options={"visibleOtherActions": True}, narrative_outcome=True,
        notes="plan_v3 merges both facts into one group (same goal/place); "
              "both result texts must be carried."))

    # 10 own move + another actor's appearance change (may)
    app = [{"id": "ch_b1", "text": "蓑衣上全是盐霜", "supersedes": []}]
    st10 = with_state(
        char_pa={"position": {"containerId": "loc_2", "slotId": None,
                              "relativeTo": None}},
        char_pb={"appearanceChanges": copy.deepcopy(app)})
    cases.append(case(
        "rb-move-other-appearance", "自己移动 + 他人外貌变化（可见）",
        point({"char_pa": moved("char_pa", "loc_2"),
               "char_pb": {"entityId": "char_pb", "positionSet": None,
                           "appearanceChanges": copy.deepcopy(app),
                           "personalityChanges": [], "subtasksAdded": [],
                           "tasksAchieved": [], "sanitySet": None}}, st10),
        options={"visibleOtherActions": True},
        notes="The other actor stays at 管线镇 while the viewpoint moves to "
              "钟楼, so the appearance change should be invisible; this case "
              "checks that selection does not quietly include it."))
    return cases


def dry_run(case):
    """Program chain only; returns the facts/selection/plan and the packed
    input. Any stop is a registration failure."""
    point_ = case["point"]
    state = point_["state"]
    resolved = n2p.resolve_perspective(
        state, case["perspective"].get("entityId"),
        case["perspective"].get("type", "protagonist"))
    if resolved["problems"]:
        return {"status": "incomplete", "reason": "perspective",
                "problems": resolved["problems"]}
    persp = resolved["perspective"]
    n1 = np_.extract_facts(point_, case["before"],
                           narrative_outcome=case["narrativeOutcome"])
    blocking = [d for d in n1["diagnostics"]
                if d["code"] in np_.INCOMPLETE_DIAGNOSTIC_CODES]
    if blocking:
        return {"status": "incomplete", "reason": "n1", "blocking": blocking}
    tasks = None
    if persp.get("entityId"):
        tasks = (state.get("characters") or {}).get(
            persp["entityId"], {}).get("tasks")
    sel = n2p.classify_facts(n1["facts"], persp, subject_tasks=tasks,
                             may_policy=case["options"]["mayPolicy"],
                             visible_other_actions=case["options"][
                                 "visibleOtherActions"])
    if sel["status"] != "ok":
        return {"status": "incomplete", "reason": "n2", "stops": sel["stops"]}
    ids = sel["selectedFactIds"]
    if not ids:
        return {"status": "stopped-at-selection", "reason": "empty"}
    selected = [f for f in n1["facts"] if f["factId"] in set(ids)]
    names = {f["entityId"]: f["name"] for f in selected if f.get("entityId")}
    hints = case.get("genderHints") or {}
    plan = n3.plan_v3(selected, names, hints, cross_group_guard=True)
    if "refusal" in plan:
        return {"status": "stopped-at-organization",
                "reason": "plan-refusal", "plan": plan}
    problems = n3.check_plan_v3(plan, selected, names, hints,
                                cross_group_guard=True)
    if problems:
        return {"status": "stopped-at-organization", "reason": "invariants",
                "problems": problems}
    scene = build_scene_context(state, persp, selected,
                                environment=case.get("environment"))
    if scene.get("status") != "ok":
        return {"status": "stopped-at-scene", "reason": scene.get("reason")}
    packed = pack_narrative_input(
        {"facts": selected, "perspective": persp,
         "sceneState": scene["sceneContext"]["sceneState"],
         "characterContext": scene["sceneContext"]["characterContext"]},
        plan, scene["worldView"], selected_fact_ids=ids)
    if packed.get("status") != "ok":
        return {"status": "stopped-at-input", "reason": packed.get("code")}
    return {"status": "ready-for-model", "perspective": persp,
            "n1": {"facts": n1["facts"], "diagnostics": n1["diagnostics"]},
            "selection": {"summary": sel["summary"], "ids": ids,
                          "decisions": sel["decisions"]},
            "plan": plan, "input": packed["input"],
            "inputChars": len(packed["input"])}


def sha(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    cases = build_cases()
    if len(cases) > 10:
        raise SystemExit(f"batch limit is 10, got {len(cases)}")
    dry, failures = {}, []
    for c in cases:
        got = dry_run(c)
        dry[c["caseId"]] = {k: got.get(k) for k in
                            ("status", "reason", "problems", "blocking",
                             "input", "inputChars", "perspective",
                             "n1", "selection", "plan")}
        if got["status"] != "ready-for-model":
            failures.append((c["caseId"], got["status"], got.get("reason")))
    if failures:
        for f in failures:
            print("NOT READY:", f)
        return 1
    CASES_OUT.write_text(json.dumps(
        {"version": "real-batch-v1-cases", "cases": cases,
         "dryRun": dry}, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8", newline="\n")

    # model identity is read from the local ollama tag at registration time
    import requests
    tags = requests.get("http://127.0.0.1:11434/api/tags", timeout=10).json()
    tag = next(m for m in tags["models"] if m["name"] == "qwen2.5:7b")
    reg = {
        "version": "real-batch-v1",
        "batchId": "real-batch-2026-11-08-v1",
        "registeredAt": "2026-11-08",
        "purpose": "first real-model offline batch for the C7 composition "
                   "chain: program N1/N2 rule/N3/N4.0 + a REAL N4 sentence "
                   "model + the adjudicated N5 v3 hard gates, then D4 labels "
                   "and an N6 semantic review",
        "sampleCount": len(cases),
        "sampleIds": [c["caseId"] for c in cases],
        "model": {
            "name": tag["name"],
            "digest": tag["digest"],
            "parameterSize": tag["details"].get("parameter_size"),
            "quantization": tag["details"].get("quantization_level"),
            "family": tag["details"].get("family"),
            "runtime": "ollama",
            "runtimeVersion": requests.get(
                "http://127.0.0.1:11434/api/version", timeout=10).json()[
                "version"],
            "endpoint": "http://127.0.0.1:11434/api/generate",
            "transport": "local HTTP, no external network",
            "device": "local machine (ollama reports no GPU flags to this "
                      "client); recorded as-is, not asserted",
        },
        "decode": {
            "temperature": 0,
            "seed": 42,
            "num_predict": 128,
            "top_p": 1.0,
            "top_k": 40,
            "repeat_penalty": 1.0,
            "stop": [],
            "stream": False,
            "system": None,
            "templateNote": "ollama applies the model's chat template to the "
                            "prompt; the prompt is the N4.0 structured record "
                            "followed by 正文：",
        },
        "selectionAndOrganization": {
            "selection": "program N2 rule (perspective rule), mayPolicy=select",
            "organization": "program plan_v3 + check_plan_v3",
            "input": "program N4.0 pack_narrative_input",
            "judge": "judge_v3 (n5-v3) hard gates only",
        },
        "retryPolicy": {
            "maxSentenceAttempts": 2,
            "feedback": "the previous attempt's hard-gate problems are "
                        "appended to the retry request (recorded)",
            "fallback": "program template when the kinds have a frame; the "
                        "case status stays a failure",
        },
        "acceptance": {
            "mechanism": [
                "all 10 samples produce a complete record: request, response, "
                "finish reason, timing, retry/fallback decision",
                "no unhandled exception; every call has an explicit status",
                "requests and responses are archived verbatim",
            ],
            "quality": [
                "n5-pass means hard gates passed ONLY; it is not a quality "
                "verdict",
                "quality comes from N6: pass / fail / undetermined, reviewed "
                "per sample against the committed facts",
                "D4 labels every produced text: count=null when unchecked",
            ],
            "tripwire": [
                "if >=3/10 samples fail the hard gates, or >=2 calls fail at "
                "the port/timeout level, stop and fix the mechanism before any "
                "further batch",
                "no decision from this batch may be reported as model quality "
                "acceptance",
            ],
        },
        "n6Rubric": {
            "A_facts": "every selected fact is stated without contradiction "
                       "(subject, action, direction, value)",
            "B_additions": "no new named entity/place/item, no invented event, "
                           "no task-goal leak",
            "C_pov": "no other character's inner state narrated",
            "D_completeness": "text ends as a complete sentence and reads as "
                              "one coherent passage",
            "verdict": "pass only when A-D all hold; unreadable -> "
                       "undetermined; anything else -> fail",
        },
        "hashes": {
            "cases": sha(CASES_OUT),
            "judge": sha(HERE / "judge_v3.py"),
            "compose": sha(HERE / "real_batch.py"),
            "chain": {
                "narration_pipeline.py": sha(WC / "narration_pipeline.py"),
                "n2_perspective.py": sha(WC / "n2_perspective.py"),
                "n3_organize.py": sha(WC / "n3_organize.py"),
                "packer.py": sha(WC / "n4_input_renderer" / "packer.py"),
                "scene_context.py": sha(WC / "n4_input_renderer" /
                                        "scene_context.py"),
            },
        },
    }
    REG_OUT.write_text(json.dumps(reg, ensure_ascii=False, indent=1) + "\n",
                       encoding="utf-8", newline="\n")
    print(f"registered {len(cases)} samples -> {REG_OUT}")
    for cid, d in dry.items():
        print(f"  {cid:26s} facts={len(d['n1']['facts'])} "
              f"selected={len(d['selection']['ids'])} "
              f"groups={len(d['plan']['sentences'])} "
              f"inputChars={d['inputChars']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
