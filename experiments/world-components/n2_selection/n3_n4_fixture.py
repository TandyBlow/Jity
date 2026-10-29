# N3->N4 interface fixtures (plan: design/world-engine-reports/components/
# n3-n4-interface-plan.md). NON-MODEL verification of the interface
# constraints only:
#
#   binding      root and non-root points are validated separately: a root
#                point has version 0, null previousPointId, NULL
#                timeAdvance and EMPTY deltas; a non-root point needs a
#                before record with matching world, version-1 and THE SAME
#                pointId as previousPointId. entityDeltas is an
#                entity-keyed MAP; each fact's source pointer is resolved
#                against it and the fact CONTENT is checked (task goal
#                against the entity's task list, time against timeAdvance).
#                Missing or mismatched -> binding-failed, never
#                reconstructed from result text.
#   invariants   the N3 hard invariants are a PRECONDITION of acceptance:
#                a plan with a known I2 violation (cross-group reference)
#                stops with error:plan-invariant-violation and produces no
#                render input — coreference not being consumed by N4 does
#                not excuse an invalid plan.
#   range        the per-run N4 input is the FLATTENED fact table; more
#                than 4 facts in total is unsupported (grouping cannot
#                bypass the limit; no splitting fallback exists).
#   tokens       counted over the text produced by a DETERMINISTIC render
#                stand-in (the shape render_input feeds N4), not over JSON;
#                the 6-char stub tokenizer and the stand-in are NOT real
#                sentencepiece / real shared-render acceptance.
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

REPO_ROOT = HERE.parent.parent.parent
MAX_FACTS_PER_GROUP = 4
MAX_INPUT_TOKENS = 128


def sha_file(path) -> str:
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def stub_tokens(text: str, n: int = 6) -> list:
    """deterministic stub tokenizer (fixed 6-char chunks). NOT a real
    sentencepiece acceptance."""
    return [text[i:i + n] for i in range(0, len(text), n)]


def render_text(render_input: list) -> str:
    """deterministic render stand-in over the flattened fact table — the
    payload whose token count the interface checks. NOT the real shared
    render_input; real rendering/tokenizing belong to the N4 batches."""
    lines = []
    for f in render_input:
        if f["kind"] == "time":
            lines.append(f"过了{f['amount']}{f['unit']}")
        elif f["kind"] == "task_achieved":
            lines.append(f"{f['name']}完成了{f['goal']}")
        else:
            lines.append(f"{f['name']}的情况有变化")
    return "\n".join(lines)


def make_deltas():
    """entity-keyed map, the shape of real entityDeltas."""
    return {
        "char_pa": {"tasks": ["晒网", "织网"], "personality": "沉稳"},
        "char_pb": {"tasks": ["补网"], "position": "探针镇"},
    }


def make_time_advance(minutes=5, unit="minute"):
    return {"minutes": minutes, "unit": unit}


def make_point(version=1, deltas=None, digest="d" * 8, time_advance="default",
               prev_point_id="default"):
    if deltas is None:
        deltas = make_deltas() if version != 0 else {}
    if time_advance == "default":
        time_advance = None if version == 0 else make_time_advance()
    if prev_point_id == "default":
        prev_point_id = None if version == 0 else f"pt-{version - 1}"
    return {"worldId": "w_probe", "pointId": f"pt-{version}", "version": version,
            "state": {"summary": "probe state"},
            "stateDigest": digest,
            "previousPointId": prev_point_id,
            "timeAdvance": time_advance, "entityDeltas": deltas}


