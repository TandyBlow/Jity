"""Re-score archived N2 selections against frozen v3 labels; never infer.

The v2 archive and its diagnostic target remain unchanged. Actual must/may/
omit judgements come only from the verified frozen v3 label file.
"""

import argparse
import datetime
from fractions import Fraction
import json
import pathlib
import tempfile

from recompute_must import ARMS, ARCHIVE, ITEMS, REPO, git_commit, judge, sha_file, summarize


HERE = pathlib.Path(__file__).resolve().parent
FROZEN = REPO / "artifacts/world-components/n2-labels-v3.json"
LABELS = HERE / "annotation/labels-v3.jsonl"
REPORT = REPO / "artifacts/world-components/n2-must-v3.json"
STATUS = REPO / "artifacts/world-components/n2-annotation-status.json"
CLASSES = {"must", "may", "omit"}


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def label_map(rows, expected_keys):
    out = {}
    for row in rows:
        key = (row["itemId"], row["factId"])
        if key in out:
            raise ValueError(f"duplicate label key: {key}")
        if row["label"] not in CLASSES:
            raise ValueError(f"invalid v3 label: {key}")
        out[key] = row["label"]
    if set(out) != expected_keys:
        raise ValueError("v3 labels do not exactly cover the source item/fact keys")
    return out


def load_frozen(frozen_path, labels_path, items, expected_items=16, expected_facts=92):
    """Reject absent/unfrozen, unbound, corrupt, incomplete or inconsistent labels."""
    frozen = json.loads(frozen_path.read_text(encoding="utf-8"))
    if frozen.get("status") != "frozen" or frozen.get("decision") != "D1":
        raise ValueError("D1 v3 labels are not frozen")
    agreement = frozen.get("agreement", {})
    kappa = agreement.get("kappaExact", agreement.get("kappaUnrounded",
                          agreement.get("kappaRaw", agreement.get("kappa"))))
    if not isinstance(kappa, (int, float)) or not 0.7 <= kappa <= 1:
        raise ValueError("frozen agreement does not satisfy kappa >= 0.7")
    item_ids = [item["itemId"] for item in items]
    source_keys = [(item["itemId"], fact["factId"])
                   for item in items for fact in item["facts"]]
    keys = set(source_keys)
    if (len(item_ids) != expected_items or len(set(item_ids)) != expected_items
            or len(source_keys) != expected_facts or len(keys) != expected_facts
            or agreement.get("n") != expected_facts):
        raise ValueError("source or frozen agreement item/fact counts differ from D1")
    binding = frozen.get("labels", {}).get("v3", {})
    if binding.get("file") != labels_path.name or binding.get("sha256") != sha_file(labels_path):
        raise ValueError("v3 label file hash/name does not match the freeze")
    labels = label_map(read_jsonl(labels_path), keys)
    embedded = label_map(frozen.get("labelsV3", []), keys)
    if embedded != labels:
        raise ValueError("frozen embedded labels differ from the bound v3 file")
    return frozen, labels


def validate_ai_protocol(frozen, annotation_dir):
    protocol = frozen.get("annotationProtocol", {})
    if protocol.get("mode") != "AI-independent-annotation":
        raise ValueError("freeze is not explicitly registered as AI independent annotation")

    def bound_json(binding):
        name = binding.get("file", "")
        if not name or pathlib.Path(name).name != name or "\\" in name:
            raise ValueError("AI evidence reference is not a local filename")
        path = annotation_dir / name
        if sha_file(path) != binding.get("sha256"):
            raise ValueError(f"AI evidence hash mismatch: {name}")
        return json.loads(path.read_text(encoding="utf-8"))

    registration = bound_json(protocol)
    if (registration != protocol.get("registration") or registration.get("decision") != "D1"
            or registration.get("mode") != protocol["mode"]):
        raise ValueError("AI protocol registration differs from the frozen copy")
    annotators = registration.get("annotators", [])
    identities = protocol.get("identities", [])
    if (len(annotators) != 2 or len(identities) != 2
            or len({entry["id"] for entry in annotators}) != 2
            or len({entry["file"] for entry in identities}) != 2):
        raise ValueError("AI annotation requires two distinct registered identities")
    identity_by_file = {entry["file"]: entry for entry in identities}
    frozen_label_files = {frozen["labels"][key]["file"] for key in ("a", "b")}
    if frozen_label_files != {entry["labels"] for entry in annotators}:
        raise ValueError("frozen label pair differs from registered AI annotators")
    for annotator in annotators:
        binding = identity_by_file.get(annotator["identity"])
        if binding is None:
            raise ValueError("registered AI identity is absent from the freeze")
        identity = bound_json(binding)
        if (identity != binding.get("statement") or identity.get("annotatorType") != "AI"
                or identity.get("annotatorId") != annotator["id"]
                or identity.get("exposureBeyondFourInputFiles") is not False
                or annotator.get("inheritedTurns") is not False):
            raise ValueError("AI identity does not match its frozen statement or blind status")


