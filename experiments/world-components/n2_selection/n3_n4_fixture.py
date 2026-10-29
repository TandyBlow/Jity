# N3->N4 interface fixtures (plan: design/world-engine-reports/components/
# n3-n4-interface-plan.md). NON-MODEL verification of the interface
# constraints only:
#
#   binding      root and non-root points are validated separately, on the
#                REAL GetStateData v2 shape: previousPointId/timeAdvance/
#                entityDeltas keys MUST EXIST (root points carry explicit
#                null/null/{}; an absent key is an incomplete read, not a
#                null). timeAdvance is {boundary, duration:{amount, unit}}.
#                entityDeltas is an entity-keyed map of EntityDelta; task
#                achievement is a TASK ID in tasksAchieved, and BOTH the
#                task text and the entity names are resolved from the
#                BOUND point.state (WorldState: state.worldId,
#                state.characters[eid].tasks[tid] -> goal/status, entity
#                name fields) — no caller-supplied registry exists, so
#                tampering facts and a side table together cannot pass.
#                Source pointers are checked for OWNERSHIP (fact entityId
#                == source entityId), NAME (fact name vs the state
#                registry) and CONTENT (goal/status vs state tasks, time
#                vs duration); unsupported fact kinds are refused. World
#                identity is state.worldId (the real GetStateData layer);
#                a missing worldId stops binding. Missing or mismatched
#                -> binding-failed, never reconstructed from result text.
#   invariants   the N3 hard invariants are a PRECONDITION of acceptance:
#                a plan with a known I2 violation (cross-group reference)
#                stops with error:plan-invariant-violation and produces no
#                render input — coreference not being consumed by N4 does
#                not excuse an invalid plan.
#   range        the per-run N4 input is the FLATTENED fact table; more
#                than 4 facts in total is unsupported (grouping cannot
#                bypass the limit; no splitting fallback exists).
#   tokens       counted over the ACTUAL shared renderer output: the
#                deterministic program render_input() from
#                experiments/world-components/n4_corpus/n4_render.py is
#                imported and its full prompt (header, fact lines, tail) is
#                stub-tokenized. Only the tokenizer is a stub; the rendered
#                bytes are the real shared-render output.
#
# Every verdict embeds the ORIGINAL plan verbatim (deep copy).

import argparse
import copy
import hashlib
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from n3_plan import check_invariants  # noqa: E402

sys.path.insert(0, str(HERE.parent / "n4_corpus"))
from n4_render import render_input as shared_render_input  # noqa: E402

REPO_ROOT = HERE.parent.parent.parent
MAX_FACTS_PER_GROUP = 4
MAX_INPUT_TOKENS = 128


def sha_file(path) -> str:
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def stub_tokens(text: str, n: int = 6) -> list:
    """deterministic stub tokenizer (fixed 6-char chunks). NOT a real
    sentencepiece acceptance."""
    return [text[i:i + n] for i in range(0, len(text), n)]


def make_deltas():
    """EntityDelta-shaped map (contracts.py): tasksAchieved carries TASK
    IDs; the task TEXT lives in the bound state."""
    return {
        "char_pa": {"entityId": "char_pa", "tasksAchieved": ["task_1", "task_2"],
                    "appearanceChanges": [], "personalityChanges": [],
                    "subtasksAdded": [], "positionSet": None, "sanitySet": None},
        "char_pb": {"entityId": "char_pb", "tasksAchieved": ["task_3"],
                    "appearanceChanges": [], "personalityChanges": [],
                    "subtasksAdded": [], "positionSet": None, "sanitySet": None},
    }


def make_state(world="w_probe"):
    """WorldState-shaped projection (contracts.py): worldId lives here;
    character task definitions (id -> goal/status) and entity names are
    resolved from THIS structure at binding time — there is no
    caller-supplied registry."""
    return {
        "worldId": world,
        "protagonistId": "char_pa",
        "locations": {"loc_1": {"entityId": "loc_1", "name": "探针镇"}},
        "items": {},
        "characters": {
            "char_pa": {"entityId": "char_pa", "name": "参商",
                        "tasks": {"task_1": {"id": "task_1", "ownerId": "char_pa",
                                             "goal": "晒网", "status": "achieved"},
                                  "task_2": {"id": "task_2", "ownerId": "char_pa",
                                             "goal": "织网", "status": "achieved"}}},
            "char_pb": {"entityId": "char_pb", "name": "辰星",
                        "tasks": {"task_3": {"id": "task_3", "ownerId": "char_pb",
                                             "goal": "补网", "status": "achieved"}}},
        },
    }


