# N3 rule arm (program comparison arm) — implements plan v2
# (design/world-engine-reports/components/n3-program-arm-plan.md).
#
# Generates N3 narrow-shape plans from the SELECTED facts by an INDEPENDENT
# implementation of the frozen rubric R1-R6 (d2-gold-rubric.md). It never
# reads gold, AI labels or build_gold_row on the generation path, and has
# no per-item branches; d2_metrics.build_gold_row is used only as a
# post-hoc DIFFERENTIAL check (report-148f412 lineage), compared on the
# same selected fact set (for diagnostic16 a temp item with facts =
# target ∩ facts is constructed first).
#
# Bindings (review round on plan v2, notes 1-3):
#   - the pre-run registration file (artifacts/world-components/
#     n3-rulearm-registration.json) pins THIS file's bytes, the reused
#     gate/runner module bytes, the metric tool bytes, both scope input
#     hashes, the gold pin and the boundary behaviours; every run verifies
#     them and refuses on drift — including the reused run_n3_arm gate
#     functions' actual module bytes;
#   - archive hashes are NOT written into the archives themselves; they
#     live in the separate delivery note, so no archive self-references;
#   - unsupported/ill-formed boundaries refuse to produce an official plan
#     (reasons listed in the archive); consecutive-time handling is an
#     exploration probe only and never enters a gate archive.

import argparse
import hashlib
import json
import pathlib
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import d2_metrics as dm  # noqa: E402
import n3_plan  # noqa: E402  (indirect dependency of d2_metrics; pinned)
import run_n3_arm as rn  # noqa: E402

REPO_ROOT = rn.REPO_ROOT
DEFAULT_REGISTRATION = REPO_ROOT / "artifacts/world-components/n3-rulearm-registration.json"


def sha_file(path) -> str:
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def load_jsonl(path) -> list:
    return rn.load_jsonl(path)


KNOWN_KINDS = {"moved", "positioned_at", "task_achieved", "personality_changed",
               "sanity_changed", "appearance_changed", "time", "no_change"}


def ill_formed(selected_facts: list) -> list:
    problems = []
    ids = [f.get("factId") for f in selected_facts]
    if any(not isinstance(x, str) or not x for x in ids):
        problems.append("missing or non-string factId")
    if len(set(ids)) != len(ids):
        problems.append("duplicate factId")
    for f in selected_facts:
        if f.get("kind") not in KNOWN_KINDS:
            problems.append(f"unknown kind {f.get('kind')!r} for {f.get('factId')}")
        if f.get("kind") == "task_achieved" and not isinstance(f.get("goal"), str):
            problems.append(f"task_achieved without string goal: {f.get('factId')}")
    return problems