def validate_current_status(frozen, status, annotation_dir):
    """A leftover freeze must not override a newer failed or incomplete run."""
    if status.get("status") != "frozen":
        raise ValueError("current annotation status is not frozen; stale freeze rejected")
    if status.get("agreement") != frozen.get("agreement"):
        raise ValueError("current status agreement differs from the frozen archive")
    for key in ("a", "b"):
        binding = frozen.get("labels", {}).get(key, {})
        current = status.get("labels", {}).get(key, {})
        if (binding.get("file") != current.get("file")
                or binding.get("sha256") != current.get("sha256")):
            raise ValueError(f"current annotator {key} binding differs from the freeze")
        name = binding.get("file", "")
        if not name or pathlib.Path(name).name != name or "\\" in name:
            raise ValueError("annotator label reference is not a local filename")
        if sha_file(annotation_dir / name) != binding.get("sha256"):
            raise ValueError(f"annotator {key} label hash differs from the freeze")


def v3_item(item, labels):
    """Replace all three judgement classes; keep v2 target solely for diagnosis."""
    return {**item,
            "must": [fact["factId"] for fact in item["facts"]
                     if labels[(item["itemId"], fact["factId"])] == "must"],
            "omittable": [fact["factId"] for fact in item["facts"]
                          if labels[(item["itemId"], fact["factId"])] == "may"],
            "forbidden": [fact["factId"] for fact in item["facts"]
                          if labels[(item["itemId"], fact["factId"])] == "omit"]}


def score_row(item, archived):
    selected_values = archived["selected"]
    if not isinstance(selected_values, list) or not all(isinstance(x, str) for x in selected_values):
        raise ValueError("archived selected must be a list of fact ids")
    selected = set(selected_values)
    out = {"itemId": item["itemId"], "selected": selected_values,
           "invalid": archived.get("invalid"), **judge(item, selected)}
    hits = out["selectedMustCount"]
    must_count, selected_count = out["mustCount"], out["selectedCount"]
    recall = Fraction(hits, must_count) if must_count else Fraction(1)
    precision = Fraction(hits, selected_count) if selected_count else None
    # Full precision display and integer/rational comparisons: never gate a rounded metric.
    out["mustRecall"] = float(recall)
    out["mustPrecision"] = float(precision) if precision is not None else None
    out["maySelectionRate"] = (out["maySelectedCount"] / out["mayCount"]
                               if out["mayCount"] else None)
    valid = (not out["invalid"] and not out["unknownIds"] and out["forbiddenHits"] == 0
             and len(selected_values) == len(selected))
    out["duplicateSelectedIds"] = len(selected_values) != len(selected)
    out["d1ItemPass"] = bool(valid and recall >= Fraction(95, 100)
                             and precision is not None and precision >= Fraction(85, 100))
    out["p1DowngradeItemCondition"] = bool(valid and recall == 1
                                           and precision is not None
                                           and precision >= Fraction(85, 100))
    return out


def full_metrics(rows):
    recalls = [Fraction(row["selectedMustCount"], row["mustCount"])
               if row["mustCount"] else Fraction(1) for row in rows]
    precisions = [Fraction(row["selectedMustCount"], row["selectedCount"])
                  for row in rows if row["selectedCount"]]
    hits = sum(row["selectedMustCount"] for row in rows)
    must = sum(row["mustCount"] for row in rows)
    selected = sum(row["selectedCount"] for row in rows)
    recall_macro = sum(recalls) / len(rows)
    precision_macro = sum(precisions) / len(precisions) if precisions else None
    may = sum(row["mayCount"] for row in rows)
    may_hits = sum(row["maySelectedCount"] for row in rows)
    return {
        "mustRecallMacro": float(recall_macro),
        "mustPrecisionMacroNonempty": float(precision_macro) if precision_macro is not None else None,
        "mustRecallMicro": hits / must if must else None,
        "mustPrecisionMicro": hits / selected if selected else None,
        "maySelectionRateMicro": may_hits / may if may else None,
        "mustHits": hits, "mustCount": must, "selectedCount": selected,
        "precisionMacroDenominator": len(precisions),
        "macroThresholdCondition": bool(recall_macro == 1 and precision_macro is not None
                                         and precision_macro >= Fraction(85, 100)),
    }


