# N3->N4 interface fixtures (plan: design/world-engine-reports/components/
# n3-n4-interface-plan.md). NON-MODEL verification of the interface
# constraints only:
#
#   - unsupported contract: >4 facts per group or >128 input tokens ->
#     {"status": "unsupported", ...} with the ORIGINAL plan embedded
#     verbatim (groups, factIds, order, entities, time untouched);
#     coreference is NEVER passed to render_input (not consumed by N4);
#   - accepted: render_input is the flat fact table in plan sentence order,
#     built from a manifest whose facts carry source pointers into the raw
#     entityDeltas of a bound committed point;
#   - binding: state/pointId/version/stateDigest/previousPointId/
#     timeAdvance/raw entityDeltas; lineage checks (same world, version
#     continuity, digest presence, per-fact source pointers). Missing or
#     mismatched -> binding-failed, never reconstructed from result text.
#
# The token counter is a DETERMINISTIC STUB (fixed 6-char chunks) — this
# is NOT a real sentencepiece acceptance; the 128/129 fixtures verify the
# interface's counting and decision logic only.

import argparse
import copy
import hashlib
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

REPO_ROOT = HERE.parent.parent.parent
MAX_FACTS_PER_GROUP = 4
MAX_INPUT_TOKENS = 128


def sha_file(path) -> str:
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def stub_tokens(text: str, n: int = 6) -> list:
    """deterministic stub tokenizer (fixed 6-char chunks). NOT a real
    sentencepiece acceptance."""
    return [text[i:i + n] for i in range(0, len(text), n)]


def bind_point(point: dict, before, manifest_facts: list) -> list:
    """authoritative input binding. point: the committed record; before:
    the previous record or None (root); manifest_facts: facts carrying a
    source pointer {"deltaIndex": i} into the point's raw entityDeltas.
    Returns a list of binding-failed reasons (empty = bound)."""
    problems = []
    for field in ("state", "pointId", "version", "stateDigest",
                  "timeAdvance", "entityDeltas"):
        if point.get(field) is None:
            problems.append(f"missing-{field}")
    if problems:
        return problems
    if before is None:
        if point["version"] != 0:
            problems.append("missing-before")
    else:
        if before.get("worldId") != point.get("worldId"):
            problems.append("world-mismatch")
        if before.get("version") != point["version"] - 1:
            problems.append("version-gap")
    for f in manifest_facts:
        ptr = (f.get("source") or {}).get("deltaIndex")
        if not isinstance(ptr, int) or not (0 <= ptr < len(point["entityDeltas"])):
            problems.append(f"source-pointer-unresolvable:{f.get('factId')}")
    return problems


def check_interface(plan: dict, manifest_facts: list, binding_problems: list) -> dict:
    """the N3->N4 interface check. Returns one verdict dict; the plan is
    embedded verbatim in every verdict."""
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
    for s in plan.get("sentences", []):
        if len(s.get("factIds", [])) > MAX_FACTS_PER_GROUP:
            out.update({"status": "unsupported", "reason": "plan-too-long",
                        "limits": {"maxFactsPerGroup": MAX_FACTS_PER_GROUP,
                                   "maxInputTokens": MAX_INPUT_TOKENS},
                        "observed": {"groupIndex": s["index"],
                                     "facts": len(s["factIds"])}})
            return out
    # flatten in plan sentence order; coreference and group boundaries are
    # NOT consumed (N4 render_input takes facts only)
    render_input = [by_id[fid] for s in plan["sentences"] for fid in s["factIds"]]
    n_tokens = len(stub_tokens(json.dumps(render_input, ensure_ascii=False)))
    if n_tokens > MAX_INPUT_TOKENS:
        out.update({"status": "unsupported", "reason": "input-too-long",
                    "limits": {"maxFactsPerGroup": MAX_FACTS_PER_GROUP,
                               "maxInputTokens": MAX_INPUT_TOKENS},
                    "observed": {"inputTokens": n_tokens}})
        return out
    out.update({"status": "accepted", "renderInput": render_input,
                "inputTokensStub": n_tokens,
                "limits": {"maxFactsPerGroup": MAX_FACTS_PER_GROUP,
                           "maxInputTokens": MAX_INPUT_TOKENS},
                "notes": {"coreferenceConsumed": False,
                          "tokenCounter": "deterministic stub, not real tokenizer acceptance"}})
    return out


def make_point(world="w_probe", version=1, deltas=None, digest="d" * 8):
    return {"worldId": world, "pointId": f"pt-{version}", "version": version,
            "state": {"summary": "probe state"},
            "stateDigest": digest,
            "previousPointId": None if version == 0 else f"pt-{version - 1}",
            "timeAdvance": {"minutes": 5}, "entityDeltas": deltas or []}


def fact(fid, char, name, goal, delta_index):
    return {"factId": fid, "kind": "task_achieved", "entityId": char,
            "name": name, "goal": goal, "at": "探针镇",
            "source": {"deltaIndex": delta_index}}


def group(fids, index=0):
    return {"index": index,
            "factIds": fids,
            "coreference": [{"mention": "参", "refersTo": "char_pa"}]}


