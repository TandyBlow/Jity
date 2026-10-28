# N4 corpus plan authority validation v2: apply-based provenance checks.
#
# v2 (2026-10-29 review): v1 only proved delta FORMAT legality (pydantic);
# it never checked where the values come from - a sanity `from` of -999 or
# a move starting anywhere passed. This version uses the A-side Python
# kernel as the authority:
#   1. the row's `world` registry is built into a before WorldState
#      (pydantic-validated, incl. fixed_registry consistency);
#   2. provenance checks against BEFORE: moved start position == registry
#      home, sanity old value == registry sanity, task exists + owned by the
#      entry entity + still pending, positioned claims match the before
#      position, no_change rows carry an empty delta;
#   3. the A-side kernel `apply_point` applies the raw delta to the before
#      state (KernelViolation = illegal); after-values are then checked
#      (moved target, sanity target, task achieved).
# The report pins the server tree HEAD and apply.py hash, and binds each row
# by the sha256 of plan+world+rawDelta.
#
# Usage: python experiments/world-components/n4_corpus/validate_plan_authority.py
#         [--server-tree D:/others/Jity/.local/world-server-worktree]
# Output: experiments/world-components/n4_corpus/authority-report.json

import hashlib
import json
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent

args = sys.argv[1:]
SERVER_TREE = pathlib.Path(args[args.index("--server-tree") + 1]) if "--server-tree" in args \
    else pathlib.Path("D:/others/Jity/.local/world-server-worktree")
BACKEND = SERVER_TREE / "backend"
sys.path.insert(0, str(BACKEND))

from app.schemas.world.contracts import (  # noqa: E402
    CharacterState, DescriptionChange, EntityDelta, InitialCharacter,
    InitialLocation, InitialItem, ItemState, LocationState, Position, Task,
    TimelinePoint, WorldInitialState, WorldState, WorldTime,
)
from app.services.world.apply import apply_point  # noqa: E402
import pydantic  # noqa: E402

CORPUS_FILES = [HERE / "corpus.seeds.jsonl", HERE / "rewrites.jsonl"]
OUT = HERE / "authority-report.json"
WORLD_ID = "world_n4_dev"
POINT_ID = "p_n4_0001"
ROOT_ID = "root_n4"

LOC_NAME = {}
CHAR_DEFS = {}


def register_registry(world: dict):
    """Collect name->id maps and per-char before values from the row's world."""
    locs = {l["name"]: l["id"] for l in world["locations"]}
    chars = {}
    for c in world["characters"]:
        chars[c["name"]] = {"id": c["id"], "home": c["homeLocId"],
                            "sanity": c["initialSanity"],
                            "personality": c["initialPersonality"],
                            "tasks": {t["goal"]: t for t in c["tasks"]}}
    return locs, chars


def build_before(world: dict) -> WorldState:
    """world registry -> before WorldState (full registry in both layers)."""
    locs = {l["id"]: l["name"] for l in world["locations"]}
    init_locations = {lid: InitialLocation(id=lid, name=name, parentLocationId=None,
                                           initialAppearance="如常。")
                      for lid, name in locs.items()}
    init_items = {}
    init_characters = {}
    for c in world["characters"]:
        init_characters[c["id"]] = InitialCharacter(
            id=c["id"], name=c["name"],
            initialPosition=Position(containerId=c["homeLocId"]),
            initialAppearance="如常。", initialPersonality=c["initialPersonality"],
            initialSanity=c["initialSanity"],
            tasks={t["id"]: Task(id=t["id"], ownerId=t["ownerId"], parentTaskId=None,
                                 goal=t["goal"], status="pending")
                   for t in c["tasks"]})
    initial = WorldInitialState(
        engineVersion="world-engine-v1", schemaVersion=1, worldId=WORLD_ID,
        protagonistId=world["protagonistId"], initialTime=WorldTime(
            calendar="gregorian", dateTime="2026-10-01T08:00:00", instantOrdinal=0),
        locations=init_locations, items=init_items, characters=init_characters)
    return WorldState(
        engineVersion="world-engine-v1", schemaVersion=1, worldId=WORLD_ID,
        protagonistId=world["protagonistId"], time=initial.initialTime,
        initial=initial,
        locations={lid: LocationState(id=lid) for lid in locs},
        items={},
        characters={c["id"]: CharacterState(
            id=c["id"], position=Position(containerId=c["homeLocId"]),
            sanity=c["initialSanity"],
            tasks={t["id"]: Task(id=t["id"], ownerId=t["ownerId"], parentTaskId=None,
                                 goal=t["goal"], status="pending")
                   for t in c["tasks"]})
            for c in world["characters"]})


