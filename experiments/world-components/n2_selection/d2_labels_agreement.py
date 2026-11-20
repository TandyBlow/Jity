# D2 gold inter-annotator agreement, adjudication and freeze (D2 prep).
#
# Consumes two independent AI label files for the 8 capability items and
# the pre-registered protocol (annotation/d2-gold-protocol.json):
#   1. validates each label against the N3 narrow shape: sentence/entry
#       shape first (a legal JSON row missing `coreference` or carrying
#       malformed entries is a reported structural problem, never a
#       crash), then I1 coverage via n3_plan.check_invariants, then
#       strict coreference count/order/name alignment,
#   2. computes the pre-registered agreement: pooled pairwise co-grouping
#      Cohen's kappa over all unordered fact pairs, order concordance by
#      ACTUAL within-group positions (both labels must place the pair in
#      the same direction), and coreference agreement over comparable
#      groups (identical factId sets),
#   3. verifies the protocol's registered input hashes against BOTH the
#      working tree and the committed git blob (always, not only at
#      freeze), validates the annotator identity files bound by the
#      protocol, and enforces the gates: kappa >= protocol.kappaMinimum
#      and EVERY disagreeing item adjudicated (source tag + reason),
#   4. freezes: writes the frozen label JSONL and an evidence JSON with
#      hashes, kappa tables, input verification and the identity record.
#
# The tool never edits labels; disagreement resolution happens in the
# adjudicated file passed on the command line.

import argparse
import hashlib
import json
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from n3_plan import check_invariants  # noqa: E402

REPO_ROOT = HERE.parent.parent.parent


def sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha_file(path: pathlib.Path) -> str:
    return sha_bytes(path.read_bytes())


def git_blob_sha(repo_root: pathlib.Path, rel: str):
    proc = subprocess.run(
        ["git", "-C", str(repo_root), "cat-file", "blob", f"HEAD:{rel}"],
        capture_output=True)
    if proc.returncode != 0:
        return None
    return sha_bytes(proc.stdout)


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


def sentence_shape_problems(sentences, tag: str) -> list:
    """structural shape check that never indexes into missing keys."""
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


def validate_label(row: dict, item: dict, tag: str) -> list:
    if row.get("itemId") != item["itemId"]:
        return [f"{tag}: itemId mismatch {row.get('itemId')!r}"]
    sentences = row.get("sentences")
    problems = sentence_shape_problems(sentences, tag)
    if problems:
        return problems
    want_index = list(range(len(sentences)))
    if [s.get("index") for s in sentences] != want_index:
        problems.append(f"{tag}: sentence index not 0..n-1 contiguous")
    names = names_map(item)
    problems.extend(check_invariants({"baseline": tag, "sentences": sentences},
                                     item["facts"], names))
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


def positions_map(row: dict) -> dict:
    """factId -> (group index, position within group), from ACTUAL output"""
    pos = {}
    for s in row["sentences"]:
        for i, fid in enumerate(s["factIds"]):
            pos[fid] = (s["index"], i)
    return pos


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
        a_pos = positions_map(a_rows[iid])
        b_pos = positions_map(b_rows[iid])
        input_order = {fid: k for k, fid in enumerate(ids)}
        for pair in a_pairs & b_pairs:
            x, y = sorted(pair, key=lambda f: input_order[f])
            order_total += 1
            if (a_pos[x] < a_pos[y]) == (b_pos[x] < b_pos[y]):
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


def verify_registered_inputs(protocol: dict, repo_root: pathlib.Path) -> tuple:
    """registered hash must equal the working-tree bytes AND, when tracked,
    the committed blob. -> (problems, details)"""
    entries = protocol.get("allowedInputs")
    if not entries:
        return ["protocol registers no allowedInputs"], []
    problems = []
    details = []
    in_repo = (repo_root / ".git").exists()
    for entry in entries:
        rel = entry.get("source")
        reg = entry.get("sha256")
        path = repo_root / rel
        if not isinstance(rel, str) or not path.exists():
            problems.append(f"registered input missing on disk: {rel!r}")
            continue
        working = sha_file(path)
        row = {"file": entry.get("file"), "registered": reg,
               "workingTree": working, "blob": None}
        if in_repo:
            blob = git_blob_sha(repo_root, rel.replace("\\", "/"))
            if blob is None:
                problems.append(f"registered input not tracked at HEAD: {rel}")
            else:
                row["blob"] = blob
                if blob != reg:
                    problems.append(f"registered hash != committed blob: {rel}")
        if working != reg:
            problems.append(f"registered hash != working-tree bytes: {rel}")
        details.append(row)
    return problems, details