def make_time_advance(minutes=5, unit="minute"):
    """TimeAdvance per contracts.py: boundary + duration{amount, unit}."""
    return {"boundary": "elapsed", "duration": {"amount": minutes, "unit": unit}}


def make_point(version=1, deltas=None, digest="d" * 8, time_advance="default",
               prev_point_id="default", world="w_probe", state=None):
    if deltas is None:
        deltas = make_deltas() if version != 0 else {}
    if time_advance == "default":
        time_advance = None if version == 0 else make_time_advance()
    if prev_point_id == "default":
        prev_point_id = None if version == 0 else f"pt-{version - 1}"
    if state is None:
        state = make_state(world) if version != 0 else {"worldId": world}
    return {"pointId": f"pt-{version}", "version": version,
            "state": state,
            "stateDigest": digest,
            "previousPointId": prev_point_id,
            "timeAdvance": time_advance, "entityDeltas": deltas}


def entity_name(state: dict, eid: str):
    for group in ("characters", "locations", "items"):
        entry = (state or {}).get(group, {}).get(eid)
        if entry is not None:
            return entry.get("name")
    return None


SUPPORTED_FACT_KINDS = {"task_achieved", "time"}


def bind_point(point: dict, before, manifest_facts: list) -> list:
    """authoritative input binding on the real contract shape. Keys must
    EXIST (root: explicit null/null/{}); the world identity is
    state.worldId; task and name resolution read the BOUND point.state.
    Returns binding-failed reasons (empty = bound)."""
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
    # world identity lives in state.worldId (GetStateData v2): missing
    # means the read is incomplete -> stop before anything else
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
        problems.append("deltas-not-entity-map")
        return problems
    state = point["state"]
    for f in manifest_facts:
        fid = f.get("factId")
        if f["kind"] not in SUPPORTED_FACT_KINDS:
            problems.append(f"unsupported-fact-kind:{fid}:{f['kind']}")
            continue
        src_ = f.get("source") or {}
        if f["kind"] == "time":
            ta = point["timeAdvance"]
            if not isinstance(ta, dict) \
                    or f.get("amount") != (ta.get("duration") or {}).get("amount") \
                    or f.get("unit") != (ta.get("duration") or {}).get("unit"):
                problems.append(f"source-content-mismatch:{fid}:timeAdvance")
            continue
        eid = src_.get("entityId")
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
        if delta is None:
            problems.append(f"source-content-mismatch:{fid}:entity")
            continue
        if f["kind"] == "task_achieved":
            tid = src_.get("taskId")
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


