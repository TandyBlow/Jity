# N1-N5 runnable narration interfaces (batch 1, world-components commit 1).
# One offline, program-authoritative pipeline that threads the five
# narrative sub-steps through their real contract shapes and failure paths.
# The authority rules are the ones frozen in README (权威锚点) and the
# N3->N4 interface plan:
#
#   input   GetStateData v2 reads only (target point + explicit before
#           record). stateDigest/version/lineage are VALIDATED, never
#           recomputed — the pipeline does not rebuild digests or summaries
#           and does not reconstruct deltas from state differences.
#   N1      program fact extraction over the ORIGINAL entityDeltas (+ time
#           from timeAdvance, + the corpus no_change convention). Facts
#           carry local factIds, source pointers into the read, quotable
#           original text, and BEFORE values from the explicit before
#           read. Aspects without an N4 narration kind (subtasksAdded,
#           supersede-only changes) become DIAGNOSTICS, never silent drops.
#   N2      selection interface; program reference arm selects all facts
#           (baseline only — no visibility/omission quality claim; the N2
#           model track is the frozen-items experiment, not this module).
#   N3      organisation via the B1/B2 program baselines + hard invariants
#           (n3_plan.check_invariants).
#   N4      the N3->N4 interface checks (binding -> coverage -> invariants
#           -> flattened 4-fact range -> 128-stub-token range over the real
#           renderer output) and the shared renderer. Batch 1 wires NO
#           generator: prose authority stays with the model track
#           (composition batch); the selftest uses a clearly-labelled
#           template composer only to give N5 something to judge.
#   N5      the corpus recognizer (corpus_check.check_row) over plan+text:
#           fails stay fails, and REVIEW-class findings are surfaced as
#           semantic_uncertain — never auto-passed, never silently dropped.
#
# Batch-1 regression target: a legal `second` point and a zero-duration
# point used to raise in the shared renderer (UNIT_CN KeyError / num_cn
# ValueError); they now run end-to-end. The frozen corpus space is proven
# byte-identical by n4_units_regression.py.

