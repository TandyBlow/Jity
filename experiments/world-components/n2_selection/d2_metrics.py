# D2 pre-registered metrics for N3 organisation plans (D2 prep).
#
# Operationalises the D2 pre-registration (n2-content-selection.md §6,
# "指标" row) over a gold plan file and an arm plan file. Pooled rates:
#   H1  coverage: union(plan factIds) == item factIds, no duplicates,
#       no fabrications, no empty sentence groups            (gate, all items)
#   H2  anchoring: every coreference.refersTo is the entityId of a fact
#       inside THAT sentence group and mention == registered name
#                                                            (gate, all items)
#   G1  cross-person same-event grouping: pairwise group precision /
#       recall / F1 vs gold, pooled over all unordered fact pairs (>= 0.80)
#   G2  antecedent accuracy: gold coreference entries in comparable
#       groups (identical factId sets), positional pairing, pooled
#       over items (>= 0.80)
#       + pronoun-site production over ALL gold pronoun sites (repeat
#       mentions of an entity inside a gold group), pooled (>= 0.50)
#   G3  time placement: gold (group rank, within-group index) of the
#       time fact reproduced by the arm, pooled over the time items
#                                                            (>= 0.75)
#   G4  order concordance of within-group relative order for pairs
#       co-grouped by both arm and gold (report only)
#
# H1/H2 always judge every item's raw plan; any structural problem
# (unknown/duplicate/dropped factId, empty group, stale index) fails the
# gates and voids that item's G-metrics. Grouping is already scored by
# G1, so G2's antecedent denominator is restricted to comparable groups;
# pronoun-site production keeps the full gold denominator because
# producing a site requires forming the group. These operationalisation
# choices are part of this freeze and are pinned by self-tests, including
# tamper probes that must move each metric.

import argparse
import json
import pathlib
import sys
from itertools import combinations

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from n3_plan import check_invariants  # noqa: E402

PASS_LINE = {"g1F1": 0.80, "g2Accuracy": 0.80, "pronounProduction": 0.50,
             "g3": 0.75}


def load_jsonl(path: pathlib.Path) -> list:
    return [json.loads(line) for line in
            path.read_text(encoding="utf-8").splitlines() if line.strip()]


def names_map(item: dict) -> dict:
    return {f["entityId"]: f["name"] for f in item["facts"] if f.get("entityId")}


def group_of_map(row: dict) -> dict:
    out = {}
    for s in row["sentences"]:
        for fid in s["factIds"]:
            out[fid] = s["index"]
    return out


def h1(row: dict, item: dict) -> bool:
    want = sorted(f["factId"] for f in item["facts"])
    got = [fid for s in row["sentences"] for fid in s["factIds"]]
    return sorted(got) == want and all(s["factIds"] for s in row["sentences"])


def h2(row: dict, item: dict) -> bool:
    problems = check_invariants({"baseline": "h2", "sentences": row["sentences"]},
                                item["facts"], names_map(item))
    return not [p for p in problems if "anchored" in p or "mention" in p]


def sentence_shape_problems(sentences, tag: str) -> list:
    """shape check that never indexes into missing keys: a legal JSON plan
    missing `coreference` (or carrying malformed entries) is a structural
    problem for the failure/retry flow, not a crash."""
    if not isinstance(sentences, list) or not sentences:
        return [f"{tag}: sentences missing or empty"]
    problems = []
    for s in sentences:
        if not isinstance(s, dict):
            problems.append(f"{tag}: sentence group is not an object")
            continue
        fids = s.get("factIds")
        if not isinstance(fids, list) or not fids \
                or not all(isinstance(x, str) for x in fids):
            problems.append(f"{tag}: sentence group factIds missing/empty/non-string")
        refs = s.get("coreference")
        if not isinstance(refs, list):
            problems.append(f"{tag}: sentence group coreference missing or not a list")
            continue
        for ref in refs:
            if not isinstance(ref, dict) \
                    or not isinstance(ref.get("mention"), str) \
                    or not isinstance(ref.get("refersTo"), str):
                problems.append(f"{tag}: coreference entry malformed")
                break
    return problems


def structural_problems(row: dict, item: dict, tag: str) -> list:
    problems = sentence_shape_problems(row.get("sentences") or [], tag)
    if problems:
        return problems
    problems = check_invariants({"baseline": tag, "sentences": row["sentences"]},
                                item["facts"], names_map(item))
    sentences = row.get("sentences") or []
    if sentences and [s.get("index") for s in sentences] != list(range(len(sentences))):
        problems.append(f"{tag}: sentence index not contiguous")
    return problems