def branch_decision(rows):
    metrics = full_metrics(rows)
    all_items = all(row["p1DowngradeItemCondition"] for row in rows)
    clean = all(not row["invalid"] and not row["unknownIds"]
                and not row["duplicateSelectedIds"] and not row["forbiddenHits"] for row in rows)
    macro = bool(metrics["macroThresholdCondition"] and clean
                 and metrics["precisionMacroDenominator"] == len(rows))
    return {
        "preRegisteredCondition": "P1-rule must-R=1.0 and must-P>=0.85",
        "operationalization": "every item satisfies the condition, with no invalid/omit/unknown/duplicate selection",
        "conservativeAllItemsTrigger": all_items,
        "macroTrigger": macro,
        "aggregationInterpretationsDiffer": all_items != macro,
        "itemCount": len(rows),
        "itemConditionPassCount": sum(row["p1DowngradeItemCondition"] for row in rows),
        "unroundedMetrics": metrics,
        "n2ModelArmDowngraded": all_items,
        "resourceTransferToN3N4": all_items,
        "action": ("downgrade-n2-to-rule-plus-audit; transfer-capacity-to-n3-n4" if all_items
                   else "no-downgrade-trigger; keep-n2-model-work-eligible"),
        "needsAggregationClarification": all_items != macro,
        "note": "Both interpretations are reported; a macro-only pass is never silently used to downgrade.",
    }


def recompute(frozen_path=FROZEN, labels_path=LABELS, items_path=ITEMS,
              archive_path=ARCHIVE, output_path=REPORT, status_path=STATUS):
    items = read_jsonl(items_path)
    frozen, labels = load_frozen(frozen_path, labels_path, items)
    expected_items_hash = frozen.get("provenance", {}).get("itemsV2")
    if expected_items_hash is not None and sha_file(items_path) != expected_items_hash:
        raise ValueError("v2 item content hash differs from the frozen source")
    status = json.loads(status_path.read_text(encoding="utf-8"))
    validate_current_status(frozen, status, labels_path.parent)
    validate_ai_protocol(frozen, labels_path.parent)
    archive = json.loads(archive_path.read_text(encoding="utf-8"))
    by_item = {item["itemId"]: v3_item(item, labels) for item in items}
    arms = {}
    for name, role, note in ARMS:
        archived_rows = archive["arms"][name]["rows"]
        row_ids = [row["itemId"] for row in archived_rows]
        if len(row_ids) != len(by_item) or set(row_ids) != set(by_item):
            raise ValueError(f"{name}: archived rows do not exactly cover all 16 items")
        rows = [score_row(by_item[row["itemId"]], row) for row in archived_rows]
        arms[name] = {"role": role, "note": note, "summary": summarize(rows),
                      "unroundedMetrics": full_metrics(rows), "rows": rows}
    branch = branch_decision(arms["P1-rule-program"]["rows"])
    report = {
        "purpose": "D1 frozen-v3 rescore of archived N2 outputs; no inference or new prediction",
        "decision": "D1", "labelsStatus": "frozen-v3",
        "annotationEvidenceType": "AI independent annotation; not human annotation",
        "rule": {"mustRecall": ">=0.95 per item", "mustPrecision": ">=0.85 per item",
                 "omitHits": "hard zero; all v3 omit labels, including visible other-person facts",
                 "unknownIds": "hard zero", "maySelectionRate": "reported only",
                 "target": "unchanged v2 target, diagnostic only",
                 "comparisonPrecision": "unrounded rational/count comparisons"},
        "definition": {"must": "frozen v3 must", "may": "frozen v3 may",
                       "omit": "frozen v3 omit; not the old v2 forbidden set",
                       "mayPrecisionTreatment": "selected may still counts as a must false positive"},
        "provenance": {"itemsV2": sha_file(items_path), "archive": sha_file(archive_path),
                       "frozenArchive": sha_file(frozen_path), "labelsV3": sha_file(labels_path),
                       "currentAnnotationStatus": sha_file(status_path),
                       "script": sha_file(pathlib.Path(__file__)),
                       "sharedJudge": sha_file(HERE / "recompute_must.py"),
                       "command": "python -X utf8 experiments/world-components/n2_selection/recompute_must_v3.py",
                       "generatedAt": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
                       "generatedFromCommit": git_commit()},
        "frozenAnnotation": {"agreement": frozen["agreement"], "mustGate": frozen.get("mustGate"),
                             "freezeProvenance": frozen.get("provenance"),
                             **{key: frozen[key] for key in ("annotationProtocol", "annotators", "identities",
                                                            "annotationMethod", "annotationIdentity") if key in frozen}},
        "arms": arms, "branchDecision": branch,
        "disclaimers": ["AI agreement is not human agreement or independent evidence of semantic truth.",
                        "Original v2 labels, outputs and reports remain unchanged.",
                        "No training, browser test or new model experiment was run.",
                        "P1-labels reads old answer labels and is a reference arm, not a model.",
                        "Rounded summary values are display only; gates use counts and rational comparisons."]}
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for name, arm in arms.items():
        print(f"{name}: {json.dumps(arm['unroundedMetrics'])}; pass={arm['summary']['d1ItemsPass']}/16")
    print(json.dumps(branch, ensure_ascii=False))
    print(f"report -> {output_path}")
    return report