def rule_plan(item: dict, selected_facts: list):
    """independent R1-R6 implementation.
    -> (plan, None) on success, (None, {"class", "reason"}) on refusal."""
    problems = ill_formed(selected_facts)
    if problems:
        return None, {"class": "ill-formed", "reason": "; ".join(problems)}
    order = {f["factId"]: i for i, f in enumerate(selected_facts)}
    names = {f["entityId"]: f["name"] for f in selected_facts if f.get("entityId")}

    # R1: entity buckets in first-appearance order
    buckets = {}
    entity_order = []
    for f in selected_facts:
        e = f.get("entityId")
        if e is None:
            continue
        if e not in buckets:
            buckets[e] = []
            entity_order.append(e)
        buckets[e].append(f["factId"])
    if not entity_order:
        if any(f["kind"] == "time" for f in selected_facts):
            return None, {"class": "unsupported",
                          "reason": "time-orphan: time with no entity fact to "
                                    "attach to; a lone-time group exceeds the "
                                    "frozen leading-time interpretation"}
        return None, {"class": "unsupported",
                      "reason": "no-entity: no fact carries an entityId; an "
                                "empty plan would drop selected facts"}

    # R2: union-find over entities via verbatim task goals (transitive)
    parent = {e: e for e in entity_order}

    def find(e):
        while parent[e] != e:
            parent[e] = parent[parent[e]]
            e = parent[e]
        return e

    seen_goal = {}
    for f in selected_facts:
        if f["kind"] == "task_achieved":
            g = f["goal"]
            if g in seen_goal:
                a, b = find(seen_goal[g]), find(f["entityId"])
                if a != b:
                    parent[a] = b
            else:
                seen_goal[g] = f["entityId"]

    groups = []  # list of member factIds (entities merged, in input order)
    group_of_entity = {}
    for e in entity_order:
        root = find(e)
        if root not in group_of_entity:
            group_of_entity[root] = len(groups)
            groups.append([])
        groups[group_of_entity[root]].extend(buckets[e])
    entity_group_of = {}
    for gi, g in enumerate(groups):
        for fid in g:
            f = selected_facts[order[fid]]
            entity_group_of[f["entityId"]] = gi

    # R3: time facts join the input-order predecessor's group (or the
    # group of the first entity fact when leading)
    edges = {"consecutive-time": False}
    group_of = {fid: gi for gi, g in enumerate(groups) for fid in g}
    placed_times = {}
    for i, f in enumerate(selected_facts):
        if f["kind"] != "time":
            continue
        if i == 0:
            target = group_of[entity_order_first(selected_facts, order)]
        else:
            pred = selected_facts[i - 1]
            if pred["kind"] == "time":
                edges["consecutive-time"] = True
                target = placed_times[pred["factId"]]
            elif pred.get("entityId"):
                target = entity_group_of[pred["entityId"]]
            else:
                target = group_of[entity_order_first(selected_facts, order)]
        groups[target].append(f["factId"])
        placed_times[f["factId"]] = target

    # R5: within-group by input index; groups by minimal input index
    groups = [sorted(g, key=lambda fid: order[fid]) for g in groups]
    groups.sort(key=lambda g: min(order[fid] for fid in g))

    # R6: one coreference entry per entity fact, in factIds order
    sentences = []
    for gi, g in enumerate(groups):
        refs = []
        for fid in g:
            f = selected_facts[order[fid]]
            if f.get("entityId"):
                refs.append({"mention": names[f["entityId"]],
                             "refersTo": f["entityId"]})
        sentences.append({"index": gi, "factIds": g, "coreference": refs})
    return {"itemId": item["itemId"], "sentences": sentences, "edges": edges}, None


def entity_order_first(selected_facts: list, order: dict) -> str:
    for f in selected_facts:
        if f.get("entityId"):
            return f["factId"]
    raise AssertionError("unreachable: no-entity refused earlier")


def check_bindings(args, registration: dict) -> list:
    """every byte this run actually executes or consumes must match the
    pre-run registration (plan v2 note 3; review of c66236b items 2-3):
    the rule arm, the reused gate module, the metric tool, its indirect
    n3_plan dependency, the consumed freeze record, the consumed items
    file and the consumed gold file."""
    problems = []
    self_sha = sha_file(pathlib.Path(__file__))
    if registration.get("ruleArm", {}).get("sha256") != self_sha:
        problems.append(f"rule arm bytes drifted from registration "
                        f"({self_sha} != {registration['ruleArm'].get('sha256')})")
    rn_sha = sha_file(pathlib.Path(rn.__file__))
    want_rn = registration.get("dependencies", {}).get("run_n3_arm", {}).get("sha256")
    if want_rn != rn_sha:
        problems.append(f"reused gate module run_n3_arm drifted "
                        f"({rn_sha} != {want_rn}); refusing to execute")
    dm_sha = sha_file(pathlib.Path(dm.__file__))
    want_dm = registration.get("dependencies", {}).get("d2_metrics", {}).get("sha256")
    if want_dm != dm_sha:
        problems.append(f"metric tool drifted ({dm_sha} != {want_dm})")
    n3_sha = sha_file(pathlib.Path(n3_plan.__file__))
    want_n3 = registration.get("dependencies", {}).get("n3_plan", {}).get("sha256")
    if want_n3 != n3_sha:
        problems.append(f"indirect dependency n3_plan drifted "
                        f"({n3_sha} != {want_n3}); structural verdicts could change")
    freeze = json.loads(pathlib.Path(args.freeze).read_text(encoding="utf-8"))
    fm_problems, _fm_sha = rn.check_metric_tool(freeze)
    problems.extend(fm_problems)
    want_gold = (freeze.get("evaluation", {}).get("gold") or {}).get("sha256")
    if registration.get("gold", {}).get("sha256") != want_gold:
        problems.append("registration gold pin disagrees with the freeze record")
    # consumed files vs the registration pins (review of c66236b item 2):
    # a drifted freeze record or items file must refuse even when the
    # registration itself names the drifted bytes as expected.
    consumed = {
        "freezeRecord": (args.freeze, registration.get("freezeRecord", {}).get("sha256")),
        "inputs": (args.items, (registration.get("inputs", {}).get(
            "diagnostic16Items" if args.scope == "diagnostic16" else "gate8Items")
            or {}).get("sha256")),
    }
    if args.gold:
        consumed["gold"] = (args.gold, registration.get("gold", {}).get("sha256"))
    for label, (path, want) in consumed.items():
        got = sha_file(path)
        if want is None:
            problems.append(f"registration has no {label} pin to verify {path}")
        elif got != want:
            problems.append(f"consumed {label} bytes {got} != registration pin "
                            f"{want} ({path})")
    return problems


