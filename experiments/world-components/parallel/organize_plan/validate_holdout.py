# -*- coding: utf-8 -*-
"""Read-only validator for a holdout package produced by A.

This is what c3 runs when A delivers new world rounds. It never writes to the
package and never calls a model. Two outcomes:

    admissible     every source can be traced, is isolated from old material,
                   and supports two legal plans
    not-admissible one or more errors, listed with codes

Package layout (a directory):

    manifest.json                         must include generationProcess
    pairs/<sourceId>-authorized.json      same shape as artifacts/world-provenance/pairs
    semantic-review.json                  AI draft (never decides anything)
    semantic-review-signoff.json          HUMAN sign-off: per-source verdict + reason,
                                          identity/date/reviewedCommit, bound package digest
    world.db                              optional but expected: lets the chain be
                                          re-checked against world_evidence and
                                          world_points.delta_json

Checks
------
P  schema         units f0..fn in order; required fields; points present
C  chain          previousPointId links, strictly increasing sequence,
                  unit order follows point order
E  evidence       with a DB: world_evidence row matches unit (id/point/entity/
                  seq/text) and the point's delta_json carries the same item;
                  without a DB: unit.inlineDelta must match text
A  authorization  verdict=pass, validatorVersion pinned, endpoints exist,
                  evidence ids point at the two endpoints, elapsedSeconds > 0
I  isolation      byte-identical / bigram-similar facts against ALL old material,
                  PLUS a human sign-off bound to the package digest (a low bigram
                  score is a screen, not proof)
M  plans          two legal plans exist, differ, and pass plan_contract
N  counts         >=10 sources, >=3 with a multi-fact group, >=2 with an edge

Usage:
    python -X utf8 validate_holdout.py --package <dir>
    python -X utf8 validate_holdout.py --package <dir> --freeze   # only if admissible
    python -X utf8 validate_holdout.py --self-test                # dry-run on the 9 known sources
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import plan_contract as contract  # noqa: E402

SOURCES = HERE / "freeze" / "sources.json"
CONTROLLABILITY = HERE.parents[3] / "artifacts/world-components/organize-wording/controllability-v1.jsonl"
PAIRS_V2 = HERE.parents[3] / "artifacts/world-components/organize-wording/pairs-v2.jsonl"
FREEZE_OUT = HERE / "freeze" / "holdout-v1-freeze.json"
PROV = Path("D:/others/Jity/artifacts/world-provenance/pairs")

GENERATION_KEYS = ("method", "worldRounds", "dedupeMethod", "producedAt", "producerCommit")
SEMANTIC_VERDICTS = ("independent", "semantic-duplicate", "unsure")
SEMANTIC_SIGNOFF = "semantic-review-signoff.json"
SEMANTIC_DRAFT = "semantic-review.json"
MIN_REASON_CHARS = 8
MIN_SOURCES = 10
MIN_MULTI_GROUP_SOURCES = 3
MIN_EDGE_SOURCES = 2
NEAR_DUP_JACCARD = 0.8

ENTITY_KINDS = contract.ENTITY_KINDS


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def bigrams(text: str) -> set[str]:
    t = "".join(ch for ch in text if ch not in "，。、；：！？“”‘’（）《》…—,.!?() \n\t")
    return {t[i:i + 2] for i in range(max(0, len(t) - 1))}


def jaccard(a: str, b: str) -> float:
    ga, gb = bigrams(a), bigrams(b)
    if not ga or not gb:
        return 0.0
    return len(ga & gb) / len(ga | gb)


def old_fingerprints() -> dict:
    """Every fact surface text that has appeared in old material."""
    facts: list[dict] = []
    if SOURCES.exists():
        for s in json.loads(SOURCES.read_text(encoding="utf-8"))["sources"]:
            for f in s["facts"]:
                facts.append({"origin": f"freeze/sources.json:{s['sourceId']}",
                              "text": f.get("text", ""), "name": f.get("name", "")})
    for path in (CONTROLLABILITY, PAIRS_V2):
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            sid = row.get("pairId") or row.get("sourceId")
            for f in row.get("facts", []):
                facts.append({"origin": f"{path.name}:{sid}",
                              "text": f.get("text", ""), "name": f.get("name", "")})
    texts = sorted({f["text"] for f in facts if f["text"]})
    return {"facts": facts, "texts": texts,
            "exact": set(texts),
            "sha256": hashlib.sha256("\n".join(texts).encode("utf-8")).hexdigest()}


def package_digest(package: Path, source_ids: list[str]) -> dict:
    """Digest the artifacts a human actually reviews.

    Bound inputs: manifest.json and every pairs/<id>-authorized.json. The
    database is deliberately excluded: SQLite rewrites pages on open, so its
    bytes are not a stable identity for the reviewed content.
    """
    files = {}
    manifest = package / "manifest.json"
    if manifest.exists():
        files["manifest.json"] = sha256(manifest)
    for sid in source_ids:
        path = package / "pairs" / f"{sid}-authorized.json"
        if path.exists():
            files[f"pairs/{sid}-authorized.json"] = sha256(path)
    canonical = json.dumps(files, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return {"files": files,
            "sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest()}


def is_template_reason(reason: str, draft_note: str) -> bool:
    """A reason that is empty, too short, or copied from the AI draft."""
    if len(reason.strip()) < MIN_REASON_CHARS:
        return True
    return bool(draft_note) and reason.strip() == draft_note.strip()


def load_semantic_signoff(package: Path, draft: dict, digest: dict,
                          errors: list[dict]) -> dict:
    """Read the human sign-off. The AI draft never decides anything.

    Rules that stop a one-field edit from upgrading the draft:
      * verdicts must come from semantic-review-signoff.json, not the draft;
      * the sign-off must name a human reviewer with identity and date;
      * it must declare explicit per-source review and a reviewed commit;
      * it must bind the exact pair files it reviewed (digest match), so either
        editing a pair or reusing an old sign-off invalidates it;
      * every reason must be present and must differ from the draft template.
    """
    path = package / SEMANTIC_SIGNOFF
    if not path.exists():
        errors.append({"code": "PKG-no-semantic-signoff",
                       "detail": f"{SEMANTIC_SIGNOFF} is missing; the AI draft "
                                 f"({SEMANTIC_DRAFT}) cannot close the semantic review"})
        return {}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        errors.append({"code": "PKG-semantic-signoff-unreadable", "detail": str(exc)})
        return {}

    reviewer = doc.get("reviewer") or {}
    if reviewer.get("kind") != "human":
        errors.append({"code": "PKG-semantic-signoff-not-human",
                       "detail": f"signoff reviewer.kind={reviewer.get('kind')!r}; editing the AI "
                                 f"draft's kind field does not create a human review"})
    for field in ("identity", "date"):
        if not str(reviewer.get(field) or "").strip():
            errors.append({"code": "PKG-semantic-signoff-incomplete",
                           "detail": f"signoff reviewer.{field} is empty"})
    if doc.get("iReviewedEachSource") is not True:
        errors.append({"code": "PKG-semantic-signoff-no-attestation",
                       "detail": "signoff must set iReviewedEachSource=true"})
    if not str(doc.get("reviewedCommit") or "").strip():
        errors.append({"code": "PKG-semantic-signoff-incomplete",
                       "detail": "signoff.reviewedCommit is empty"})
    if doc.get("packageSha256") != digest["sha256"]:
        errors.append({"code": "PKG-semantic-signoff-stale",
                       "detail": f"signoff bound package {str(doc.get('packageSha256'))[:12]} but the "
                                 f"package digest is {digest['sha256'][:12]}; a pair file changed "
                                 f"after the review"})
    return doc


def signoff_source_error(source_id: str, signoff: dict, draft: dict) -> dict | None:
    """The per-source rule, kept as a function so it can be tested alone."""
    row = (signoff.get("sources") or {}).get(source_id) or {}
    draft_note = ((draft.get("sources") or {}).get(source_id) or {}).get("note", "")
    verdict = row.get("verdict")
    reason = str(row.get("reason") or "")
    if verdict not in SEMANTIC_VERDICTS:
        return {"code": "PKG-semantic-signoff-incomplete",
                "detail": f"{source_id} has no verdict in the human sign-off ({SEMANTIC_VERDICTS})"}
    if is_template_reason(reason, draft_note):
        return {"code": "PKG-semantic-signoff-template-reason",
                "detail": f"{source_id} reason is empty, too short, or copied from the AI draft; a "
                          f"real review states what was compared and why"}
    if verdict == "semantic-duplicate":
        return {"code": "I-semantic-duplicate",
                "detail": f"{source_id} judged semantically equivalent to old material: {reason}"}
    if verdict == "unsure":
        return {"code": "I-semantic-unsure",
                "detail": f"{source_id} independence undecided: {reason}"}
    return None


def check_source(source_id: str, auth: dict, db_path: Path | None,
                 old: dict) -> tuple[list[dict], dict]:
    errors: list[dict] = []

    def err(code: str, detail: str, **extra) -> None:
        item = {"code": code, "detail": detail}
        item.update(extra)
        errors.append(item)

    units = auth.get("units") or []
    points = auth.get("points") or []
    if not units:
        err("P-no-units", "no units")
    if [u.get("factId") for u in units] != [f"f{i}" for i in range(len(units))]:
        err("P-fact-ids", "units are not f0..fn in order")
    for u in units:
        for key in ("factId", "entityId", "name", "kind", "text", "pointId", "evidenceId", "sequence"):
            if u.get(key) in (None, ""):
                err("P-missing-field", f"{u.get('factId')} lacks {key}", factId=u.get("factId"))
        if u.get("kind") in contract.NON_ENTITY_KINDS:
            err("P-unsupported-kind", f"{u.get('factId')} kind {u.get('kind')!r} is not entity-bearing",
                factId=u.get("factId"))
        elif u.get("kind") not in ENTITY_KINDS:
            err("P-unknown-kind", f"{u.get('factId')} kind {u.get('kind')!r}", factId=u.get("factId"))

    point_by_id = {p.get("id"): p for p in points}
    if not points:
        err("P-no-points", "no points")
    for u in units:
        if u.get("pointId") not in point_by_id:
            err("P-unknown-point", f"{u.get('factId')} point {u.get('pointId')} missing", factId=u.get("factId"))

    # C: chain
    ordered = sorted(points, key=lambda p: p.get("sequence", 0))
    seqs = [p.get("sequence") for p in ordered]
    if seqs != sorted(seqs) or len(set(seqs)) != len(seqs):
        err("C-sequence", f"point sequences are not strictly increasing: {seqs}")
    for prev, cur in zip(ordered, ordered[1:]):
        if cur.get("previousPointId") != prev.get("id"):
            err("C-chain", f"{cur.get('id')}.previousPointId != {prev.get('id')}",
                pointId=cur.get("id"))
    unit_seq = [point_by_id[u["pointId"]].get("sequence") for u in units if u.get("pointId") in point_by_id]
    if unit_seq != sorted(unit_seq):
        err("C-unit-order", f"units are not ordered by point sequence: {unit_seq}")

    # E: evidence
    if db_path and db_path.exists():
        con = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
        con.row_factory = sqlite3.Row
        for u in units:
            row = con.execute(
                "select point_id, entity_id, sequence, kind, item_key, payload_json "
                "from world_evidence where evidence_id=?", (u.get("evidenceId"),)).fetchone()
            if row is None:
                err("E-missing", f"{u.get('factId')} evidence row absent", factId=u.get("factId"))
                continue
            payload = json.loads(row["payload_json"])
            if row["point_id"] != u.get("pointId") or row["entity_id"] != u.get("entityId"):
                err("E-identity", f"{u.get('factId')} evidence point/entity mismatch", factId=u.get("factId"))
            if payload.get("text") != u.get("text"):
                err("E-text", f"{u.get('factId')} evidence text mismatch", factId=u.get("factId"))
            point = con.execute("select delta_json, time_json from world_points where id=?",
                                (u.get("pointId"),)).fetchone()
            if point is None:
                err("E-point", f"{u.get('factId')} point row absent", factId=u.get("factId"))
            else:
                delta = json.loads(point["delta_json"] or "{}")
                ent = delta.get(u.get("entityId")) or {}
                field = {"appearance_changed": "appearanceChanges",
                         "personality_changed": "personalityChanges"}.get(u.get("kind"), "changes")
                items = ent.get(field) or []
                if not any(i.get("id") == row["item_key"] and i.get("text") == u.get("text") for i in items):
                    err("E-delta", f"{u.get('factId')} point delta has no matching item", factId=u.get("factId"))
    else:
        for u in units:
            inline = u.get("inlineDelta")
            if inline is None:
                err("E-no-db-no-inline",
                    f"{u.get('factId')} has no DB and no inlineDelta; the chain cannot be checked",
                    factId=u.get("factId"))
            elif inline.get("text") != u.get("text"):
                err("E-inline-text", f"{u.get('factId')} inlineDelta text mismatch", factId=u.get("factId"))

    # A: authorization
    auth_rec = auth.get("authorization") or {}
    if auth_rec.get("verdict") != "pass":
        err("A-verdict", f"authorization verdict {auth_rec.get('verdict')!r}")
    if auth_rec.get("validatorVersion") != "world-relation-validator/1":
        err("A-validator", f"unexpected validator {auth_rec.get('validatorVersion')!r}")
    by_fact = {u.get("factId"): u for u in units}
    for rel in auth_rec.get("relations") or []:
        src, dst = by_fact.get(rel.get("fromFactId")), by_fact.get(rel.get("toFactId"))
        if src is None or dst is None:
            err("A-endpoint", f"relation {rel.get('fromFactId')}->{rel.get('toFactId')} endpoint missing")
            continue
        if [e.get("evidenceId") for e in rel.get("evidence") or []] != [src["evidenceId"], dst["evidenceId"]]:
            err("A-evidence", f"relation {rel['fromFactId']}->{rel['toFactId']} evidence mismatch")
        if not isinstance(rel.get("elapsedSeconds"), int) or rel["elapsedSeconds"] <= 0:
            err("A-elapsed", "elapsedSeconds is not a positive integer")
    if [r.get("fromFactId") for r in auth.get("requestedRelations") or []] != \
            [r.get("fromFactId") for r in auth_rec.get("relations") or []]:
        err("A-request", "requestedRelations and authorized relations disagree")

    # I: isolation against old material
    near = []
    for u in units:
        text = u.get("text", "")
        if text in old["exact"]:
            err("I-exact-fact", f"{u.get('factId')} text {text!r} already exists in old material",
                factId=u.get("factId"))
            continue
        best = max(((jaccard(text, o), o) for o in old["texts"]), default=(0.0, ""))
        if best[0] >= NEAR_DUP_JACCARD:
            near.append({"factId": u.get("factId"), "text": text, "score": round(best[0], 3), "old": best[1]})
            err("I-near-duplicate-fact",
                f"{u.get('factId')} is {best[0]:.2f} similar to an old fact {best[1]!r}; renaming or "
                f"re-wording is not a new source", factId=u.get("factId"))

    info = {
        "sourceId": source_id,
        "worldId": auth.get("worldId"),
        "facts": len(units),
        "points": len(points),
        "factsWithText": sum(1 for u in units if u.get("text")),
        "relations": len(auth_rec.get("relations") or []),
        "nearDuplicates": near,
        "authSha256": hashlib.sha256(json.dumps(auth, ensure_ascii=False, sort_keys=True)
                                     .encode("utf-8")).hexdigest(),
    }
    return errors, info


def plans_for(facts: list[dict], edges: list[dict]) -> tuple[dict | None, dict | None, list[dict]]:
    """Two legal plans that differ in grouping, plus validation errors."""
    errors: list[dict] = []
    ids = [f["factId"] for f in facts]
    by_id = {f["factId"]: f for f in facts}
    targets = {e["to"] for e in edges}

    pairs = [(ids[i], ids[i + 1]) for i in range(len(ids) - 1)
             if by_id[ids[i]]["entityId"] == by_id[ids[i + 1]]["entityId"]]
    pairs = [(a, b) for a, b in pairs if a not in targets and b not in targets]
    if not pairs:
        errors.append({"code": "M-no-merge-pair",
                       "detail": "no adjacent same-entity pair is mergeable; two different legal groupings "
                                 "cannot be built from this source"})
        return None, None, errors

    def build(merge: tuple[str, str] | None, separate: bool) -> dict:
        groups, refs, i = [], {}, 0
        while i < len(ids):
            fid = ids[i]
            if separate:
                groups.append({"facts": [fid], "links": []})
                refs[fid] = "name"
                i += 1
                continue
            if merge and i + 1 < len(ids) and (fid, ids[i + 1]) == merge:
                b = ids[i + 1]
                groups.append({"facts": [fid, b], "links": ["continuation"]})
                refs[fid], refs[b] = "name", "omit"
                i += 2
                continue
            groups.append({"facts": [fid], "links": []})
            refs[fid] = "name"
            i += 1
        return {"groups": groups, "refs": refs,
                "edges": [{"from": e["from"], "to": e["to"], "type": "before", "mode": "required"}
                          for e in edges]}

    p1 = build(pairs[0], separate=False)
    p2 = build(None, separate=True)
    for label, plan in (("P1", p1), ("P2", p2)):
        result = contract.validate_plan(facts, edges, plan)
        if not result["ok"]:
            errors.append({"code": "M-illegal-plan", "detail": f"{label} fails the plan contract",
                           "errors": result["errors"][:4]})
    if json.dumps(p1, sort_keys=True) == json.dumps(p2, sort_keys=True):
        errors.append({"code": "M-identical-plans", "detail": "the two plans are identical"})
    return p1, p2, errors


def run(package: Path, freeze: bool) -> int:
    manifest_path = package / "manifest.json"
    if not manifest_path.exists():
        print(json.dumps({"status": "not-admissible", "errors": [
            {"code": "PKG-no-manifest", "detail": f"{manifest_path} is missing"}]},
            ensure_ascii=False, indent=1))
        return 1
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    pair_dir = package / "pairs"
    # manifest.databases maps a sourceId prefix to a DB (relative to the package,
    # or absolute); the longest matching prefix wins, else "world.db".
    db_map = manifest.get("databases") or {}
    default_db = package / "world.db"

    def db_for(source_id: str) -> Path:
        best = None
        for prefix, rel in db_map.items():
            if source_id.startswith(prefix) and (best is None or len(prefix) > len(best[0])):
                best = (prefix, rel)
        if best is None:
            return default_db
        p = Path(best[1])
        return p if p.is_absolute() else package / p

    old = old_fingerprints()

    all_errors: list[dict] = []

    # PKG: the generation process must be documented. Without it, "new source"
    # is unverifiable even when the texts look different.
    gen = manifest.get("generationProcess") or {}
    for key in GENERATION_KEYS:
        if not gen.get(key):
            all_errors.append({"code": "PKG-no-generation-process",
                               "detail": f"manifest.generationProcess.{key} is missing"})
    if gen.get("worldRounds") is not None and not isinstance(gen.get("worldRounds"), list):
        all_errors.append({"code": "PKG-generation-process-shape",
                           "detail": "manifest.generationProcess.worldRounds must be a list"})

    # PKG: a separate semantic review. bigram Jaccard is a screen, not proof of
    # independence, so a HUMAN sign-off file is required before freezing. The AI
    # draft is read only to detect copy-pasted reasons; it never decides anything.
    draft = {}
    draft_path = package / SEMANTIC_DRAFT
    if draft_path.exists():
        try:
            draft = json.loads(draft_path.read_text(encoding="utf-8"))
        except Exception as exc:
            all_errors.append({"code": "PKG-semantic-draft-unreadable", "detail": str(exc)})
    digest = package_digest(package, manifest.get("sources", []))
    semantic = load_semantic_signoff(package, draft, digest, all_errors)
    infos, plans = [], {}
    for source_id in manifest.get("sources", []):
        auth_path = pair_dir / f"{source_id}-authorized.json"
        if not auth_path.exists():
            all_errors.append({"code": "PKG-missing-source", "detail": f"{auth_path} is missing"})
            continue
        auth = json.loads(auth_path.read_text(encoding="utf-8"))
        this_db = db_for(source_id)
        errors, info = check_source(source_id, auth, this_db if this_db.exists() else None, old)
        # A low bigram score is only a screen. The per-source verdict is what
        # decides independence, and it must be present.
        row = (semantic.get("sources") or {}).get(source_id) or {}
        info["semanticVerdict"] = row.get("verdict")
        info["semanticReason"] = row.get("reason", "")
        source_error = signoff_source_error(source_id, semantic, draft)
        if source_error:
            errors.append(source_error)
        all_errors.extend({"sourceId": source_id, **e} for e in errors)
        infos.append(info)

        facts = [{"factId": u["factId"], "entityId": u["entityId"], "name": u["name"],
                  "kind": u["kind"], "text": u["text"],
                  "goal": u.get("goal"), "from": u.get("from"), "to": u.get("to")}
                 for u in auth.get("units", [])]
        edges = [{"from": r["fromFactId"], "to": r["toFactId"]}
                 for r in (auth.get("authorization") or {}).get("relations", [])]
        p1, p2, plan_errors = plans_for(facts, edges)
        all_errors.extend({"sourceId": source_id, **e} for e in plan_errors)
        if p1 and p2:
            plans[source_id] = {"P1": p1, "P2": p2,
                                "facts": facts, "edges": edges}

    # N: counts
    multi = sum(1 for s, p in plans.items() if any(len(g["facts"]) > 1 for g in p["P1"]["groups"]))
    with_edge = sum(1 for s, p in plans.items() if p["edges"])
    if len(infos) < MIN_SOURCES:
        all_errors.append({"code": "N-too-few-sources",
                           "detail": f"{len(infos)} sources, need >= {MIN_SOURCES}"})
    if multi < MIN_MULTI_GROUP_SOURCES:
        all_errors.append({"code": "N-too-few-multi-group",
                           "detail": f"{multi} sources have a multi-fact group, need >= {MIN_MULTI_GROUP_SOURCES}"})
    if with_edge < MIN_EDGE_SOURCES:
        all_errors.append({"code": "N-too-few-edges",
                           "detail": f"{with_edge} sources carry an authorised edge, need >= {MIN_EDGE_SOURCES}"})

    by_family: dict[str, int] = {}
    for e in all_errors:
        fam = e["code"].split("-")[0]
        by_family[fam] = by_family.get(fam, 0) + 1

    status = "admissible" if not all_errors else "not-admissible"
    doc = {
        "package": str(package),
        "manifest": manifest,
        "manifestSha256": sha256(manifest_path),
        "oldMaterialFingerprintSha256": old["sha256"],
        "counts": {"sources": len(infos), "multiGroupSources": multi, "edgeSources": with_edge},
        "thresholds": {"minSources": MIN_SOURCES, "minMultiGroup": MIN_MULTI_GROUP_SOURCES,
                       "minEdges": MIN_EDGE_SOURCES, "nearDupJaccard": NEAR_DUP_JACCARD},
        "status": status,
        "errorsByFamily": by_family,
        "familyMeaning": {
            "PKG": "package layout / generation process / semantic review", "P": "schema",
            "C": "point chain", "E": "evidence / delta",
            "A": "authorization", "I": "isolation from old material", "M": "two legal plans",
            "N": "counts",
        },
        "errors": all_errors,
        "sources": infos,
    }
    print(json.dumps({"status": status, "counts": doc["counts"],
                      "errorsByFamily": by_family,
                      "sampleErrors": all_errors[:6]}, ensure_ascii=False, indent=1))

    if status != "admissible":
        return 1
    if freeze:
        frozen = dict(doc)
        signoff_path = package / SEMANTIC_SIGNOFF
        frozen["semanticSignoff"] = {"file": SEMANTIC_SIGNOFF,
                                     "sha256": sha256(signoff_path)}
        frozen["packageDigest"] = digest
        frozen["pairFiles"] = digest["files"]
        frozen["gateRule"] = {
            "sources": len(plans),
            "minimumPairedSuccess": max(8, math.ceil(0.8 * len(plans))),
            "formula": "max(8, ceil(0.8 * N)) with N = number of frozen sources",
            "mustUseAllSources": True,
            "noSubsetSelection": True,
            "preregisteredAtFreeze": True,
        }
        frozen["plans"] = plans
        frozen["frozenAt"] = manifest.get("createdAt")
        FREEZE_OUT.write_text(json.dumps(frozen, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"froze {FREEZE_OUT} ({len(plans)} sources, {sum(len(v['facts']) for v in plans.values())} facts)")
    return 0


def self_test() -> int:
    """Dry-run on the 9 known sources: schema/chain/evidence/plans should pass,
    isolation must fail."""
    src = json.loads(SOURCES.read_text(encoding="utf-8"))["sources"]
    tmp = HERE / "runs" / "holdout-selftest"
    pair_dir = tmp / "pairs"
    pair_dir.mkdir(parents=True, exist_ok=True)
    sources = []
    for s in src:
        auth = {
            "worldId": s["worldId"],
            "units": s["facts"],
            "points": s["points"],
            "requestedRelations": s["requestedRelations"],
            "authorization": s["authorization"],
        }
        (pair_dir / f"{s['sourceId']}-authorized.json").write_text(
            json.dumps(auth, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        sources.append(s["sourceId"])
    # The semantic reviewer is marked "ai" on purpose: c3 cannot claim a human
    # review, so PKG-semantic-review-not-human stays in the output as a reminder
    # while the isolation errors (the real point) remain visible.
    (tmp / "semantic-review.json").write_text(json.dumps({
        "protocol": "c3-holdout-semantic-review-v1",
        "reviewer": {"identity": "c3 self-test fixture", "kind": "ai"},
        "note": "self-test only: these 9 sources are old material by construction",
        "sources": {sid: {"verdict": "independent",
                          "note": "self-test placeholder; the bigram check is expected to reject it"}
                    for sid in sources},
    }, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    (tmp / "manifest.json").write_text(json.dumps({
        "packageId": "c3-holdout-selftest",
        "producedBy": "c3 self-test (the 9 already-used sources)",
        "createdAt": "n/a",
        "sources": sources,
        "databases": {"fixture-": str(PROV / "fixture.db"), "train-": str(PROV / "train.db")},
        "generationProcess": {
            "method": "self-test: copied from the 9 already-used sources",
            "worldRounds": [f"{sid}_p1..p3" for sid in sources],
            "dedupeMethod": "none (self-test)",
            "producedAt": "n/a",
            "producerCommit": "n/a",
        },
        "note": ("these sources are old material on purpose: schema/chain/evidence/plans should pass, "
                 "isolation must reject every fact"),
    }, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    # The sign-off is filled in completely but marked "ai" on purpose: c3 cannot
    # claim a human review, so PKG-semantic-signoff-not-human stays visible while
    # the isolation errors (the real point) remain the bulk of the output.
    (tmp / "semantic-review.json").write_text(json.dumps({
        "protocol": "c3-holdout-semantic-review-v1",
        "reviewer": {"identity": "c3 self-test fixture", "kind": "ai"},
        "note": "self-test draft only",
        "sources": {sid: {"verdict": "independent", "note": "self-test draft placeholder"}
                    for sid in sources},
    }, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    digest = package_digest(tmp, sources)
    (tmp / "semantic-review-signoff.json").write_text(json.dumps({
        "protocol": "c3-holdout-semantic-signoff-v1",
        "packageId": "c3-holdout-selftest",
        "packageSha256": digest["sha256"],
        "reviewedCommit": "self-test",
        "iReviewedEachSource": True,
        "reviewer": {"identity": "c3 self-test fixture", "kind": "ai", "date": "n/a"},
        "sources": {sid: {"verdict": "independent",
                          "reason": f"self-test fixture for {sid}: isolation is expected to reject it"}
                    for sid in sources},
    }, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"built self-test package at {tmp}")
    return run(tmp, freeze=False)


def unit_test() -> int:
    """Two synthetic units, clearly not world records:
       U1  new fact texts + valid chain + valid edge  -> no errors
       U2  one fact is an old fact with one extra character -> I-near-duplicate-fact
    The point is to show the isolation check is not a blanket "reject everything".
    """
    old = old_fingerprints()
    point = "synth_p1"
    units = [
        {"factId": "f0", "entityId": "synth_a", "name": "测甲", "kind": "appearance_changed",
         "text": "靴筒裹了一层盐霜", "pointId": point,
         "evidenceId": f"{point}/synth_a/appearance/s1", "sequence": 1,
         "inlineDelta": {"text": "靴筒裹了一层盐霜"}},
        {"factId": "f1", "entityId": "synth_b", "name": "测乙", "kind": "appearance_changed",
         "text": "袖袋里漏出半把谷粒", "pointId": point,
         "evidenceId": f"{point}/synth_b/appearance/s2", "sequence": 1,
         "inlineDelta": {"text": "袖袋里漏出半把谷粒"}},
    ]
    points = [{"id": point, "sequence": 1, "previousPointId": "synth_root",
               "time": {"boundary": "elapsed", "duration": {"amount": 2, "unit": "second"}}}]
    rel = {"fromFactId": "f0", "toFactId": "f1", "type": "before",
           "evidence": [{"type": "event", "evidenceId": units[0]["evidenceId"]},
                        {"type": "event", "evidenceId": units[1]["evidenceId"]}],
           "authorization": {"verdict": "pass", "validatorVersion": "world-relation-validator/1"},
           "elapsedSeconds": 1}
    auth = {"worldId": "synth_world", "units": units, "points": points,
            "requestedRelations": [{"fromFactId": "f0", "toFactId": "f1"}],
            "authorization": {"verdict": "pass", "validatorVersion": "world-relation-validator/1",
                              "relations": [rel], "rejected": [], "problems": []}}
    e1, i1 = check_source("synth-new", json.loads(json.dumps(auth)), None, old)

    dup = json.loads(json.dumps(auth))
    dup["units"][0]["text"] = "袖口沾了雨水"
    dup["units"][0]["inlineDelta"]["text"] = "袖口沾了雨水"
    e2, _ = check_source("synth-dup", dup, None, old)

    codes1 = sorted({e["code"] for e in e1})
    codes2 = sorted({e["code"] for e in e2})
    ok = (not codes1) and ("I-near-duplicate-fact" in codes2 or "I-exact-fact" in codes2)
    print(json.dumps({
        "status": "pass" if ok else "FAIL",
        "U1_newTextWithoutErrors": codes1,
        "U2_oldTextWithOneExtraChar": codes2,
        "note": "synthetic units; they are not world records and are not added to any material",
    }, ensure_ascii=False, indent=1))
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--package")
    ap.add_argument("--freeze", action="store_true")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--unit-test", action="store_true")
    args = ap.parse_args()
    if args.unit_test:
        return unit_test()
    if args.self_test:
        return self_test()
    if not args.package:
        ap.error("--package or --self-test is required")
    return run(Path(args.package), args.freeze)


if __name__ == "__main__":
    raise SystemExit(main())