def reconcile(r: dict, locs: dict, chars: dict):
    """v3: full plan <-> rawDelta reconciliation (review round 4, gap 3).
    The generator's same-source promise is NOT trusted: every plan entry
    must correspond to a delta field with an EQUAL value, and every delta
    field must be covered by a plan entry - both directions, all kinds
    (time, appearance, personality, positioned current-state included)."""
    problems, checks = [], []
    deltas = r["rawDelta"]["entityDeltas"]
    time_entry = r["rawDelta"]["time"]
    plan = r["plan"]

    for entry in plan:
        k, ref = entry["kind"], entry["ref"]
        if k == "moved":
            d = next((d for d in deltas if d["entityId"] == entry["entityId"]
                      and "positionSet" in d), None)
            if d is None:
                problems.append(f"plan ref {ref} moved: no positionSet in rawDelta")
            elif d["positionSet"]["containerId"] != locs[entry["to"]]:
                problems.append(f"plan ref {ref} moved to {entry['to']} "
                                f"({locs[entry['to']]}) but rawDelta positionSet is "
                                f"{d['positionSet']['containerId']}")
            else:
                checks.append({"check": "reconcile-moved", "ref": ref, "result": "ok"})
        elif k == "task_achieved":
            tid = chars[entry["name"]]["tasks"].get(entry["goal"], {}).get("id")
            d = next((d for d in deltas if d["entityId"] == entry["entityId"]
                      and "tasksAchieved" in d), None)
            if d is None or tid is None or tid not in d["tasksAchieved"]:
                problems.append(f"plan ref {ref} task '{entry['goal']}' has no matching "
                                f"tasksAchieved in rawDelta")
            else:
                checks.append({"check": "reconcile-task", "ref": ref, "result": "ok"})
        elif k == "sanity_changed":
            d = next((d for d in deltas if d["entityId"] == entry["entityId"]
                      and "sanitySet" in d), None)
            if d is None or d["sanitySet"] != entry["to"]:
                problems.append(f"plan ref {ref} sanity to={entry['to']} but rawDelta "
                                f"sanitySet={d['sanitySet'] if d else None}")
            else:
                checks.append({"check": "reconcile-sanity", "ref": ref, "result": "ok"})
        elif k == "personality_changed":
            texts = [c["text"] for d in deltas if d["entityId"] == entry["entityId"]
                     for c in d.get("personalityChanges", [])]
            if entry["text"] not in texts:
                problems.append(f"plan ref {ref} personality text '{entry['text']}' not "
                                f"in rawDelta personalityChanges {texts}")
            else:
                checks.append({"check": "reconcile-personality", "ref": ref, "result": "ok"})
        elif k == "appearance_changed":
            texts = [c["text"] for d in deltas if d["entityId"] == entry["entityId"]
                     for c in d.get("appearanceChanges", [])]
            if entry["text"] not in texts:
                problems.append(f"plan ref {ref} appearance text '{entry['text']}' not in "
                                f"rawDelta appearanceChanges {texts}")
            else:
                checks.append({"check": "reconcile-appearance", "ref": ref, "result": "ok"})
        elif k == "time":
            if (time_entry["amount"] != entry["amount"]
                    or time_entry["unit"] != entry["unit"]):
                problems.append(f"plan ref {ref} time {entry['amount']}{entry['unit']} but "
                                f"rawDelta time {time_entry['amount']}{time_entry['unit']}")
            else:
                checks.append({"check": "reconcile-time", "ref": ref, "result": "ok"})
        elif k == "positioned_at":
            if any(d["entityId"] == entry["entityId"] and "positionSet" in d
                   for d in deltas):
                problems.append(f"plan ref {ref} claims {entry['name']} is ALREADY at "
                                f"{entry['at']} but rawDelta moves them — current state "
                                f"must not be a delta")
            else:
                checks.append({"check": "reconcile-positioned", "ref": ref, "result": "ok"})
        elif k == "no_change":
            if deltas:
                problems.append("plan claims no_change but rawDelta carries deltas")
            else:
                checks.append({"check": "reconcile-no-change", "ref": ref, "result": "ok"})

    # reverse direction: every delta field must be covered by a plan entry
    for d in deltas:
        eid = d["entityId"]
        if "positionSet" in d and not any(
                e["kind"] == "moved" and e["entityId"] == eid for e in plan):
            problems.append(f"rawDelta moves {eid} but no plan entry expresses it")
        if "tasksAchieved" in d and not any(
                e["kind"] == "task_achieved" and e["entityId"] == eid for e in plan):
            problems.append(f"rawDelta completes tasks for {eid} but no plan entry expresses it")
        if "sanitySet" in d and not any(
                e["kind"] == "sanity_changed" and e["entityId"] == eid for e in plan):
            problems.append(f"rawDelta sets sanity for {eid} but no plan entry expresses it")
        if "personalityChanges" in d and not any(
                e["kind"] == "personality_changed" and e["entityId"] == eid for e in plan):
            problems.append(f"rawDelta changes personality for {eid} but no plan entry "
                            f"expresses it")
        if "appearanceChanges" in d and not any(
                e["kind"] == "appearance_changed" and e["entityId"] == eid for e in plan):
            problems.append(f"rawDelta changes appearance for {eid} but no plan entry "
                            f"expresses it")
    if time_entry is not None and not any(e["kind"] == "time" for e in plan):
        problems.append("rawDelta carries a time advance but no plan entry expresses it")
    return problems, checks