def bind_point(point: dict, before, manifest_facts: list) -> list:
    """authoritative input binding. Root and non-root validated separately;
    source pointers resolved against the entity-keyed delta MAP with
    content checks. Returns binding-failed reasons (empty = bound)."""
    problems = []
    for field in ("state", "pointId", "version", "stateDigest", "entityDeltas"):
        if point.get(field) is None:
            problems.append(f"missing-{field}")
    if problems:
        return problems
    is_root = point["version"] == 0
    if is_root:
        if point.get("previousPointId") is not None:
            problems.append("root-with-predecessor")
        if point.get("timeAdvance") is not None:
            problems.append("root-with-time")
        if point["entityDeltas"]:
            problems.append("root-with-deltas")
        if before is not None:
            problems.append("root-with-before-record")
    else:
        if point.get("timeAdvance") is None:
            problems.append("missing-timeAdvance")
        if before is None:
            problems.append("missing-before")
        else:
            if before.get("worldId") != point.get("worldId"):
                problems.append("world-mismatch")
            if before.get("version") != point["version"] - 1:
                problems.append("version-gap")
            if before.get("pointId") != point.get("previousPointId"):
                problems.append("predecessor-identity-mismatch")
    if not isinstance(point["entityDeltas"], dict):
        problems.append("deltas-not-entity-map")
        return problems
    # source resolution with CONTENT checks
    for f in manifest_facts:
        fid = f.get("factId")
        src = f.get("source") or {}
        if f["kind"] == "time":
            ta = point.get("timeAdvance")
            if not isinstance(ta, dict):
                problems.append(f"source-content-mismatch:{fid}:timeAdvance")
            elif f.get("amount") != ta.get("minutes") or f.get("unit") != ta.get("unit"):
                problems.append(f"source-content-mismatch:{fid}:timeAdvance")
            continue
        eid = src.get("entityId")
        if eid not in point["entityDeltas"]:
            problems.append(f"source-content-mismatch:{fid}:entity")
            continue
        entry = point["entityDeltas"][eid]
        if f["kind"] == "task_achieved":
            idx = src.get("taskIndex")
            tasks = entry.get("tasks") if isinstance(entry, dict) else None
            if not isinstance(tasks, list) or not isinstance(idx, int) \
                    or not (0 <= idx < len(tasks)) or tasks[idx] != f.get("goal"):
                problems.append(f"source-content-mismatch:{fid}:task")
        else:
            field = src.get("field")
            if not isinstance(field, str) or field not in entry:
                problems.append(f"source-content-mismatch:{fid}:field")
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
    text = render_text(render_input)
    n_tokens = len(stub_tokens(text))
    if n_tokens > MAX_INPUT_TOKENS:
        out.update({"status": "unsupported", "reason": "input-too-long",
                    "limits": {"maxFactsPerRun": MAX_FACTS_PER_GROUP,
                               "maxInputTokens": MAX_INPUT_TOKENS},
                    "observed": {"inputTokens": n_tokens}})
        return out
    out.update({"status": "accepted", "renderInput": render_input,
                "renderText": text, "inputTokensStub": n_tokens,
                "limits": {"maxFactsPerRun": MAX_FACTS_PER_GROUP,
                           "maxInputTokens": MAX_INPUT_TOKENS},
                "notes": {"coreferenceConsumed": False,
                          "invariantsVerified": True,
                          "tokenCounter": "deterministic stub over a render "
                                          "stand-in; not real tokenizer/render acceptance"}})
    return out


def task(fid, char, name, goal, task_index):
    return {"factId": fid, "kind": "task_achieved", "entityId": char,
            "name": name, "goal": goal, "at": "探针镇",
            "source": {"entityId": char, "taskIndex": task_index}}


def time_fact(fid):
    return {"factId": fid, "kind": "time", "amount": 5, "unit": "minute",
            "at": None, "source": {"timeAdvance": True}}


def group(fids, index=0, ref=None):
    refs = [ref] if ref else []
    return {"index": index, "factIds": fids, "coreference": refs}


