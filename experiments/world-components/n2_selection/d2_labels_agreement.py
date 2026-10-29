# D2 gold inter-annotator agreement, adjudication and freeze (D2 prep).
#
# Consumes two independent AI label files for the 8 capability items and
# the pre-registered protocol (annotation/d2-gold-protocol.json):
#   1. validates each label against the N3 narrow shape (I1 coverage via
#      n3_plan.check_invariants + strict coreference count/order/name
#      alignment + sentence index continuity),
#   2. computes the pre-registered agreement: pooled pairwise co-grouping
#      Cohen's kappa over all unordered fact pairs, plus report-only order
#      concordance and coreference agreement over comparable groups
#      (identical factId sets in both labels),
#   3. enforces the gates: kappa >= protocol.kappaMinimum and EVERY
#      disagreeing item adjudicated (source tag + written reason),
#   4. freezes: writes the frozen label JSONL and an evidence JSON with
#      hashes, kappa tables and the adjudication record.
#
# The tool never edits labels; disagreement resolution happens in the
# adjudicated file passed on the command line.

import argparse
import hashlib
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from n3_plan import check_invariants  # noqa: E402


def sha_file(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_jsonl(path: pathlib.Path) -> list:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def load_items(path: pathlib.Path) -> dict:
    items = {}
    for row in load_jsonl(path):
        items[row["itemId"]] = row
    return items


def names_map(item: dict) -> dict:
    return {f["entityId"]: f["name"] for f in item["facts"] if f.get("entityId")}


def validate_label(row: dict, item: dict, tag: str) -> list:
    problems = []
    if row.get("itemId") != item["itemId"]:
        problems.append(f"{tag}: itemId mismatch {row.get('itemId')!r}")
        return problems
    sentences = row.get("sentences")
    if not isinstance(sentences, list) or not sentences:
        problems.append(f"{tag}: sentences missing or empty")
        return problems
    want_index = list(range(len(sentences)))
    if [s.get("index") for s in sentences] != want_index:
        problems.append(f"{tag}: sentence index not 0..n-1 contiguous")
    names = names_map(item)
    plan = {"baseline": tag, "sentences": sentences}
    problems.extend(check_invariants(plan, item["facts"], names))
    facts_by_id = {f["factId"]: f for f in item["facts"]}
    for s in sentences:
        group = [facts_by_id.get(fid) for fid in s.get("factIds", [])]
        with_entity = [f for f in group if f is not None and f.get("entityId")]
        refs = s.get("coreference", [])
        if len(refs) != len(with_entity):
            problems.append(
                f"{tag}: item {item['itemId']} group {s.get('index')}: "
                f"coreference has {len(refs)} entries, expected {len(with_entity)} "
                "(one per entity fact, in factIds order)")
            continue
        for ref, fact in zip(refs, with_entity):
            if ref.get("refersTo") != fact["entityId"]:
                problems.append(
                    f"{tag}: item {item['itemId']} group {s.get('index')}: "
                    f"coreference not aligned with factIds order "
                    f"({ref.get('refersTo')!r} vs {fact['entityId']!r})")
    return problems


def pair_sets(row: dict, item: dict) -> set:
    ids = [f["factId"] for f in item["facts"]]
    group_of = {}
    for s in row["sentences"]:
        for fid in s["factIds"]:
            group_of[fid] = s["index"]
    return {frozenset((a, b))
            for i, a in enumerate(ids) for b in ids[i + 1:]
            if group_of[a] == group_of[b]}


def order_pairs(row: dict, item: dict) -> set:
    """within-group relative order as a set of ordered pairs"""
    ids = [f["factId"] for f in item["facts"]]
    group_of = {}
    for s in row["sentences"]:
        for fid in s["factIds"]:
            group_of[fid] = s["index"]
    return {(a, b) for i, a in enumerate(ids) for b in ids[i + 1:]
            if group_of[a] == group_of[b]}


def kappa_from_table(a: int, b: int, c: int, d: int) -> float:
    """2x2 table: a=both yes, b=A only, c=B only, d=neither"""
    n = a + b + c + d
    if n == 0:
        raise ValueError("empty table")
    po = (a + d) / n
    pe = ((a + b) * (a + c) + (c + d) * (b + d)) / (n * n)
    if pe == 1.0:
        raise ValueError("degenerate table (expected agreement = 1)")
    return (po - pe) / (1 - pe)


def coref_comparable(a_row: dict, b_row: dict) -> tuple:
    """(entries_compared, entries_equal, comparable_groups, total_groups)"""
    a_groups = {frozenset(s["factIds"]): s for s in a_row["sentences"]}
    b_groups = {frozenset(s["factIds"]): s for s in b_row["sentences"]}
    compared = equal = comparable = 0
    for key, a_s in a_groups.items():
        if key not in b_groups:
            continue
        comparable += 1
        a_refs = a_s.get("coreference", [])
        b_refs = b_groups[key].get("coreference", [])
        if len(a_refs) != len(b_refs):
            compared += max(len(a_refs), len(b_refs))
            continue
        for ra, rb in zip(a_refs, b_refs):
            compared += 1
            if ra == rb:
                equal += 1
    return compared, equal, comparable, len(a_groups)


def compare_items(items: dict, a_rows: dict, b_rows: dict) -> dict:
    table = {"both": 0, "aOnly": 0, "bOnly": 0, "neither": 0}
    per_item = {}
    order_total = order_agree = 0
    coref_comp = coref_eq = 0
    comparable_groups = total_groups = 0
    disagreeing = []
    for iid, item in items.items():
        a_pairs = pair_sets(a_rows[iid], item)
        b_pairs = pair_sets(b_rows[iid], item)
        ids = [f["factId"] for f in item["facts"]]
        t = {"both": 0, "aOnly": 0, "bOnly": 0, "neither": 0}
        for i, x in enumerate(ids):
            for y in ids[i + 1:]:
                key = frozenset((x, y))
                ay, by = key in a_pairs, key in b_pairs
                if ay and by:
                    t["both"] += 1
                elif ay:
                    t["aOnly"] += 1
                elif by:
                    t["bOnly"] += 1
                else:
                    t["neither"] += 1
        for k in table:
            table[k] += t[k]
        a_order = order_pairs(a_rows[iid], item)
        b_order = order_pairs(b_rows[iid], item)
        for p in a_pairs & b_pairs:
            order_total += 1
            if (p in a_order) == (p in b_order):
                order_agree += 1
        c_comp, c_eq, comp_groups, tot_groups = coref_comparable(a_rows[iid], b_rows[iid])
        coref_comp += c_comp
        coref_eq += c_eq
        comparable_groups += comp_groups
        total_groups += tot_groups
        differs = (a_pairs != b_pairs
                   or a_rows[iid]["sentences"] != b_rows[iid]["sentences"])
        per_item[iid] = {"table": t, "groupingDiffers": a_pairs != b_pairs,
                         "labelsDiffer": differs}
        if differs:
            disagreeing.append(iid)
    return {"table": table, "perItem": per_item, "disagreeingItems": disagreeing,
            "orderConcordance": {"agreed": order_agree, "of": order_total},
            "coref": {"equal": coref_eq, "compared": coref_comp,
                      "comparableGroups": comparable_groups,
                      "totalGroups": total_groups}}


def validate_adjudication(items: dict, adjud_rows: dict, disagreeing: list) -> list:
    problems = []
    for iid in disagreeing:
        row = adjud_rows.get(iid)
        if row is None:
            problems.append(f"adjudication missing for disagreeing item {iid}")
            continue
        tag = row.get("source")
        if tag not in ("ai-a", "ai-b", "merged"):
            problems.append(f"{iid}: adjudication source tag invalid: {tag!r}")
        if not isinstance(row.get("reason"), str) or len(row.get("reason", "").strip()) < 4:
            problems.append(f"{iid}: adjudication reason missing or too short")
        label = row.get("label")
        if not isinstance(label, dict):
            problems.append(f"{iid}: adjudication label object missing")
            continue
        problems.extend(validate_label(label, items[iid], f"adjudicated:{iid}"))
    return problems


def run(args) -> int:
    items = load_items(pathlib.Path(args.items))
    a_rows = {r["itemId"]: r for r in load_jsonl(pathlib.Path(args.labels_a))}
    b_rows = {r["itemId"]: r for r in load_jsonl(pathlib.Path(args.labels_b))}
    protocol = json.loads(pathlib.Path(args.protocol).read_text(encoding="utf-8"))
    problems = []
    if sorted(items) != sorted(a_rows) or sorted(items) != sorted(b_rows):
        problems.append("label files must cover exactly the item ids")
    for iid, item in items.items():
        if iid in a_rows:
            problems.extend(validate_label(a_rows[iid], item, "ai-a"))
        if iid in b_rows:
            problems.extend(validate_label(b_rows[iid], item, "ai-b"))
    if problems:
        for p in problems:
            print("PROBLEM:", p)
        return 1
    cmp = compare_items(items, a_rows, b_rows)
    t = cmp["table"]
    try:
        kappa = kappa_from_table(t["both"], t["aOnly"], t["bOnly"], t["neither"])
    except ValueError as exc:
        print("KAPPA DEGENERATE:", exc)
        return 1
    minimum = protocol["gates"]["kappaMinimum"]
    disagreeing = cmp["disagreeingItems"]
    adjud_rows = {}
    if disagreeing:
        if not args.adjudicated:
            print(f"ADJUDICATION REQUIRED: {len(disagreeing)} disagreeing item(s): {disagreeing}")
            return 1
        for row in load_jsonl(pathlib.Path(args.adjudicated)):
            adj = dict(row)
            adjud_rows[adj.pop("itemId")] = adj
        problems.extend(validate_adjudication(items, adjud_rows, disagreeing))
        if problems:
            for p in problems:
                print("PROBLEM:", p)
            return 1
    verdict = "PASS" if kappa >= minimum else "FAIL"
    print(f"kappa={kappa:.4f} (minimum {minimum}) -> {verdict}")
    print(f"pair table: {t}")
    print(f"disagreeing items: {disagreeing or 'none'}")
    print(f"order concordance: {cmp['orderConcordance']}")
    print(f"coref agreement: {cmp['coref']}")
    if verdict == "FAIL":
        return 1
    if args.out:
        frozen_rows = []
        for iid in items:
            if iid in adjud_rows:
                frozen_rows.append(adjud_rows[iid]["label"])
            elif a_rows[iid]["sentences"] == b_rows[iid]["sentences"]:
                frozen_rows.append(a_rows[iid])
            else:  # pragma: no cover - guarded by adjudication requirement
                raise AssertionError(f"{iid} differs but has no adjudication")
        out_path = pathlib.Path(args.out)
        frozen_path = out_path.parent / args.freeze_labels
        frozen_path.write_text(
            "\n".join(json.dumps(r, ensure_ascii=False) for r in frozen_rows) + "\n",
            encoding="utf-8", newline="\n")
        record = {
            "purpose": "D2 gold freeze (AI independent annotation)",
            "decision": "D2",
            "annotationProtocol": pathlib.Path(args.protocol).name,
            "protocolSha256": sha_file(pathlib.Path(args.protocol)),
            "items": pathlib.Path(args.items).name,
            "itemsSha256": sha_file(pathlib.Path(args.items)),
            "labelsA": {"file": pathlib.Path(args.labels_a).name,
                        "sha256": sha_file(pathlib.Path(args.labels_a))},
            "labelsB": {"file": pathlib.Path(args.labels_b).name,
                        "sha256": sha_file(pathlib.Path(args.labels_b))},
            "kappa": {"definition": protocol["gates"]["kappaDefinition"],
                      "value": kappa, "minimum": minimum, "verdict": verdict,
                      "pairTable": t},
            "orderConcordance": cmp["orderConcordance"],
            "corefAgreement": cmp["coref"],
            "disagreeingItems": disagreeing,
            "adjudication": {iid: {"source": adjud_rows[iid].get("source"),
                                   "reason": adjud_rows[iid].get("reason")}
                             for iid in disagreeing} if disagreeing else None,
            "frozenLabels": {"file": frozen_path.name,
                             "sha256": sha_file(frozen_path)},
            "limitations": protocol["limitations"],
        }
        out_path.write_text(json.dumps(record, ensure_ascii=False, indent=1) + "\n",
                            encoding="utf-8", newline="\n")
        print(f"froze {len(frozen_rows)} labels -> {frozen_path.name}; record -> {out_path.name}")
    return 0


def selftest() -> int:
    failures = []

    def fact(fid, char, name):
        return {"factId": fid, "kind": "task_achieved", "entityId": char,
                "name": name, "goal": f"目标{fid}", "at": "潮音渡"}

    facts = [fact("f1", "char_600", "洛九针"), fact("f2", "char_601", "孟潮生"),
             fact("f3", "char_602", "温白山"), fact("f4", "char_603", "桑晚照")]
    item = {"itemId": "n3cap-t1", "task": "n3-plan", "split": "dev", "batch": "d2",
            "viewpoint": {"type": "protagonist", "entityId": "char_600",
                          "name": "洛九针", "at": "潮音渡", "rule": "r"},
            "facts": facts, "hashes": {"facts": "x"}}
    ref = {"f1": "char_600", "f2": "char_601", "f3": "char_602", "f4": "char_603"}
    mention = {"f1": "洛九针", "f2": "孟潮生", "f3": "温白山", "f4": "桑晚照"}

    def label(groups):
        return {"itemId": "n3cap-t1",
                "sentences": [{"index": i, "factIds": list(g),
                               "coreference": [{"mention": mention[fid], "refersTo": ref[fid]}
                                               for fid in g]}
                              for i, g in enumerate(groups)]}

    items = {"n3cap-t1": item}
    la = label([["f1", "f2"], ["f3", "f4"]])
    rows_a = {"n3cap-t1": la}
    cmp = compare_items(items, rows_a, {"n3cap-t1": label([["f1", "f2"], ["f3", "f4"]])})
    t = cmp["table"]
    if cmp["disagreeingItems"] or kappa_from_table(t["both"], t["aOnly"], t["bOnly"], t["neither"]) != 1.0:
        failures.append("perfect agreement case failed")
    rows_b2 = {"n3cap-t1": label([["f1"], ["f2", "f3"], ["f4"]])}
    cmp2 = compare_items(items, rows_a, rows_b2)
    t2 = cmp2["table"]
    want = {"both": 0, "aOnly": 2, "bOnly": 1, "neither": 3}
    if t2 != want:
        failures.append(f"disagreement table {t2} != {want}")
    k = kappa_from_table(t2["both"], t2["aOnly"], t2["bOnly"], t2["neither"])
    n = 6
    po = (0 + 3) / n
    pe = ((0 + 2) * (0 + 1) + (3 + 1) * (2 + 3)) / (n * n)
    want_k = (po - pe) / (1 - pe)
    if abs(k - want_k) > 1e-12:
        failures.append(f"kappa {k} != hand-computed {want_k}")
    cmp3 = compare_items(items, {"n3cap-t1": label([["f1", "f2", "f3", "f4"]])},
                         {"n3cap-t1": label([["f1", "f2", "f3", "f4"]])})
    t3 = cmp3["table"]
    try:
        kappa_from_table(t3["both"], t3["aOnly"], t3["bOnly"], t3["neither"])
        failures.append("degenerate case did not raise")
    except ValueError:
        pass
    bad = label([["f1", "f2"], ["f3"]])
    p = validate_label(bad, item, "bad")
    if not any("plan ids" in x for x in p):
        failures.append(f"missing fact not caught: {p}")
    bad2 = label([["f1", "f2"], ["f3", "f4"]])
    bad2["sentences"][0]["coreference"][0]["refersTo"] = "char_602"
    p = validate_label(bad2, item, "bad2")
    if not any("anchored" in x for x in p):
        failures.append(f"cross-group referent not caught: {p}")
    bad3 = label([["f1", "f2"], ["f3", "f4"]])
    bad3["sentences"][1]["coreference"] = bad3["sentences"][1]["coreference"][:1]
    p = validate_label(bad3, item, "bad3")
    if not any("coreference has" in x for x in p):
        failures.append(f"coref count misalignment not caught: {p}")
    bad4 = label([["f1"], ["f2"], ["f3"], ["f4"]])
    bad4["sentences"][2], bad4["sentences"][3] = bad4["sentences"][3], bad4["sentences"][2]
    p = validate_label(bad4, item, "bad4")
    if not any("index" in x for x in p):
        failures.append(f"sentence reordering with stale indices not caught: {p}")
    import tempfile
    import argparse as _ap
    with tempfile.TemporaryDirectory() as td:
        td = pathlib.Path(td)
        item2 = {"itemId": "n3cap-t2", "task": "n3-plan", "split": "dev", "batch": "d2",
                 "viewpoint": {"type": "protagonist", "entityId": "char_600",
                               "name": "洛九针", "at": "潮音渡", "rule": "r"},
                 "facts": facts, "hashes": {"facts": "x"}}
        items2 = {"n3cap-t1": item, "n3cap-t2": item2}
        la2 = {"n3cap-t1": la,
               "n3cap-t2": {**label([["f1", "f2"], ["f3"], ["f4"]]), "itemId": "n3cap-t2"}}
        lb2 = {"n3cap-t1": label([["f1", "f2"], ["f3", "f4"]]),
               "n3cap-t2": {**label([["f1", "f2"], ["f3", "f4"]]), "itemId": "n3cap-t2"}}
        items_p = td / "items.jsonl"
        items_p.write_text("\n".join(json.dumps(v, ensure_ascii=False) for v in items2.values()) + "\n",
                           encoding="utf-8")
        la_p = td / "a.jsonl"
        la_p.write_text("\n".join(json.dumps(v, ensure_ascii=False) for v in la2.values()) + "\n",
                        encoding="utf-8")
        lb_p = td / "b.jsonl"
        lb_p.write_text("\n".join(json.dumps(v, ensure_ascii=False) for v in lb2.values()) + "\n",
                        encoding="utf-8")
        proto_p = td / "proto.json"
        proto_p.write_text(json.dumps({"gates": {"kappaMinimum": 0.7,
                                                 "kappaDefinition": "test"},
                                       "limitations": []}),
                           encoding="utf-8")
        base = {"items": str(items_p), "labels_a": str(la_p), "labels_b": str(lb_p),
                "protocol": str(proto_p), "adjudicated": None, "out": None,
                "freeze_labels": "frozen.jsonl"}
        if run(_ap.Namespace(**base)) != 1:
            failures.append("missing adjudication not enforced")
        cmp_pool = compare_items(items2, la2, lb2)
        kt = cmp_pool["table"]
        pooled = kappa_from_table(kt["both"], kt["aOnly"], kt["bOnly"], kt["neither"])
        if not (0.7 <= pooled < 1.0) or cmp_pool["disagreeingItems"] != ["n3cap-t2"]:
            failures.append(f"pooled scenario wrong: kappa={pooled}, disagreeing={cmp_pool['disagreeingItems']}")
        adj = {"itemId": "n3cap-t2", "source": "ai-b",
               "reason": "rubric R1: facts of one entity stay together", "label": lb2["n3cap-t2"]}
        adj_p = td / "adj.jsonl"
        adj_p.write_text(json.dumps(adj, ensure_ascii=False) + "\n", encoding="utf-8")
        if run(_ap.Namespace(**{**base, "adjudicated": str(adj_p),
                                "out": str(td / "record.json")})) != 0:
            failures.append("valid adjudication rejected")
        if not (td / "record.json").exists() or not (td / "frozen.jsonl").exists():
            failures.append("freeze outputs missing")
        else:
            record = json.loads((td / "record.json").read_text(encoding="utf-8"))
            if record["kappa"]["value"] != 1.0:
                pass  # kappa below 1 with disagreement is expected here
            if "frozenLabels" not in record or "sha256" not in record["frozenLabels"]:
                failures.append("freeze record incomplete")
        bad_adj = {"itemId": "n3cap-t1", "source": "ai-a", "reason": "", "label": la}
        bad_p = td / "badadj.jsonl"
        bad_p.write_text(json.dumps(bad_adj, ensure_ascii=False) + "\n", encoding="utf-8")
        if run(_ap.Namespace(**{**base, "adjudicated": str(bad_p)})) != 1:
            failures.append("empty adjudication reason not caught")
    for f in failures:
        print("SELFTEST FAIL:", f)
    print("selftest:", "PASS" if not failures else f"{len(failures)} failure(s)")
    return 1 if failures else 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--selftest", action="store_true")
    p.add_argument("--items", default=str(HERE / "d2_capability_items.jsonl"))
    p.add_argument("--labels-a")
    p.add_argument("--labels-b")
    p.add_argument("--adjudicated", default=None)
    p.add_argument("--protocol", default=str(HERE / "annotation" / "d2-gold-protocol.json"))
    p.add_argument("--out", default=None, help="freeze record JSON path")
    p.add_argument("--freeze-labels", default="n2-labels-d2-gold.jsonl",
                   help="frozen labels file name (relative to --out dir)")
    return p


def main() -> int:
    args = build_parser().parse_args()
    if args.selftest:
        return selftest()
    if not args.labels_a or not args.labels_b:
        print("--labels-a and --labels-b are required")
        return 2
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
