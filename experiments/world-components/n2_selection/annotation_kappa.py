# N2 v3 annotation agreement / freeze (joint decision D1).
#
# Reads the two independent 3-class label files, verifies the blind sheet and
# rubric hashes, computes Cohen's kappa, and (only when kappa >= 0.7 AND every
# disagreement is adjudicated) freezes v3. The freeze also runs the gate:
# per-item must-set differences vs the v2 labels; > 2/16 rebuilds the N3
# 16-item inputs, otherwise they are reused.
#
# Files (under experiments/world-components/n2_selection/annotation/):
#   items-blind.jsonl, manifest.json, labels-c-impl.jsonl,
#   labels-c-reviewer.jsonl, labels-adjudicated.jsonl (differences only)
# Status archive: artifacts/world-components/n2-annotation-status.json
# Frozen archive: artifacts/world-components/n2-labels-v3.json
#
# Usage:
#   python .../annotation_kappa.py --selftest
#   python .../annotation_kappa.py            # real two-annotator run
#   python .../annotation_kappa.py --labels-a labels-c-impl.jsonl \
#       --labels-b labels-c-reviewer.jsonl --adjudicated labels-adjudicated.jsonl

import argparse
import datetime
import hashlib
import json
import pathlib
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent.parent.parent
OUT = HERE / "annotation"
ITEMS = HERE / "items.jsonl"
STATUS = REPO / "artifacts" / "world-components" / "n2-annotation-status.json"
FROZEN = REPO / "artifacts" / "world-components" / "n2-labels-v3.json"
CLASSES = ("must", "omit", "may")


def sha_file(p) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def git_commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO,
                                       text=True).strip()
    except Exception:
        return "unknown"


def load_labels(path: pathlib.Path, template_keys: list) -> dict:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]
    out = {}
    for r in rows:
        key = (r["itemId"], r["factId"])
        if key in out:
            sys.exit(f"{path.name}: duplicate key {key}")
        if r["label"] not in CLASSES:
            sys.exit(f"{path.name}: invalid label {r['label']!r} at {key}")
        out[key] = r["label"]
    missing = [k for k in template_keys if k not in out]
    extra = [k for k in out if k not in set(template_keys)]
    if missing or extra:
        sys.exit(f"{path.name}: missing {len(missing)} / extra {len(extra)} keys; "
                 f"first missing {missing[:3]}, first extra {extra[:3]}")
    return out


def load_adjudication(path: pathlib.Path, disagreement_keys: list) -> dict:
    """The adjudicator file contains ONLY the disagreement keys."""
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]
    allowed = set(disagreement_keys)
    out = {}
    for r in rows:
        key = (r["itemId"], r["factId"])
        if key not in allowed:
            sys.exit(f"{path.name}: adjudication includes non-disagreement key {key}")
        if key in out:
            sys.exit(f"{path.name}: duplicate adjudication key {key}")
        if r["label"] not in CLASSES:
            sys.exit(f"{path.name}: invalid label {r['label']!r} at {key}")
        out[key] = r["label"]
    missing = [k for k in disagreement_keys if k not in out]
    if missing:
        sys.exit(f"{path.name}: missing {len(missing)} disagreement(s); "
                 f"first {missing[:3]}")
    return out


def kappa(a: dict, b: dict, keys: list) -> dict:
    n = len(keys)
    matrix = {x: {y: 0 for y in CLASSES} for x in CLASSES}
    for k in keys:
        matrix[a[k]][b[k]] += 1
    observed = sum(matrix[c][c] for c in CLASSES) / n
    row = {c: sum(matrix[c].values()) for c in CLASSES}
    col = {c: sum(matrix[r][c] for r in CLASSES) for c in CLASSES}
    expected = sum((row[c] / n) * (col[c] / n) for c in CLASSES)
    if expected == 1.0:
        k = 1.0 if observed == 1.0 else 0.0
    else:
        k = (observed - expected) / (1.0 - expected)
    return {"n": n, "observedAgreement": round(observed, 4),
            "expectedAgreement": round(expected, 4), "kappa": round(k, 4),
            "confusion": matrix}