def check_interface(plan: dict, manifest_facts: list, binding_problems: list) -> dict:
    """the N3->N4 interface check. Order: binding -> coverage -> N3
    invariants (precondition) -> per-run range -> rendered-token range.
    Returns one verdict dict; the plan is embedded verbatim."""
    out = {"plan": copy.deepcopy(plan)}
    if binding_problems:
        out.update({"status": "binding-failed", "reasons": binding_problems})
        return out
    by_id = {f["factId"]: f for f in manifest_facts}
    seen = []
    for s in plan.get("sentences", []):
        for fid in s.get("factIds", []):
            if fid not in by_id:
                out.update({"status": "error",
                            "reason": "plan-fact-mismatch:unknown",
                            "factId": fid})
                return out
            if fid in seen:
                out.update({"status": "error",
                            "reason": "plan-fact-mismatch:duplicate",
                            "factId": fid})
                return out
            seen.append(fid)
    missing = [f["factId"] for f in manifest_facts if f["factId"] not in seen]
    if missing:
        out.update({"status": "error", "reason": "plan-fact-mismatch:missing",
                    "factIds": missing})
        return out
    # N3 hard invariants are a PRECONDITION: an I2-violating plan must stop
    # here, regardless of coreference not being consumed by N4
    names = {f["entityId"]: f["name"] for f in manifest_facts if f.get("entityId")}
    selected = [by_id[fid] for fid in seen]
    violations = check_invariants({"baseline": "interface", "sentences": plan["sentences"]},
                                  selected, names)
    if violations:
        out.update({"status": "error", "reason": "plan-invariant-violation",
                    "violations": violations})
        return out
    # the actual per-run N4 input is the FLATTENED table: grouping cannot
    # bypass the fact limit
    render_input = [by_id[fid] for s in plan["sentences"] for fid in s["factIds"]]
    if len(render_input) > MAX_FACTS_PER_GROUP:
        out.update({"status": "unsupported", "reason": "plan-too-long",
                    "limits": {"maxFactsPerRun": MAX_FACTS_PER_GROUP,
                               "maxInputTokens": MAX_INPUT_TOKENS},
                    "observed": {"facts": len(render_input)}})
        return out
    text = shared_render_input(render_input)
    n_tokens = len(stub_tokens(text))
    if n_tokens > MAX_INPUT_TOKENS:
        out.update({"status": "unsupported", "reason": "input-too-long",
                    "limits": {"maxFactsPerRun": MAX_FACTS_PER_GROUP,
                               "maxInputTokens": MAX_INPUT_TOKENS},
                    "observed": {"inputTokens": n_tokens}})
        return out
    out.update({"status": "accepted", "renderInput": render_input,
                "renderText": text, "sharedRenderer": "n4_render.render_input",
                "inputTokensStub": n_tokens,
                "limits": {"maxFactsPerRun": MAX_FACTS_PER_GROUP,
                           "maxInputTokens": MAX_INPUT_TOKENS},
                "notes": {"coreferenceConsumed": False,
                          "invariantsVerified": True,
                          "tokenCounter": "deterministic 6-char stub over the "
                                          "REAL shared render_input output; only "
                                          "the tokenizer is a stub"}})
    return out


def task(fid, char, name, goal, task_id):
    return {"factId": fid, "kind": "task_achieved", "entityId": char,
            "name": name, "goal": goal, "at": "探针镇",
            "source": {"entityId": char, "taskId": task_id}}


def time_fact(fid):
    return {"factId": fid, "kind": "time", "amount": 5, "unit": "minute",
            "at": None, "source": {"timeAdvance": True}}


def group(fids, index=0, ref=None):
    refs = [ref] if ref else []
    return {"index": index, "factIds": fids, "coreference": refs}