ROOT = None  # canonical version-0 record, built lazily below


def root_record():
    return make_point(version=0, deltas=[])


def fixtures() -> list:
    """(name, description, expected, build) — all synthetic."""
    def t1():
        m = [fact("f1", "char_pa", "参商", "晒网", 0)]
        plan = {"itemId": "fx", "sentences": [group(["f1"])]}
        return plan, m, make_point(deltas=[{"entityId": "char_pa"}]), root_record()

    def t4():
        m = [fact(f"f{i}", "char_pa", "参商", f"任务{i}", i) for i in range(4)]
        plan = {"itemId": "fx", "sentences": [group([f"f{i}" for i in range(4)])]}
        return plan, m, make_point(deltas=[{"entityId": "char_pa"} for _ in range(4)]), root_record()

    def t5():
        m = [fact(f"f{i}", "char_pa" if i % 2 == 0 else "char_pb",
                  "参商" if i % 2 == 0 else "辰星", f"任务{i}", i) for i in range(5)]
        plan = {"itemId": "fx", "sentences": [group([f"f{i}" for i in range(5)])]}
        return plan, m, make_point(deltas=[{"entityId": "char_pa"} for _ in range(5)]), root_record()

    def sized(total_tokens):
        m = [fact("f1", "char_pa", "参商", "", 0)]
        base = len(json.dumps(m, ensure_ascii=False))
        m[0]["goal"] = "网" * (total_tokens * 6 - base)
        plan = {"itemId": "fx", "sentences": [group(["f1"])]}
        return plan, m, make_point(deltas=[{"entityId": "char_pa"}]), root_record()

    def t128():
        return sized(128)

    def t129():
        return sized(129)

    def missing():
        m = [fact("f1", "char_pa", "参商", "晒网", 0), fact("f2", "char_pa", "参商", "织网", 1)]
        plan = {"itemId": "fx", "sentences": [group(["f1"])]}
        return plan, m, make_point(deltas=[{"entityId": "char_pa"}] * 2), root_record()

    def duplicate():
        m = [fact("f1", "char_pa", "参商", "晒网", 0), fact("f2", "char_pa", "参商", "织网", 1)]
        plan = {"itemId": "fx", "sentences": [group(["f1", "f1"])]}
        return plan, m, make_point(deltas=[{"entityId": "char_pa"}] * 2), root_record()

    def unknown():
        m = [fact("f1", "char_pa", "参商", "晒网", 0)]
        plan = {"itemId": "fx", "sentences": [group(["f1", "f9"])]}
        return plan, m, make_point(deltas=[{"entityId": "char_pa"}]), root_record()

    def order():
        m = [fact("f1", "char_pa", "参商", "晒网", 0), fact("f2", "char_pb", "辰星", "补网", 1)]
        plan = {"itemId": "fx", "sentences": [group(["f2"], 0), group(["f1"], 1)]}
        return plan, m, make_point(deltas=[{"entityId": "char_pa"}, {"entityId": "char_pb"}]), root_record()

    def time_pred():
        m = [fact("f1", "char_pa", "参商", "晒网", 0),
             {"factId": "f2", "kind": "time", "amount": 3, "unit": "minute",
              "at": None, "source": {"deltaIndex": 1}}]
        plan = {"itemId": "fx", "sentences": [group(["f1", "f2"])]}
        return plan, m, make_point(deltas=[{"entityId": "char_pa"}, {"kind": "time"}]), root_record()

    def same_name():
        m = [fact("f1", "char_pa", "同名者", "扫地", 0), fact("f2", "char_pb", "同名者", "洗碗", 1)]
        plan = {"itemId": "fx", "sentences": [
            {"index": 0, "factIds": ["f1"],
             "coreference": [{"mention": "同名者", "refersTo": "char_pa"}]},
            {"index": 1, "factIds": ["f2"],
             "coreference": [{"mention": "同名者", "refersTo": "char_pb"}]}]}
        return plan, m, make_point(deltas=[{"entityId": "char_pa"}, {"entityId": "char_pb"}]), root_record()

    def cross_group():
        m = [fact("f1", "char_pa", "参商", "晒网", 0), fact("f2", "char_pb", "辰星", "补网", 1)]
        plan = {"itemId": "fx", "sentences": [
            {"index": 0, "factIds": ["f1"],
             "coreference": [{"mention": "辰星", "refersTo": "char_pb"}]},
            {"index": 1, "factIds": ["f2"], "coreference": []}]}
        return plan, m, make_point(deltas=[{"entityId": "char_pa"}, {"entityId": "char_pb"}]), root_record()

    def no_before():
        m = [fact("f1", "char_pa", "参商", "晒网", 0)]
        plan = {"itemId": "fx", "sentences": [group(["f1"])]}
        return plan, m, make_point(version=3, deltas=[{"entityId": "char_pa"}]), None

    def version_gap():
        m = [fact("f1", "char_pa", "参商", "晒网", 0)]
        before = make_point(version=1, deltas=[])
        plan = {"itemId": "fx", "sentences": [group(["f1"])]}
        return plan, m, make_point(version=3, deltas=[{"entityId": "char_pa"}]), before

    def no_digest():
        m = [fact("f1", "char_pa", "参商", "晒网", 0)]
        p = make_point(deltas=[{"entityId": "char_pa"}])
        p["stateDigest"] = None
        plan = {"itemId": "fx", "sentences": [group(["f1"])]}
        return plan, m, p, root_record()

    return [
        ("F01", "1 fact in range", "accepted", t1),
        ("F04", "4 facts in range (upper bound)", "accepted", t4),
        ("F05", "5 facts over limit, plan preserved", "unsupported:plan-too-long", t5),
        ("FT128", "exactly 128 stub tokens", "accepted", t128),
        ("FT129", "129 stub tokens", "unsupported:input-too-long", t129),
        ("FM01", "plan missing a factId", "error:plan-fact-mismatch:missing", missing),
        ("FM02", "plan duplicate factId", "error:plan-fact-mismatch:duplicate", duplicate),
        ("FM03", "plan unknown factId", "error:plan-fact-mismatch:unknown", unknown),
        ("FO01", "order change follows plan sentence order", "accepted", order),
        ("FT01", "time after its predecessor passes through", "accepted", time_pred),
        ("FN01", "same name different entities; coref not consumed", "accepted", same_name),
        ("FX01", "cross-group reference; coref not consumed", "accepted", cross_group),
        ("FB01", "non-root point without before record", "binding-failed:missing-before", no_before),
        ("FB02", "version discontinuity", "binding-failed:version-gap", version_gap),
        ("FB03", "missing stateDigest", "binding-failed:missing-stateDigest", no_digest),
    ]