def run(args) -> int:
    registration = json.loads(pathlib.Path(args.registration).read_text(encoding="utf-8"))
    problems = check_bindings(args, registration)
    if problems:
        for p in problems:
            print("GATE:", p)
        return 3
    freeze = json.loads(pathlib.Path(args.freeze).read_text(encoding="utf-8"))
    diagnostic = args.scope == "diagnostic16"

    items = {r["itemId"]: r for r in load_jsonl(args.items)}
    item_problems = rn.check_items_binding(pathlib.Path(args.items), args.scope,
                                           items, REPO_ROOT)
    if item_problems:
        for p in item_problems:
            print("PROBLEM:", p)
        return 2

    gold_rows = {}
    if not diagnostic:
        if not args.gold:
            print("gate8 scope requires --gold")
            return 2
        problem = dm.check_gold_sha(args.gold, freeze["evaluation"]["gold"]["sha256"])
        if problem:
            print("PROBLEM:", problem)
            return 2
        gold_rows = {r["itemId"]: r for r in load_jsonl(args.gold)}

    plans = {}
    refusals = {}
    timings = {}
    started = time.perf_counter()
    for iid, item in items.items():
        selected = rn.selected_facts_of(item, selected_from_target=diagnostic)
        t0 = time.perf_counter()
        plan, refusal = rule_plan(item, selected)
        timings[iid] = round(time.perf_counter() - t0, 6)
        if plan is None:
            refusals[iid] = refusal
            continue
        problems = classify(plan, item, selected)
        if problems:
            refusals[iid] = {"class": "structural", "reason": problems[0]}
            continue
        plans[iid] = plan
    total_wall = round(time.perf_counter() - started, 4)

    if diagnostic:
        report = dm.evaluate(items, {}, plans, diagnostic=True,
                             selected_from_target=True)
    else:
        report = dm.evaluate(items, gold_rows, plans)

    # N4 boundary: marking only, no splitting (plan v2 section 4)
    over = [{"itemId": iid, "groupIndex": s["index"], "facts": len(s["factIds"])}
            for iid, p in plans.items() for s in p["sentences"]
            if len(s["factIds"]) > 4]

    # B1/B2 historical comparison, listed separately and never part of the
    # rule arm verdict (gate8 only: the baselines are an 8-item reference)
    baselines = None
    if gold_rows:
        baselines = {}
        for name, fn in (("B1", n3_plan.plan_b1), ("B2", n3_plan.plan_b2)):
            rows = {}
            for iid, item in items.items():
                generated = fn(item["facts"], dm.names_map(item))
                rows[iid] = {"itemId": iid, "sentences": generated["sentences"]}
            s_ = dm.evaluate(items, gold_rows, rows)["summary"]
            baselines[name] = {"h1": s_["h1"], "h2": s_["h2"],
                               "g1F1": s_["g1"]["f1"],
                               "pronounProduction": s_["pronounProduction"],
                               "g3": s_["g3"], "gate": s_["gate"],
                               "pass": s_["verdict"]["pass"],
                               "note": "historical comparison only; not part "
                                       "of the rule arm verdict"}

    # differential vs the reference convention function, on the SAME
    # selected fact set (a temp item is built for diagnostic16)
    differential = {"compared": 0, "identical": 0, "mismatches": [],
                    "inapplicable": []}
    for iid, item in items.items():
        selected = rn.selected_facts_of(item, selected_from_target=diagnostic)
        if iid in refusals:
            differential["inapplicable"].append(
                {"itemId": iid, "reason": refusals[iid]["class"]})
            continue
        ref_item = {**item, "facts": selected}
        ref_plan = dm.build_gold_row(ref_item)
        differential["compared"] += 1
        if ref_plan["sentences"] == plans[iid]["sentences"]:
            differential["identical"] += 1
        else:
            differential["mismatches"].append(iid)

    archive = {
        "purpose": "D2 N3 rule arm run (program comparison arm)",
        "scope": args.scope,
        "registration": pathlib.Path(args.registration).name,
        "registrationSha256": sha_file(args.registration),
        "ruleArmSha256": sha_file(pathlib.Path(__file__)),
        "metricToolSha256": sha_file(pathlib.Path(dm.__file__)),
        "gateModuleSha256": sha_file(pathlib.Path(rn.__file__)),
        "goldExpectedSha256": freeze["evaluation"]["gold"]["sha256"] if not diagnostic else None,
        "items": pathlib.Path(args.items).name,
        "gold": pathlib.Path(args.gold).name if args.gold else None,
        "timingsPerItem": timings,
        "totalWall": total_wall,
        "timingNote": "offline CPU generation only; not comparable with model inference",
        "differential": differential,
        "n4OutOfRange": over,
        "plans": plans,
        "itemOutcomes": {iid: ("ok" if iid in plans else refusals[iid])
                         for iid in items},
        "baselines": baselines,
        "report": report,
    }
    text = json.dumps(archive, ensure_ascii=False, indent=1) + "\n"
    if args.out:
        pathlib.Path(args.out).write_text(text, encoding="utf-8", newline="\n")
    s = report["summary"]
    print(f"scope={args.scope} items={len(items)} ok={len(plans)} "
          f"refused={len(refusals)} differential={differential['identical']}/"
          f"{differential['compared']} n4OutOfRange={len(over)}")
    print(f"h1={s['h1']} h2={s['h2']} g1={s['g1']['f1']:.4f} gate={s['gate']} "
          f"diagnostic={s['diagnostic']} pass={s['verdict']['pass']}")
    if args.out:
        print(f"archive -> {args.out}")
    return 0