def main() -> None:
    rows = []
    for cf in CORPUS_FILES:
        if cf.exists():
            rows += [json.loads(line) for line in
                     cf.read_text(encoding="utf-8").splitlines() if line.strip()]

    head = subprocess.run(["git", "-C", str(SERVER_TREE), "rev-parse", "HEAD"],
                          capture_output=True, text=True).stdout.strip()
    apply_py = SERVER_TREE / "backend" / "app" / "services" / "world" / "apply.py"

    # ---- tamper self-test: plan<->delta divergence MUST be caught ----
    def tampered_problems(src, mutate):
        import copy
        t = copy.deepcopy(src)
        mutate(t)
        locs_t, chars_t = register_registry(t["world"])
        return reconcile(t, locs_t, chars_t)[0]

    loc1 = next(r for r in rows if r["sourceGroupId"] == "n4-loc-001")
    appear = next(r for r in rows if r["sourceGroupId"].startswith("n4-appear"))
    void = []
    p1 = tampered_problems(loc1, lambda t: t["rawDelta"]["time"].__setitem__("amount", 8))
    if not any("time" in p for p in p1):
        void.append(f"time tamper not caught: {p1}")
    p2 = tampered_problems(appear, lambda t: t["rawDelta"]["entityDeltas"][0]
                           ["appearanceChanges"][0].__setitem__("text", "门柱刷上了金漆"))
    if not any("appearance" in p for p in p2):
        void.append(f"appearance tamper not caught: {p2}")
    if void:
        print("REPORT VOID — reconciliation self-test failed:")
        for x in void:
            print(" ", x)
        sys.exit(2)
    print("self-test PASS: 2/2 plan<->delta tamper rows caught")

    report = {
        "purpose": "apply-based provenance validation of corpus fact plans (evidence, not a claim)",
        "pydanticVersion": pydantic.VERSION,
        "serverTree": {"path": str(SERVER_TREE), "head": head,
                       "applyPySha256_16": hashlib.sha256(apply_py.read_bytes()).hexdigest()[:16]},
        "rows": [],
    }
    failures = 0
    for r in rows:
        problems = []
        checks = []
        locs, chars = register_registry(r["world"])

        # 1. before state (pydantic, incl. fixed_registry)
        try:
            before = build_before(r["world"])
            checks.append({"check": "before-state-pydantic", "result": "ok"})
        except Exception as exc:
            problems.append(f"before state invalid: {str(exc)[:180]}")
            checks.append({"check": "before-state-pydantic", "result": "error",
                           "error": str(exc)[:180]})
            report["rows"].append({"sourceGroupId": r["sourceGroupId"], "checks": checks,
                                   "errors": problems})
            failures += 1
            continue

        deltas_json = r["rawDelta"]["entityDeltas"]
        time_entry = r["rawDelta"]["time"]

        # 2. provenance checks against BEFORE (source legality, not format)
        merged = {}
        for d in deltas_json:
            eid = d["entityId"]
            m = merged.setdefault(eid, {})
            for k, v in d.items():
                if k == "entityId":
                    continue
                if k in ("tasksAchieved", "personalityChanges", "appearanceChanges",
                         "subtasksAdded"):
                    m.setdefault(k, []).extend(v)
                else:
                    m[k] = v
        for entry in r["plan"]:
            kind = entry["kind"]
            if kind == "moved":
                cid, frm = entry["entityId"], entry["from"]
                home = chars[entry["name"]]["home"]
                if home != locs[frm]:
                    problems.append(
                        f"moved start provenance: plan from={frm}({locs[frm]}) but world "
                        f"registry home for {entry['name']} is {home} — start value not "
                        f"backed by the before state")
                else:
                    checks.append({"check": "moved-start", "ref": entry["ref"], "result": "ok"})
            elif kind == "sanity_changed":
                reg = chars[entry["name"]]
                if entry["from"] != reg["sanity"]:
                    problems.append(
                        f"sanity old-value provenance: plan from={entry['from']} but "
                        f"registry sanity={reg['sanity']} — old value not backed by "
                        f"the before state")
                else:
                    checks.append({"check": "sanity-old-value", "ref": entry["ref"],
                                   "result": "ok"})
            elif kind == "task_achieved":
                reg = chars[entry["name"]]
                tid = reg["tasks"].get(entry["goal"], {}).get("id")
                t = reg["tasks"].get(entry["goal"])
                if t is None:
                    problems.append(
                        f"task provenance: goal '{entry['goal']}' not registered for "
                        f"{entry['name']} in the before state")
                elif t["ownerId"] != entry["entityId"]:
                    problems.append(
                        f"task ownership: '{entry['goal']}' owned by {t['ownerId']}, "
                        f"entry says {entry['entityId']}")
                else:
                    checks.append({"check": "task-owned-pending", "ref": entry["ref"],
                                   "result": "ok"})
            elif kind == "no_change":
                if deltas_json:
                    problems.append("no_change row carries a non-empty delta")
                else:
                    checks.append({"check": "empty-delta", "result": "ok"})

        for claim in r.get("planOnlyClaims", []):
            if claim["kind"] == "positioned_at":
                home = chars[claim["name"]]["home"]
                if home != locs[claim["at"]]:
                    problems.append(
                        f"positioned claim provenance: {claim['name']} claimed at "
                        f"{claim['at']}({locs[claim['at']]}) but registry home is {home} "
                        f"— current-state claim not backed by the before state")
                else:
                    checks.append({"check": "positioned-before", "result": "ok"})

        # 2b. full plan <-> rawDelta reconciliation (both directions)
        rec_problems, rec_checks = reconcile(r, locs, chars)
        problems.extend(rec_problems)
        checks.extend(rec_checks)

        # 3. apply via the A-side kernel, then check AFTER values
        if not problems:
            entity_deltas = {}
            for eid, m in merged.items():
                try:
                    entity_deltas[eid] = EntityDelta(
                        entityId=eid,
                        positionSet=Position(**m["positionSet"]) if "positionSet" in m else None,
                        appearanceChanges=[DescriptionChange(**c) for c in m.get("appearanceChanges", [])],
                        personalityChanges=[DescriptionChange(**c) for c in m.get("personalityChanges", [])],
                        sanitySet=m.get("sanitySet"),
                        tasksAchieved=m.get("tasksAchieved", []),
                        subtasksAdded=[],
                    )
                except Exception as exc:
                    problems.append(f"delta format ({eid}): {str(exc)[:180]}")
            if not problems:
                try:
                    point = TimelinePoint(
                        worldId=WORLD_ID, id=POINT_ID, sequence=1, kind="normal",
                        previousPointId=ROOT_ID, roundId="round_n4_001",
                        advanceId="advance_n4_001", trigger="player",
                        linkedFromPointId=None,
                        timeAdvance={"boundary": "instant" if time_entry["amount"] == 0
                                     else "elapsed",
                                     "duration": {"amount": time_entry["amount"],
                                                  "unit": time_entry["unit"]}},
                        entityDeltas=entity_deltas)
                    after = apply_point(before, point)
                    checks.append({"check": "kernel-apply", "result": "ok"})
                    for entry in r["plan"]:
                        if entry["kind"] == "moved":
                            got = after.characters[entry["entityId"]].position.containerId
                            if got != locs[entry["to"]]:
                                problems.append(f"after position mismatch: {got} != "
                                                f"{locs[entry['to']]}")
                        elif entry["kind"] == "sanity_changed":
                            got = after.characters[entry["entityId"]].sanity
                            if got != entry["to"]:
                                problems.append(f"after sanity mismatch: {got} != {entry['to']}")
                        elif entry["kind"] == "task_achieved":
                            tid = chars[entry["name"]]["tasks"][entry["goal"]]["id"]
                            got = after.characters[entry["entityId"]].tasks[tid].status
                            if got != "achieved":
                                problems.append(f"after task status: {got} != achieved")
                except Exception as exc:
                    problems.append(f"kernel apply rejected the delta: {str(exc)[:180]}")

        row_hash = hashlib.sha256("".join(
            json.dumps(r[k], ensure_ascii=False, sort_keys=True)
            for k in ("plan", "world", "rawDelta")).encode("utf-8")).hexdigest()
        failures += len(problems)
        report["rows"].append({
            "sourceGroupId": r["sourceGroupId"], "rowHash": row_hash,
            "checks": checks, "errors": problems,
        })

    report["summary"] = {
        "rows": len(rows),
        "validationErrors": failures,
        "verdict": "all plans provenance-valid under the A-side kernel"
        if failures == 0 else f"{failures} provenance errors",
    }
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{report['summary']['verdict']}")
    print(f"server tree: {head[:12]} apply.py={report['serverTree']['applyPySha256_16']}")
    print(f"report -> {OUT}")
    sys.exit(0 if failures == 0 else 1)


if __name__ == "__main__":
    main()