def run_suite(out=None) -> int:
    results = {}
    failures = []
    for name, desc, expected, build in fixtures():
        plan, manifest, point, before = build()
        verdict = check_interface(plan, manifest, bind_point(point, before, manifest))
        tail = (":" + verdict["reason"] if "reason" in verdict
                else ":" + ",".join(verdict["reasons"]) if "reasons" in verdict else "")
        got = verdict["status"] + tail
        ok = got == expected
        # plan preservation: every verdict embeds the original verbatim
        if verdict["plan"] != plan:
            ok = False
        # coreference never reaches render_input
        if verdict["status"] == "accepted" and "coreference" in json.dumps(
                verdict["renderInput"], ensure_ascii=False):
            ok = False
        results[name] = {"description": desc, "expected": expected, "got": got,
                         "pass": ok}
        if not ok:
            failures.append(f"{name}: expected {expected}, got {got}")
    archive = {
        "purpose": "N3->N4 interface fixture verification (non-model)",
        "tokenCounter": "deterministic 6-char stub; NOT a real sentencepiece acceptance",
        "interfaceConstraints": {"maxFactsPerGroup": MAX_FACTS_PER_GROUP,
                                 "maxInputTokens": MAX_INPUT_TOKENS,
                                 "coreferenceConsumed": False,
                                 "unsupportedPreservesPlan": True},
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
    # stub tokenizer determinism and chunking
    if stub_tokens("abcdefg") != ["abcdef", "g"] or \
            stub_tokens("abcdefg") != stub_tokens("abcdefg"):
        failures.append("stub tokenizer nondeterministic")
    # accepted verdict embeds the plan verbatim and keeps render facts only
    m = [fact("f1", "char_pa", "参商", "晒网", 0)]
    plan = {"itemId": "fx", "sentences": [{"index": 0, "factIds": ["f1"],
                                           "coreference": [{"mention": "参商", "refersTo": "char_pa"}]}]}
    v = check_interface(plan, m, [])
    if v["status"] != "accepted" or v["plan"] != plan or \
            v["renderInput"] != m or len(stub_tokens(json.dumps(m, ensure_ascii=False))) != v["inputTokensStub"]:
        failures.append(f"accepted verdict wrong: {json.dumps(v, ensure_ascii=False)[:200]}")
    # unsupported keeps the original plan deep-equal, including coreference
    m5 = [fact(f"f{i}", "char_pa", "参商", f"任务{i}", i) for i in range(5)]
    plan5 = {"itemId": "fx", "sentences": [group([f"f{i}" for i in range(5)])]}
    v = check_interface(plan5, m5, [])
    if v["status"] != "unsupported" or v["reason"] != "plan-too-long" or v["plan"] != plan5:
        failures.append(f"unsupported verdict wrong: {v.get('reason')}")
    v["plan"]["sentences"][0]["factIds"].append("f9")
    if plan5["sentences"][0]["factIds"] == v["plan"]["sentences"][0]["factIds"]:
        failures.append("embedded plan is not a deep copy")
    # binding failures stop before plan checks
    m2 = [fact("f1", "char_pa", "参商", "晒网", 7)]
    v = check_interface(plan, m2, bind_point(make_point(), None, m2))
    if v["status"] != "binding-failed" or not any("source-pointer" in r for r in v["reasons"]):
        failures.append(f"unresolvable source pointer not reported: {v.get('reasons')}")
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
