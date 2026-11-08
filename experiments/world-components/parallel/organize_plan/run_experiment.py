# -*- coding: utf-8 -*-
"""Run the c3 offline experiment: legality, negative controls, reference
composition, text conformance, and fixed-strategy controls.

No model, no training, no GPU. The only executable "downstream" here is the
deterministic reference composer, which exists to prove that (a) a legal plan
determines a text, (b) the checker can tell the two plans apart, and (c) no
fixed grouping policy passes both plans. The pre-registered model arm is NOT
run in this round (no plan-trained checkpoint is available locally and this
round forbids training).

Outputs (under runs/r1/):
    legality.json          plan validator results, per source/plan
    negatives.json         invalid plans and the codes they trigger
    reference-output.jsonl deterministic text for every plan
    conformance.json       self / cross / negative text checks
    controls.json          fixed-strategy paired results
    downstream-inputs.jsonl N4 prompts (simulated downstream input)
    summary.json           headline counts
    input-hashes.json      code/input hashes, git head, environment
    run.log                human-readable tables

Usage:
    python -X utf8 run_experiment.py
"""

from __future__ import annotations

import copy
import hashlib
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]  # c3 worktree root
RUN = HERE / "runs" / "r2"   # v2 checker; runs/r1 stays as the v1 record

sys.path.insert(0, str(HERE))
import plan_contract as contract  # noqa: E402
import reference_compose  # noqa: E402
import render_input  # noqa: E402
import text_conformance  # noqa: E402


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def git(*args: str) -> str:
    try:
        return subprocess.run(
            ["git", "-c", f"safe.directory={ROOT.as_posix()}", *args],
            cwd=ROOT, capture_output=True, text=True, check=True,
        ).stdout.strip()
    except Exception as exc:  # recorded, not fatal
        return f"<git error: {exc}>"