def validate_identity(path: pathlib.Path, expected_id: str,
                      protocol: dict) -> tuple:
    problems = []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return [f"{path.name}: unreadable identity file ({exc})"], None
    if data.get("annotatorId") != expected_id:
        problems.append(f"{path.name}: annotatorId {data.get('annotatorId')!r} != {expected_id!r}")
    if data.get("exposureBeyondFourInputFiles") is not False:
        problems.append(f"{path.name}: exposureBeyondFourInputFiles must be false")
    if data.get("context") != "fresh task without inherited turns":
        problems.append(f"{path.name}: context must declare no inherited turns")
    want = sorted(e["file"] for e in protocol.get("allowedInputs", []))
    if sorted(data.get("inputFileNames", [])) != want:
        problems.append(f"{path.name}: inputFileNames != protocol allowedInputs")
    if not isinstance(data.get("method"), str) or len(data.get("method", "")) < 8:
        problems.append(f"{path.name}: method description missing")
    if not isinstance(data.get("limitations"), list) or not data.get("limitations"):
        problems.append(f"{path.name}: limitations missing")
    return problems, data


def registered_pins(repo_root: pathlib.Path) -> dict:
    """the pre-registration chain is the only legitimate source for the
    protocol hash and this tool's own hash. The revision artifact
    supersedes the v1 record; both are checked when present."""
    pins = {}
    v1 = repo_root / "artifacts/world-components/d2-metrics-preregistration.json"
    rev = repo_root / "artifacts/world-components/d2-preregistration-revision.json"
    for path in (v1, rev):
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        if "goldProtocol" in data:
            pins.setdefault("protocol", (data["goldProtocol"]["sha256"], path.name))
        if "unchanged" in data and "goldProtocol" in data.get("unchanged", {}):
            pins["protocol"] = (data["unchanged"]["goldProtocol"]["sha256"], path.name)
        tool = data.get("agreementTool") or {}
        if "sha256" in tool:
            pins.setdefault("agreementTool_v1", (tool["sha256"], path.name))
        now = (data.get("changed", {}).get("agreementTool") or {}).get("now")
        if now:
            pins["agreementTool"] = (now, path.name)
    return pins


def verify_bindings(protocol_path: pathlib.Path, repo_root: pathlib.Path) -> list:
    """the consumed protocol file and the running tool itself must match
    the pre-registered hashes; a re-tokened gates copy must not freeze."""
    pins = registered_pins(repo_root)
    problems = []
    if "protocol" not in pins:
        return ["no pre-registration artifact found to pin the protocol hash"]
    if sha_file(protocol_path) != pins["protocol"][0]:
        problems.append(
            f"protocol file hash != registered pin ({pins['protocol'][1]}); "
            "gates/annotators/inputs may not be altered without re-registration")
    if "agreementTool" not in pins:
        problems.append("no registered agreementTool hash to verify this tool against")
    elif sha_file(pathlib.Path(__file__)) != pins["agreementTool"][0]:
        problems.append(
            f"running agreement tool bytes != registered hash ({pins['agreementTool'][1]})")
    return problems


