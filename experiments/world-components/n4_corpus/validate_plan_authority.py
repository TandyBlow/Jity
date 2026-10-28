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


def identity_problem(entry: dict, locs: dict, chars: dict):
    """v5 invariant: entityId <-> name binding. The name is the human-facing
    side, the registry maps it to exactly one id; a plan entry may never
    carry a name pointing at a different id."""
    name = entry.get("name")
    if name is None:
        return None
    kind = entry["kind"]
    if kind == "appearance_changed":
        expected = locs.get(name)
    else:
        reg = chars.get(name)
        expected = reg["id"] if reg else None
    if expected is None:
        return f"plan ref {entry['ref']}: name '{name}' not in the world registry"
    if expected != entry["entityId"]:
        return (f"plan ref {entry['ref']}: identity mismatch — name '{name}' is "
                f"{expected} in the registry but the entry says {entry['entityId']}")
    return None


def reconcile(r: dict, locs: dict, chars: dict):
    """v3: full plan <-> rawDelta reconciliation (review round 4, gap 3).
    v5 (review round 5): entityId<->name binding; positioned plan entries
    reconcile against planOnlyClaims in BOTH directions; reverse coverage is
    PER-CHANGE (each delta list item must be consumed by a plan entry), not
    per-field. The generator's same-source promise is NOT trusted."""
    problems, checks = [], []
    deltas = r["rawDelta"]["entityDeltas"]
    time_entry = r["rawDelta"]["time"]
    plan = r["plan"]

    for entry in plan:
        k, ref = entry["kind"], entry["ref"]
        idp = identity_problem(entry, locs, chars)
        if idp:
            problems.append(idp)
            continue
        if k == "moved":
            d = next((d for d in deltas if d["entityId"] == entry["entityId"]
                      and "positionSet" in d), None)
            to_id = locs.get(entry["to"])
            if to_id is None:
                problems.append(f"plan ref {ref} moved to '{entry['to']}' which is not "
                                f"in the world registry")
            elif d is None:
                problems.append(f"plan ref {ref} moved: no positionSet in rawDelta")
            elif d["positionSet"]["containerId"] != to_id:
                problems.append(f"plan ref {ref} moved to {entry['to']} "
                                f"({to_id}) but rawDelta positionSet is "
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
            d = next((d for d in deltas if d["entityId"] == entry["entityId"]
                      and any(c["text"] == entry["text"]
                              for c in d.get("personalityChanges", []))), None)
            if d is None:
                problems.append(f"plan ref {ref} personality text '{entry['text']}' not "
                                f"in rawDelta personalityChanges")
            else:
                checks.append({"check": "reconcile-personality", "ref": ref, "result": "ok"})
        elif k == "appearance_changed":
            d = next((d for d in deltas if d["entityId"] == entry["entityId"]
                      and any(c["text"] == entry["text"]
                              for c in d.get("appearanceChanges", []))), None)
            if d is None:
                problems.append(f"plan ref {ref} appearance text '{entry['text']}' not in "
                                f"rawDelta appearanceChanges")
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
            claim = next((c for c in r.get("planOnlyClaims", [])
                          if c["kind"] == "positioned_at"
                          and c["entityId"] == entry["entityId"]), None)
            if claim is None or claim["at"] != entry["at"]:
                problems.append(f"plan ref {ref} positioned at {entry['at']} does not "
                                f"match its planOnlyClaims entry "
                                f"({claim['at'] if claim else 'missing'}) — two "
                                f"copies of the current state disagree")
            else:
                checks.append({"check": "reconcile-positioned", "ref": ref, "result": "ok"})
        elif k == "no_change":
            if deltas:
                problems.append("plan claims no_change but rawDelta carries deltas")
            else:
                checks.append({"check": "reconcile-no-change", "ref": ref, "result": "ok"})

    # reverse direction, PER CHANGE: every delta list item must be consumed
    # by a plan entry with the same entity and value (v5: not per-field)
    consumed = set()
    for d in deltas:
        eid = d["entityId"]
        if "positionSet" in d:
            if not any(e["kind"] == "moved" and e["entityId"] == eid
                       and locs.get(e["to"]) == d["positionSet"]["containerId"]
                       for e in plan):
                problems.append(f"rawDelta moves {eid} to "
                                f"{d['positionSet']['containerId']} but no plan entry "
                                f"expresses it")
            else:
                consumed.add((eid, "moved"))
        for tid in d.get("tasksAchieved", []):
            if not any(e["kind"] == "task_achieved" and e["entityId"] == eid
                       and chars.get(e["name"], {}).get("tasks", {}).get(e["goal"], {}).get("id") == tid
                       for e in plan):
                problems.append(f"rawDelta completes task {tid} for {eid} but no plan "
                                f"entry expresses it")
            else:
                consumed.add((eid, f"task:{tid}"))
        if "sanitySet" in d:
            if not any(e["kind"] == "sanity_changed" and e["entityId"] == eid
                       and e["to"] == d["sanitySet"] for e in plan):
                problems.append(f"rawDelta sets sanity {d['sanitySet']} for {eid} but no "
                                f"plan entry expresses it")
            else:
                consumed.add((eid, "sanity"))
        for c in d.get("personalityChanges", []):
            if not any(e["kind"] == "personality_changed" and e["entityId"] == eid
                       and e["text"] == c["text"] for e in plan):
                problems.append(f"rawDelta personality change '{c['text']}' for {eid} "
                                f"has no corresponding plan entry")
            else:
                consumed.add((eid, f"pers:{c['text']}"))
        for c in d.get("appearanceChanges", []):
            if not any(e["kind"] == "appearance_changed" and e["entityId"] == eid
                       and e["text"] == c["text"] for e in plan):
                problems.append(f"rawDelta appearance change '{c['text']}' for {eid} "
                                f"has no corresponding plan entry")
            else:
                consumed.add((eid, f"app:{c['text']}"))
    if time_entry is not None and not any(e["kind"] == "time" for e in plan):
        problems.append("rawDelta carries a time advance but no plan entry expresses it")

    # every planOnlyClaims entry must surface in the plan too (v5, both ways)
    claims = r.get("planOnlyClaims", [])
    for c in claims:
        if c["kind"] == "positioned_at" and not any(
                e["kind"] == "positioned_at" and e["entityId"] == c["entityId"]
                and e["at"] == c["at"] for e in plan):
            problems.append(f"planOnlyClaims positions {c['name']} at {c['at']} but no "
                            f"plan entry expresses this current state")
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

    # ---- tamper MATRIX: per-field invariant tests (review round 5) ----
    # Three fixed invariants, one generated tamper per relevant field:
    #   I. duration consistency (value AND unit, both sides)
    #  II. identity & current-state consistency (entityId<->name binding,
    #      positioned plan<->claim agreement)
    # III. per-change completeness (every delta list item consumed by a plan
    #      entry, not merely "same entity has the kind")
    import copy

    def tampered_problems(src, mutate):
        t = copy.deepcopy(src)
        mutate(t)
        locs_t, chars_t = register_registry(t["world"])
        return reconcile(t, locs_t, chars_t)[0]

    loc1 = next(r for r in rows if r["sourceGroupId"] == "n4-loc-001")
    appear = next(r for r in rows if r["sourceGroupId"].startswith("n4-appear"))
    chain = next(r for r in rows if r["sourceGroupId"].startswith("n4-chain"))
    multi = next(r for r in rows if r["sourceGroupId"].startswith("n4-multi"))
    empty = next(r for r in rows if r["sourceGroupId"].startswith("n4-empty"))
    task = next(r for r in rows if any(e["kind"] == "task_achieved" for e in r["plan"])
                and r["split"] == "train")

    other_loc = next(l["id"] for l in loc1["world"]["locations"]
                     if l["id"] != loc1["rawDelta"]["entityDeltas"][0]["positionSet"]["containerId"])

    MATRIX = [
        ("I: delta time amount", loc1,
         lambda t: t["rawDelta"]["time"].__setitem__("amount", 99)),
        ("I: delta time unit", loc1,
         lambda t: t["rawDelta"]["time"].__setitem__("unit", "hour")),
        ("I: plan time amount", loc1,
         lambda t: next(e for e in t["plan"] if e["kind"] == "time").__setitem__("amount", 99)),
        ("I: plan moved target", loc1,
         lambda t: t["plan"][0].__setitem__("to", "水房")),
        ("II: appearance name/id mismatch", appear,
         lambda t: next(e for e in t["plan"] if e["kind"] == "appearance_changed")
         .__setitem__("name", "东门")),
        ("II: positioned plan/claim divergence", multi,
         lambda t: next(e for e in t["plan"] if e["kind"] == "positioned_at")
         .__setitem__("at", "东门")),
        ("II: positioned claim dropped", multi,
         lambda t: t.__setitem__("planOnlyClaims", [])),
        ("III: extra appearance change", appear,
         lambda t: t["rawDelta"]["entityDeltas"][0]["appearanceChanges"].append(
             {"id": "chg_extra", "text": "屋顶变成了红色", "supersedes": []})),
        ("III: extra personality change", chain,
         lambda t: t["rawDelta"]["entityDeltas"][1]["personalityChanges"].append(
             {"id": "chg_extra", "text": "变得烦躁", "supersedes": []})),
        ("III: extra task in delta", task,
         lambda t: t["rawDelta"]["entityDeltas"][0]["tasksAchieved"].append("task_004")),
        ("III: moved target swap", loc1,
         lambda t: t["rawDelta"]["entityDeltas"][0]["positionSet"].__setitem__("containerId", other_loc)),
        ("III: no_change polluted", empty,
         lambda t: t["rawDelta"]["entityDeltas"].append(
             {"entityId": "char_001", "positionSet": {"containerId": "loc_002"}})),
    ]
    void = []
    for label, src, mutate in MATRIX:
        probs = tampered_problems(src, mutate)
        if not probs:
            void.append(f"{label}: tamper NOT caught")
    if void:
        print("REPORT VOID — reconciliation matrix failed:")
        for x in void:
            print(" ", x)
        sys.exit(2)
    print(f"self-test PASS: {len(MATRIX)}/{len(MATRIX)} tamper-matrix rows caught")

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
                if locs.get(claim["at"]) is None:
                    problems.append(
                        f"positioned claim provenance: {claim['name']} claimed at "
                        f"'{claim['at']}' which is not in the world registry")
                elif home != locs[claim["at"]]:
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
                        if entry["kind"] == "moved" and entry["entityId"] in after.characters:
                            got = after.characters[entry["entityId"]].position.containerId
                            if got != locs.get(entry["to"]):
                                problems.append(f"after position mismatch: {got} != "
                                                f"{locs.get(entry['to'])}")
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