def must_sets(labels: dict) -> dict:
    out = {}
    for (item_id, fact_id), label in labels.items():
        out.setdefault(item_id, set())
        if label == "must":
            out[item_id].add(fact_id)
    return out


def v2_must_sets() -> dict:
    items = [json.loads(line) for line in
             ITEMS.read_text(encoding="utf-8").splitlines() if line.strip()]
    return {it["itemId"]: set(it["must"]) for it in items}


def write_status(payload: dict) -> None:
    STATUS.parent.mkdir(parents=True, exist_ok=True)
    STATUS.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"status -> {STATUS}")


def run(labels_a: str, labels_b: str, adjudicated: str) -> None:
    manifest_path = OUT / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for key, path in (("rubric", REPO / manifest["rubric"]["file"]),
                      ("blindItems", OUT / manifest["blindItems"]["file"]),
                      ("template", OUT / manifest["template"]["file"])):
        if sha_file(path) != manifest[key]["sha256"]:
            sys.exit(f"{key} hash mismatch: {path}")
    template = [json.loads(line) for line in
                (OUT / "labels-template.jsonl").read_text(encoding="utf-8").splitlines()
                if line.strip()]
    keys = [(r["itemId"], r["factId"]) for r in template]

    a = load_labels(OUT / labels_a, keys)
    b_path = OUT / labels_b
    if not b_path.exists():
        write_status({
            "purpose": "N2 v3 annotation status (D1)",
            "status": "awaiting-reviewer-labels",
            "rubric": manifest["rubric"],
            "labelsA": {"file": labels_a, "sha256": sha_file(OUT / labels_a)},
            "labelsB": {"file": labels_b, "present": False},
            "generatedAt": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
            "generatedFromCommit": git_commit(),
        })
        print(f"{labels_b} is missing; the reviewer must label before kappa is computed")
        return

    b = load_labels(b_path, keys)
    result = kappa(a, b, keys)
    disagreements = [{"itemId": i, "factId": f,
                      "a": a[(i, f)], "b": b[(i, f)]}
                     for (i, f) in keys if a[(i, f)] != b[(i, f)]]
    payload = {
        "purpose": "N2 v3 annotation agreement (D1)",
        "labels": {"a": {"file": labels_a, "sha256": sha_file(OUT / labels_a)},
                   "b": {"file": labels_b, "sha256": sha_file(b_path)}},
        "agreement": result,
        "disagreements": disagreements,
        "generatedAt": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "generatedFromCommit": git_commit(),
    }
    if result["kappa"] < 0.7:
        payload["status"] = "kappa-below-0.7-no-freeze"
        write_status(payload)
        print(f"kappa {result['kappa']} < 0.7 -> no v3 freeze")
        return

    adj_path = OUT / adjudicated
    disagreement_keys = [(i, f) for (i, f) in keys if a[(i, f)] != b[(i, f)]]
    if disagreement_keys and not adj_path.exists():
        payload["status"] = "kappa-pass-adjudication-needed"
        payload["needsAdjudication"] = len(disagreements)
        write_status(payload)
        print(f"kappa {result['kappa']} >= 0.7; {len(disagreements)} disagreements "
              f"need {adjudicated}")
        return

    # Adjudication contains ONLY disagreement keys; agreed keys keep both labels.
    v3 = dict(a)
    if disagreement_keys:
        adj = load_adjudication(adj_path, disagreement_keys)
        for (i, f) in disagreement_keys:
            if adj[(i, f)] not in (a[(i, f)], b[(i, f)]):
                sys.exit(f"adjudication for {(i, f)} is neither annotator label")
            v3[(i, f)] = adj[(i, f)]
    v3_path = OUT / "labels-v3.jsonl"
    v3_text = "\n".join(json.dumps({"itemId": i, "factId": f, "label": v3[(i, f)]},
                                   ensure_ascii=False) for (i, f) in keys) + "\n"
    v3_path.write_text(v3_text, encoding="utf-8")

    v3_must = must_sets(v3)
    v2_must = v2_must_sets()
    changed = [{"itemId": i, "v2": sorted(v2_must[i]), "v3": sorted(v3_must.get(i, set())),
                "added": sorted(v3_must.get(i, set()) - v2_must[i]),
                "removed": sorted(v2_must[i] - v3_must.get(i, set()))}
               for i in sorted(v2_must) if v2_must[i] != v3_must.get(i, set())]
    gate = {"threshold": ">2 items out of 16", "changedItems": len(changed),
            "action": "rebuild-n3-16-inputs" if len(changed) > 2 else "reuse-n3-16-inputs",
            "items": changed}
    frozen = {
        "purpose": "N2 v3 frozen labels (D1) with kappa and the v2->v3 must gate",
        "status": "frozen",
        "decision": "D1",
        "rubric": manifest["rubric"],
        "labels": {"a": payload["labels"]["a"], "b": payload["labels"]["b"],
                   "adjudicated": ({"file": adjudicated, "sha256": sha_file(adj_path)}
                                   if adj_path.exists() else None),
                   "v3": {"file": "labels-v3.jsonl", "sha256": sha_file(v3_path)}},
        "agreement": result,
        "disagreements": disagreements,
        "mustGate": gate,
        "generatedAt": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "generatedFromCommit": git_commit(),
        "labelsV3": [{"itemId": i, "factId": f, "label": v3[(i, f)]} for (i, f) in keys],
    }
    FROZEN.parent.mkdir(parents=True, exist_ok=True)
    FROZEN.write_text(json.dumps(frozen, ensure_ascii=False, indent=2), encoding="utf-8")
    write_status({**payload, "status": "frozen", "mustGate": gate,
                  "frozenArchive": str(FROZEN.relative_to(REPO))})
    print(f"kappa {result['kappa']} >= 0.7; v3 frozen; must gate: "
          f"{len(changed)}/16 changed -> {gate['action']}")
    print(f"frozen -> {FROZEN}")