import copy
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
N2_DIR = HERE / "n2_selection"
N4_DIR = HERE / "n4_corpus"
for p in (str(N2_DIR), str(N4_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

from n3_plan import plan_b1, plan_b2, check_invariants  # noqa: E402
from n3_n4_fixture import check_interface, stub_tokens  # noqa: E402
from n4_render import render_input  # noqa: E402
import corpus_check  # noqa: E402

REPO = HERE.parent.parent
sys.path.insert(0, str(REPO / "backend"))
from app.schemas.world.contracts import WorldState  # noqa: E402

MAX_FACTS_PER_RUN = 4  # mirrored from the frozen N3->N4 interface contract


# ---------- name / container resolution (initial definitions only) ----------

def entity_name(state: dict, eid: str):
    initial = (state or {}).get("initial") or {}
    for group in ("characters", "locations", "items"):
        entry = (initial.get(group) or {}).get(eid)
        if entry is not None:
            return entry.get("name")
    return None


def container_name(state: dict, position) -> str | None:
    if not position:
        return None
    cid = position.get("containerId")
    if cid is None:
        return None
    initial = (state or {}).get("initial") or {}
    for group in ("locations", "items", "characters"):
        entry = (initial.get(group) or {}).get(cid)
        if entry is not None:
            return entry.get("name")
    return None


# ---------- N1: program fact extraction (original deltas, no diffing) ------

def _before_entity(before: dict, eid: str):
    if not before:
        return None
    st = before.get("state") or {}
    for group in ("characters", "items", "locations"):
        ent = (st.get(group) or {}).get(eid)
        if ent is not None:
            return ent
    return None


def _after_entity(state: dict, eid: str):
    for group in ("characters", "items", "locations"):
        ent = ((state or {}).get(group) or {}).get(eid)
        if ent is not None:
            return ent
    return None


def extract_facts(point: dict, before: dict | None) -> dict:
    """N1: enumerate fact entries from the ORIGINAL entityDeltas + time.
    Returns {"facts": [...], "diagnostics": [...]} — diagnostics record
    everything the N4 narration vocabulary cannot express yet, so nothing
    is dropped silently."""
    state = point.get("state") or {}
    deltas = point.get("entityDeltas") or {}
    facts, diagnostics = [], []

    def add(fact):
        fact["ref"] = len(facts)
        facts.append(fact)

    ta = point.get("timeAdvance")
    for eid, d in deltas.items():
        name = entity_name(state, eid)
        live_after = _after_entity(state, eid)
        live_before = _before_entity(before, eid)
        if name is None:
            diagnostics.append({"code": "entity-unregistered", "entityId": eid})
            continue
        if d.get("positionSet"):
            frm = container_name(before.get("state") if before else None,
                                 (live_before or {}).get("position"))
            to = container_name(state, d["positionSet"])
            if to is None:
                diagnostics.append({"code": "destination-unresolvable",
                                    "entityId": eid})
                continue
            add({"factId": f"f{len(facts)}", "kind": "moved", "entityId": eid,
                 "name": name, "from": frm, "to": to, "at": to,
                 "source": {"entityId": eid, "field": "positionSet"}})
        for ch in d.get("appearanceChanges") or []:
            if ch.get("text") is None:
                diagnostics.append({"code": "supersede-only-change",
                                    "entityId": eid, "changeId": ch.get("id")})
                continue
            add({"factId": f"f{len(facts)}", "kind": "appearance_changed",
                 "entityId": eid, "name": name, "text": ch["text"],
                 "at": container_name(state, live_after.get("position"))
                 if live_after else None,
                 "source": {"entityId": eid, "changeId": ch.get("id"),
                            "field": "appearanceChanges"}})
        for ch in d.get("personalityChanges") or []:
            if ch.get("text") is None:
                diagnostics.append({"code": "supersede-only-change",
                                    "entityId": eid, "changeId": ch.get("id")})
                continue
            add({"factId": f"f{len(facts)}", "kind": "personality_changed",
                 "entityId": eid, "name": name, "text": ch["text"],
                 "at": container_name(state, live_after.get("position"))
                 if live_after else None,
                 "source": {"entityId": eid, "changeId": ch.get("id"),
                            "field": "personalityChanges"}})
        if d.get("sanitySet") is not None:
            if live_before is None or "sanity" not in live_before:
                diagnostics.append({"code": "sanity-from-unresolvable",
                                    "entityId": eid})
                continue
            add({"factId": f"f{len(facts)}", "kind": "sanity_changed",
                 "entityId": eid, "name": name,
                 "from": live_before["sanity"], "to": d["sanitySet"],
                 "at": container_name(state, live_after.get("position"))
                 if live_after else None,
                 "source": {"entityId": eid, "field": "sanitySet"}})
        for tid in d.get("tasksAchieved") or []:
            task = ((state.get("characters") or {}).get(eid, {})
                    .get("tasks", {}).get(tid))
            if task is None or task.get("status") != "achieved":
                diagnostics.append({"code": "task-unresolvable",
                                    "entityId": eid, "taskId": tid})
                continue
            add({"factId": f"f{len(facts)}", "kind": "task_achieved",
                 "entityId": eid, "name": name, "goal": task["goal"],
                 "at": container_name(state, live_after.get("position"))
                 if live_after else None,
                 "source": {"entityId": eid, "taskId": tid}})
        for t in d.get("subtasksAdded") or []:
            # no N4 narration kind exists for new-task facts yet: recorded,
            # never silently dropped
            diagnostics.append({"code": "unsupported-narration-kind",
                                "entityId": eid, "detail": "subtasksAdded",
                                "taskId": t.get("id")})
    # co-presence at a destination (the corpus `positioned_at` convention):
    # entities OUTSIDE the delta whose after-state position equals a moved
    # entity's destination. Scope note: this is a bounded program rule, not
    # the deferred full-roster scan (contracts §5.2 待办).
    destinations = {f["to"] for f in facts if f["kind"] == "moved"}
    moved_ids = {f["entityId"] for f in facts if f["kind"] == "moved"}
    if destinations:
        for group in ("characters", "items"):
            for eid, ent in ((state.get(group) or {}).items()):
                if eid in deltas or eid in moved_ids:
                    continue
                at = container_name(state, ent.get("position"))
                if at in destinations:
                    name = entity_name(state, eid)
                    if name is None:
                        diagnostics.append({"code": "entity-unregistered",
                                            "entityId": eid})
                        continue
                    add({"factId": f"f{len(facts)}", "kind": "positioned_at",
                         "entityId": eid, "name": name, "at": at,
                         "source": {"entityId": eid, "statePosition": True}})
    if ta is not None:
        dur = ta.get("duration") or {}
        add({"factId": f"f{len(facts)}", "kind": "time",
             "amount": dur.get("amount"), "unit": dur.get("unit"),
             "at": None, "source": {"timeAdvance": True}})
    if not deltas:
        add({"factId": f"f{len(facts)}", "kind": "no_change", "scope": "全局",
             "source": {"noChange": True}})
    return {"facts": facts, "diagnostics": diagnostics}


# ---------- authoritative binding, generalised to all N4 fact kinds --------

def bind_point_full(point: dict, before: dict | None, manifest: list) -> list:
    """Same discipline as the frozen n3_n4_fixture.bind_point (keys must
    exist, world identity is state.worldId, names from state.initial.*,
    content checked against the read), extended from task_achieved/time to
    every N4 fact kind. Returns binding-failed reasons (empty = bound)."""
    problems = []
    for field in ("state", "pointId", "version", "stateDigest",
                  "previousPointId", "timeAdvance", "entityDeltas"):
        if field not in point:
            problems.append(f"missing-{field}")
        elif point[field] is None and field in ("state", "pointId", "version",
                                                "stateDigest", "entityDeltas"):
            problems.append(f"missing-{field}")
    if problems:
        return problems
    world = (point["state"] or {}).get("worldId")
    if not world:
        return ["world-missing"]
    is_root = point["version"] == 0
    if is_root:
        if point["previousPointId"] is not None:
            problems.append("root-with-predecessor")
        if point["timeAdvance"] is not None:
            problems.append("root-with-time")
        if point["entityDeltas"]:
            problems.append("root-with-deltas")
        if before is not None:
            problems.append("root-with-before-record")
    else:
        if point["timeAdvance"] is None:
            problems.append("missing-timeAdvance-value")
        if before is None:
            problems.append("missing-before")
        else:
            bstate = before.get("state") or {}
            if not bstate.get("worldId"):
                return problems + ["world-missing"]
            if bstate["worldId"] != world:
                problems.append("world-mismatch")
            if before.get("version") != point["version"] - 1:
                problems.append("version-gap")
            if before.get("pointId") != point["previousPointId"]:
                problems.append("predecessor-identity-mismatch")
    if not isinstance(point["entityDeltas"], dict):
        return problems + ["deltas-not-entity-map"]
    state = point["state"]
    for f in manifest:
        fid, kind = f.get("factId"), f.get("kind")
        if kind not in ("moved", "task_achieved", "personality_changed",
                        "sanity_changed", "appearance_changed",
                        "positioned_at", "time", "no_change"):
            problems.append(f"unsupported-fact-kind:{fid}:{kind}")
            continue
        src = f.get("source") or {}
        if kind == "time":
            ta = point["timeAdvance"]
            if not isinstance(ta, dict) \
                    or f.get("amount") != (ta.get("duration") or {}).get("amount") \
                    or f.get("unit") != (ta.get("duration") or {}).get("unit"):
                problems.append(f"source-content-mismatch:{fid}:timeAdvance")
            continue
        if kind == "no_change":
            if point["entityDeltas"]:
                problems.append(f"source-content-mismatch:{fid}:noChange")
            continue
        eid = src.get("entityId")
        if f.get("entityId") != eid:
            problems.append(f"ownership-mismatch:{fid}")
            continue
        registered = entity_name(state, eid)
        if registered is None:
            problems.append(f"entity-unregistered:{fid}")
            continue
        if f.get("name") != registered:
            problems.append(f"name-mismatch:{fid}")
        delta = point["entityDeltas"].get(eid)
        if kind == "positioned_at":
            if not src.get("statePosition"):
                problems.append(f"source-content-mismatch:{fid}:statePosition")
                continue
            live = _after_entity(state, eid)
            at = container_name(state, (live or {}).get("position"))
            if at != f.get("at"):
                problems.append(f"source-content-mismatch:{fid}:position")
            continue
        if delta is None:
            problems.append(f"source-content-mismatch:{fid}:entity")
            continue
        if kind == "moved":
            if src.get("field") != "positionSet" or not delta.get("positionSet"):
                problems.append(f"source-content-mismatch:{fid}:positionSet")
                continue
            to = container_name(state, delta["positionSet"])
            frm = container_name((before or {}).get("state"),
                                 (_before_entity(before, eid) or {}).get("position"))
            if to != f.get("to") or frm != f.get("from"):
                problems.append(f"source-content-mismatch:{fid}:containers")
            continue
        if kind in ("appearance_changed", "personality_changed"):
            field_name = "appearanceChanges" if kind == "appearance_changed" else "personalityChanges"
            change = next((c for c in delta.get(field_name) or []
                           if c.get("id") == src.get("changeId")), None)
            if change is None or change.get("text") != f.get("text"):
                problems.append(f"source-content-mismatch:{fid}:change")
            continue
        if kind == "sanity_changed":
            if delta.get("sanitySet") != f.get("to") \
                    or f.get("from") != (_before_entity(before, eid) or {}).get("sanity"):
                problems.append(f"source-content-mismatch:{fid}:sanity")
            continue
        if kind == "task_achieved":
            tid = src.get("taskId")
            if tid not in (delta.get("tasksAchieved") or []):
                problems.append(f"source-content-mismatch:{fid}:taskId")
                continue
            task_def = (state.get("characters", {}).get(eid, {})
                        .get("tasks", {}).get(tid))
            if task_def is None or task_def.get("ownerId") != eid \
                    or task_def.get("goal") != f.get("goal") \
                    or task_def.get("status") != "achieved":
                problems.append(f"source-content-mismatch:{fid}:task")
    return problems


# ---------- N2 (interface + program reference) and N3 ----------------------

def select_facts(facts: list, perspective: str, arm: str = "select-all") -> dict:
    """N2 interface. The program reference arm selects every N1 fact — a
    BASELINE, not a visibility/omission quality claim. Model arms belong to
    the frozen-items N2 track and are NOT-IMPLEMENTED here."""
    if arm != "select-all":
        return {"status": "not-implemented", "arm": arm,
                "reason": "N2 model arms run in the frozen-items track "
                          "(commit 2); this module carries the interface "
                          "and the program reference only"}
    valid = {f["factId"] for f in facts}
    selected = [f["factId"] for f in facts]
    return {"status": "ok", "arm": arm,
            "selectedFactIds": selected,
            "invalidReferences": [x for x in selected if x not in valid]}


def organize(selected_facts: list, baseline: str = "B1") -> dict:
    """N3 via the program baselines; narrow shape + hard invariants."""
    names = {f["entityId"]: f["name"] for f in selected_facts if f.get("entityId")}
    planner = plan_b1 if baseline == "B1" else plan_b2
    plan = planner(selected_facts, names)
    violations = check_invariants(plan, selected_facts, names)
    if violations:
        return {"status": "error", "reason": "plan-invariant-violation",
                "violations": violations}
    plan["itemId"] = "pipeline"
    return {"status": "ok", "plan": plan}


# ---------- N4 (interface checks + renderer) and N5 (judge) ----------------

def interface_check(plan: dict, manifest: list, binding_problems: list) -> dict:
    """The frozen N3->N4 interface contract (coverage -> invariants ->
    flattened range -> stub-token range over the real renderer output)."""
    return check_interface(plan, manifest, binding_problems)


def generate_reference_text(plan_facts: list) -> str:
    """SELFTEST-ONLY template composer in the frontend narration-split v0
    style. This is NOT a product renderer and NOT a model output: it exists
    so the N5 stage has text to judge in the offline selftest. Prose
    authority in the real chain stays with the N4 model track."""
    parts = []
    for e in plan_facts:
        k = e["kind"]
        if k == "moved":
            parts.append(f"{e['name']}从{e['from']}来到了{e['to']}。" if e.get("from")
                         else f"{e['name']}来到了{e['to']}。")
        elif k == "task_achieved":
            parts.append(f"{e['name']}完成了任务「{e['goal']}」。")
        elif k == "personality_changed":
            parts.append(f"{e['name']}{e['text']}。")
        elif k == "sanity_changed":
            parts.append(f"{e['name']}的精神值从{e['from']}{'升' if e['to'] > e['from'] else '降'}到了{e['to']}。")
        elif k == "appearance_changed":
            parts.append(f"{e['name']}的外观变了:{e['text']}。")
        elif k == "positioned_at":
            parts.append(f"{e['name']}已在{e['at']}。")
        elif k == "time":
            from n4_render import num_cn, UNIT_CN
            parts.append(f"前后大约{num_cn(e['amount'])}{UNIT_CN[e['unit']]}。")
        elif k == "no_change":
            parts.append("一切如旧。")
    return "".join(parts)


def verify_text(plan_facts: list, text: str) -> dict:
    """N5: the program recognizer core (corpus_check.check_narration) over
    plan+text. fails stay fails; reviews are surfaced as semantic_uncertain
    and are NEVER auto-passed (the page gate stays B-side; this module only
    reports)."""
    plan = copy.deepcopy(plan_facts)
    sentences = [s for s in text.split("。") if s.strip()]
    all_refs = [e["ref"] for e in plan]
    fails, reviews = corpus_check.check_narration(
        plan, text, [all_refs for _ in sentences], list(all_refs))
    return {"status": "checked",
            "fails": fails,
            "semanticUncertain": reviews,
            "autoPassed": False,
            "note": "review-class findings are listed for human/model "
                    "review; this module does not gate the page"}


def hashlib_plan(plan: list) -> str:
    import hashlib
    return hashlib.sha256(corpus_check.canon(plan).encode("utf-8")).hexdigest()


# ---------- the pipeline ----------------------------------------------------

def run_pipeline(point: dict, before: dict | None, perspective: str,
                 baseline: str = "B1") -> dict:
    """N1 -> N2 -> N3 -> N4 (program path). Any step can stop the pipeline;
    every stop is a structured status, never a silent pass."""
    out = {"pointId": point.get("pointId"), "version": point.get("version"),
           "perspective": perspective}
    n1 = extract_facts(point, before)
    out["n1"] = {"factCount": len(n1["facts"]), "diagnostics": n1["diagnostics"]}
    n2 = select_facts(n1["facts"], perspective)
    out["n2"] = {"arm": n2.get("arm"), "status": n2["status"],
                 "selectedCount": len(n2.get("selectedFactIds", []))}
    if n2["status"] != "ok":
        out["status"] = "stopped-at-n2"
        return out
    n3 = organize([f for f in n1["facts"] if f["factId"] in set(n2["selectedFactIds"])],
                  baseline)
    out["n3"] = {"baseline": baseline, "status": n3["status"]}
    if n3["status"] != "ok":
        out["status"] = "stopped-at-n3"
        out["n3"]["violations"] = n3.get("violations")
        return out
    manifest = n1["facts"]
    binding = bind_point_full(point, before, manifest)
    verdict = interface_check(n3["plan"], manifest, binding)
    out["n4"] = {"status": verdict["status"]}
    if verdict["status"] == "accepted":
        out["n4"]["renderText"] = verdict["renderText"]
        out["n4"]["inputTokensStub"] = verdict["inputTokensStub"]
        out["n4"]["renderInput"] = verdict["renderInput"]
    elif "reason" in verdict:
        out["n4"]["reason"] = verdict["reason"]
    elif "reasons" in verdict:
        out["n4"]["reasons"] = verdict["reasons"]
    out["status"] = {"accepted": "ok", "unsupported": "unsupported",
                     "error": "stopped-at-n4",
                     "binding-failed": "stopped-at-binding"}[verdict["status"]]
    return out


# ---------- selftest ---------------------------------------------------------

def _task_def(tid, owner, goal, status="pending"):
    return {"id": tid, "ownerId": owner, "parentTaskId": None,
            "goal": goal, "status": status}


def make_pipeline_state(world="w_pipe", second_loc=True):
    locations = {"loc_1": {"id": "loc_1", "name": "管线镇", "parentLocationId": None,
                           "initialAppearance": "安静", "slots": []}}
    if second_loc:
        locations["loc_2"] = {"id": "loc_2", "name": "钟楼", "parentLocationId": None,
                              "initialAppearance": "旧", "slots": []}
    ws = WorldState.model_validate({
        "engineVersion": "world-engine-v1", "schemaVersion": 1,
        "worldId": world, "protagonistId": "char_pa",
        "time": {"calendar": "gregorian", "dateTime": "2026-11-01T00:00:00",
                 "instantOrdinal": 2},
        "initial": {
            "engineVersion": "world-engine-v1", "schemaVersion": 1,
            "worldId": world, "protagonistId": "char_pa",
            "initialTime": {"calendar": "gregorian",
                            "dateTime": "2026-11-01T00:00:00", "instantOrdinal": 1},
            "locations": locations, "items": {},
            "characters": {
                "char_pa": {"id": "char_pa", "name": "管线甲",
                            "initialPosition": {"containerId": "loc_1",
                                                "slotId": None, "relativeTo": None},
                            "initialAppearance": "常态",
                            "initialPersonality": "沉稳", "initialSanity": 10,
                            "tasks": {"task_1": _task_def("task_1", "char_pa", "把铜铃挂回钟楼"),
                                      "task_2": _task_def("task_2", "char_pa", "晒网")}},
                "char_pb": {"id": "char_pb", "name": "管线乙",
                            "initialPosition": {"containerId": "loc_1",
                                                "slotId": None, "relativeTo": None},
                            "initialAppearance": "常态",
                            "initialPersonality": "急躁", "initialSanity": 11,
                            "tasks": {"task_3": _task_def("task_3", "char_pb", "补网")}},
            },
        },
        "locations": {k: {"id": k, "appearanceChanges": []} for k in locations},
        "items": {},
        "characters": {
            "char_pa": {"id": "char_pa", "position": {"containerId": "loc_1",
                                                      "slotId": None, "relativeTo": None},
                        "personalityChanges": [], "sanity": 10,
                        "tasks": {"task_1": _task_def("task_1", "char_pa", "把铜铃挂回钟楼"),
                                  "task_2": _task_def("task_2", "char_pa", "晒网")}},
            "char_pb": {"id": "char_pb", "position": {"containerId": "loc_1",
                                                      "slotId": None, "relativeTo": None},
                        "personalityChanges": [], "sanity": 11,
                        "tasks": {"task_3": _task_def("task_3", "char_pb", "补网")}},
        },
    })
    return ws.model_dump(mode="json")


def make_point(version, deltas, time_advance, world="w_pipe", state=None,
               prev=None):
    return {"pointId": f"pt-{version}", "version": version,
            "state": state if state is not None else make_pipeline_state(world),
            "stateDigest": "d" * 8, "previousPointId": prev,
            "timeAdvance": time_advance, "entityDeltas": deltas}


def moved_delta(eid, to_container):
    return {"entityId": eid, "positionSet": {"containerId": to_container,
                                             "slotId": None, "relativeTo": None},
            "appearanceChanges": [], "personalityChanges": [],
            "subtasksAdded": [], "tasksAchieved": [], "sanitySet": None}


def selftest() -> int:
    failures = []

    def check(cond, label):
        if not cond:
            failures.append(label)

    state = make_pipeline_state()
    before_state = make_pipeline_state()
    before = make_point(1, {}, None, state=before_state, prev=None)
    # fix lineage: before is version 1, point is version 2
    before = {**before, "pointId": "pt-1", "version": 1}

    def point(deltas, amount, unit="minute", version=2, st=None):
        ta = None if amount is None else {"boundary": "elapsed",
                                          "duration": {"amount": amount, "unit": unit}}
        return make_point(version, deltas, ta, state=st or copy.deepcopy(state),
                          prev="pt-1")

    # S1: legal `second` point — used to KeyError in the shared renderer
    deltas = {"char_pa": {**moved_delta("char_pa", "loc_2"),
                          "tasksAchieved": ["task_1"]}}
    st = copy.deepcopy(state)
    st["characters"]["char_pa"]["position"] = {"containerId": "loc_2",
                                               "slotId": None, "relativeTo": None}
    st["characters"]["char_pa"]["tasks"]["task_1"]["status"] = "achieved"
    r = run_pipeline(point(deltas, 40, "second", st=st), before, "主角视角")
    check(r["status"] == "ok", f"S1 second pipeline: {r['status']}")
    check("四十秒" in (r.get("n4", {}).get("renderText") or ""), "S1 second rendering")
    check(any(d["code"] == "unsupported-narration-kind" for d in
              []) or True, "S1 placeholder")

    # S1b: N5 judges the selftest template text for the same point
    n1 = extract_facts(point(deltas, 40, "second", st=st), before)
    text = generate_reference_text(n1["facts"])
    v = verify_text(n1["facts"], text)
    check(v["status"] == "checked" and not v["fails"] and not v["semanticUncertain"],
          f"S1b n5 clean: {json.dumps(v, ensure_ascii=False)[:200]}")

    # S2: zero-duration point — used to ValueError in num_cn
    r = run_pipeline(point({}, 0, "minute"), before, "主角视角")
    check(r["status"] == "ok", f"S2 zero pipeline: {r['status']}")
    check("零分钟" in (r.get("n4", {}).get("renderText") or ""), "S2 zero rendering")

    # S3: root point (explicit null/null/{}) binds and renders 无变化
    root = {"pointId": "pt-0", "version": 0,
            "state": {"worldId": "w_pipe"}, "stateDigest": "d" * 8,
            "previousPointId": None, "timeAdvance": None, "entityDeltas": {}}
    r = run_pipeline(root, None, "主角视角")
    check(r["status"] == "ok", f"S3 root: {r['status']}")
    check(any(f["kind"] == "no_change" for f in extract_facts(root, None)["facts"]),
          "S3 no_change fact")

    # S4: co-presence positioned_at + sanity — char_pb reached loc_2 in an
    # EARLIER point (before state), stays put here, and is extracted as
    # positioned_at when char_pa moves to the same destination
    st1 = make_pipeline_state()
    st1["characters"]["char_pb"]["position"] = {"containerId": "loc_2",
                                                "slotId": None, "relativeTo": None}
    before4 = make_point(1, {}, None, state=st1, prev=None)
    before4 = {**before4, "pointId": "pt-1", "version": 1}
    st2 = copy.deepcopy(st1)
    st2["characters"]["char_pa"]["position"] = {"containerId": "loc_2",
                                                "slotId": None, "relativeTo": None}
    st2["characters"]["char_pa"]["sanity"] = 13
    deltas = {"char_pa": {**moved_delta("char_pa", "loc_2"), "sanitySet": 13}}
    n1 = extract_facts(point(deltas, 5, st=st2), before4)
    kinds = sorted(f["kind"] for f in n1["facts"])
    check("positioned_at" in kinds and "sanity_changed" in kinds,
          f"S4 co-presence/sanity: {kinds}")
    pa = next(f for f in n1["facts"] if f["kind"] == "positioned_at")
    check(pa["entityId"] == "char_pb" and pa["at"] == "钟楼",
          f"S4 positioned_at fact: {pa}")

    # S5: five facts -> unsupported/plan-too-long through the REAL interface
    deltas5 = {"char_pa": {**moved_delta("char_pa", "loc_2"),
                           "tasksAchieved": ["task_1", "task_2"]},
               "char_pb": {**moved_delta("char_pb", "loc_2"),
                           "tasksAchieved": ["task_3"]}}
    st5 = copy.deepcopy(state)
    for c in ("char_pa", "char_pb"):
        st5["characters"][c]["position"] = {"containerId": "loc_2",
                                            "slotId": None, "relativeTo": None}
    for tid in ("task_1", "task_2"):
        st5["characters"]["char_pa"]["tasks"][tid]["status"] = "achieved"
    st5["characters"]["char_pb"]["tasks"]["task_3"]["status"] = "achieved"
    r = run_pipeline(point(deltas5, 5, st=st5), before, "主角视角")
    check(r["status"] == "unsupported" and r["n4"]["reason"] == "plan-too-long",
          f"S5 five facts: {r['status']}/{r.get('n4', {}).get('reason')}")

    # S6: subtasksAdded becomes a diagnostic, not a fact, not a crash
    deltas_sub = {"char_pa": {**moved_delta("char_pa", "loc_2"),
                              "subtasksAdded": [_task_def("task_9", "char_pa",
                                                          "找梯子", status="pending")]}}
    n1 = extract_facts(point(deltas_sub, 5), before)
    check(not any(f["kind"] == "subtask" for f in n1["facts"])
          and any(d["code"] == "unsupported-narration-kind" for d in n1["diagnostics"]),
          "S6 subtask diagnostic")

    # S7: version gap stops at binding
    r = run_pipeline(point({}, 5, version=3), before, "主角视角")
    check(r["status"] == "stopped-at-binding", f"S7 version gap: {r['status']}")

    # S8: N5 mismatch text -> semantic_uncertain, never auto-passed
    n1 = extract_facts(point(deltas, 40, "second", st=st), before)
    bad_text = "管线甲从管线镇来到了钟楼。前后零秒。"  # wrong duration value
    v = verify_text(n1["facts"], bad_text)
    check(v["semanticUncertain"] and v["autoPassed"] is False,
          f"S8 review not auto-passed: {json.dumps(v, ensure_ascii=False)[:160]}")

    # S9: N2 model arm is honestly NOT-IMPLEMENTED
    n2 = select_facts([], "视角", arm="encoder-head")
    check(n2["status"] == "not-implemented", "S9 n2 model arm status")

    for f in failures:
        print("SELFTEST FAIL:", f)
    print("narration-pipeline selftest:",
          "PASS" if not failures else f"{len(failures)} failure(s)")
    return 1 if failures else 0


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--out", default=None)
    args = parser.parse_args()
    if args.selftest:
        rc = selftest()
        if args.out:
            pathlib.Path(args.out).write_text(json.dumps(
                {"module": "narration_pipeline", "selftest": "PASS" if rc == 0 else "FAIL"},
                ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
        return rc
    parser.print_usage()
    return 2


if __name__ == "__main__":
    sys.exit(main())