def pairwise_counts(row: dict, gold_row: dict, item: dict) -> dict:
    ids = [f["factId"] for f in item["facts"]]
    arm = group_of_map(row)
    gold = group_of_map(gold_row)
    tp = fp = fn = 0
    for a, b in combinations(ids, 2):
        arm_same = arm[a] == arm[b]
        gold_same = gold[a] == gold[b]
        if arm_same and gold_same:
            tp += 1
        elif arm_same:
            fp += 1
        elif gold_same:
            fn += 1
    return {"tp": tp, "fp": fp, "fn": fn}


def g2(row: dict, gold_row: dict) -> dict:
    arm_groups = {frozenset(s["factIds"]): s for s in row["sentences"]}
    gold_groups = {frozenset(s["factIds"]): s for s in gold_row["sentences"]}
    correct = comparable = produced = sites = 0
    for key, g_s in gold_groups.items():
        seen = set()
        g_entries = []
        for ref in g_s.get("coreference", []):
            g_entries.append({"entry": ref,
                              "pronounSite": ref["refersTo"] in seen})
            seen.add(ref["refersTo"])
        a_s = arm_groups.get(key)
        if a_s is None:
            sites += sum(1 for e in g_entries if e["pronounSite"])
            continue
        a_refs = a_s.get("coreference", [])
        aligned = len(a_refs) == len(g_entries)
        for pos, g_entry in enumerate(g_entries):
            if g_entry["pronounSite"]:
                sites += 1
                if aligned and a_refs[pos].get("refersTo") == g_entry["entry"]["refersTo"]:
                    produced += 1
        if not aligned:
            continue
        comparable += len(g_entries)
        for pos, g_entry in enumerate(g_entries):
            if a_refs[pos] == g_entry["entry"]:
                correct += 1
    return {"correct": correct, "comparableEntries": comparable,
            "produced": produced, "goldSites": sites}


def g3(row: dict, gold_row: dict, item: dict):
    time_fids = [f["factId"] for f in item["facts"] if f["kind"] == "time"]
    if not time_fids:
        return None
    fid = time_fids[0]

    def placement(r: dict):
        for rank, s in enumerate(r["sentences"]):
            for pos, f in enumerate(s["factIds"]):
                if f == fid:
                    return (rank, pos)
        return None

    return {"match": placement(row) == placement(gold_row),
            "gold": placement(gold_row), "arm": placement(row)}


def g4(row: dict, gold_row: dict, item: dict) -> dict:
    ids = [f["factId"] for f in item["facts"]]
    arm_g = group_of_map(row)
    gold_g = group_of_map(gold_row)

    def within_positions(r: dict) -> dict:
        out = {}
        for s in r["sentences"]:
            for pos, fid in enumerate(s["factIds"]):
                out[(s["index"], fid)] = pos
        return out

    arm_pos = within_positions(row)
    gold_pos = within_positions(gold_row)
    total = agree = 0
    for a, b in combinations(ids, 2):
        if arm_g[a] == arm_g[b] and gold_g[a] == gold_g[b] and arm_g[a] == gold_g[a]:
            total += 1
            if ((arm_pos[(arm_g[a], a)] < arm_pos[(arm_g[a], b)])
                    == (gold_pos[(gold_g[a], a)] < gold_pos[(gold_g[a], b)])):
                agree += 1
    return {"agreed": agree, "of": total}