def bind_consumed(items_path, labels_a, labels_b, protocol) -> tuple:
    """pure binding check: the CONSUMED files (not the registered paths)
    must match the protocol registration. Returns (problems, bound); the
    freeze record carries the ACTUAL bound value."""
    problems = []
    bound = True
    consumed_items = pathlib.Path(items_path)
    item_entries = [e for e in protocol.get("allowedInputs", [])
                    if pathlib.Path(e.get("source", "")).name == consumed_items.name]
    if not item_entries:
        problems.append(f"consumed --items {consumed_items.name} matches no registered input by name")
        bound = False
    else:
        items_sha = sha_file(consumed_items)
        for e in item_entries:
            if items_sha != e.get("sha256"):
                problems.append(
                    f"consumed --items bytes != registered hash for {e.get('file')}: {consumed_items}")
                bound = False
    for side, argval in (("ai-a", labels_a), ("ai-b", labels_b)):
        spec = next((a for a in protocol.get("annotators", []) if a.get("id") == side), None)
        if spec is None or pathlib.Path(argval).name != spec.get("labels"):
            problems.append(
                f"--labels-{side[-1]} {pathlib.Path(argval).name} != protocol labels for {side}")
            bound = False
    return problems, bound


def assert_frozen_paths(repo_root: pathlib.Path) -> list:
    """read-only freeze-gate assertion (round 27 task 6, limited scope):
    registered paths must satisfy working tree == HEAD blob == pin.
    allowedInputs / protocol / the agreement tool itself are covered by
    verify_registered_inputs / verify_bindings; this adds the metric tool
    and the archived gold. No working-tree-wide status check."""
    problems = []
    checks = []
    rev_path = repo_root / "artifacts/world-components/d2-preregistration-revision.json"
    if rev_path.exists():
        data = json.loads(rev_path.read_text(encoding="utf-8"))
        mt = data.get("changed", {}).get("metricTool") or {}
        if mt.get("now") and mt.get("file"):
            checks.append(("metricTool", repo_root / mt["file"], mt["now"]))
    freeze_path = repo_root / "artifacts/world-components/d2-n3-prompt-freeze.json"
    if freeze_path.exists():
        data = json.loads(freeze_path.read_text(encoding="utf-8"))
        gold = data.get("evaluation", {}).get("gold") or {}
        if gold.get("sha256") and gold.get("file"):
            checks.append(("gold", repo_root / gold["file"], gold["sha256"]))
    for label, path, pin in checks:
        if not path.exists():
            problems.append(f"frozen assertion: {label} missing on disk: {path.name}")
            continue
        if sha_file(path) != pin:
            problems.append(f"frozen assertion: {label} working-tree bytes != pin ({path.name})")
        rel = path.relative_to(repo_root).as_posix()
        blob = git_blob_sha(repo_root, rel)
        if blob is None:
            problems.append(f"frozen assertion: {label} not tracked at HEAD ({path.name})")
        elif blob != pin:
            problems.append(f"frozen assertion: {label} HEAD blob != pin ({path.name})")
    return problems


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
    protocol_path = pathlib.Path(args.protocol)
    protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
    problems = []
    if sorted(items) != sorted(a_rows) or sorted(items) != sorted(b_rows):
        problems.append("label files must cover exactly the item ids")
    ver_problems, ver_details = verify_registered_inputs(protocol, REPO_ROOT)
    problems.extend(ver_problems)
    problems.extend(verify_bindings(protocol_path, REPO_ROOT))
    bind_problems, items_bound = bind_consumed(args.items, args.labels_a,
                                               args.labels_b, protocol)
    problems.extend(bind_problems)
    identities = {}
    if not problems:
        for side, rows in (("ai-a", a_rows), ("ai-b", b_rows)):
            spec = next((a for a in protocol.get("annotators", [])
                         if a.get("id") == side), None)
            if spec is None:
                problems.append(f"protocol has no annotator spec for {side}")
                continue
            id_path = protocol_path.parent / spec.get("identity", "")
            if not id_path.exists():
                problems.append(f"identity file missing for {side}: {id_path.name}")
                continue
            iproblems, idata = validate_identity(id_path, side, protocol)
            problems.extend(iproblems)
            identities[side] = {"file": id_path.name,
                                "sha256": sha_file(id_path), "data": idata}
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
        freeze_problems = assert_frozen_paths(REPO_ROOT)
        if freeze_problems:
            for p in freeze_problems:
                print("PROBLEM:", p)
            return 1
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
            "protocolSha256": sha_file(protocol_path),
            "inputVerification": ver_details,
            "identities": {side: {"file": v["file"], "sha256": v["sha256"],
                                  "annotatorId": v["data"].get("annotatorId"),
                                  "exposureBeyondFourInputFiles":
                                      v["data"].get("exposureBeyondFourInputFiles"),
                                  "context": v["data"].get("context")}
                           for side, v in identities.items()},
            "items": pathlib.Path(args.items).name,
            "itemsSha256": sha_file(pathlib.Path(args.items)),
            "itemsBoundToRegistration": items_bound,
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
    import tempfile
    import argparse as _ap

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
    if cmp["orderConcordance"] != {"agreed": 2, "of": 2}:
        failures.append(f"order concordance baseline wrong: {cmp['orderConcordance']}")

    # order reversal probe: reversed within-group order must NOT agree 2/2
    def reversed_label(groups):
        row = label(groups)
        for s in row["sentences"]:
            s["factIds"] = list(reversed(s["factIds"]))
            s["coreference"] = list(reversed(s["coreference"]))
        return row
    cmp_rev = compare_items(items, rows_a, {"n3cap-t1": reversed_label([["f1", "f2"], ["f3", "f4"]])})
    if cmp_rev["orderConcordance"]["agreed"] != 0 \
            or cmp_rev["orderConcordance"]["of"] != 2:
        failures.append(f"reversal probe: order concordance {cmp_rev['orderConcordance']}, must be 0/2")
    if cmp_rev["table"] != {"both": 2, "aOnly": 0, "bOnly": 0, "neither": 4}:
        failures.append(f"reversal probe: grouping table changed {cmp_rev['table']}")
    # stale-index reordering must be caught
    bad4 = label([["f1"], ["f2"], ["f3"], ["f4"]])
    bad4["sentences"][2], bad4["sentences"][3] = bad4["sentences"][3], bad4["sentences"][2]
    p = validate_label(bad4, item, "bad4")
    if not any("index" in x for x in p):
        failures.append(f"sentence reordering with stale indices not caught: {p}")
    # known disagreement kappa matches hand computation
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
    if abs(k - (po - pe) / (1 - pe)) > 1e-12:
        failures.append(f"kappa {k} != hand-computed")
    # degenerate table raises
    t3 = {"both": 6, "aOnly": 0, "bOnly": 0, "neither": 0}
    try:
        kappa_from_table(t3["both"], t3["aOnly"], t3["bOnly"], t3["neither"])
        failures.append("degenerate case did not raise")
    except ValueError:
        pass
    # invalid labels caught
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
    # legal JSON without coreference key -> structural problem, no crash
    bad5 = {"itemId": "n3cap-t1",
            "sentences": [{"index": 0, "factIds": ["f1", "f2"]},
                          {"index": 1, "factIds": ["f3", "f4"]}]}
    p = validate_label(bad5, item, "bad5")
    if not any("coreference missing" in x for x in p):
        failures.append(f"missing coreference key not reported: {p}")
    bad6 = {"itemId": "n3cap-t1",
            "sentences": [{"index": 0, "factIds": ["f1", "f2"], "coreference": "x"},
                          {"index": 1, "factIds": ["f3", "f4"], "coreference": []}]}
    p = validate_label(bad6, item, "bad6")
    if not any("not a list" in x for x in p):
        failures.append(f"non-list coreference not reported: {p}")

    # freeze gate: registered-hash verification + identity binding, in a temp repo
    with tempfile.TemporaryDirectory() as td:
        td = pathlib.Path(td)
        rel_dir = "experiments/world-components/n2_selection/annotation"
        (td / rel_dir).mkdir(parents=True)
        (td / "experiments/world-components/n2_selection").mkdir(parents=True, exist_ok=True)
        item2 = {**item, "itemId": "n3cap-t2"}
        items2 = {"n3cap-t1": item, "n3cap-t2": item2}
        la2 = {"n3cap-t1": la,
               "n3cap-t2": {**label([["f1", "f2"], ["f3"], ["f4"]]), "itemId": "n3cap-t2"}}
        lb2 = {"n3cap-t1": label([["f1", "f2"], ["f3", "f4"]]),
               "n3cap-t2": {**label([["f1", "f2"], ["f3", "f4"]]), "itemId": "n3cap-t2"}}
        files = {
            "experiments/world-components/n2_selection/d2_capability_items.jsonl":
                "\n".join(json.dumps(v, ensure_ascii=False) for v in items2.values()) + "\n",
            f"{rel_dir}/labels-a.jsonl":
                "\n".join(json.dumps(v, ensure_ascii=False) for v in la2.values()) + "\n",
            f"{rel_dir}/labels-b.jsonl":
                "\n".join(json.dumps(v, ensure_ascii=False) for v in lb2.values()) + "\n",
            f"{rel_dir}/d2-gold-rubric.md": "# rubric\nR1-R6\n",
            f"{rel_dir}/d2-sheet.md": "# sheet\n",
            f"{rel_dir}/d2-labels-template.jsonl": "{}\n",
        }
        for rel, text in files.items():
            (td / rel).write_text(text, encoding="utf-8", newline="\n")

        def sha_rel(rel):
            return sha_bytes((td / rel).read_bytes())

        def identity(exposure=False, iid="ai-a", files_list=None):
            return {"annotatorId": iid, "annotatorType": "AI",
                    "context": "fresh task without inherited turns",
                    "inputFileNames": files_list or ["rubric.md", "items.jsonl", "sheet.md", "template.jsonl"],
                    "exposureBeyondFourInputFiles": exposure,
                    "method": "按 rubric 独立标注并自查。",
                    "limitations": ["AI 标注非人工。"]}

        protocol = {
            "gates": {"kappaMinimum": 0.7, "kappaDefinition": "test"},
            "limitations": [],
            "annotators": [
                {"id": "ai-a", "identity": "identity-a.json", "labels": "labels-a.jsonl"},
                {"id": "ai-b", "identity": "identity-b.json", "labels": "labels-b.jsonl"}],
            "allowedInputs": [
                {"file": "rubric.md", "source": f"{rel_dir}/d2-gold-rubric.md", "sha256": sha_rel(f"{rel_dir}/d2-gold-rubric.md")},
                {"file": "items.jsonl", "source": "experiments/world-components/n2_selection/d2_capability_items.jsonl", "sha256": sha_rel("experiments/world-components/n2_selection/d2_capability_items.jsonl")},
                {"file": "sheet.md", "source": f"{rel_dir}/d2-sheet.md", "sha256": sha_rel(f"{rel_dir}/d2-sheet.md")},
                {"file": "template.jsonl", "source": f"{rel_dir}/d2-labels-template.jsonl", "sha256": sha_rel(f"{rel_dir}/d2-labels-template.jsonl")}],
        }
        (td / rel_dir / "identity-a.json").write_text(
            json.dumps(identity(), ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
        (td / rel_dir / "identity-b.json").write_text(
            json.dumps(identity(iid="ai-b"), ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
        proto_rel = f"{rel_dir}/d2-gold-protocol.json"
        (td / proto_rel).write_text(json.dumps(protocol, ensure_ascii=False, indent=1),
                                    encoding="utf-8", newline="\n")
        temp_proto_sha = sha_file(td / proto_rel)
        real_tool_sha = sha_file(pathlib.Path(__file__))
        real_metrics_sha = sha_file(pathlib.Path(__file__).parent / "d2_metrics.py")
        # pinned artifacts must exist BEFORE the temp commit so the blob
        # assertions can be exercised end to end
        rev_art = td / "artifacts/world-components/d2-preregistration-revision.json"
        rev_art.parent.mkdir(parents=True, exist_ok=True)
        rev_art.write_text(json.dumps({
            "changed": {"agreementTool": {"now": real_tool_sha},
                        "metricTool": {"file": "experiments/world-components/n2_selection/d2_metrics.py",
                                       "now": real_metrics_sha}},
            "unchanged": {"goldProtocol": {"sha256": temp_proto_sha}},
        }, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
        gold_art = td / "artifacts/world-components/n2-labels-d2-gold.jsonl"
        gold_art.write_text("\n".join(json.dumps(v, ensure_ascii=False)
                                      for v in lb2.values()) + "\n",
                            encoding="utf-8", newline="\n")
        gold_sha = sha_file(gold_art)
        freeze_art = td / "artifacts/world-components/d2-n3-prompt-freeze.json"
        freeze_art.write_text(json.dumps({
            "evaluation": {"gold": {"file": "artifacts/world-components/n2-labels-d2-gold.jsonl",
                                    "sha256": gold_sha}}}, ensure_ascii=False),
            encoding="utf-8", newline="\n")
        adj = {"itemId": "n3cap-t2", "source": "ai-b",
               "reason": "rubric R1: facts of one entity stay together",
               "label": lb2["n3cap-t2"]}
        (td / rel_dir / "adj.jsonl").write_text(
            json.dumps(adj, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
        metrics_mirror = td / "experiments/world-components/n2_selection/d2_metrics.py"
        metrics_mirror.parent.mkdir(parents=True, exist_ok=True)
        metrics_mirror.write_bytes((pathlib.Path(__file__).parent / "d2_metrics.py").read_bytes())
        subprocess.run(["git", "init", "-q"], cwd=td, check=True)
        subprocess.run(["git", "add", "-A"], cwd=td, check=True)
        subprocess.run(["git", "-c", "user.email=t@x", "-c", "user.name=t",
                        "commit", "-qm", "init"], cwd=td, check=True)
        base = {"items": "experiments/world-components/n2_selection/d2_capability_items.jsonl",
                "labels_a": f"{rel_dir}/labels-a.jsonl",
                "labels_b": f"{rel_dir}/labels-b.jsonl",
                "protocol": proto_rel, "adjudicated": f"{rel_dir}/adj.jsonl",
                "out": str(td / "record.json"), "freeze_labels": "frozen.jsonl"}
        # relative paths resolved against cwd: run chdir-safe via absolute
        base = {k: (str(td / v) if not pathlib.Path(v).is_absolute() and k != "items"
                    else v) for k, v in base.items()}
        # items path also relative to repo root but REPO_ROOT is this repo's root;
        # for the selftest we must keep the tool's REPO_ROOT pointing at td.
        import d2_labels_agreement as mod
        old_root = mod.REPO_ROOT
        mod.REPO_ROOT = td
        try:
            base["items"] = str(td / "experiments/world-components/n2_selection/d2_capability_items.jsonl")
            base["labels_a"] = str(td / rel_dir / "labels-a.jsonl")
            base["labels_b"] = str(td / rel_dir / "labels-b.jsonl")
            base["protocol"] = str(td / proto_rel)
            base["adjudicated"] = str(td / rel_dir / "adj.jsonl")
            if mod.run(_ap.Namespace(**base)) != 0:
                failures.append("clean temp-repo freeze rejected")
            if not (td / "record.json").exists() or not (td / "frozen.jsonl").exists():
                failures.append("freeze outputs missing")
            else:
                rec = json.loads((td / "record.json").read_text(encoding="utf-8"))
                if len(rec.get("inputVerification", [])) != 4 \
                        or any(v["blob"] is None for v in rec["inputVerification"]):
                    failures.append("input verification rows incomplete")
                if rec.get("identities", {}).get("ai-a", {}).get("sha256") is None:
                        failures.append("identity not bound into freeze record")
            probes = []

            def probe(name, ns):
                rc = mod.run(ns)
                probes.append((name, rc))
                return rc

            proto_saved = (td / proto_rel).read_bytes()
            # zeroed registered hash
            proto_bad = json.loads(proto_saved.decode("utf-8"))
            proto_bad["allowedInputs"] = [dict(e) for e in proto_bad["allowedInputs"]]
            proto_bad["allowedInputs"][0]["sha256"] = "0" * 64
            (td / proto_rel).write_text(json.dumps(proto_bad, ensure_ascii=False, indent=1),
                                        encoding="utf-8", newline="\n")
            probe("registered-hash-zeroed", _ap.Namespace(**base))
            (td / proto_rel).write_bytes(proto_saved)
            # working-tree rubric drift after commit
            rub = td / rel_dir / "d2-gold-rubric.md"
            rub_saved = rub.read_bytes()
            rub.write_text("# rubric\nR1-R6 tampered\n", encoding="utf-8", newline="\n")
            probe("rubric-working-drift", _ap.Namespace(**base))
            rub.write_bytes(rub_saved)
            # identity exposure flag true
            (td / rel_dir / "identity-a.json").write_text(
                json.dumps(identity(exposure=True), ensure_ascii=False) + "\n",
                encoding="utf-8", newline="\n")
            probe("identity-exposure", _ap.Namespace(**base))
            (td / rel_dir / "identity-a.json").write_text(
                json.dumps(identity(), ensure_ascii=False) + "\n",
                encoding="utf-8", newline="\n")
            # identity file names mismatch protocol
            (td / rel_dir / "identity-a.json").write_text(
                json.dumps(identity(files_list=["rubric.md"]), ensure_ascii=False) + "\n",
                encoding="utf-8", newline="\n")
            probe("identity-file-names-mismatch", _ap.Namespace(**base))
            (td / rel_dir / "identity-a.json").write_text(
                json.dumps(identity(), ensure_ascii=False) + "\n",
                encoding="utf-8", newline="\n")
            # archived gold bytes tampered
            gold_saved = gold_art.read_bytes()
            gold_art.write_bytes(gold_saved + b"\n")
            probe("gold-bytes-tampered", _ap.Namespace(**base))
            gold_art.write_bytes(gold_saved)

            def load_rows(p):
                return [json.loads(l) for l in pathlib.Path(p).read_text(encoding="utf-8").splitlines() if l.strip()]

            def write_rows(p, rows):
                pathlib.Path(p).write_text(
                    "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
                    encoding="utf-8", newline="\n")

            # substituted --items under a different name
            rows = load_rows(base["items"])
            rows[0]["facts"][1]["goal"] = "被改写的协作目标文本"
            tam = td / "tampered-items.jsonl"
            write_rows(tam, rows)
            probe("items-renamed-copy", _ap.Namespace(**{**base, "items": str(tam)}))
            # counterfactual: the pure binding function must report bound=False
            bproblems, bbound = mod.bind_consumed(
                str(tam), base["labels_a"], base["labels_b"],
                json.loads(proto_saved.decode("utf-8")))
            if bbound is not False or not bproblems:
                failures.append("counterfactual bind_consumed must return bound=False")
            probes.append(("bind-consumed-counterfactual", 0 if bbound is False else 1))
            # same-name copy in another directory
            rows2 = load_rows(base["items"])
            rows2[1]["facts"][2]["goal"] = "另一个被改写的目标文本"
            moved = td / "moved"
            moved.mkdir()
            same_name = moved / "d2_capability_items.jsonl"
            write_rows(same_name, rows2)
            probe("items-same-name-copy", _ap.Namespace(**{**base, "items": str(same_name)}))
            # protocol copy with lowered kappa gate
            proto_bad2 = json.loads(proto_saved.decode("utf-8"))
            proto_bad2["gates"]["kappaMinimum"] = 0.1
            (td / proto_rel).write_text(json.dumps(proto_bad2, ensure_ascii=False, indent=1),
                                        encoding="utf-8", newline="\n")
            probe("gates-retokened-copy", _ap.Namespace(**base))
            (td / proto_rel).write_bytes(proto_saved)
            # revision pinning a wrong tool hash
            rev_saved = rev_art.read_bytes()
            rev_bad = json.loads(rev_saved.decode("utf-8"))
            rev_bad["changed"]["agreementTool"]["now"] = "0" * 64
            rev_art.write_text(json.dumps(rev_bad, ensure_ascii=False, indent=1),
                               encoding="utf-8", newline="\n")
            probe("tool-pin-wrong", _ap.Namespace(**base))
            rev_art.write_bytes(rev_saved)
            for name in ("items-renamed-copy", "items-same-name-copy", "identity-exposure",
                         "registered-hash-zeroed", "rubric-working-drift",
                         "gold-bytes-tampered", "gates-retokened-copy", "tool-pin-wrong"):
                rc = dict(probes)[name]
                if rc != 1:
                    failures.append(f"probe {name} exit {rc}, expected 1")
            for name, rc in probes:
                print(f"probe {name}: exit {rc}")
                rev_art.write_bytes(rev_saved)
        finally:
            mod.REPO_ROOT = old_root
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