def selftest():
    item = {"itemId": "test", "facts": [{"factId": x} for x in ("a", "b", "c")],
            "must": ["a"], "omittable": ["b"], "forbidden": ["c"], "target": ["a", "b"]}
    labels = {("test", "a"): "may", ("test", "b"): "must", ("test", "c"): "omit"}
    changed = v3_item(item, labels)
    assert changed["must"] == ["b"] and item["must"] == ["a"]
    assert changed["target"] == item["target"]
    row = score_row(changed, {"selected": ["b"]})
    assert row["d1ItemPass"] and row["mustRecall"] == 1
    assert not score_row(changed, {"selected": ["a"]})["d1ItemPass"]
    assert score_row(changed, {"selected": ["b", "c"]})["forbiddenHits"] == 1
    assert score_row(changed, {"selected": ["b", "a"]})["maySelectedCount"] == 1
    assert not score_row(changed, {"selected": []})["d1ItemPass"]
    assert not score_row(changed, {"selected": ["b", "unknown"]})["d1ItemPass"]
    assert not score_row(changed, {"selected": ["b"], "invalid": "bad output"})["d1ItemPass"]
    assert not score_row(changed, {"selected": ["b", "b"]})["d1ItemPass"]
    many = {"itemId": "many", "facts": [{"factId": str(i)} for i in range(10001)],
            "must": [str(i) for i in range(8499)], "omittable": [], "forbidden": [], "target": []}
    near = score_row(many, {"selected": [str(i) for i in range(10000)]})
    assert round(near["mustPrecision"], 3) == 0.85 and not near["d1ItemPass"]
    assert not branch_decision([near])["conservativeAllItemsTrigger"]
    exact_item = {**many, "must": [str(i) for i in range(8500)]}
    exact = score_row(exact_item, {"selected": [str(i) for i in range(10000)]})
    assert exact["d1ItemPass"] and exact["p1DowngradeItemCondition"]
    assert branch_decision([exact])["conservativeAllItemsTrigger"]
    assert branch_decision([row, near])["aggregationInterpretationsDiffer"]
    with tempfile.TemporaryDirectory() as directory:
        folder = pathlib.Path(directory)
        path, freeze = folder / "labels-v3.jsonl", folder / "freeze.json"
        rows = [{"itemId": i, "factId": f, "label": value} for (i, f), value in labels.items()]
        path.write_text("\n".join(json.dumps(x) for x in rows) + "\n", encoding="utf-8")
        frozen = {"status": "frozen", "decision": "D1", "agreement": {"n": 3, "kappa": 0.9},
                  "labels": {"v3": {"file": path.name, "sha256": sha_file(path)}}, "labelsV3": rows}
        freeze.write_text(json.dumps(frozen), encoding="utf-8")
        assert load_frozen(freeze, path, [item], 1, 3)[1] == labels
        for mutation in ("unfrozen", "bad-hash", "bad-kappa", "exact-kappa-below-threshold", "bad-label", "mismatched-embedded", "missing-key"):
            broken = json.loads(json.dumps(frozen))
            if mutation == "unfrozen": broken["status"] = "awaiting-labels"
            if mutation == "bad-hash": broken["labels"]["v3"]["sha256"] = "0" * 64
            if mutation == "bad-kappa": broken["agreement"]["kappa"] = 0.6999
            if mutation == "exact-kappa-below-threshold":
                broken["agreement"].update(kappa=0.7, kappaExact=0.69999)
            if mutation == "bad-label": broken["labelsV3"][0]["label"] = "invalid"
            if mutation == "mismatched-embedded": broken["labelsV3"][0]["label"] = "must"
            if mutation == "missing-key": broken["labelsV3"].pop()
            freeze.write_text(json.dumps(broken), encoding="utf-8")
            try:
                load_frozen(freeze, path, [item], 1, 3)
            except ValueError:
                pass
            else:
                raise AssertionError(f"did not reject {mutation}")
        identities = []
        annotators = []
        for letter in ("a", "b"):
            identity_path = folder / f"identity-{letter}.json"
            statement = {"annotatorId": f"ai-{letter}", "annotatorType": "AI",
                         "exposureBeyondFourInputFiles": False}
            identity_path.write_text(json.dumps(statement), encoding="utf-8")
            identities.append({"file": identity_path.name, "sha256": sha_file(identity_path),
                               "statement": statement})
            annotators.append({"id": f"ai-{letter}", "identity": identity_path.name,
                               "labels": f"labels-{letter}.jsonl", "inheritedTurns": False})
        registration = {"decision": "D1", "mode": "AI-independent-annotation", "annotators": annotators}
        protocol_path = folder / "protocol.json"
        protocol_path.write_text(json.dumps(registration), encoding="utf-8")
        evidence = {"annotationProtocol": {"file": protocol_path.name, "sha256": sha_file(protocol_path),
                    "registration": registration, "mode": registration["mode"], "identities": identities},
                    "labels": {letter: {"file": f"labels-{letter}.jsonl"} for letter in ("a", "b")}}
        validate_ai_protocol(evidence, folder)
        for mutation in ("protocol-hash", "identity-hash", "identity-statement", "protocol-mode"):
            broken = json.loads(json.dumps(evidence))
            if mutation == "protocol-hash": broken["annotationProtocol"]["sha256"] = "0" * 64
            if mutation == "identity-hash": broken["annotationProtocol"]["identities"][0]["sha256"] = "0" * 64
            if mutation == "identity-statement": broken["annotationProtocol"]["identities"][0]["statement"]["annotatorType"] = "human"
            if mutation == "protocol-mode": broken["annotationProtocol"]["mode"] = "human"
            try:
                validate_ai_protocol(broken, folder)
            except ValueError:
                pass
            else:
                raise AssertionError(f"did not reject {mutation}")
        bindings = {}
        for letter in ("a", "b"):
            raw_labels = folder / f"raw-{letter}.jsonl"
            raw_labels.write_text(json.dumps(rows) + letter, encoding="utf-8")
            bindings[letter] = {"file": raw_labels.name, "sha256": sha_file(raw_labels)}
        current_freeze = {"labels": bindings, "agreement": {"n": 3, "kappaExact": 1.0}}
        current_status = {**current_freeze, "status": "frozen"}
        validate_current_status(current_freeze, current_status, folder)
        for mutation in ("newer-low-kappa", "newer-missing-adjudication", "changed-label-binding", "changed-agreement"):
            broken = json.loads(json.dumps(current_status))
            if mutation == "newer-low-kappa": broken["status"] = "kappa-below-0.7-no-freeze"
            if mutation == "newer-missing-adjudication": broken["status"] = "kappa-pass-adjudication-needed"
            if mutation == "changed-label-binding": broken["labels"]["a"]["sha256"] = "0" * 64
            if mutation == "changed-agreement": broken["agreement"]["kappaExact"] = 0.8
            try:
                validate_current_status(current_freeze, broken, folder)
            except ValueError:
                pass
            else:
                raise AssertionError(f"did not reject {mutation}")
        (folder / bindings["a"]["file"]).write_text("modified", encoding="utf-8")
        try:
            validate_current_status(current_freeze, current_status, folder)
        except ValueError:
            pass
        else:
            raise AssertionError("modified original annotation was not rejected")
    print("selftest PASS: v3 replacement, omit/may, exact gates, empty/unknown/invalid/duplicate selections, frozen/hash/coverage checks")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--frozen", type=pathlib.Path, default=FROZEN)
    parser.add_argument("--labels", type=pathlib.Path, default=LABELS)
    parser.add_argument("--output", type=pathlib.Path, default=REPORT)
    parser.add_argument("--status", type=pathlib.Path, default=STATUS)
    args = parser.parse_args()
    if args.selftest:
        selftest()
    else:
        try:
            recompute(args.frozen, args.labels, output_path=args.output, status_path=args.status)
        except (ValueError, FileNotFoundError, KeyError) as exc:
            parser.exit(1, f"D1 v3 rescore stopped: {exc}\n")


if __name__ == "__main__":
    main()