def evaluate(items: dict, gold_rows: dict, plan_rows: dict) -> dict:
    report = {"items": {}, "problems": []}
    n = len(items)
    tp = fp = fn = 0
    correct = comparable = 0
    produced = sites = 0
    g3_match = g3_total = 0
    g4_agree = g4_total = 0
    h1_pass = h2_pass = 0
    rows_present = 0
    for iid, item in items.items():
        gold_row = gold_rows.get(iid)
        plan_row = plan_rows.get(iid)
        if gold_row is None or plan_row is None:
            report["problems"].append(f"{iid}: missing gold or plan row")
            continue
        rows_present += 1
        shape = sentence_shape_problems(plan_row.get("sentences") or [], f"plan:{iid}")
        h1_ok = h2_ok = False
        if shape:
            problems = shape
        else:
            h1_ok = h1(plan_row, item)
            h2_ok = h2(plan_row, item)
            problems = structural_problems(plan_row, item, f"plan:{iid}")
        h1_pass += int(h1_ok)
        h2_pass += int(h2_ok)
        entry = {"h1": h1_ok, "h2": h2_ok, "g1": None, "g2": None,
                 "g3": None, "g4": None}
        if problems:
            report["problems"].extend(problems)
            report["items"][iid] = entry
            continue
        pc = pairwise_counts(plan_row, gold_row, item)
        tp += pc["tp"]; fp += pc["fp"]; fn += pc["fn"]
        g2r = g2(plan_row, gold_row)
        correct += g2r["correct"]; comparable += g2r["comparableEntries"]
        produced += g2r["produced"]; sites += g2r["goldSites"]
        g3r = g3(plan_row, gold_row, item)
        if g3r is not None:
            g3_total += 1
            g3_match += int(g3r["match"])
        g4r = g4(plan_row, gold_row, item)
        g4_agree += g4r["agreed"]; g4_total += g4r["of"]
        precision = pc["tp"] / (pc["tp"] + pc["fp"]) if pc["tp"] + pc["fp"] else 1.0
        recall = pc["tp"] / (pc["tp"] + pc["fn"]) if pc["tp"] + pc["fn"] else 1.0
        entry["g1"] = {**pc, "f1": 2 * precision * recall / (precision + recall)
                       if precision + recall else 0.0}
        entry["g2"] = g2r
        entry["g3"] = g3r
        entry["g4"] = g4r
        report["items"][iid] = entry
    g1_p = tp / (tp + fp) if tp + fp else 1.0
    g1_r = tp / (tp + fn) if tp + fn else 1.0
    summary = {
        "items": n, "itemsScored": rows_present,
        "h1": f"{h1_pass}/{n}", "h2": f"{h2_pass}/{n}",
        "g1": {"precision": g1_p, "recall": g1_r,
               "f1": 2 * g1_p * g1_r / (g1_p + g1_r) if g1_p + g1_r else 0.0,
               "tp": tp, "fp": fp, "fn": fn},
        "g2Accuracy": correct / comparable if comparable else None,
        "pronounProduction": produced / sites if sites else None,
        "g3": g3_match / g3_total if g3_total else None,
        "g4": g4_agree / g4_total if g4_total else None,
        "passLine": PASS_LINE,
        "verdict": {},
    }
    summary["verdict"] = {
        "pass": bool(not report["problems"] and rows_present == n
                     and h1_pass == n and h2_pass == n
                     and summary["g1"]["f1"] >= PASS_LINE["g1F1"]
                     and summary["g2Accuracy"] is not None
                     and summary["g2Accuracy"] >= PASS_LINE["g2Accuracy"]
                     and summary["pronounProduction"] is not None
                     and summary["pronounProduction"] >= PASS_LINE["pronounProduction"]
                     and summary["g3"] is not None
                     and summary["g3"] >= PASS_LINE["g3"]),
    }
    report["summary"] = summary
    return report


def build_gold_row(item: dict) -> dict:
    """rubric convention (R1-R6) applied programmatically; self-test only.
    The real gold comes from the frozen AI annotation."""
    facts = item["facts"]
    order = {f["factId"]: i for i, f in enumerate(facts)}
    by_entity = {}
    entity_order = []
    for f in facts:
        ent = f.get("entityId")
        if ent is None:
            continue
        if ent not in by_entity:
            by_entity[ent] = []
            entity_order.append(ent)
        by_entity[ent].append(f["factId"])
    parent = {e: e for e in entity_order}

    def find(e: str) -> str:
        while parent[e] != e:
            parent[e] = parent[parent[e]]
            e = parent[e]
        return e

    seen_goal = {}
    for f in facts:
        if f["kind"] == "task_achieved":
            if f["goal"] in seen_goal:
                a, b = find(seen_goal[f["goal"]]), find(f["entityId"])
                if a != b:
                    parent[a] = b
            else:
                seen_goal[f["goal"]] = f["entityId"]
    members = {}
    roots = []
    for e in entity_order:
        root = find(e)
        if root not in members:
            members[root] = []
            roots.append(root)
        members[root].extend(by_entity[e])
    groups = [members[r] for r in roots]
    group_of = {fid: gi for gi, g in enumerate(groups) for fid in g}
    for f in facts:  # R3
        if f["kind"] != "time":
            continue
        i = order[f["factId"]]
        target = group_of[facts[i - 1]["factId"]] if i > 0 else 0
        groups[target].append(f["factId"])
    groups = [sorted(g, key=lambda fid: order[fid]) for g in groups]  # R5
    groups.sort(key=lambda g: min(order[fid] for fid in g))
    names = names_map(item)
    sentences = []
    for i, g in enumerate(groups):
        refs = []
        for fid in g:
            f = facts[order[fid]]
            if f.get("entityId"):
                refs.append({"mention": names[f["entityId"]],
                             "refersTo": f["entityId"]})
        sentences.append({"index": i, "factIds": g, "coreference": refs})
    return {"itemId": item["itemId"], "sentences": sentences}


