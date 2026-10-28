# N4 corpus plan authority validation (protocol §1 planValidation).
#
# The corpus planConstruction/planValidation row fields are construction
# CLAIMS, not evidence (review finding #4). This script produces the actual
# evidence: every row's fact plan is mapped onto the backend's authoritative
# v2 contract models (EntityDelta / TimeAdvance, backend/app/schemas/world/
# contracts.py) and validated with pydantic. Results go to
# authority-report.json with the contracts.py source hash, so the validation
# target is pinned.
#
# Mapping rules:
#   moved              -> EntityDelta.positionSet = Position(containerId=locId)
#   positioned_at      -> no delta (current-state statement is not an
#                         increment; skip recorded with reason)
#   task_achieved      -> tasksAchieved += [taskId]
#   personality_changed-> personalityChanges += [DescriptionChange(id, text)]
#   sanity_changed     -> sanitySet = to (Sanity: 0-100)
#   appearance_changed -> appearanceChanges += [DescriptionChange(id, text)]
#   time               -> TimeAdvance(boundary="elapsed", duration=Duration)
#   no_change          -> no delta (recorded)
#
# Entity names are Chinese; the v2 Id pattern is ASCII-only, so the script
# assigns program draft ids (char_NNN / loc_NNN / task_NNN / chg_NNN) — the
# same "draft key replaced by program" rule as component-contracts C5. The
# idMap per row is recorded in the report.
#
# Usage: python experiments/world-components/n4_corpus/validate_plan_authority.py
# Output: experiments/world-components/n4_corpus/authority-report.json

import hashlib
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent.parent.parent          # worktree root
BACKEND = REPO / "backend"
sys.path.insert(0, str(BACKEND))

from app.schemas.world.contracts import (  # noqa: E402
    DescriptionChange, Duration, EntityDelta, Position, TimeAdvance,
)
import pydantic  # noqa: E402

CORPUS_FILES = [HERE / "corpus.seeds.jsonl", HERE / "rewrites.jsonl"]
OUT = HERE / "authority-report.json"
CONTRACTS = BACKEND / "app" / "schemas" / "world" / "contracts.py"


def build_id_maps(rows):
    """Stable draft-id assignment in first-appearance order."""
    chars, locs, tasks, chg = {}, {}, {}, 0
    for r in rows:
        for e in r["plan"]:
            kind = e["kind"]
            if kind in ("moved", "positioned_at", "task_achieved",
                        "personality_changed", "sanity_changed"):
                chars.setdefault(e["name"], f"char_{len(chars) + 1:03d}")
            if kind == "moved":
                locs.setdefault(e["from"], f"loc_{len(locs) + 1:03d}")
                locs.setdefault(e["to"], f"loc_{len(locs) + 1:03d}")
            if kind == "positioned_at":
                locs.setdefault(e["at"], f"loc_{len(locs) + 1:03d}")
            if kind == "appearance_changed":
                locs.setdefault(e["name"], f"loc_{len(locs) + 1:03d}")
            if kind == "task_achieved":
                tasks.setdefault(e["goal"], f"task_{len(tasks) + 1:03d}")
    return chars, locs, tasks