def fixtures() -> list:
    """(name, description, expected, build). build -> (plan|None, manifest,
    point, before); plan None means a binding-only assertion."""
    root = make_point(version=0)

    def t1():
        m = [task("f1", "char_pa", "参商", "晒网", "task_1")]
        return {"itemId": "fx", "sentences": [group(["f1"])]}, m, make_point(), root

    def t4():
        m = [task("f1", "char_pa", "参商", "晒网", "task_1"),
             task("f2", "char_pa", "参商", "织网", "task_2"),
             task("f3", "char_pb", "辰星", "补网", "task_3"),
             time_fact("f4")]
        plan = {"itemId": "fx", "sentences": [group(["f1", "f2", "f3", "f4"])]}
        return plan, m, make_point(), root

    def t5():
        m = [task("f1", "char_pa", "参商", "晒网", "task_1"),
             task("f2", "char_pa", "参商", "织网", "task_2"),
             task("f3", "char_pb", "辰星", "补网", "task_3"),
             time_fact("f4"),
             task("f5", "char_pa", "参商", "晒网", "task_1")]
        plan = {"itemId": "fx", "sentences": [group([f"f{i}" for i in range(1, 6)])]}
        return plan, m, make_point(), root

    def t52():
        m = [task("f1", "char_pa", "参商", "晒网", "task_1"),
             task("f2", "char_pa", "参商", "织网", "task_2"),
             task("f3", "char_pb", "辰星", "补网", "task_3"),
             time_fact("f4"),
             task("f5", "char_pa", "参商", "晒网", "task_1")]
        plan = {"itemId": "fx", "sentences": [group(["f1", "f2"]), group(["f3", "f4", "f5"])]}
        return plan, m, make_point(), root

    def sized(total_tokens):
        m = [task("f1", "char_pa", "参商", "", "task_1")]
        base = len(shared_render_input(m))
        goal = "网" * (total_tokens * 6 - base)
        m[0]["goal"] = goal
        state = make_state()
        state["characters"]["char_pa"]["tasks"]["task_1"]["goal"] = goal
        return {"itemId": "fx", "sentences": [group(["f1"])]}, m, make_point(state=state), root

    def t128():
        return sized(128)

    def t129():
        return sized(129)

    def missing():
        m = [task("f1", "char_pa", "参商", "晒网", "task_1"),
             task("f2", "char_pa", "参商", "织网", "task_2")]
        return {"itemId": "fx", "sentences": [group(["f1"])]}, m, make_point(), root

    def duplicate():
        m = [task("f1", "char_pa", "参商", "晒网", "task_1")]
        return {"itemId": "fx", "sentences": [group(["f1", "f1"])]}, m, make_point(), root

    def unknown():
        m = [task("f1", "char_pa", "参商", "晒网", "task_1")]
        return {"itemId": "fx", "sentences": [group(["f1", "f9"])]}, m, make_point(), root

    def order():
        m = [task("f1", "char_pa", "参商", "晒网", "task_1"),
             task("f2", "char_pb", "辰星", "补网", "task_3")]
        plan = {"itemId": "fx", "sentences": [group(["f2"], 0), group(["f1"], 1)]}
        return plan, m, make_point(), root

    def time_pred():
        m = [task("f1", "char_pa", "参商", "晒网", "task_1"), time_fact("f2")]
        plan = {"itemId": "fx", "sentences": [group(["f1", "f2"])]}
        return plan, m, make_point(), root

    def same_name():
        m = [task("f1", "char_pa", "同名者", "晒网", "task_1"),
             task("f2", "char_pb", "同名者", "补网", "task_3")]
        state = make_state()
        state["characters"]["char_pa"]["name"] = "同名者"
        state["characters"]["char_pb"]["name"] = "同名者"
        plan = {"itemId": "fx", "sentences": [
            group(["f1"], 0, {"mention": "同名者", "refersTo": "char_pa"}),
            group(["f2"], 1, {"mention": "同名者", "refersTo": "char_pb"})]}
        return plan, m, make_point(state=state), root

    def cross_group():
        m = [task("f1", "char_pa", "参商", "晒网", "task_1"),
             task("f2", "char_pb", "辰星", "补网", "task_3")]
        plan = {"itemId": "fx", "sentences": [
            group(["f1"], 0, {"mention": "辰星", "refersTo": "char_pb"}),
            group(["f2"], 1)]}
        return plan, m, make_point(), root

    def no_before():
        return {"itemId": "fx", "sentences": [group(["f1"])]}, \
            [task("f1", "char_pa", "参商", "晒网", "task_1")], make_point(version=3), None

    def version_gap():
        before = make_point(version=1)
        point = make_point(version=3)
        point["previousPointId"] = before["pointId"]  # isolate the version gap
        return {"itemId": "fx", "sentences": [group(["f1"])]}, \
            [task("f1", "char_pa", "参商", "晒网", "task_1")], point, before

    def no_digest():
        point = make_point(version=2)
        point["stateDigest"] = None
        return {"itemId": "fx", "sentences": [group(["f1"])]}, \
            [task("f1", "char_pa", "参商", "晒网", "task_1")], point, make_point(version=1)

    def pred_identity():
        before = make_point(version=1)
        point = make_point(version=2)
        point["previousPointId"] = "pt-9"  # unrelated id
        return None, [task("f1", "char_pa", "参商", "晒网", "task_1")], point, before

    def root_ok():
        return None, [], make_point(version=0), None

    def root_with_time():
        return None, [], make_point(version=0, time_advance=make_time_advance()), None

    def missing_keys():
        point = make_point(version=2)
        del point["previousPointId"]
        del point["timeAdvance"]
        return None, [task("f1", "char_pa", "参商", "晒网", "task_1")], point, make_point(version=1)

    def ownership():
        m = [{"factId": "f1", "kind": "task_achieved", "entityId": "char_pb",
              "name": "辰星", "goal": "晒网", "at": "探针镇",
              "source": {"entityId": "char_pa", "taskId": "task_1"}}]
        return {"itemId": "fx", "sentences": [group(["f1"])]}, m, make_point(), root

    def source_content():
        m = [task("f1", "char_pa", "参商", "被篡改的目标", "task_1")]
        return {"itemId": "fx", "sentences": [group(["f1"])]}, m, make_point(), root

    def time_content():
        m = [{"factId": "f1", "kind": "time", "amount": 9, "unit": "minute",
              "at": None, "source": {"timeAdvance": True}}]
        return {"itemId": "fx", "sentences": [group(["f1"])]}, m, make_point(), root

    def unsupported_kind():
        m = [{"factId": "f1", "kind": "personality_changed", "entityId": "char_pa",
              "name": "参商", "text": "变得沉默", "at": "探针镇",
              "source": {"entityId": "char_pa"}}]
        return {"itemId": "fx", "sentences": [group(["f1"])]}, m, make_point(), root

    def wrong_name():
        m = [task("f1", "char_pa", "冒名者", "晒网", "task_1")]
        return {"itemId": "fx", "sentences": [group(["f1"])]}, m, make_point(), root

    def world_gap():
        before = make_point(version=1, world="w_other")
        point = make_point(version=2)
        return None, [task("f1", "char_pa", "参商", "晒网", "task_1")], point, before

    def world_missing():
        point = make_point(version=2)
        del point["state"]["worldId"]
        return None, [task("f1", "char_pa", "参商", "晒网", "task_1")], point, make_point(version=1)

    return [
        ("F01", "1 fact in range", "accepted", t1),
        ("F04", "4 facts flattened (upper bound)", "accepted", t4),
        ("F05", "5 facts in one group over limit", "unsupported:plan-too-long", t5),
        ("F52", "3+2 grouping cannot bypass: flattened 5", "unsupported:plan-too-long", t52),
        ("FT128", "128 stub tokens over the REAL shared renderer output", "accepted", t128),
        ("FT129", "129 stub tokens", "unsupported:input-too-long", t129),
        ("FM01", "plan missing a factId", "error:plan-fact-mismatch:missing", missing),
        ("FM02", "plan duplicate factId", "error:plan-fact-mismatch:duplicate", duplicate),
        ("FM03", "plan unknown factId", "error:plan-fact-mismatch:unknown", unknown),
        ("FO01", "order follows plan sentence order", "accepted", order),
        ("FT01", "time after its predecessor passes through", "accepted", time_pred),
        ("FN01", "same name different entities; anchored refs legal", "accepted", same_name),
        ("FX01", "cross-group reference: I2 violation stops acceptance",
         "error:plan-invariant-violation", cross_group),
        ("FB01", "non-root point without before record", "binding-failed:missing-before", no_before),
        ("FB02", "version discontinuity", "binding-failed:version-gap", version_gap),
        ("FB03", "missing stateDigest value", "binding-failed:missing-stateDigest", no_digest),
        ("FBL1", "predecessor identity mismatch", "binding-failed:predecessor-identity-mismatch", pred_identity),
        ("FBR1", "legal root point (explicit null/null/{})", "bound", root_ok),
        ("FBR2", "root point carrying timeAdvance", "binding-failed:root-with-time", root_with_time),
        ("FBM1", "GetStateData keys removed (incomplete read)",
         "binding-failed:missing-previousPointId,missing-timeAdvance", missing_keys),
        ("FOWN1", "fact entity differs from its source entity", "binding-failed:ownership-mismatch:f1", ownership),
        ("FSC1", "goal diverges from the bound state task definition",
         "binding-failed:source-content-mismatch:f1:task", source_content),
        ("FTT1", "time amount diverges from TimeAdvance.duration",
         "binding-failed:source-content-mismatch:f1:timeAdvance", time_content),
        ("FUK1", "unsupported fact kind refused, not silently accepted",
         "binding-failed:unsupported-fact-kind:f1:personality_changed", unsupported_kind),
        ("FNAM1", "fact name diverges from the state entity registry",
         "binding-failed:name-mismatch:f1", wrong_name),
        ("FWLD1", "before.state.worldId differs", "binding-failed:world-mismatch", world_gap),
        ("FWLD2", "state.worldId absent", "binding-failed:world-missing", world_missing),
    ]