def plan_signature(plan: dict) -> str:
    return json.dumps(plan, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def fixed_plans(facts: list[dict], authorized_edges: list[dict]) -> dict[str, dict]:
    """Three fixed, plan-blind policies. They see only facts + authorization."""
    ids = [f["factId"] for f in facts]
    by_id = {f["factId"]: f for f in facts}
    auth = [{"from": e["from"], "to": e["to"], "type": "before", "mode": "required"}
            for e in authorized_edges if e["from"] in by_id and e["to"] in by_id]
    targets = {e["to"] for e in auth}

    def split_all() -> dict:
        return {"groups": [{"facts": [fid], "links": []} for fid in ids],
                "refs": {fid: "name" for fid in ids}, "edges": auth}

    def merge_adjacent_pairs() -> dict:
        groups, refs, i = [], {}, 0
        while i < len(ids):
            fid = ids[i]
            nxt = ids[i + 1] if i + 1 < len(ids) else None
            can = (nxt is not None
                   and by_id[fid]["entityId"] == by_id[nxt]["entityId"]
                   and fid not in targets and nxt not in targets)
            if can:
                groups.append({"facts": [fid, nxt], "links": ["continuation"]})
                refs[fid] = "name"
                refs[nxt] = "omit"
                i += 2
            else:
                groups.append({"facts": [fid], "links": []})
                refs[fid] = "name"
                i += 1
        return {"groups": groups, "refs": refs, "edges": auth}

    def merge_one(pick: str) -> dict:
        candidates = [
            (i, ids[i], ids[i + 1]) for i in range(len(ids) - 1)
            if by_id[ids[i]]["entityId"] == by_id[ids[i + 1]]["entityId"]
            and ids[i] not in targets and ids[i + 1] not in targets
        ]
        if not candidates:
            return split_all()
        choose = candidates[0] if pick == "first" else candidates[-1]
        a, b = choose[1], choose[2]
        groups, refs = [], {}
        i = 0
        while i < len(ids):
            if i + 1 < len(ids) and ids[i] == a and ids[i + 1] == b:
                groups.append({"facts": [a, b], "links": ["continuation"]})
                refs[a] = "name"
                refs[b] = "omit"
                i += 2
            else:
                fid = ids[i]
                groups.append({"facts": [fid], "links": []})
                refs[fid] = "name"
                i += 1
        return {"groups": groups, "refs": refs, "edges": auth}

    return {
        "split-all": split_all(),
        "merge-all-adjacent": merge_adjacent_pairs(),
        "merge-first-pair": merge_one("first"),
        "merge-last-pair": merge_one("last"),
    }


def _smoke_summary():
    path = RUN / "model-smoke.json"
    if not path.exists():
        return None
    rec = json.loads(path.read_text(encoding="utf-8"))
    rows = rec.get("rows", [])
    return {
        "file": "runs/r1/model-smoke.json",
        "arm": rec.get("arm"),
        "rows": len(rows),
        "conformancePass": sum(1 for r in rows if r.get("conformanceOk")),
        "note": rec.get("notTheMissingArm"),
    }


REVIEW_FIELDS = ("verdict", "reviewerNote", "reviewer", "reviewedAt")


def write_manual_review(queue: list[dict]) -> dict:
    """Write the review queue WITHOUT destroying filled-in verdicts.

    A re-run regenerates the rows (same queueIds, same order), but the
    verdict/reviewerNote of an existing row and the top-level `reviewer` block
    are carried over. Rows that no longer exist are kept under `orphanedRows`
    instead of being dropped silently.
    """
    path = RUN / "manual-review.json"
    previous: dict[str, dict] = {}
    reviewer = None
    if path.exists():
        old = json.loads(path.read_text(encoding="utf-8"))
        reviewer = old.get("reviewer")
        previous = {r["queueId"]: r for r in old.get("rows", [])}
    merged, seen, preserved = [], set(), 0
    for row in queue[:10]:
        old = previous.get(row["queueId"])
        if old:
            seen.add(row["queueId"])
            for field in REVIEW_FIELDS:
                if old.get(field) not in (None, "", {}):
                    row[field] = old[field]
                    if field == "verdict":
                        preserved += 1
        merged.append(row)
    orphaned = [r for k, r in previous.items() if k not in seen]
    doc: dict = {}
    if reviewer:
        doc["reviewer"] = reviewer
    doc["rows"] = merged
    if orphaned:
        doc["orphanedRows"] = orphaned
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return {"rows": len(merged), "preservedVerdicts": preserved,
            "orphaned": len(orphaned), "reviewer": reviewer}


def check_frozen_criteria() -> list[str]:
    """Refuse to run when the frozen criteria no longer describe this code."""
    # Prefer the newest frozen criteria file; criteria-v2 stays as the R2 record.
    candidates = sorted((HERE / "freeze").glob("criteria-v*.json"))
    path = candidates[-1] if candidates else HERE / "freeze" / "criteria-v2.json"
    if not path.exists():
        return []          # first run: criteria are generated afterwards
    doc = json.loads(path.read_text(encoding="utf-8"))
    problems = []
    want = doc["checker"]["sha256"]
    got = sha256(HERE / "text_conformance.py")
    if want != got:
        problems.append(f"text_conformance.py hash {got[:12]} != frozen in {path.name}: {want[:12]}")
    want_probes = doc["probeSet"]["sha256"]
    got_probes = sha256(HERE / "freeze" / "tamper-probes.json")
    if want_probes != got_probes:
        problems.append(f"tamper-probes.json hash {got_probes[:12]} != frozen {want_probes[:12]}")
    return problems


def main() -> int:
    drift = check_frozen_criteria()
    if drift:
        print("FROZEN CRITERIA DRIFT:")
        for d in drift:
            print(" -", d)
        print("regenerate with: python -X utf8 build_criteria.py (then re-run this script)")
        return 1
    RUN.mkdir(parents=True, exist_ok=True)
    sources = json.loads((HERE / "freeze/sources.json").read_text(encoding="utf-8"))["sources"]
    src_by_id = {s["sourceId"]: s for s in sources}
    plans = load_jsonl(HERE / "freeze/plans-v1.jsonl")
    contexts = json.loads((HERE / "freeze/contexts.json").read_text(encoding="utf-8"))["contexts"]

    # --- 1. legality ------------------------------------------------------
    legality = []
    for p in plans:
        src = src_by_id[p["sourceId"]]
        facts = [f for f in src["facts"] if f["factId"] in p["factsUsed"]]
        result = contract.validate_plan(facts, p["authorizedEdges"], p["plan"])
        legality.append({
            "sourceId": p["sourceId"],
            "family": p["family"],
            "planId": p["planId"],
            "shape": p["shape"],
            "factsUsed": p["factsUsed"],
            "ok": result["ok"],
            "errors": result["errors"],
            "stats": result["stats"],
        })
    legal_count = sum(1 for r in legality if r["ok"])

    # --- 2. negative controls --------------------------------------------
    neg_cases = json.loads((HERE / "freeze/negative-cases.json").read_text(encoding="utf-8"))["cases"]
    negatives = []
    for c in neg_cases:
        result = contract.validate_plan(c["facts"], c["authorizedEdges"], c["plan"])
        codes = sorted({e["code"] for e in result["errors"]})
        expected = sorted(set(c["expectedCodes"]))
        missing = [x for x in expected if x not in codes]
        negatives.append({
            "caseId": c["caseId"],
            "note": c["note"],
            "synthetic": c["synthetic"],
            "expectedCodes": expected,
            "actualCodes": codes,
            "ok": not missing and not result["ok"],
            "missingExpected": missing,
            "errors": result["errors"],
        })
    negative_pass = sum(1 for r in negatives if r["ok"])

    # --- 2b. the OLD controllability plans, re-checked by this validator ---
    # The old edge carries an inline `authorized: true` field; this contract
    # takes authorization from the fixture record instead, so that key is
    # removed before validation. Nothing else is changed.
    legacy_path = ROOT / "artifacts/world-components/organize-wording/controllability-v1.jsonl"
    legacy_rows = []
    if legacy_path.exists():
        old_by_id = {json.loads(l)["pairId"]: json.loads(l)
                     for l in legacy_path.read_text(encoding="utf-8").splitlines() if l.strip()}
        for src in sources:
            old = old_by_id.get(src["sourceId"])
            if old is None:
                continue
            auth = [{"from": r["fromFactId"], "to": r["toFactId"]}
                    for r in src["authorization"].get("relations", [])]
            for arm in ("A", "B"):
                plan = copy.deepcopy(old["plans"][arm]["plan"])
                for e in plan.get("edges", []):
                    e.pop("authorized", None)
                result = contract.validate_plan(src["facts"], auth, plan)
                legacy_rows.append({
                    "sourceId": src["sourceId"],
                    "arm": arm,
                    "ok": result["ok"],
                    "errors": result["errors"],
                })

    # --- 3. reference text ------------------------------------------------
    ref_rows = []
    for p in plans:
        src = src_by_id[p["sourceId"]]
        facts = [f for f in src["facts"] if f["factId"] in p["factsUsed"]]
        text = reference_compose.compose(facts, p["plan"])
        ref_rows.append({
            "sourceId": p["sourceId"],
            "family": p["family"],
            "planId": p["planId"],
            "shape": p["shape"],
            "text": text,
            "chars": len(text),
        })
    (RUN / "reference-output.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in ref_rows), encoding="utf-8")

    # --- 4. conformance: self / cross / missing-edge ----------------------
    text_by_key = {(r["sourceId"], r["planId"]): r["text"] for r in ref_rows}
    plan_by_key = {(p["sourceId"], p["planId"]): p for p in plans}
    conformance = []
    for src_id in sorted({p["sourceId"] for p in plans}):
        src = src_by_id[src_id]
        p1, p2 = plan_by_key[(src_id, "P1")], plan_by_key[(src_id, "P2")]
        for check_id, plan_key, text_key in [
            ("self-P1", "P1", "P1"),
            ("self-P2", "P2", "P2"),
            ("cross-P1-text-vs-P2", "P2", "P1"),
            ("cross-P2-text-vs-P1", "P1", "P2"),
        ]:
            plan = plan_by_key[(src_id, plan_key)]
            facts = [f for f in src["facts"] if f["factId"] in plan["factsUsed"]]
            result = text_conformance.check_text(
                facts, plan["authorizedEdges"], plan["plan"], text_by_key[(src_id, text_key)],
                context=contexts.get(src_id),
            )
            conformance.append({
                "sourceId": src_id,
                "family": src["family"],
                "check": check_id,
                "textPlanId": text_key,
                "checkedPlanId": plan_key,
                "accepted": result["accepted"],
                "hard": result["hard"],
                "review": result["review"],
                "checks": result["checks"],
            })

    # negative: remove the "随后，" wording from a required edge source
    edge_source = next(s for s in sources if s["family"] == "edge")
    edge_plan = next(p for p in plans if p["sourceId"] == edge_source["sourceId"])
    edge_text = text_by_key[(edge_source["sourceId"], edge_plan["planId"])]
    broken = edge_text.replace("随后，", "", 1)
    broken_result = text_conformance.check_text(
        [f for f in edge_source["facts"] if f["factId"] in edge_plan["factsUsed"]],
        edge_plan["authorizedEdges"], edge_plan["plan"], broken,
        context=contexts.get(edge_source["sourceId"]),
    )
    conformance.append({
        "sourceId": edge_source["sourceId"],
        "family": "edge",
        "check": "negative-missing-required-wording",
        "textPlanId": edge_plan["planId"],
        "checkedPlanId": edge_plan["planId"],
        "accepted": broken_result["accepted"],
        "hard": broken_result["hard"],
        "review": broken_result["review"],
        "checks": broken_result["checks"],
    })

    self_pass = sum(1 for r in conformance if r["check"].startswith("self") and r["accepted"])
    self_total = sum(1 for r in conformance if r["check"].startswith("self"))
    cross_fail = sum(1 for r in conformance if r["check"].startswith("cross") and not r["accepted"])
    cross_total = sum(1 for r in conformance if r["check"].startswith("cross"))
    negative_caught = next(r for r in conformance if r["check"].startswith("negative"))["accepted"] is False

    # --- 4b. frozen tamper probes (v2 gate) ------------------------------
    probe_doc = json.loads((HERE / "freeze/tamper-probes.json").read_text(encoding="utf-8"))
    probes = []
    for pr in probe_doc["probes"]:
        plan = plan_by_key[(pr["baseSourceId"], pr["basePlanId"])]
        src = src_by_id[pr["baseSourceId"]]
        facts = [f for f in src["facts"] if f["factId"] in plan["factsUsed"]]
        result = text_conformance.check_text(
            facts, plan["authorizedEdges"], plan["plan"], pr["text"],
            context=contexts.get(pr["baseSourceId"]),
        )
        hard_codes = sorted({h["code"] for h in result["hard"]})
        review_runs = sorted({r.get("run", "") for r in result["review"]})
        expect = pr["expect"]
        if expect["verdict"] == "fail":
            met = bool(set(hard_codes) & set(expect["mustIncludeCodes"]))
        else:
            need = expect["reviewRunContains"]
            met = (not result["hard"]) and any(all(n in run for n in need) for run in review_runs)
        probes.append({
            "probeId": pr["probeId"],
            "mutation": pr["mutation"],
            "expectedVerdict": expect["verdict"],
            "expectedCodes": expect["mustIncludeCodes"],
            "actualHardCodes": hard_codes,
            "actualReviewRuns": review_runs,
            "accepted": result["accepted"],
            "met": met,
        })
    probes_met = sum(1 for p in probes if p["met"])

    # --- 4c. manual review queue (review items only, max 10 rows/batch) ---
    queue = []
    for pr in probe_doc["probes"]:
        plan = plan_by_key[(pr["baseSourceId"], pr["basePlanId"])]
        src = src_by_id[pr["baseSourceId"]]
        facts = [f for f in src["facts"] if f["factId"] in plan["factsUsed"]]
        result = text_conformance.check_text(
            facts, plan["authorizedEdges"], plan["plan"], pr["text"],
            context=contexts.get(pr["baseSourceId"]),
        )
        for item in result["review"]:
            queue.append({
                "queueId": f"{pr['probeId']}:{item.get('run', '')}",
                "origin": "tamper-probe",
                "probeId": pr["probeId"],
                "sourceId": pr["baseSourceId"],
                "planId": pr["basePlanId"],
                "code": item["code"],
                "run": item.get("run"),
                "outsideVocabulary": item.get("outsideVocabulary", ""),
                "detail": item["detail"],
                "text": pr["text"],
                "verdict": None,
                "reviewerNote": "",
            })
    # archived base-model output, re-scored with v2 (no new model call)
    smoke_path = HERE / "runs" / "r1" / "model-smoke.jsonl"
    if smoke_path.exists():
        for line in smoke_path.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            plan = plan_by_key[(row["sourceId"], row["planId"])]
            src = src_by_id[row["sourceId"]]
            facts = [f for f in src["facts"] if f["factId"] in plan["factsUsed"]]
            result = text_conformance.check_text(
                facts, plan["authorizedEdges"], plan["plan"], row["output"],
                context=contexts.get(row["sourceId"]),
            )
            queue.append({
                "queueId": f"smoke:{row['sourceId']}:{row['planId']}",
                "origin": "archived-base-smoke",
                "probeId": None,
                "sourceId": row["sourceId"],
                "planId": row["planId"],
                "code": "archived-output-hard-fail" if result["hard"] else "archived-output-accepted",
                "run": None,
                "outsideVocabulary": "",
                "detail": f"{len(result['hard'])} hard finding(s): "
                          + ", ".join(sorted({h['code'] for h in result['hard']})[:6]),
                "text": row["output"],
                # leave the verdict empty: acceptance criteria allow only
                # paraphrase-ok / new-content-fail / unsure, and these rows are
                # already decided by the program's hard checks.
                "verdict": None,
                "alreadyFailedHard": bool(result["hard"]),
                "reviewerNote": "archived output already fails hard; listed for completeness",
            })
    queue = queue[:10]
    review_write = write_manual_review(queue)

    # --- 5. fixed-strategy controls --------------------------------------
    controls = []
    for src_id in sorted(src_by_id):
        src = src_by_id[src_id]
        facts = src["facts"] if src["family"] == "edge" else [
            f for f in src["facts"] if f["factId"] in src["selectedFactIds"]]
        auth = [{"from": r["fromFactId"], "to": r["toFactId"]}
                for r in src["authorization"].get("relations", [])
                if r["fromFactId"] in {f["factId"] for f in facts}
                and r["toFactId"] in {f["factId"] for f in facts}]
        p1, p2 = plan_by_key[(src_id, "P1")], plan_by_key[(src_id, "P2")]
        p1sig, p2sig = plan_signature(p1["plan"]), plan_signature(p2["plan"])
        for name, fixed in fixed_plans(facts, auth).items():
            v = contract.validate_plan(facts, auth, fixed)
            sig = plan_signature(fixed)
            controls.append({
                "sourceId": src_id,
                "family": src["family"],
                "strategy": name,
                "planLegal": v["ok"],
                "matchesP1": sig == p1sig,
                "matchesP2": sig == p2sig,
                "paired": sig == p1sig and sig == p2sig,
            })
    controls_paired = sum(1 for c in controls if c["paired"])
    controls_legal = sum(1 for c in controls if c["planLegal"])

    # --- 6. downstream inputs --------------------------------------------
    inputs = []
    for p in plans:
        src = src_by_id[p["sourceId"]]
        facts = [f for f in src["facts"] if f["factId"] in p["factsUsed"]]
        prompt = render_input.render_prompt(contexts[p["sourceId"]], facts, p["plan"], p["authorizedEdges"])
        inputs.append({
            "sourceId": p["sourceId"],
            "family": p["family"],
            "planId": p["planId"],
            "shape": p["shape"],
            "factsUsed": p["factsUsed"],
            "plan": p["plan"],
            "prompt": prompt,
        })
    (RUN / "downstream-inputs.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in inputs), encoding="utf-8")

    # --- 6b. compare this run's inputs with the r1 record ----------------
    same_as_r1 = "<r1 missing>"
    r1_inputs = HERE / "runs" / "r1" / "downstream-inputs.jsonl"
    if r1_inputs.exists():
        same_as_r1 = sha256(r1_inputs) == sha256(RUN / "downstream-inputs.jsonl")

    # --- 7. summaries -----------------------------------------------------
    summary = {
        "sources": len(sources),
        "families": {
            "edge": sum(1 for s in sources if s["family"] == "edge"),
            "grouping": sum(1 for s in sources if s["family"] == "grouping"),
        },
        "plans": len(plans),
        "legalPlans": legal_count,
        "negativeCases": len(negatives),
        "negativePass": negative_pass,
        "legacyPlans": {"rows": len(legacy_rows),
                        "legal": sum(1 for r in legacy_rows if r["ok"])},
        "referenceTexts": len(ref_rows),
        "checkerVersion": text_conformance.CONTRACT_VERSION,
        "conformance": {
            "selfPass": self_pass,
            "selfTotal": self_total,
            "crossFail": cross_fail,
            "crossTotal": cross_total,
            "missingRequiredWordingCaught": negative_caught,
        },
        "tamperProbes": {
            "total": len(probes),
            "met": probes_met,
            "hardFail": sum(1 for p in probes if p["expectedVerdict"] == "fail"),
            "manualReview": sum(1 for p in probes if p["expectedVerdict"] == "review"),
        },
        "manualReviewQueue": review_write["rows"],
        "manualReviewPreservedVerdicts": review_write["preservedVerdicts"],
        "manualReviewOrphaned": review_write["orphaned"],
        "downstreamInputsIdenticalToR1": same_as_r1,
        "fixedStrategy": {
            "rows": len(controls),
            "legalRows": controls_legal,
            "pairedRows": controls_paired,
        },
        "modelArm": {
            "capability": "not run: no plan-trained checkpoint locally; training is out of scope this round",
            "baseSmoke": _smoke_summary(),
        },
    }
    (RUN / "legality.json").write_text(json.dumps({"rows": legality}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    (RUN / "negatives.json").write_text(json.dumps({"rows": negatives}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    (RUN / "legacy-plans.json").write_text(json.dumps({"rows": legacy_rows}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    (RUN / "conformance.json").write_text(json.dumps({"rows": conformance}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    (RUN / "controls.json").write_text(json.dumps({"rows": controls}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    (RUN / "tamper-probes.json").write_text(json.dumps({"rows": probes}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    review_write = write_manual_review(queue)
    (RUN / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    hashes = {
        "created": datetime.now(timezone.utc).isoformat(),
        "runtimeHead": git("rev-parse", "HEAD"),
        "runtimeBranch": git("rev-parse", "--abbrev-ref", "HEAD"),
        "runtimeStatus": git("status", "--porcelain"),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "code": {name: sha256(HERE / name) for name in [
            "plan_contract.py", "build_freeze.py", "build_tamper_probes.py", "build_criteria.py",
            "reference_compose.py", "text_conformance.py", "render_input.py",
            "run_experiment.py", "model_smoke.py"]},
        "freeze": {name: sha256(HERE / "freeze" / name) for name in [
            "sources.json", "plans-v1.jsonl", "negative-cases.json",
            "contexts.json", "tamper-probes.json", "criteria-v2.json",
            "source-hashes.json"]},
    }
    (RUN / "input-hashes.json").write_text(json.dumps(hashes, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    lines = [
        f"# c3 organize-plan run r1  {summary['plans']} plans / {summary['sources']} sources",
        "",
        "## Legality",
        f"legal plans: {legal_count}/{len(plans)}",
        "",
        "| source | family | P1 shape | P1 legal | P2 shape | P2 legal |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for src_id in sorted(src_by_id):
        r1 = next(r for r in legality if r["sourceId"] == src_id and r["planId"] == "P1")
        r2 = next(r for r in legality if r["sourceId"] == src_id and r["planId"] == "P2")
        lines.append(f"| {src_id} | {r1['family']} | {r1['shape']} | {'yes' if r1['ok'] else 'NO'} "
                     f"| {r2['shape']} | {'yes' if r2['ok'] else 'NO'} |")
    lines += [
        "",
        "## Negative controls",
        f"pass: {negative_pass}/{len(negatives)}",
        "",
        "| case | expected | actual | ok |",
        "| --- | --- | --- | --- |",
    ]
    for r in negatives:
        lines.append(f"| {r['caseId']} | {', '.join(r['expectedCodes'])} | {', '.join(r['actualCodes'])} | {'yes' if r['ok'] else 'NO'} |")
    lines += [
        "",
        "## Tamper probes (v2 gate)",
        f"met: {probes_met}/{len(probes)}",
        "",
        "| probe | mutation | expected | hard codes | review runs | met |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for p in probes:
        lines.append(f"| {p['probeId']} | {p['mutation'][:52]} | {p['expectedVerdict']} "
                     f"| {', '.join(p['actualHardCodes']) or '-'} "
                     f"| {', '.join(p['actualReviewRuns']) or '-'} | {'yes' if p['met'] else 'NO'} |")
    lines += [
        "",
        "## Manual review queue",
        f"rows: {len(queue)} (verdicts are empty until a human fills them)",
        "",
        "## Old controllability plans re-checked",
        f"legal: {sum(1 for r in legacy_rows if r['ok'])}/{len(legacy_rows)} "
        "(A/B on the 9 overlapping sources; inline `authorized: true` removed)",
        "",
        "## Reference text conformance",
        f"self pass: {self_pass}/{self_total}; cross fail: {cross_fail}/{cross_total}; "
        f"missing-required-wording caught: {negative_caught}",
        "",
        "## Fixed-strategy controls",
        f"legal fixed plans: {controls_legal}/{len(controls)}; paired successes: {controls_paired}",
        "",
        "| source | strategy | legal | =P1 | =P2 | paired |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for c in controls:
        lines.append(f"| {c['sourceId']} | {c['strategy']} | {'yes' if c['planLegal'] else 'NO'} "
                     f"| {'yes' if c['matchesP1'] else 'no'} | {'yes' if c['matchesP2'] else 'no'} "
                     f"| {'YES' if c['paired'] else 'no'} |")
    lines += ["", "## Downstream", json.dumps(summary["modelArm"], ensure_ascii=False), ""]
    (RUN / "run.log").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(json.dumps(summary, ensure_ascii=False, indent=1))
    print(f"wrote {RUN}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