def main() -> None:
    rows = []
    for cf in CORPUS_FILES:
        if cf.exists():
            rows += [json.loads(line) for line in
                     cf.read_text(encoding="utf-8").splitlines() if line.strip()]

    chars, locs, tasks = build_id_maps(rows)
    report = {
        "purpose": "authority-path validation of corpus fact plans (evidence, not a claim)",
        "pydanticVersion": pydantic.VERSION,
        "contractsSource": {
            "path": "backend/app/schemas/world/contracts.py",
            "sha256_16": hashlib.sha256(CONTRACTS.read_bytes()).hexdigest()[:16],
        },
        "draftIdAssignment": {"characters": chars, "locations": locs, "tasks": tasks},
        "rows": [],
    }
    failures = 0
    for r in rows:
        deltas = {}
        entries = []
        time_advance = None
        id_map_used = {}
        for e in r["plan"]:
            kind = e["kind"]
            if kind == "time":
                try:
                    time_advance = TimeAdvance(
                        boundary="instant" if e["amount"] == 0 else "elapsed",
                        duration=Duration(amount=e["amount"], unit=e["unit"]))
                    entries.append({"ref": e["ref"], "kind": kind, "result": "ok",
                                    "mapped": "TimeAdvance(elapsed)"})
                except Exception as exc:  # pydantic ValidationError
                    failures += 1
                    entries.append({"ref": e["ref"], "kind": kind, "result": "error",
                                    "error": str(exc)[:200]})
                continue
            if kind == "no_change":
                entries.append({"ref": e["ref"], "kind": kind, "result": "ok",
                                "mapped": "no delta (explicit)"})
                continue
            if kind == "positioned_at":
                entries.append({"ref": e["ref"], "kind": kind, "result": "skipped",
                                "reason": "current-state statement is not an increment"})
                continue
            entity_name = e.get("name") or e.get("entityId")
            if e["entityId"].startswith("l_"):
                eid = locs[entity_name]
            else:
                eid = chars[entity_name]
            id_map_used[entity_name] = eid
            d = deltas.setdefault(eid, EntityDelta(entityId=eid))
            try:
                if kind == "moved":
                    d.positionSet = Position(containerId=locs[e["to"]])
                    entries.append({"ref": e["ref"], "kind": kind, "result": "ok",
                                    "mapped": f"positionSet(container={locs[e['to']]})"})
                elif kind == "task_achieved":
                    d.tasksAchieved = [*d.tasksAchieved, tasks[e["goal"]]]
                    entries.append({"ref": e["ref"], "kind": kind, "result": "ok",
                                    "mapped": f"tasksAchieved+={tasks[e['goal']]}"})
                elif kind == "personality_changed":
                    global_chg = f"chg_{len(entries) + 1:03d}"
                    d.personalityChanges = [*d.personalityChanges,
                                            DescriptionChange(id=global_chg, text=e["text"],
                                                              supersedes=[])]
                    entries.append({"ref": e["ref"], "kind": kind, "result": "ok",
                                    "mapped": f"personalityChanges+={global_chg}"})
                elif kind == "sanity_changed":
                    d.sanitySet = e["to"]
                    entries.append({"ref": e["ref"], "kind": kind, "result": "ok",
                                    "mapped": f"sanitySet={e['to']}"})
                elif kind == "appearance_changed":
                    global_chg = f"chg_{len(entries) + 1:03d}"
                    d.appearanceChanges = [*d.appearanceChanges,
                                           DescriptionChange(id=global_chg, text=e["text"],
                                                             supersedes=[])]
                    entries.append({"ref": e["ref"], "kind": kind, "result": "ok",
                                    "mapped": f"appearanceChanges+={global_chg}"})
            except Exception as exc:
                failures += 1
                entries.append({"ref": e["ref"], "kind": kind, "result": "error",
                                "error": str(exc)[:200]})

        # final construct: EntityDelta validators run on field assignment is
        # partial (model_validator(mode=after) runs on construction), so each
        # delta is re-constructed explicitly to trigger full validation.
        row_errors = []
        final_deltas = []
        for eid, d in deltas.items():
            try:
                final_deltas.append(EntityDelta(
                    entityId=d.entityId,
                    positionSet=d.positionSet,
                    appearanceChanges=d.appearanceChanges,
                    personalityChanges=d.personalityChanges,
                    sanitySet=d.sanitySet,
                    tasksAchieved=d.tasksAchieved,
                    subtasksAdded=d.subtasksAdded,
                ).model_dump(exclude_none=True))
            except Exception as exc:
                failures += 1
                row_errors.append(f"{eid}: {str(exc)[:200]}")
        if time_advance is not None:
            try:
                time_advance = TimeAdvance(
                    boundary=time_advance.boundary, duration=time_advance.duration)
            except Exception as exc:
                failures += 1
                row_errors.append(f"timeAdvance: {str(exc)[:200]}")

        report["rows"].append({
            "sourceGroupId": r["sourceGroupId"],
            "idMap": id_map_used,
            "timeAdvance": (time_advance.model_dump(exclude_none=True)
                            if time_advance is not None else None),
            "deltas": final_deltas,
            "entries": entries,
            "errors": row_errors,
        })

    report["summary"] = {
        "rows": len(rows),
        "validationErrors": failures,
        "verdict": "all plans valid under backend v2 contracts" if failures == 0
        else f"{failures} validation errors",
    }
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{report['summary']['verdict']}")
    print(f"report -> {OUT}")
    sys.exit(0 if failures == 0 else 1)


if __name__ == "__main__":
    main()