def classify(plan, item, selected_facts) -> list:
    """runner-side structural re-check of the generated plan (reuses the
    runner's own classifier, review note 3)."""
    return rn.classify_plan(plan, item, selected_facts)


def run_probes(out) -> int:
    """T-P1..T-P7 on synthetic items (plan v2 section 3); independent of
    the 8 registered items and their answers."""
    results = {}

    def mk(item_id, name_a, name_b, facts):
        return {"itemId": item_id, "task": "n3-plan", "split": "probe",
                "batch": "rulearm-probes",
                "viewpoint": {"type": "protagonist", "entityId": facts[0].get("entityId") or "char_p0",
                              "name": name_a, "at": "探针镇", "rule": "probe"},
                "facts": facts, "hashes": {"facts": "probe"}}

    def task(fid, char, name, goal, at="探针镇"):
        return {"factId": fid, "kind": "task_achieved", "entityId": char,
                "name": name, "goal": goal, "at": at}

    # T-P1 transitive merge: A~B via g1, B~C via g2 -> one group
    p1_item = mk("probe-p1", "甲一", "乙二", [
        task("f1", "char_pa", "甲一", "合力修桥"), task("f2", "char_pb", "乙二", "合力修桥"),
        task("f3", "char_pb", "乙二", "合力清淤"), task("f4", "char_pc", "丙三", "合力清淤")])
    plan, err = rule_plan(p1_item, p1_item["facts"])
    results["T-P1"] = (err is None and len(plan["sentences"]) == 1
                       and plan["sentences"][0]["factIds"] == ["f1", "f2", "f3", "f4"])
    # T-P2 leading time joins the first entity group
    p2_item = mk("probe-p2", "甲一", "乙二", [
        {"factId": "f1", "kind": "time", "amount": 3, "unit": "minute", "at": None},
        task("f2", "char_pa", "甲一", "晒网"), task("f3", "char_pb", "乙二", "补网")])
    plan, err = rule_plan(p2_item, p2_item["facts"])
    results["T-P2"] = (err is None and plan["sentences"][0]["factIds"] == ["f1", "f2"]
                       and len(plan["sentences"]) == 2)
    # T-P3a reorder with the IMMEDIATE predecessor preserved -> same grouping
    base = [task("f1", "char_pa", "甲一", "晒网"), task("f2", "char_pa", "甲一", "织网"),
            {"factId": "f3", "kind": "time", "amount": 4, "unit": "minute", "at": None},
            task("f4", "char_pb", "乙二", "补网")]
    reordered = [base[3], base[0], base[1], base[2]]  # f3 still right after f2
    pa, _ = rule_plan(mk("probe-p3a", "甲一", "乙二", base), base)
    pb, _ = rule_plan(mk("probe-p3a", "甲一", "乙二", reordered), reordered)
    groups_a = sorted(sorted(s["factIds"]) for s in pa["sentences"])
    groups_b = sorted(sorted(s["factIds"]) for s in pb["sentences"])
    results["T-P3a"] = groups_a == groups_b == [["f1", "f2", "f3"], ["f4"]]
    # T-P3b predecessor changed -> time follows the new predecessor's group
    moved = [base[0], base[1], base[3], base[2]]  # f3 now right after f4
    pc, _ = rule_plan(mk("probe-p3b", "甲一", "乙二", moved), moved)
    results["T-P3b"] = (pc is not None and
                        pc["sentences"][-1]["factIds"] == ["f4", "f3"] and
                        len(pc["sentences"]) == 2)
    # T-P4 same name, different entityIds -> separate groups, same mention
    p4_item = mk("probe-p4", "甲一", "乙二", [
        task("f1", "char_pd", "同名者", "扫地"), task("f2", "char_pe", "同名者", "洗碗")])
    plan, err = rule_plan(p4_item, p4_item["facts"])
    all_refs = [r for s in (plan["sentences"] if err is None else [])
                for r in s["coreference"]]
    results["T-P4"] = (err is None and len(plan["sentences"]) == 2 and
                        all_refs == [{"mention": "同名者", "refersTo": "char_pd"},
                                     {"mention": "同名者", "refersTo": "char_pe"}])
    # T-P5 illegal inputs refuse
    bad_kind = mk("probe-p5a", "甲一", "乙二", [
        {"factId": "f1", "kind": "teleported", "entityId": "char_pd", "name": "同名者"}])
    _, err = rule_plan(bad_kind, bad_kind["facts"])
    r1 = err is not None and err["class"] == "ill-formed"
    dup = mk("probe-p5b", "甲一", "乙二", [task("f1", "char_pd", "同名者", "扫地"),
                                          task("f1", "char_pe", "同名者", "洗碗")])
    _, err = rule_plan(dup, dup["facts"])
    r2 = err is not None and err["class"] == "ill-formed"
    results["T-P5"] = r1 and r2
    # T-P6 unsupported boundaries refuse official plans
    orphan = mk("probe-p6a", "甲一", "乙二", [
        {"factId": "f1", "kind": "time", "amount": 2, "unit": "minute", "at": None}])
    _, err = rule_plan(orphan, orphan["facts"])
    r1 = err is not None and err["class"] == "unsupported" and "time-orphan" in err["reason"]
    noent = mk("probe-p6b", "甲一", "乙二", [
        {"factId": "f1", "kind": "no_change", "scope": "探针镇", "at": "探针镇"}])
    _, err = rule_plan(noent, noent["facts"])
    r2 = err is not None and err["class"] == "unsupported" and "no-entity" in err["reason"]
    results["T-P6"] = r1 and r2
    # T-P7 consecutive time: reproducible by the R3 definition (exploration
    # only; never part of the frozen gate)
    p7_item = mk("probe-p7", "甲一", "乙二", [
        task("f1", "char_pa", "甲一", "晒网"),
        {"factId": "f2", "kind": "time", "amount": 2, "unit": "minute", "at": None},
        {"factId": "f3", "kind": "time", "amount": 3, "unit": "minute", "at": None}])
    plan, err = rule_plan(p7_item, p7_item["facts"])
    results["T-P7"] = (err is None and plan["sentences"][0]["factIds"] == ["f1", "f2", "f3"]
                       and plan["edges"] == {"consecutive-time": True})
    ok = all(results.values())
    payload = {"purpose": "N3 rule arm independent probes (T-P1..T-P7)",
               "results": {k: bool(v) for k, v in results.items()},
               "pass": ok}
    text = json.dumps(payload, ensure_ascii=False, indent=1) + "\n"
    if out:
        pathlib.Path(out).write_text(text, encoding="utf-8", newline="\n")
    print(text)
    return 0 if ok else 1