def deep_copy(rows: dict) -> dict:
    return json.loads(json.dumps(rows))


def selftest() -> int:
    failures = []
    items = {r["itemId"]: r for r in load_jsonl(HERE / "d2_capability_items.jsonl")}
    gold_rows = {iid: build_gold_row(item) for iid, item in items.items()}

    base = evaluate(items, gold_rows, deep_copy(gold_rows))
    s = base["summary"]
    if not (s["verdict"]["pass"] and s["h1"] == "8/8" and s["h2"] == "8/8"
            and s["g1"]["f1"] == 1.0 and s["g2Accuracy"] == 1.0
            and s["g3"] == 1.0 and s["g4"] == 1.0):
        failures.append(f"gold-vs-gold not perfect: {json.dumps(s, ensure_ascii=False)[:300]}")

    # T1 fabricated factId -> H1 7/8, verdict False
    plans = deep_copy(gold_rows)
    plans["n3cap-01"]["sentences"][0]["factIds"].append("f99")
    s = evaluate(items, gold_rows, plans)["summary"]
    if s["h1"] != "7/8" or s["verdict"]["pass"]:
        failures.append(f"T1 fabricated factId h1={s['h1']} pass={s['verdict']['pass']}")

    # T2 cross-group referent -> H2 7/8
    plans = deep_copy(gold_rows)
    plans["n3cap-01"]["sentences"][0]["coreference"][0]["refersTo"] = "char_601"
    s = evaluate(items, gold_rows, plans)["summary"]
    if s["h2"] != "7/8" or s["verdict"]["pass"]:
        failures.append(f"T2 cross-group referent h2={s['h2']}")

    # T3 merged-when-gold-split -> G1 < 1
    def t3(r):
        merged = {"factIds": r["sentences"][0]["factIds"] + r["sentences"][1]["factIds"],
                  "coreference": r["sentences"][0]["coreference"] + r["sentences"][1]["coreference"]}
        rest = r["sentences"][2:]
        r["sentences"] = [merged] + rest
        for i, s_ in enumerate(r["sentences"]):
            s_["index"] = i
    plans = deep_copy(gold_rows)
    t3(plans["n3cap-01"])
    s = evaluate(items, gold_rows, plans)["summary"]
    if not (0.8 <= s["g1"]["f1"] < 1.0):
        failures.append(f"T3 merge tamper g1={s['g1']['f1']}")

    # T4 split-when-gold-merged -> G1 < 1
    def t4(r):
        g0 = r["sentences"][0]
        r["sentences"] = [
            {"index": 0, "factIds": g0["factIds"][:2], "coreference": g0["coreference"][:2]},
            {"index": 1, "factIds": g0["factIds"][2:], "coreference": g0["coreference"][2:]},
            {**r["sentences"][1], "index": 2},
            {**r["sentences"][2], "index": 3}]
    plans = deep_copy(gold_rows)
    t4(plans["n3cap-05"])
    s = evaluate(items, gold_rows, plans)["summary"]
    if not (0.8 <= s["g1"]["f1"] < 1.0):
        failures.append(f"T4 split tamper g1={s['g1']['f1']}")

    # T5 wrong antecedent inside a comparable group -> G2 < 1, item entries wrong
    def t5(r):
        refs = r["sentences"][0]["coreference"]
        refs[1], refs[2] = refs[2], refs[1]
    plans = deep_copy(gold_rows)
    t5(plans["n3cap-07"])
    rep = evaluate(items, gold_rows, plans)
    s = rep["summary"]
    if not (s["g2Accuracy"] < 1.0
            and rep["items"]["n3cap-07"]["g2"]["correct"]
            < rep["items"]["n3cap-07"]["g2"]["comparableEntries"]):
        failures.append(f"T5 antecedent swap g2={s['g2Accuracy']}")

    # T6 misplaced time in two items -> G3 < 0.75, verdict False
    def t6(r, item):
        tf = next(f["factId"] for f in item["facts"] if f["kind"] == "time")
        src = next(s_ for s_ in r["sentences"] if tf in s_["factIds"])
        src["factIds"].remove(tf)
        dst = next(s_ for s_ in r["sentences"] if s_ is not src)
        dst["factIds"].append(tf)
    plans = deep_copy(gold_rows)
    t6(plans["n3cap-01"], items["n3cap-01"])
    t6(plans["n3cap-03"], items["n3cap-03"])
    s = evaluate(items, gold_rows, plans)["summary"]
    if not (s["g3"] is not None and s["g3"] < 0.75 and not s["verdict"]["pass"]):
        failures.append(f"T6 time tamper g3={s['g3']}")

    # T7 reordered within group -> G4 < 1
    def t7(r):
        fids = r["sentences"][0]["factIds"]
        fids[0], fids[1] = fids[1], fids[0]
    plans = deep_copy(gold_rows)
    t7(plans["n3cap-03"])
    s = evaluate(items, gold_rows, plans)["summary"]
    if not (s["g4"] is not None and s["g4"] < 1.0):
        failures.append(f"T7 order tamper g4={s['g4']}")

    # T8 pronoun-site drop -> production 0, verdict False
    def t8(r):
        for s_ in r["sentences"]:
            seen = set()
            keep = []
            for ref in s_["coreference"]:
                if ref["refersTo"] in seen:
                    continue
                seen.add(ref["refersTo"])
                keep.append(ref)
            s_["coreference"] = keep
    plans = deep_copy(gold_rows)
    for iid in plans:
        t8(plans[iid])
    s = evaluate(items, gold_rows, plans)["summary"]
    if not (s["pronounProduction"] == 0.0 and not s["verdict"]["pass"]):
        failures.append(f"T8 pronoun-site drop prod={s['pronounProduction']}")

    # T9 uncovered fact -> reported as a problem, item G-metrics void
    plans = deep_copy(gold_rows)
    plans["n3cap-02"]["sentences"][0]["factIds"].remove("f1")
    rep = evaluate(items, gold_rows, plans)
    if not any("plan ids" in p for p in rep["problems"]) \
            or rep["items"]["n3cap-02"]["g1"] is not None:
        failures.append("T9 uncovered fact not reported/voided")

    # T10 legal JSON without coreference key -> structural problem, no crash
    plans = deep_copy(gold_rows)
    for s_ in plans["n3cap-04"]["sentences"]:
        s_.pop("coreference", None)
    rep = evaluate(items, gold_rows, plans)
    if not any("coreference missing" in p for p in rep["problems"]) \
            or rep["summary"]["verdict"]["pass"] \
            or rep["summary"]["h1"] != "7/8" or rep["summary"]["h2"] != "7/8":
        failures.append(f"T10 missing coreference not handled: "
                        f"{rep['summary']['h1']}/{rep['summary']['h2']} pass={rep['summary']['verdict']['pass']}")
    # T11 malformed coreference entries -> structural problem
    plans = deep_copy(gold_rows)
    plans["n3cap-05"]["sentences"][0]["coreference"] = [{"mention": "洛九针"}]
    rep = evaluate(items, gold_rows, plans)
    if not any("malformed" in p or "not a list" in p for p in rep["problems"]):
        failures.append(f"T11 malformed entry not reported: {rep['problems'][:2]}")

    for f in failures:
        print("SELFTEST FAIL:", f)
    print("selftest:", "PASS" if not failures else f"{len(failures)} failure(s)")
    return 1 if failures else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--items", default=str(HERE / "d2_capability_items.jsonl"))
    parser.add_argument("--gold", help="frozen gold plan JSONL")
    parser.add_argument("--plan", help="arm plan JSONL")
    parser.add_argument("--out", help="report JSON path")
    args = parser.parse_args()
    if args.selftest:
        return selftest()
    if not args.gold or not args.plan:
        print("--gold and --plan are required")
        return 2
    items = {r["itemId"]: r for r in load_jsonl(pathlib.Path(args.items))}
    gold_rows = {r["itemId"]: r for r in load_jsonl(pathlib.Path(args.gold))}
    plan_rows = {r["itemId"]: r for r in load_jsonl(pathlib.Path(args.plan))}
    report = evaluate(items, gold_rows, plan_rows)
    payload = {
        "purpose": "D2 N3 arm evaluation (pre-registered metrics)",
        "items": pathlib.Path(args.items).name,
        "gold": pathlib.Path(args.gold).name,
        "plan": pathlib.Path(args.plan).name,
        "report": report,
    }
    text = json.dumps(payload, ensure_ascii=False, indent=1) + "\n"
    if args.out:
        pathlib.Path(args.out).write_text(text, encoding="utf-8", newline="\n")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