def run_suite(out=None) -> int:
    results = {}
    failures = []
    for name, desc, expected, build in fixtures():
        plan, manifest, point, before = build()
        if plan is None:
            problems = bind_point(point, before, manifest)
            got = "bound" if not problems else "binding-failed:" + ",".join(problems)
            ok = got == expected
            results[name] = {"description": desc, "expected": expected, "got": got,
                             "pass": ok, "kind": "binding-only"}
            if not ok:
                failures.append(f"{name}: expected {expected}, got {got}")
            continue
        verdict = check_interface(plan, manifest, bind_point(point, before, manifest))
        tail = (":" + verdict["reason"] if "reason" in verdict
                else ":" + ",".join(verdict["reasons"]) if "reasons" in verdict else "")
        got = verdict["status"] + tail
        ok = got == expected
        if verdict["plan"] != plan:
            ok = False  # plan must be preserved verbatim in every verdict
        if verdict["status"] == "accepted":
            if "coreference" in json.dumps(verdict["renderInput"], ensure_ascii=False):
                ok = False  # coreference is never consumed
            if len(stub_tokens(shared_render_input(verdict["renderInput"]))) \
                    != verdict["inputTokensStub"]:
                ok = False  # token count is over the REAL renderer output
        results[name] = {"description": desc, "expected": expected, "got": got,
                         "pass": ok}
        if not ok:
            failures.append(f"{name}: expected {expected}, got {got}")
    archive = {
        "purpose": "N3->N4 interface fixture verification (non-model)",
        "tokenCounter": "deterministic 6-char stub over the REAL shared "
                        "render_input output (n4_render.py); only the tokenizer is a stub",
        "sourceModel": "WorldState/EntityDelta per contracts.py: task ids in "
                       "tasksAchieved resolved against state.characters[eid].tasks; "
                       "entity names from the bound state; world identity = "
                       "state.worldId; GetStateData keys must exist (root = "
                       "explicit null/null/{})",
        "interfaceConstraints": {"maxFactsPerRun": MAX_FACTS_PER_GROUP,
                                 "maxInputTokens": MAX_INPUT_TOKENS,
                                 "coreferenceConsumed": False,
                                 "invariantsArePrecondition": True,
                                 "unsupportedPreservesPlan": True,
                                 "rangeCheckedOnFlattenedRun": True,
                                 "supportedFactKinds": sorted(SUPPORTED_FACT_KINDS)},
        "results": results,
        "failures": failures,
        "pass": not failures,
    }
    text = json.dumps(archive, ensure_ascii=False, indent=1) + "\n"
    if out:
        pathlib.Path(out).write_text(text, encoding="utf-8", newline="\n")
    print(text)
    return 0 if not failures else 1