def selftest() -> int:
    failures = []
    # generator unit checks on synthetic items
    def task(fid, char, name, goal):
        return {"factId": fid, "kind": "task_achieved", "entityId": char,
                "name": name, "goal": goal, "at": "潮音渡"}
    facts = [task("f1", "char_x", "洛九针", "晒网"),
             {"factId": "f2", "kind": "time", "amount": 1, "unit": "minute", "at": None},
             task("f3", "char_x", "洛九针", "织网")]
    item = {"itemId": "u1", "facts": facts}
    plan, err = rule_plan(item, facts)
    if err is not None or plan["sentences"][0]["factIds"] != ["f1", "f2", "f3"] \
            or len(plan["sentences"][0]["coreference"]) != 2:
        failures.append(f"leading-time unit failed: {err}")
    # binding checks: consumed freeze/items/gold vs registration, and the
    # indirect n3_plan dependency pin (review of c66236b items 2-3)
    import tempfile
    with tempfile.TemporaryDirectory() as td1:
        b = pathlib.Path(td1)
        dm_sha = sha_file(pathlib.Path(dm.__file__))
        (b / "gold.jsonl").write_text("gold", encoding="utf-8")
        gold_sha = sha_file(b / "gold.jsonl")
        (b / "freeze.json").write_text(json.dumps(
            {"evaluation": {"metricTool": {"sha256": dm_sha},
                            "gold": {"sha256": gold_sha}}}), encoding="utf-8")
        (b / "items.jsonl").write_text("rows", encoding="utf-8")
        reg = {"ruleArm": {"sha256": sha_file(pathlib.Path(__file__))},
               "dependencies": {"run_n3_arm": {"sha256": sha_file(pathlib.Path(rn.__file__))},
                                "d2_metrics": {"sha256": dm_sha},
                                "n3_plan": {"sha256": sha_file(pathlib.Path(n3_plan.__file__))}},
               "gold": {"sha256": gold_sha},
               "freezeRecord": {"sha256": sha_file(b / "freeze.json")},
               "inputs": {"gate8Items": {"sha256": sha_file(b / "items.jsonl")}}}
        ns = argparse.Namespace(freeze=str(b / "freeze.json"),
                                items=str(b / "items.jsonl"),
                                gold=str(b / "gold.jsonl"), scope="gate8")
        if check_bindings(ns, reg):
            failures.append("consistent registration produced problems")
        bad = json.loads(json.dumps(reg))
        bad["freezeRecord"]["sha256"] = "0" * 64
        if not [x for x in check_bindings(ns, bad) if "freezeRecord bytes" in x]:
            failures.append("consumed freeze drift not refused")
        bad2 = json.loads(json.dumps(reg))
        bad2["inputs"]["gate8Items"]["sha256"] = "0" * 64
        if not [x for x in check_bindings(ns, bad2) if "inputs bytes" in x]:
            failures.append("consumed items drift not refused")
        bad3 = json.loads(json.dumps(reg))
        bad3["dependencies"]["n3_plan"]["sha256"] = "0" * 64
        if not [x for x in check_bindings(ns, bad3) if "n3_plan drifted" in x]:
            failures.append("n3_plan dependency drift not refused")
    for f in failures:
        print("SELFTEST FAIL:", f)
    # the probe suite doubles as the generator's behavioural test
    rc = run_probes(None)
    if rc != 0:
        failures.append("probe suite failed")
    print("selftest:", "PASS" if not failures else f"{len(failures)} failure(s)")
    return 1 if failures else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--probes", action="store_true")
    parser.add_argument("--registration", default=str(DEFAULT_REGISTRATION))
    parser.add_argument("--items", default=str(HERE / "d2_capability_items.jsonl"))
    parser.add_argument("--scope", choices=["gate8", "diagnostic16"], default="gate8")
    parser.add_argument("--gold",
                        default=str(REPO_ROOT / "artifacts/world-components/n2-labels-d2-gold.jsonl"))
    parser.add_argument("--freeze",
                        default=str(REPO_ROOT / "artifacts/world-components/d2-n3-prompt-freeze.json"))
    parser.add_argument("--out", default=None)
    args = parser.parse_args()
    if args.selftest:
        return selftest()
    if args.probes:
        return run_probes(args.out)
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