def fixtures() -> list:
    """(name, description, expected, build). build -> (plan|None, manifest,
    point, before); plan None means a binding-only assertion."""

    def t1():
        m = [task("f1", "char_pa", "参商", "晒网", 0)]
        return {"itemId": "fx", "sentences": [group(["f1"])]}, m, make_point(), make_point(version=0)

    def t4():
        deltas = {"char_pa": {"tasks": ["任务0", "任务1", "任务2", "任务3"]}}
        m = [task(f"f{i}", "char_pa", "参商", f"任务{i}", i) for i in range(4)]
        return {"itemId": "fx", "sentences": [group([f"f{i}" for i in range(4)])]}, \
            m, make_point(deltas=deltas), make_point(version=0)

    def t5():
        deltas = {"char_pa": {"tasks": ["任务0", "任务1"]},
                  "char_pb": {"tasks": ["任务2", "任务3", "任务4"]}}
        m = [task("f0", "char_pa", "参商", "任务0", 0), task("f1", "char_pa", "参商", "任务1", 1),
             task("f2", "char_pb", "辰星", "任务2", 0), task("f3", "char_pb", "辰星", "任务3", 1),
             task("f4", "char_pb", "辰星", "任务4", 2)]
        plan = {"itemId": "fx", "sentences": [group([f"f{i}" for i in range(5)])]}
        return plan, m, make_point(deltas=deltas), make_point(version=0)

    def t52():
        deltas = {"char_pa": {"tasks": ["任务0", "任务1"]},
                  "char_pb": {"tasks": ["任务2", "任务3", "任务4"]}}
        m = [task("f0", "char_pa", "参商", "任务0", 0), task("f1", "char_pa", "参商", "任务1", 1),
             task("f2", "char_pb", "辰星", "任务2", 0), task("f3", "char_pb", "辰星", "任务3", 1),
             task("f4", "char_pb", "辰星", "任务4", 2)]
        plan = {"itemId": "fx", "sentences": [group(["f0", "f1"], 0), group(["f2", "f3", "f4"], 1)]}
        return plan, m, make_point(deltas=deltas), make_point(version=0)

    def sized(total_tokens):
        m = [task("f1", "char_pa", "参商", "", 0)]
        base = len(render_text(m))
        goal = "网" * (total_tokens * 6 - base)
        m[0]["goal"] = goal
        deltas = {"char_pa": {"tasks": [goal]}}
        return {"itemId": "fx", "sentences": [group(["f1"])]}, m, make_point(deltas=deltas), make_point(version=0)

    def t128():
        return sized(128)

    def t129():
        return sized(129)

    def missing():
        deltas = {"char_pa": {"tasks": ["晒网", "织网"]}}
        m = [task("f1", "char_pa", "参商", "晒网", 0), task("f2", "char_pa", "参商", "织网", 1)]
        return {"itemId": "fx", "sentences": [group(["f1"])]}, m, make_point(deltas=deltas), make_point(version=0)

    def duplicate():
        deltas = {"char_pa": {"tasks": ["晒网", "织网"]}}
        m = [task("f1", "char_pa", "参商", "晒网", 0), task("f2", "char_pa", "参商", "织网", 1)]
        return {"itemId": "fx", "sentences": [group(["f1", "f1"])]}, m, make_point(deltas=deltas), make_point(version=0)

    def unknown():
        m = [task("f1", "char_pa", "参商", "晒网", 0)]
        return {"itemId": "fx", "sentences": [group(["f1", "f9"])]}, m, make_point(), make_point(version=0)

    def order():
        m = [task("f1", "char_pa", "参商", "晒网", 0), task("f2", "char_pb", "辰星", "补网", 0)]
        plan = {"itemId": "fx", "sentences": [group(["f2"], 0), group(["f1"], 1)]}
        return plan, m, make_point(), make_point(version=0)

    def time_pred():
        m = [task("f1", "char_pa", "参商", "晒网", 0), time_fact("f2")]
        plan = {"itemId": "fx", "sentences": [group(["f1", "f2"])]}
        return plan, m, make_point(), make_point(version=0)

    def same_name():
        deltas = {"char_pa": {"tasks": ["扫地"]}, "char_pb": {"tasks": ["洗碗"]}}
        m = [task("f1", "char_pa", "同名者", "扫地", 0), task("f2", "char_pb", "同名者", "洗碗", 0)]
        plan = {"itemId": "fx", "sentences": [
            group(["f1"], 0, {"mention": "同名者", "refersTo": "char_pa"}),
            group(["f2"], 1, {"mention": "同名者", "refersTo": "char_pb"})]}
        return plan, m, make_point(deltas=deltas), make_point(version=0)

    def cross_group():
        m = [task("f1", "char_pa", "参商", "晒网", 0), task("f2", "char_pb", "辰星", "补网", 0)]
        plan = {"itemId": "fx", "sentences": [
            group(["f1"], 0, {"mention": "辰星", "refersTo": "char_pb"}),
            group(["f2"], 1)]}
        return plan, m, make_point(), make_point(version=0)

    def no_before():
        return {"itemId": "fx", "sentences": [group(["f1"])]}, \
            [task("f1", "char_pa", "参商", "晒网", 0)], make_point(version=3), None

    def version_gap():
        before = make_point(version=1)
        point = make_point(version=3)
        point["previousPointId"] = before["pointId"]  # isolate the version gap
        return {"itemId": "fx", "sentences": [group(["f1"])]}, \
            [task("f1", "char_pa", "参商", "晒网", 0)], point, before

    def no_digest():
        point = make_point(version=2)
        point["stateDigest"] = None
        return {"itemId": "fx", "sentences": [group(["f1"])]}, \
            [task("f1", "char_pa", "参商", "晒网", 0)], point, make_point(version=1)

    def pred_identity():
        before = make_point(version=1)
        point = make_point(version=2)
        point["previousPointId"] = "pt-9"  # unrelated id
        return None, [task("f1", "char_pa", "参商", "晒网", 0)], point, before

    def root_ok():
        return None, [], make_point(version=0), None

    def root_with_time():
        return None, [], make_point(version=0, time_advance=make_time_advance()), None

    def source_content():
        m = [task("f1", "char_pa", "参商", "被篡改的目标", 0)]
        return {"itemId": "fx", "sentences": [group(["f1"])]}, m, make_point(), make_point(version=0)

    def time_content():
        m = [{"factId": "f1", "kind": "time", "amount": 9, "unit": "minute",
              "at": None, "source": {"timeAdvance": True}}]
        return {"itemId": "fx", "sentences": [group(["f1"])]}, m, make_point(), make_point(version=0)

    return [
        ("F01", "1 fact in range", "accepted", t1),
        ("F04", "4 facts flattened (upper bound)", "accepted", t4),
        ("F05", "5 facts in one group over limit", "unsupported:plan-too-long", t5),
        ("F52", "3+2 grouping cannot bypass: flattened 5", "unsupported:plan-too-long", t52),
        ("FT128", "exactly 128 stub tokens of rendered text", "accepted", t128),
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
        ("FB03", "missing stateDigest", "binding-failed:missing-stateDigest", no_digest),
        ("FBL1", "predecessor identity mismatch", "binding-failed:predecessor-identity-mismatch", pred_identity),
        ("FBR1", "legal root point (null timeAdvance, empty deltas)", "bound", root_ok),
        ("FBR2", "root point carrying timeAdvance", "binding-failed:root-with-time", root_with_time),
        ("FSC1", "fact content diverges from its delta", "binding-failed:source-content-mismatch:f1:task", source_content),
        ("FTT1", "time amount diverges from timeAdvance", "binding-failed:source-content-mismatch:f1:timeAdvance", time_content),
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
            if len(stub_tokens(verdict["renderText"])) != verdict["inputTokensStub"]:
                ok = False
        results[name] = {"description": desc, "expected": expected, "got": got,
                         "pass": ok}
        if not ok:
            failures.append(f"{name}: expected {expected}, got {got}")
    archive = {
        "purpose": "N3->N4 interface fixture verification (non-model)",
        "tokenCounter": "deterministic 6-char stub over a deterministic render "
                        "stand-in; NOT real sentencepiece or real shared-render acceptance",
        "interfaceConstraints": {"maxFactsPerRun": MAX_FACTS_PER_GROUP,
                                 "maxInputTokens": MAX_INPUT_TOKENS,
                                 "coreferenceConsumed": False,
                                 "invariantsArePrecondition": True,
                                 "unsupportedPreservesPlan": True,
                                 "rangeCheckedOnFlattenedRun": True},
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
    if stub_tokens("abcdefg") != ["abcdef", "g"] or \
            stub_tokens("abcdefg") != stub_tokens("abcdefg"):
        failures.append("stub tokenizer nondeterministic")
    m = [task("f1", "char_pa", "参商", "晒网", 0)]
    plan = {"itemId": "fx", "sentences": [group(["f1"], 0, {"mention": "参商", "refersTo": "char_pa"})]}
    v = check_interface(plan, m, [])
    if v["status"] != "accepted" or v["plan"] != plan or v["renderInput"] != m \
            or "晒网" not in v["renderText"] or v["inputTokensStub"] > 128:
        failures.append(f"accepted verdict wrong: {json.dumps(v, ensure_ascii=False)[:200]}")
    m5 = [task(f"f{i}", "char_pa", "参商", f"任务{i}", i) for i in range(5)]
    deltas5 = {"char_pa": {"tasks": [f"任务{i}" for i in range(5)]}}
    plan5 = {"itemId": "fx", "sentences": [group([f"f{i}" for i in range(5)])]}
    v = check_interface(plan5, m5, bind_point(make_point(deltas=deltas5), make_point(version=0), m5))
    if v["status"] != "unsupported" or v["reason"] != "plan-too-long" or v["plan"] != plan5 \
            or v.get("observed", {}).get("facts") != 5:
        failures.append(f"unsupported verdict wrong: {v.get('reason')}/{v.get('observed')}")
    v["plan"]["sentences"][0]["factIds"].append("f9")
    if plan5["sentences"][0]["factIds"] == v["plan"]["sentences"][0]["factIds"]:
        failures.append("embedded plan is not a deep copy")
    plan52 = {"itemId": "fx", "sentences": [group(["f0", "f1"]), group(["f2", "f3", "f4"])]}
    v = check_interface(plan52, m5, bind_point(make_point(deltas=deltas5), make_point(version=0), m5))
    if v["status"] != "unsupported" or v["reason"] != "plan-too-long":
        failures.append(f"3+2 bypass not caught: {v.get('status')}/{v.get('reason')}")
    bad = {"itemId": "fx", "sentences": [
        group(["f1"], 0, {"mention": "辰星", "refersTo": "char_pb"}), group(["f2"], 1)]}
    m2 = [task("f1", "char_pa", "参商", "晒网", 0), task("f2", "char_pb", "辰星", "补网", 0)]
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
    if "root-with-time" not in bind_point(make_point(version=0, time_advance=make_time_advance()), None, []):
        failures.append("root with timeAdvance not refused")
    diverged = [task("f1", "char_pa", "参商", "被篡改的目标", 0)]
    problems = bind_point(make_point(), make_point(version=0), diverged)
    if not any("source-content-mismatch" in x for x in problems):
        failures.append(f"content divergence not caught: {problems}")
    diverged_t = [{"factId": "f1", "kind": "time", "amount": 9, "unit": "minute",
                   "at": None, "source": {"timeAdvance": True}}]
    problems = bind_point(make_point(), make_point(version=0), diverged_t)
    if not any("source-content-mismatch" in x for x in problems):
        failures.append(f"time divergence not caught: {problems}")
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