def selftest() -> None:
    keys = [(f"i{n}", f"f{n}") for n in range(20)]
    a = {k: CLASSES[n % 3] for n, k in enumerate(keys)}
    b = dict(a)
    perfect = kappa(a, b, keys)
    assert perfect["kappa"] == 1.0 and perfect["observedAgreement"] == 1.0
    b2 = dict(a)
    for k in keys[:4]:
        b2[k] = "must" if b2[k] != "must" else "may"
    mixed = kappa(a, b2, keys)
    assert 0.0 <= mixed["kappa"] < 1.0
    # verify a 3x3 confusion reconstruction
    total = sum(sum(row.values()) for row in mixed["confusion"].values())
    assert total == len(keys)
    with tempfile.TemporaryDirectory() as td:
        adj = pathlib.Path(td) / "adj.jsonl"
        adj.write_text("\n".join(json.dumps({"itemId": i, "factId": f,
                                              "label": "omit"})
                                 for (i, f) in keys[:2]) + "\n", encoding="utf-8")
        got = load_adjudication(adj, keys[:2])
        assert set(got) == set(keys[:2])
        try:
            load_adjudication(adj, keys[:3])
            raise AssertionError("missing adjudication was not rejected")
        except SystemExit:
            pass
    print(f"selftest PASS: perfect kappa=1.0; mixed kappa={mixed['kappa']}; "
          f"adjudication coverage enforced")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--labels-a", default="labels-c-impl.jsonl")
    parser.add_argument("--labels-b", default="labels-c-reviewer.jsonl")
    parser.add_argument("--adjudicated", default="labels-adjudicated.jsonl")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()
    if args.selftest:
        selftest()
        return
    run(args.labels_a, args.labels_b, args.adjudicated)


if __name__ == "__main__":
    main()
