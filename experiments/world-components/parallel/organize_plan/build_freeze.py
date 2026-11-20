# -*- coding: utf-8 -*-
"""Build the c3 frozen inputs from the registered world-provenance fixture.

Reads (read-only, main worktree):
    artifacts/world-provenance/pairs/<source>-authorized.json
    artifacts/world-provenance/pairs/{fixture,train}.db
    artifacts/world-provenance/pairs/pair-worlds.json
    artifacts/world-components/organize-wording/controllability-v1.jsonl
    (presentation context only; the facts come from the fixture above)

Writes (this task's own directory only):
    freeze/sources.json          selected facts + provenance + authorization
    freeze/plans-v1.jsonl        two legal plans per source
    freeze/negative-cases.json   deliberately invalid plans for the validator
    freeze/contexts.json         scene context copied from the registered material
    freeze/source-hashes.json    every input hash + the verification record

The script refuses to write anything if any single fact cannot be traced to
(a) the authorized JSON, (b) a world_evidence row, and (c) the point's
delta_json. Nothing is inferred from narration text.

Usage:
    python -X utf8 build_freeze.py
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXPERIMENT = HERE
MAIN = HERE.parents[6]  # D:/others/Jity (c3 lives under .local/parallel/...)

PROV = MAIN / "artifacts/world-provenance/pairs"
COMMITTED = MAIN / ".local/parallel/e-browser-regression"
COMMITTED_PAIRS = "artifacts/next-inputs/world-provenance/pairs"
CONTROLLABILITY = EXPERIMENT.parents[3] / "artifacts/world-components/organize-wording/controllability-v1.jsonl"

EDGE_SOURCES = [f"fixture-r{i}" for i in range(1, 6)]
# train-r1 is not in the registered controllability/pairs material (it only exists
# in the provenance extraction), so the grouping family starts at train-r2.
GROUP_SOURCES = [f"train-r{i}" for i in range(2, 6)]

# fact kind -> (world_evidence.kind, delta_json field)
KIND_MAP = {
    "appearance_changed": ("appearance", "appearanceChanges"),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_sha256(obj) -> str:
    raw = json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def git_head() -> str:
    try:
        return subprocess.run(
            ["git", "-c", f"safe.directory={MAIN.as_posix()}", "rev-parse", "HEAD"],
            cwd=MAIN, capture_output=True, text=True, check=True,
        ).stdout.strip()
    except Exception as exc:  # recorded, not fatal
        return f"<git error: {exc}>"


def git_in(root: Path, *args: str) -> str:
    try:
        return subprocess.run(
            ["git", "-c", f"safe.directory={root.as_posix()}", *args],
            cwd=root, capture_output=True, text=True, check=True,
        ).stdout.strip()
    except Exception as exc:  # recorded, not fatal
        return f"<git error: {exc}>"


def committed_copy(rel: str) -> dict | None:
    """Return {file, sha256, tracked} for the committed fixture copy, or None."""
    path = COMMITTED / rel
    if not path.exists():
        return None
    try:
        tracked = subprocess.run(
            ["git", "-c", f"safe.directory={COMMITTED.as_posix()}", "ls-files", "--error-unmatch", rel],
            cwd=COMMITTED, capture_output=True, text=True,
        ).returncode == 0
    except Exception:
        tracked = False
    return {"file": rel, "sha256": sha256(path), "tracked": tracked}


def verify_source(source_id: str) -> dict:
    auth_path = PROV / f"{source_id}-authorized.json"
    db_name = "fixture.db" if source_id.startswith("fixture-") else "train.db"
    db_path = PROV / db_name
    auth_raw = auth_path.read_bytes()
    auth = json.loads(auth_raw.decode("utf-8"))

    problems: list[str] = []
    committed = committed_copy(f"{COMMITTED_PAIRS}/{source_id}-authorized.json")
    if committed is None:
        problems.append("committed fixture copy is missing")
    else:
        if not committed["tracked"]:
            problems.append("committed fixture copy is not tracked by git")
        if committed["sha256"] != hashlib.sha256(auth_raw).hexdigest():
            problems.append("committed fixture copy hash differs from the working copy")
    units = auth.get("units") or []
    points = auth.get("points") or []

    if [u.get("factId") for u in units] != [f"f{i}" for i in range(len(units))]:
        problems.append("units are not f0..fn in order")
    if len(units) != 5:
        problems.append(f"expected 5 units, got {len(units)}")

    point_by_id = {p.get("id"): p for p in points}
    unit_point_ids = [u.get("pointId") for u in units]
    if any(p is None for p in unit_point_ids):
        problems.append("a unit has no pointId")

    con = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    evidence_checks = 0
    delta_checks = 0
    chain_checks = 0
    for unit in units:
        eid = unit.get("evidenceId")
        row = con.execute(
            "select evidence_id, world_id, point_id, sequence, entity_id, kind, item_key, payload_json "
            "from world_evidence where evidence_id=?", (eid,)
        ).fetchone()
        if row is None:
            problems.append(f"{unit.get('factId')}: evidence row {eid} missing")
            continue
        evidence_checks += 1
        payload = json.loads(row["payload_json"])
        if row["point_id"] != unit.get("pointId"):
            problems.append(f"{unit.get('factId')}: evidence point_id mismatch")
        if row["entity_id"] != unit.get("entityId"):
            problems.append(f"{unit.get('factId')}: evidence entity_id mismatch")
        if int(row["sequence"]) != int(unit.get("sequence")):
            problems.append(f"{unit.get('factId')}: evidence sequence mismatch")
        if payload.get("text") != unit.get("text"):
            problems.append(f"{unit.get('factId')}: evidence text mismatch")
        if payload.get("id") != row["item_key"]:
            problems.append(f"{unit.get('factId')}: evidence payload id/item_key mismatch")

        expected_kind, field = KIND_MAP.get(unit.get("kind"), (None, None))
        if expected_kind is None:
            problems.append(f"{unit.get('factId')}: unmapped kind {unit.get('kind')!r}")
            continue
        if row["kind"] != expected_kind:
            problems.append(f"{unit.get('factId')}: evidence kind {row['kind']!r} != {expected_kind!r}")

        point = con.execute(
            "select id, previous_point_id, sequence, time_json, delta_json from world_points where id=?",
            (unit.get("pointId"),)
        ).fetchone()
        if point is None:
            problems.append(f"{unit.get('factId')}: point row missing")
            continue
        delta = json.loads(point["delta_json"] or "{}")
        ent = delta.get(unit.get("entityId")) or {}
        changes = ent.get(field) or []
        if not any(c.get("id") == row["item_key"] and c.get("text") == unit.get("text") for c in changes):
            problems.append(f"{unit.get('factId')}: point delta has no matching {field} item")
        else:
            delta_checks += 1

        pe = con.execute(
            "select point_id, sequence, previous_point_id, delta_status from world_point_evidence where point_id=?",
            (unit.get("pointId"),)
        ).fetchone()
        if pe is None:
            problems.append(f"{unit.get('factId')}: world_point_evidence row missing")
        else:
            expected_point = point_by_id.get(unit.get("pointId"))
            if expected_point is None:
                problems.append(f"{unit.get('factId')}: authorized points list lacks {unit.get('pointId')}")
            else:
                if int(pe["sequence"]) != int(expected_point.get("sequence")):
                    problems.append(f"{unit.get('factId')}: point sequence mismatch")
                if (pe["previous_point_id"] or None) != (expected_point.get("previousPointId") or None):
                    problems.append(f"{unit.get('factId')}: previousPointId mismatch")
                want_time = expected_point.get("time")
                got_time = json.loads(point["time_json"]) if point["time_json"] else None
                if got_time != want_time:
                    problems.append(f"{unit.get('factId')}: time_json mismatch")
                if pe["delta_status"] != "recorded":
                    problems.append(f"{unit.get('factId')}: delta_status not recorded")
                chain_checks += 1

    # authorization record
    auth_rec = auth.get("authorization") or {}
    relations = auth_rec.get("relations") or []
    if auth_rec.get("verdict") != "pass":
        problems.append(f"authorization verdict is {auth_rec.get('verdict')!r}")
    if auth_rec.get("validatorVersion") != "world-relation-validator/1":
        problems.append(f"unexpected validator {auth_rec.get('validatorVersion')!r}")
    by_fact = {u.get("factId"): u for u in units}
    relation_checks = 0
    for rel in relations:
        if rel.get("type") != "before":
            problems.append(f"relation type {rel.get('type')!r} is not before")
            continue
        src, dst = by_fact.get(rel.get("fromFactId")), by_fact.get(rel.get("toFactId"))
        if src is None or dst is None:
            problems.append("relation endpoint not in units")
            continue
        ev = [e.get("evidenceId") for e in rel.get("evidence") or []]
        if ev != [src.get("evidenceId"), dst.get("evidenceId")]:
            problems.append(f"relation {rel.get('fromFactId')}->{rel.get('toFactId')} evidence mismatch")
        if not isinstance(rel.get("elapsedSeconds"), int) or rel["elapsedSeconds"] <= 0:
            problems.append("relation elapsedSeconds is not a positive integer")
        if (rel.get("authorization") or {}).get("verdict") != "pass":
            problems.append("relation has no pass verdict")
        relation_checks += 1
    if [u.get("factId") for u in units] and relations and len(relations) != 1:
        problems.append(f"expected exactly 1 authorized relation, got {len(relations)}")

    point_order = [point_by_id[u["pointId"]]["sequence"] for u in units]
    if point_order != sorted(point_order):
        problems.append("unit order is not point order")

    return {
        "sourceId": source_id,
        "worldId": auth.get("worldId"),
        "sourceFile": str(auth_path.relative_to(MAIN)),
        "sourceSha256": hashlib.sha256(auth_raw).hexdigest(),
        "committedCopy": committed,
        "dbFile": str(db_path.relative_to(MAIN)),
        "dbSha256": sha256(db_path),
        "facts": [
            {
                "factId": u["factId"],
                "entityId": u["entityId"],
                "name": u["name"],
                "kind": u["kind"],
                "text": u["text"],
                "pointId": u["pointId"],
                "evidenceId": u["evidenceId"],
                "sequence": u["sequence"],
            }
            for u in units
        ],
        "points": points,
        "requestedRelations": auth.get("requestedRelations") or [],
        "authorization": auth_rec,
        "verification": {
            "ok": not problems,
            "units": len(units),
            "evidenceRows": evidence_checks,
            "deltaChecks": delta_checks,
            "pointChainChecks": chain_checks,
            "relationChecks": relation_checks,
            "problems": problems,
        },
    }


def edge_plans(facts: list[dict]) -> dict[str, dict]:
    """All 5 facts. The authorized before(f2->f3) is required in both plans.
    Two legal organizations that differ ONLY by whether f0/f1 is one
    expression or two; both keep f3 alone, as the relation rule requires."""
    ids = [f["factId"] for f in facts]
    edge = {"from": "f2", "to": "f3", "type": "before", "mode": "required"}
    merge = {
        "groups": [{"facts": [ids[0], ids[1]], "links": ["continuation"]}]
        + [{"facts": [fid], "links": []} for fid in ids[2:]],
        "refs": {ids[0]: "name", ids[1]: "omit", **{fid: "name" for fid in ids[2:]}},
        "edges": [edge],
    }
    split = {
        "groups": [{"facts": [fid], "links": []} for fid in ids],
        "refs": {fid: "name" for fid in ids},
        "edges": [edge],
    }
    return {"merge-left": merge, "split-all": split}


def group_plans(facts: list[dict]) -> dict[str, dict]:
    """Facts [f0,f1,f3,f4]: f2 is excluded, so the authorization has no
    applicable endpoint and edges must be empty. Two legal organizations
    merge a DIFFERENT same-entity pair. A fixed "merge every pair" or
    "split everything" strategy fails both."""
    ids = [f["factId"] for f in facts]
    left = {
        "groups": [
            {"facts": [ids[0], ids[1]], "links": ["continuation"]},
            {"facts": [ids[2]], "links": []},
            {"facts": [ids[3]], "links": []},
        ],
        "refs": {ids[0]: "name", ids[1]: "omit", ids[2]: "name", ids[3]: "name"},
        "edges": [],
    }
    right = {
        "groups": [
            {"facts": [ids[0]], "links": []},
            {"facts": [ids[1]], "links": []},
            {"facts": [ids[2], ids[3]], "links": ["continuation"]},
        ],
        "refs": {ids[0]: "name", ids[1]: "name", ids[2]: "name", ids[3]: "omit"},
        "edges": [],
    }
    return {"merge-left": left, "merge-right": right}


def negative_cases() -> list[dict]:
    """Invalid plans, each with the error codes it must trigger. The base is
    the legal fixture-r1 merge plan; synthetic cases are marked as such and
    are not counted as world records."""
    base_facts = [
        {"factId": "f0", "entityId": "person_a", "name": "林川", "kind": "appearance_changed", "text": "袖口沾了雨"},
        {"factId": "f1", "entityId": "person_a", "name": "林川", "kind": "appearance_changed", "text": "指节发白"},
        {"factId": "f2", "entityId": "person_b", "name": "周宁", "kind": "appearance_changed", "text": "斗篷下摆湿了一片"},
        {"factId": "f3", "entityId": "person_c", "name": "陈默", "kind": "appearance_changed", "text": "鞋底沾了泥"},
        {"factId": "f4", "entityId": "person_c", "name": "陈默", "kind": "appearance_changed", "text": "袖口湿到肘部"},
    ]
    base_auth = [{"from": "f2", "to": "f3"}]
    good = edge_plans(base_facts)["merge-left"]

    def clone():
        return json.loads(json.dumps(good, ensure_ascii=False))

    cases: list[dict] = []

    def add(case_id: str, plan: dict, expected: list[str], note: str,
            facts=None, auth=None) -> None:
        cases.append({
            "caseId": case_id,
            "note": note,
            "synthetic": facts is not None or auth is not None,
            "facts": facts if facts is not None else base_facts,
            "authorizedEdges": auth if auth is not None else base_auth,
            "plan": plan,
            "expectedCodes": expected,
        })

    p = clone(); p["groups"] = p["groups"][:-1]
    add("N01-missing-fact", p, ["fact-missing"], "drop f4's group")

    p = clone(); p["groups"][3]["facts"].append("f4")
    add("N02-duplicate-fact", p, ["fact-duplicate"], "f4 appears in two groups")

    p = clone(); p["groups"][3]["facts"] = ["f9"]
    add("N03-unknown-fact", p, ["fact-unknown", "fact-missing"], "replace f4 with f9")

    p = clone(); p["groups"][1], p["groups"][2] = p["groups"][2], p["groups"][1]
    add("N04-order-changed", p, ["order-changed"], "swap f2 and f3 groups")

    p = clone(); p["groups"][0]["facts"] = ["f0", "f2"]; p["groups"][1]["facts"] = ["f1"]; p["groups"][1]["links"] = []
    add("N05-non-contiguous", p, ["order-changed", "link-entity-mismatch"], "group f0+f2 skips f1")

    p = clone(); p["groups"] = [{"facts": ["f2", "f3"], "links": ["continuation"]}, {"facts": ["f0", "f1"], "links": ["continuation"]}, {"facts": ["f4"], "links": []}]
    add("N06-continuation-across-entities", p, ["link-entity-mismatch", "order-changed"], "continuation joins 周宁 with 陈默")

    p = clone(); p["groups"][0]["links"] = ["parallel"]
    add("N07-parallel-within-entity", p, ["link-entity-mismatch"], "parallel joins two 林川 facts")

    p = clone(); p["refs"]["f0"] = "omit"
    add("N08-first-mention-omit", p, ["ref-first-mention-omit", "ref-omit-without-name"], "first 林川 fact is omitted")

    p = clone(); p["refs"]["f4"] = "omit"
    add("N09-cross-group-omit", p, ["ref-cross-group-omit"], "omit 陈默 in a later group")

    p = clone(); p["edges"] = []
    add("N10-missing-edge", p, ["edge-missing-authorized"], "drop the authorized before(f2->f3)")

    p = clone(); p["edges"] = [{"from": "f0", "to": "f1", "type": "before", "mode": "optional"}]
    add("N11-unauthorized-edge", p, ["edge-unauthorized", "edge-missing-authorized"], "invent before(f0->f1)")

    p = clone(); p["edges"] = [{"from": "f3", "to": "f2", "type": "before", "mode": "required"}]
    add("N12-reversed-edge", p, ["edge-order", "edge-unauthorized", "edge-missing-authorized"], "reverse the authorized direction")

    p = clone(); p["groups"] = p["groups"][:2] + [
        {"facts": ["f3", "f4"], "links": ["continuation"]},
    ]
    add("N13-target-not-isolated", p, ["edge-target-not-isolated"], "merge the relation target f3 with f4")

    p = clone(); p["then"] = "f0 随后 f1"
    add("N14-extra-field", p, ["unknown-field", "plan-free-text"], "add a free-text temporal field")

    p = clone(); p["edges"] = [{"from": "f2", "to": "f3", "type": "cause", "mode": "required"}]
    add("N15-cause-edge", p, ["edge-type"], "turn before into cause")

    p = clone(); p["groups"][0]["time"] = "随后"
    add("N16-time-on-group", p, ["unknown-field", "plan-free-text"], "add a time field to a group")

    p = clone(); p["edges"] = [{"from": "f2", "to": "f3", "type": "before", "mode": "then"}]
    add("N17-bad-edge-mode", p, ["edge-mode"], "mode is a temporal word")

    # synthetic: two entities share a display name -> `name` cannot disambiguate
    dup_facts = [
        {"factId": "f0", "entityId": "p1", "name": "张伟", "kind": "appearance_changed", "text": "袖口沾了雨"},
        {"factId": "f1", "entityId": "p2", "name": "张伟", "kind": "appearance_changed", "text": "指节发白"},
    ]
    dup_plan = {"groups": [{"facts": ["f0"], "links": []}, {"facts": ["f1"], "links": []}],
                "refs": {"f0": "name", "f1": "name"}, "edges": []}
    add("N18-ambiguous-name", dup_plan, ["ref-ambiguous-name"], "two entities named 张伟", facts=dup_facts, auth=[])

    # synthetic: A name, B name, A omit -> nearest named antecedent is B
    amb_facts = [
        {"factId": "f0", "entityId": "p1", "name": "甲", "kind": "appearance_changed", "text": "袖口沾了雨"},
        {"factId": "f1", "entityId": "p2", "name": "乙", "kind": "appearance_changed", "text": "鞋底沾了泥"},
        {"factId": "f2", "entityId": "p1", "name": "甲", "kind": "appearance_changed", "text": "指节发白"},
    ]
    amb_plan = {"groups": [{"facts": ["f0", "f1", "f2"], "links": ["parallel", "parallel"]}],
                "refs": {"f0": "name", "f1": "name", "f2": "omit"}, "edges": []}
    add("N19-ambiguous-omit", amb_plan, ["ref-ambiguous-omit"],
        "A/B/A: omit at f2 points back to B if read nearest-first", facts=amb_facts, auth=[])

    # synthetic: time fact -> not covered by this round's schema
    time_facts = [
        {"factId": "f0", "entityId": "p1", "name": "甲", "kind": "appearance_changed", "text": "袖口沾了雨"},
        {"factId": "f1", "entityId": None, "name": None, "kind": "time", "amount": 2, "unit": "minute"},
    ]
    time_plan = {"groups": [{"facts": ["f0"], "links": []}, {"facts": ["f1"], "links": []}],
                 "refs": {"f0": "name", "f1": "name"}, "edges": []}
    add("N20-time-fact-unsupported", time_plan, ["unsupported-fact-kind"],
        "time facts have no entity; this schema refuses them", facts=time_facts, auth=[])

    return cases


def main() -> int:
    sources = []
    all_problems = []
    for sid in EDGE_SOURCES + GROUP_SOURCES:
        rec = verify_source(sid)
        if not rec["verification"]["ok"]:
            all_problems.extend(f"{sid}: {p}" for p in rec["verification"]["problems"])
        rec["family"] = "edge" if sid in EDGE_SOURCES else "grouping"
        if rec["family"] == "edge":
            rec["selectedFactIds"] = [f["factId"] for f in rec["facts"]]
            rec["droppedFacts"] = {}
        else:
            # keep f0,f1,f3,f4; drop f2 so the authorized f2->f3 relation has
            # no target and both grouping candidates are legal.
            rec["selectedFactIds"] = ["f0", "f1", "f3", "f4"]
            rec["droppedFacts"] = {"f2": "removed so the f2->f3 authorization has no applicable endpoint; "
                                          "this creates a second legal merge candidate (f3+f4)"}
        sources.append(rec)

    if all_problems:
        print("SOURCE VERIFICATION FAILED:")
        for p in all_problems:
            print(" -", p)
        return 1

    committed_pw = committed_copy(f"{COMMITTED_PAIRS}/pair-worlds.json")
    if committed_pw is None or not committed_pw["tracked"]:
        print("SOURCE VERIFICATION FAILED: committed pair-worlds.json is missing or untracked")
        return 1
    if committed_pw["sha256"] != sha256(PROV / "pair-worlds.json"):
        print("SOURCE VERIFICATION FAILED: committed pair-worlds.json hash differs from the working copy")
        return 1

    # plans
    plan_rows = []
    for i, rec in enumerate(sources):
        if rec["family"] == "edge":
            facts = rec["facts"]
            variants = edge_plans(facts)
            order = ["merge-left", "split-all"] if i % 2 == 0 else ["split-all", "merge-left"]
            auth = [{"from": r["fromFactId"], "to": r["toFactId"],
                     "elapsedSeconds": r.get("elapsedSeconds")}
                    for r in rec["authorization"].get("relations", [])]
        else:
            facts = [f for f in rec["facts"] if f["factId"] in rec["selectedFactIds"]]
            variants = group_plans(facts)
            order = ["merge-left", "merge-right"] if i % 2 == 0 else ["merge-right", "merge-left"]
            auth = []
        for label, shape in zip(["P1", "P2"], order):
            plan_rows.append({
                "sourceId": rec["sourceId"],
                "family": rec["family"],
                "planId": label,
                "shape": shape,
                "factsUsed": [f["factId"] for f in facts],
                "authorizedEdges": auth,
                "plan": variants[shape],
            })

    # contexts from the registered old material (presentation only)
    ctx_rows = {}
    for line in CONTROLLABILITY.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        ctx_rows[row["pairId"]] = row["context"]

    out = EXPERIMENT / "freeze"
    out.mkdir(parents=True, exist_ok=True)

    sources_obj = {
        "protocol": "c3-organize-plan-sources-v1",
        "created": datetime.now(timezone.utc).isoformat(),
        "sourceRoot": str(MAIN),
        "sourceHead": git_head(),
        "committedFixture": {
            "worktree": str(COMMITTED),
            "branch": git_in(COMMITTED, "rev-parse", "--abbrev-ref", "HEAD"),
            "head": git_in(COMMITTED, "rev-parse", "HEAD"),
            "pairsDir": COMMITTED_PAIRS,
            "note": ("the authorized JSONs and pair-worlds are tracked at this commit; the SQLite "
                     "databases are not tracked, so every selected fact is additionally verified by "
                     "hash against the main-worktree DBs and the frozen rows are copied into sources.json"),
        },
        "note": ("Facts are taken from artifacts/world-provenance/pairs/*-authorized.json and verified "
                 "against world_evidence / world_points.delta_json in the paired SQLite databases. "
                 "A byte-identical committed copy of the authorized JSONs exists at committedFixture; "
                 "the selected rows and all hashes are frozen here so the experiment is reproducible from freeze/."),
        "families": {
            "edge": {"sources": EDGE_SOURCES, "selection": "all 5 facts; authorized before(f2->f3) applies"},
            "grouping": {"sources": GROUP_SOURCES, "selection": "[f0,f1,f3,f4]; f2 excluded; edges empty"},
        },
        "sources": sources,
    }
    (out / "sources.json").write_text(json.dumps(sources_obj, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    (out / "plans-v1.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in plan_rows), encoding="utf-8")

    neg = {
        "protocol": "c3-organize-plan-negative-v1",
        "note": ("Each case mutates the legal fixture-r1 merge plan or uses a marked synthetic fact set. "
                 "expectedCodes must be a subset of the validator's actual codes."),
        "cases": negative_cases(),
    }
    (out / "negative-cases.json").write_text(json.dumps(neg, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    contexts = {
        "source": "artifacts/world-components/organize-wording/controllability-v1.jsonl",
        "sha256": sha256(CONTROLLABILITY),
        "note": "Presentation context only (place/visible/scene/viewpoint). Facts never come from this file.",
        "contexts": {sid: ctx_rows[sid] for sid in EDGE_SOURCES + GROUP_SOURCES},
    }
    (out / "contexts.json").write_text(json.dumps(contexts, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    hashes = {
        "protocol": "c3-organize-plan-freeze-hashes-v1",
        "created": datetime.now(timezone.utc).isoformat(),
        "environment": {
            "python": sys.version.split()[0],
            "platform": sys.platform,
        },
        "inputs": {
            "sourceRoot": str(MAIN),
            "sourceHead": git_head(),
            "committedFixtureHead": git_in(COMMITTED, "rev-parse", "HEAD"),
            "committedPairWorlds": committed_copy(f"{COMMITTED_PAIRS}/pair-worlds.json"),
            "pairWorlds": {"file": "artifacts/world-provenance/pairs/pair-worlds.json",
                           "sha256": sha256(PROV / "pair-worlds.json")},
            "fixtureDb": {"file": "artifacts/world-provenance/pairs/fixture.db",
                          "sha256": sha256(PROV / "fixture.db")},
            "trainDb": {"file": "artifacts/world-provenance/pairs/train.db",
                        "sha256": sha256(PROV / "train.db")},
            "controllabilityContexts": {"file": str(CONTROLLABILITY),
                                        "sha256": sha256(CONTROLLABILITY)},
        },
        "outputs": {
            "sources.json": sha256(out / "sources.json"),
            "plans-v1.jsonl": sha256(out / "plans-v1.jsonl"),
            "negative-cases.json": sha256(out / "negative-cases.json"),
            "contexts.json": sha256(out / "contexts.json"),
        },
    }
    (out / "source-hashes.json").write_text(json.dumps(hashes, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    print(f"wrote {out}")
    print(f"  sources: {len(sources)} ({len(EDGE_SOURCES)} edge / {len(GROUP_SOURCES)} grouping)")
    print(f"  plans:   {len(plan_rows)}")
    print(f"  negatives: {len(neg['cases'])}")
    for sid in EDGE_SOURCES + GROUP_SOURCES:
        rec = next(s for s in sources if s["sourceId"] == sid)
        v = rec["verification"]
        print(f"  {sid}: facts={v['units']} evidence={v['evidenceRows']} "
              f"delta={v['deltaChecks']} chain={v['pointChainChecks']} relations={v['relationChecks']} ok={v['ok']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