def selftest() -> int:
    failures = []
    if stub_tokens("abcdefg") != ["abcdef", "g"] \
            or stub_tokens("abcdefg") != stub_tokens("abcdefg"):
        failures.append("stub tokenizer nondeterministic")
    m = [task("f1", "char_pa", "参商", "晒网", "task_1")]
    plan = {"itemId": "fx",
            "sentences": [group(["f1"], 0, {"mention": "参商", "refersTo": "char_pa"})]}
    v = check_interface(plan, m, [])
    if v["status"] != "accepted" or v["plan"] != plan or v["renderInput"] != m \
            or "晒网" not in v["renderText"] or "叙事生成任务" not in v["renderText"] \
            or v["inputTokensStub"] > 128:
        failures.append(f"accepted verdict wrong: {json.dumps(v, ensure_ascii=False)[:220]}")
    if len(stub_tokens(shared_render_input(m))) != v["inputTokensStub"]:
        failures.append("token count is not over the shared renderer output")
    m5 = [task("f1", "char_pa", "参商", "晒网", "task_1"),
          task("f2", "char_pa", "参商", "织网", "task_2"),
          task("f3", "char_pb", "辰星", "补网", "task_3"),
          time_fact("f4"),
          task("f5", "char_pa", "参商", "晒网", "task_1")]
    plan5 = {"itemId": "fx", "sentences": [group([f"f{i}" for i in range(1, 6)])]}
    v = check_interface(plan5, m5, bind_point(make_point(), make_point(version=0), m5))
    if v["status"] != "unsupported" or v["reason"] != "plan-too-long" or v["plan"] != plan5 \
            or v.get("observed", {}).get("facts") != 5:
        failures.append(f"unsupported verdict wrong: {v.get('reason')}/{v.get('observed')}")
    v["plan"]["sentences"][0]["factIds"].append("f9")
    if plan5["sentences"][0]["factIds"] == v["plan"]["sentences"][0]["factIds"]:
        failures.append("embedded plan is not a deep copy")
    plan52 = {"itemId": "fx", "sentences": [group(["f1", "f2"]), group(["f3", "f4", "f5"])]}
    v = check_interface(plan52, m5, bind_point(make_point(), make_point(version=0), m5))
    if v["status"] != "unsupported" or v["reason"] != "plan-too-long":
        failures.append(f"3+2 bypass not caught: {v.get('status')}/{v.get('reason')}")
    bad = {"itemId": "fx", "sentences": [
        group(["f1"], 0, {"mention": "辰星", "refersTo": "char_pb"}), group(["f2"], 1)]}
    m2 = [task("f1", "char_pa", "参商", "晒网", "task_1"),
          task("f2", "char_pb", "辰星", "补网", "task_3")]
    v = check_interface(bad, m2, [])
    if v["status"] != "error" or v["reason"] != "plan-invariant-violation" \
            or "renderInput" in v:
        failures.append(f"I2-violating plan not stopped: {v.get('status')}/{v.get('reason')}")
    before = make_point(version=1)
    point = make_point(version=2)
    point["previousPointId"] = "pt-9"
    problems = bind_point(point, before, [])
    if "predecessor-identity-mismatch" not in problems:
        failures.append(f"predecessor identity not checked: {problems}")
    if bind_point(make_point(version=0), None, []):
        failures.append(f"legal root rejected: {bind_point(make_point(version=0), None, [])}")
    if "root-with-time" not in bind_point(make_point(version=0, time_advance=make_time_advance()),
                                          None, []):
        failures.append("root with timeAdvance not refused")
    incomplete = make_point(version=2)
    del incomplete["previousPointId"]
    del incomplete["timeAdvance"]
    problems = bind_point(incomplete, make_point(version=1), [])
    if "missing-previousPointId" not in problems or "missing-timeAdvance" not in problems:
        failures.append(f"absent GetStateData keys not reported: {problems}")
    diverged = [task("f1", "char_pa", "参商", "被篡改的目标", "task_1")]
    problems = bind_point(make_point(), make_point(version=0), diverged)
    if not any("source-content-mismatch" in x for x in problems):
        failures.append(f"content divergence not caught: {problems}")
    diverged_t = [{"factId": "f1", "kind": "time", "amount": 9, "unit": "minute",
                   "at": None, "source": {"timeAdvance": True}}]
    problems = bind_point(make_point(), make_point(version=0), diverged_t)
    if not any("source-content-mismatch" in x for x in problems):
        failures.append(f"time divergence not caught: {problems}")
    owned = [{"factId": "f1", "kind": "task_achieved", "entityId": "char_pb",
              "name": "辰星", "goal": "晒网", "at": "探针镇",
              "source": {"entityId": "char_pa", "taskId": "task_1"}}]
    problems = bind_point(make_point(), make_point(version=0), owned)
    if not any("ownership-mismatch" in x for x in problems):
        failures.append(f"ownership divergence not caught: {problems}")
    wrong_kind = [{"factId": "f1", "kind": "personality_changed", "entityId": "char_pa",
                   "name": "参商", "text": "变得沉默", "at": "探针镇",
                   "source": {"entityId": "char_pa"}}]
    problems = bind_point(make_point(), make_point(version=0), wrong_kind)
    if not any("unsupported-fact-kind" in x for x in problems):
        failures.append(f"unsupported kind not refused: {problems}")
    renamed = [task("f1", "char_pa", "冒名者", "晒网", "task_1")]
    problems = bind_point(make_point(), make_point(version=0), renamed)
    if not any("name-mismatch" in x for x in problems):
        failures.append(f"name divergence not caught: {problems}")
    other_world = make_point(version=1, world="w_other")
    problems = bind_point(make_point(version=2), other_world, [])
    if "world-mismatch" not in problems:
        failures.append(f"cross-world before not caught: {problems}")
    no_world = make_point(version=2)
    del no_world["state"]["worldId"]
    if bind_point(no_world, make_point(version=1), []) != ["world-missing"]:
        failures.append(f"missing state.worldId not stopped: "
                        f"{bind_point(no_world, make_point(version=1), [])}")
    for f in failures:
        print("SELFTEST FAIL:", f)
    print("selftest:", "PASS" if not failures else f"{len(failures)} failure(s)")
    return 1 if failures else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--out", default=None)
    args = parser.parse_args()
    if args.selftest:
        return selftest()
    return run_suite(args.out)


if __name__ == "__main__":
    sys.exit(main())
