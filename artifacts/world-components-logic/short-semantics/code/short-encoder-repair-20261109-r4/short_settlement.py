"""D05/D06 experimental orchestration; no world application or semantic defaults.

All model calls receive the complete context. The preview callback is an A/B
boundary: it must validate/apply cumulative candidates and return a bound world.
Engineering fixture callbacks are explicitly not a model or a production server.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable

from short_contracts import Completion, ContractError, digest, result, incomplete

STAGES = ("position", "appearance", "tasks", "subtasks", "personality", "sanity")
RELATIONS = {"under", "above", "beside", "in_front_of", "behind"}


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ContractError(message)


def _text(value: Any, name: str) -> str:
    _require(isinstance(value, str) and bool(value.strip()), name + ": nonempty text required")
    return value


def _exact_ids(values: Any, expected: Any, name: str) -> None:
    _require(isinstance(values, list) and all(isinstance(x, str) for x in values), name + ": ID list required")
    _require(len(values) == len(set(values)) and set(values) == set(expected), name + ": exact coverage required")


def _rows(rows: Any, key: str, expected: Any, name: str) -> dict:
    _require(isinstance(rows, list) and all(isinstance(x, dict) for x in rows), name + ": row list required")
    _exact_ids([x.get(key) for x in rows], expected, name)
    return {x[key]: x for x in rows}


def _bind_candidate(value: dict) -> dict:
    """Content identity for transient work, separate from authoritative state."""
    _require("contentHash" not in value, "candidate hash field reserved")
    return {**deepcopy(value), "contentHash": digest(value)}


def verify_candidate_packet(value: dict) -> None:
    """Detect accidental/stale work mutation; provenance remains journal-bound."""
    _require(isinstance(value, dict) and value.get("contentHash") == digest({k: v for k, v in value.items() if k != "contentHash"}),
             "candidate content hash mismatch")


def _call(session: Any, component: str, payload: dict) -> Any:
    outcome = session.call(component, deepcopy(payload))
    _require(isinstance(outcome, Completion), component + ": Completion required")
    _require(outcome.status == "result", component + ": " + str(outcome.reason or outcome.status))
    return outcome.value


def _world(world: dict) -> tuple[dict, dict, dict]:
    _require(isinstance(world, dict), "world: object required")
    for field in ("initial", "locations", "items", "characters", "time"):
        _require(field in world, "world: missing " + field)
    locations, items, people = world["locations"], world["items"], world["characters"]
    _require(all(isinstance(x, dict) for x in (locations, items, people)), "world: entity maps required")
    entities = {**locations, **items, **people}
    _require(len(entities) == len(locations) + len(items) + len(people), "world: duplicate entity")
    _require(bool(locations) and bool(people), "world: location and character required")
    for kind in ("locations", "items", "characters"):
        _require(set(world["initial"][kind]) == set(world[kind]), "world: initial roster differs")
        for key, entity in world[kind].items():
            _require(entity.get("id") == key, "world: entity key mismatch")
            original = world["initial"][kind][key]
            _require(original.get("id") == key, "world: initial identity mismatch")
            _text(original.get("name"), "world initial name")
            _text(original.get("initialAppearance"), "world initial appearance")
            if kind == "characters":
                _text(original.get("initialPersonality"), "world initial personality")
            if kind != "locations":
                _require(isinstance(entity.get("position"), dict) and entity["position"].get("containerId") in entities, "world: current position required")
            _require(isinstance(entity.get("appearanceChanges"), list), "world: appearance records required")
    tasks = {}
    for owner, person in people.items():
        _require(isinstance(person.get("personalityChanges"), list), "world: personality records required")
        _require(isinstance(person.get("tasks"), dict), "world: tasks required")
        _require(type(person.get("sanity")) is int and 0 <= person["sanity"] <= 100, "world: invalid sanity")
        for key, task in person["tasks"].items():
            _require(key not in tasks and task.get("id") == key and task.get("ownerId") == owner, "world: invalid task identity")
            _require(task.get("status") in ("pending", "achieved"), "world: invalid task status")
            _text(task.get("goal"), "world current task goal")
            _require("parentTaskId" in task and (task["parentTaskId"] is None or task["parentTaskId"] in person["tasks"]), "world: task parent missing/foreign")
            tasks[key] = task
    return entities, people, tasks


def validate_group(context: dict) -> dict:
    """Check declared closed-group completeness, including nonadmitted rolls.

    Service authenticity must be checked by the caller's A/B read adapter; this
    function establishes structure and frozen-byte binding, not authenticity.
    """
    _, people, _ = _world(context["world"])
    _require(isinstance(context.get("binding"), dict) and context["binding"], "binding required")
    group = context["group"]
    _require(group.get("closed") is True, "group_not_closed")
    ids = group["memberIds"]
    _exact_ids(ids, ids, "members")
    _require(bool(ids) and set(ids) <= set(people), "unknown/empty group")
    members = _rows(group["members"], "memberId", ids, "frozen actions")
    for member in members.values():
        _text(member.get("actionText"), "frozen action")
        if "fragments" in member:
            fragments = member["fragments"]
            _require(isinstance(fragments, list) and fragments and all(isinstance(f, dict) for f in fragments), "invalid frozen fragments")
            _require("\n".join(_text(f["text"], "frozen fragment") for f in fragments) == member["actionText"], "fragments do not compose frozen action")
    targets = _rows(group["confirmedTargets"], "sourceId", ids, "confirmed targets")
    required = set()
    for source, row in targets.items():
        _exact_ids(row["targetIds"], row["targetIds"], "target set")
        _require(set(row["targetIds"]) <= set(people), "unknown target")
        required.update((source, target) for target in row["targetIds"])
    checks = group["judgments"]
    _require(isinstance(checks, list), "actual judgments required")
    from short_intent import _judgments
    _judgments(checks, set(people), set(ids))
    _text(group.get("groupId"), "program group identity")
    _require(all(c["groupId"] == group["groupId"] for c in checks), "foreign group dice receipt")
    pairs, roll_ids = [], []
    acted = group["alreadyActedIds"]
    _exact_ids(acted, acted, "alreadyActedIds")
    _require(set(acted) <= set(people), "unknown already-acted person")
    for check in checks:
        pair = (check["sourceId"], check["targetId"])
        pairs.append(pair)
        roll_ids.append(_text(check.get("rollId"), "actual roll ID"))
        _text(check.get("ruleVersion"), "roll rule")
        value, threshold = check.get("result", check.get("value")), check.get("target", check.get("threshold"))
        if "value" in check:
            _require(check["value"] == value, "conflicting actual roll aliases")
        if "threshold" in check:
            _require(check["threshold"] == threshold, "conflicting actual threshold aliases")
        _require(type(value) is int and 1 <= value <= 20 and type(threshold) is int and 1 <= threshold <= 20, "invalid actual d20 judgment")
        _require(all(type(check.get(k)) is bool for k in ("eligible", "admitted")), "incomplete actual judgment")
        if "passed" in check:
            _require(type(check["passed"]) is bool and check["passed"] == (value >= threshold), "inconsistent roll pass")
        _require(check["admitted"] == (check["eligible"] and value >= threshold), "inconsistent admission")
        _require(not (pair[1] in acted and check["eligible"]), "already acted cannot be readmitted")
        _require(not check["admitted"] or pair[1] in ids, "admitted target missing")
    _require(set(pairs) == required and len(pairs) == len(required), "all relevant judgments required, including denied and already acted")
    _require(len(roll_ids) == len(set(roll_ids)), "duplicate roll ID")
    return group


def settlement_context(action_context: dict, chain: Completion, *, group_id: str, binding: dict) -> dict:
    """Bind a real D02→D03→D04 output to D05, without regenerating any work.

    The program supplies group/point identities. Actual receipts remain byte-for-
    byte dictionaries; the closed group is not a formal A/B close receipt.
    """
    _require(isinstance(chain, Completion) and chain.status == "result", "unfinished action chain")
    value = chain.value
    _require(value.get("closed") is True, "action chain not closed")
    _text(group_id, "program group ID")
    _require(isinstance(binding, dict) and bool(binding), "program binding required")
    group = {k: deepcopy(value[k]) for k in ("members", "confirmedTargets", "judgments", "closed", "memberIds", "alreadyActedIds")}
    group["groupId"] = group_id
    frozen = {a.actor_id: a.verify() for a in value["frozenActions"]}
    _require(len(frozen) == len(value["frozenActions"]) and set(frozen) == set(group["memberIds"]), "frozen-action coverage mismatch")
    for member in group["members"]:
        action = frozen[member["memberId"]]
        _require(member["actionText"] == action.text and member["actionDigest"] == action.content_digest, "action bytes differ from frozen candidate")
        _require(member.get("fragments") == action.material()["renderedFragments"], "fragments differ from frozen material")
    context = deepcopy(action_context)
    context.update(group=group, binding=deepcopy(binding), sourceChainHash=digest(value))
    validate_group(context)
    return context


def settle_joint(session: Any, context: dict, *, max_facts: int = 32) -> Completion:
    """D05.1–D05.6, all-group semantics, original text in member wire output."""
    try:
        context = deepcopy(context)
        group = validate_group(context)
        _require(type(max_facts) is int and max_facts > 0, "invalid fact resource limit")
        frozen = deepcopy(context)
        source_hash = digest(frozen)
        action_ids = group["memberIds"]
        common = {"context": frozen, "inputHash": source_hash}
        relations = _call(session, "D05.1", common)
        _exact_ids(relations["checkedActionIds"], action_ids, "relation action coverage")
        _require(isinstance(relations["relations"], list), "relations required")
        for edge in relations["relations"]:
            _require(edge["sourceId"] in action_ids and edge["targetId"] in action_ids, "relation outside group")
            _require(edge["kind"] in ("obstructs", "supports", "contests", "depends"), "invalid relation label")
        attempts = []
        for member in group["members"]:
            # Fragment references identify attempts without rewriting their text.
            fragments = member.get("fragments")
            if fragments is None:
                attempts.append({"attemptId": member["memberId"], "memberId": member["memberId"], "text": member["actionText"]})
            else:
                _require(isinstance(fragments, list) and bool(fragments), "empty action fragments")
                for f in fragments:
                    attempts.append({"attemptId": _text(f["id"], "fragment ID"), "memberId": member["memberId"], "text": _text(f["text"], "fragment text")})
        _exact_ids([a["attemptId"] for a in attempts], [a["attemptId"] for a in attempts], "attempt identities")
        joint_answer = session.call("D05.2", deepcopy({**common, "relations": relations, "attempts": attempts}))
        _require(isinstance(joint_answer, Completion), "D05.2: Completion required")
        if joint_answer.status == "incomplete":
            return joint_answer
        _require(joint_answer.status == "result", "D05.2: completed joint judgment required")
        joint = joint_answer.value
        judgments = _rows(joint["judgments"], "attemptId", [a["attemptId"] for a in attempts], "joint judgment coverage")
        for item in judgments.values():
            _require(item["label"] in ("achieved", "partial", "not_achieved", "incomplete"), "joint judgment invalid")
        unfinished = [a["attemptId"] for a in attempts if judgments[a["attemptId"]]["label"] == "incomplete"]
        if unfinished:
            # The session/provider journal retains the complete first joint
            # answer. No facts or wire result may be generated from it.
            return incomplete("semantic_incomplete:D05.2:" + ",".join(unfinished))
        facts = []
        for index in range(max_facts + 1):
            next_fact = _call(session, "D05.3", {**common, "relations": relations, "joint": joint, "candidates": facts})
            if next_fact.get("kind") == "end":
                _require(set(next_fact) == {"kind"}, "end must not carry hidden facts")
                break
            _require(next_fact.get("kind") == "fact" and set(next_fact) == {"kind", "text"}, "next fact or explicit end required")
            _require(index < max_facts, "fact_budget_pause: explicit end not reached")
            facts.append({"id": "fact:" + str(index + 1), "text": _text(next_fact["text"], "result fact")})
        _require(bool(facts), "interface_gap: member results need nonempty semantic facts")
        audit = _call(session, "D05.4", {**common, "relations": relations, "joint": joint, "candidates": facts})
        _require(audit["verdict"] == "pass", "joint consistency/causal/side-effect audit rejected")
        _exact_ids(audit["checkedActionIds"], action_ids, "audit actions")
        _exact_ids(audit["checkedFactIds"], [f["id"] for f in facts], "audit facts")
        _exact_ids(audit["checkedRollIds"], [j["rollId"] for j in group["judgments"]], "audit actual rolls")
        links = _call(session, "D05.5", {**common, "joint": joint, "candidates": facts, "audit": audit})
        associations = _rows(links["facts"], "factId", [f["id"] for f in facts], "fact association coverage")
        member_texts = {member: [] for member in action_ids}
        for fact in facts:
            recipients = associations[fact["id"]]["memberIds"]
            _exact_ids(recipients, recipients, "fact members")
            _require(bool(recipients) and set(recipients) <= set(action_ids), "unknown/empty fact association")
            for member in recipients:
                member_texts[member].append(fact["text"])
        _require(all(member_texts.values()), "missing member result facts")
        _exact_ids(links["checkedMemberIds"], action_ids, "member coverage")
        return result(_bind_candidate({"inputHash": source_hash, "binding": deepcopy(context["binding"]), "facts": facts,
                       "relations": relations, "joint": joint, "audit": audit, "associations": links,
                       "results": {member: "\n".join(texts) for member, texts in member_texts.items()},
                       "semanticReview": "model_checked_not_human_signed", "committed": False}))
    except Exception as exc:
        return incomplete("D05: " + str(exc))


def validate_positions(world: dict, positions: dict) -> None:
    """Validate the FINAL simultaneous graph; never apply one move at a time."""
    entities, people, _ = _world(world)
    movable = {**world["items"], **people}
    _require(set(positions) <= set(movable), "only items/characters can move")
    current = {k: deepcopy(v["position"]) for k, v in movable.items()}
    current.update(deepcopy(positions))
    parents = {k: v["parentLocationId"] for k, v in world["initial"]["locations"].items()}
    edges = {k: ([] if v is None else [v]) for k, v in parents.items()}
    for key, position in current.items():
        _require(isinstance(position, dict) and set(position) <= {"containerId", "slotId", "relativeTo"}, "invalid position shape")
        container = position["containerId"]
        _require(container in entities and container != key, "invalid container")
        parents[key] = container
        slots = next(world["initial"][kind][container].get("slots", []) for kind in ("locations", "items", "characters") if container in world["initial"][kind])
        _require(position.get("slotId") is None or position["slotId"] in {s["id"] for s in slots}, "slot does not belong to container")
        edges[key] = [container]
        relative = position.get("relativeTo")
        if relative is not None:
            _require(isinstance(relative, dict) and set(relative) == {"entityId", "relation"}, "invalid relative position")
            _require(relative["entityId"] in entities and relative["relation"] in RELATIONS, "unknown relative target/relation")
            edges[key].append(relative["entityId"])
    visiting, visited = set(), set()
    def visit(node):
        _require(node not in visiting, "cyclic simultaneous position graph")
        if node in visited:
            return
        visiting.add(node)
        for target in edges[node]:
            visit(target)
        visiting.remove(node)
        visited.add(node)
    for key in edges:
        visit(key)
    def room(key):
        while key not in world["locations"]:
            key = parents[key]
        return key
    for key, position in current.items():
        if position.get("relativeTo") is not None:
            _require(room(key) == room(position["relativeTo"]["entityId"]), "relative target is in another location")


def _records(world: dict, kind: str) -> dict:
    entities, people, _ = _world(world)
    owners = people if kind == "personality" else entities
    field = kind + "Changes"
    return {owner: {r["id"]: r for r in entity[field] if r["active"]} for owner, entity in owners.items()}


def _candidate_refs(calls: list[dict]) -> list[dict]:
    refs = []
    for call in calls:
        for owner, delta in call["changes"].items():
            for field, value in delta.items():
                if field == "entityId":
                    continue
                if isinstance(value, list):
                    for item in value:
                        refs.append({"stage": call["stage"], "entityId": owner, "operationId": item["id"] if isinstance(item, dict) else item})
                else:
                    refs.append({"stage": call["stage"], "entityId": owner, "operationId": field})
    return refs


def validate_fact_mapping(mapping: dict, facts: list[dict], calls: list[dict], *, time_fact: dict | None = None) -> None:
    """Reference/coverage only. The model must judge semantic correspondence."""
    ids = [f["id"] for f in facts]
    if time_fact is not None:
        ids.append(time_fact["id"])
    _exact_ids(ids, ids, "result/time fact identities")
    sources = set(ids)
    available = {digest(ref) for ref in _candidate_refs(calls)}
    used, covered = set(), set()
    _require(mapping.get("verdict") == "pass", "fact-to-state semantic audit rejected")
    _require(isinstance(mapping.get("mappings"), list), "fact mappings required")
    _exact_ids([row["factId"] for row in mapping["mappings"]], ids, "fact mapping dispositions")
    for row in mapping["mappings"]:
        _require(row["factId"] in sources, "unknown mapped fact")
        covered.add(row["factId"])
        kind = row["kind"]
        _require(kind in ("state", "unchanged", "transient", "gap"), "invalid fact disposition")
        _require(kind != "gap", "interface_gap: retained fact has no protocol representation")
        targets = row["targets"]
        _require(isinstance(targets, list), "mapping targets required")
        _require(len(targets) == len({digest(target) for target in targets}), "duplicate target within fact mapping")
        _require((kind == "state") == bool(targets), "state facts require targets; unchanged/transient cannot claim changes")
        for target in targets:
            _require(digest(target) in available, "unknown candidate mapping reference")
            used.add(digest(target))
    _require(covered == sources, "unmapped result/time fact")
    _require(used == available, "candidate consequence lacks semantic source mapping")


def assemble_wire(group_id: str | None, actors: list[str], calls: list[dict], roster: list[str], *, personality_scanned: bool) -> dict:
    """Existing updates and SettlementGroup shapes; no semantic material added."""
    _require([c["stage"] for c in calls] == list(STAGES), "six ordered stages required")
    candidate = {"groupId": group_id, "actorIds": actors, "positions": {}, "appearances": {}, "tasksAchieved": {},
                 "subtasksAdded": {}, "personalities": {}, "sanities": {}, "taskCoverageIds": roster,
                 "personalityCoverageIds": roster if personality_scanned else []}
    fields = {"positionSet": "positions", "appearanceChanges": "appearances", "tasksAchieved": "tasksAchieved",
              "subtasksAdded": "subtasksAdded", "personalityChanges": "personalities", "sanitySet": "sanities"}
    for index, call in enumerate(calls):
        allowed = tuple(fields)[index]
        for owner, delta in call["changes"].items():
            _require(set(delta) == {"entityId", allowed} and delta["entityId"] == owner, "cross-stage/wrong entity delta")
            _require(owner not in candidate[fields[allowed]], "duplicate candidate owner")
            candidate[fields[allowed]][owner] = deepcopy(delta[allowed])
    _require(set(candidate["personalities"]) == set(candidate["sanities"]), "personality/sanity coverage mismatch")
    if group_id is None:
        _require(not actors and not candidate["positions"] and not candidate["appearances"], "time scan cannot invent action/movement/appearance")
    return candidate


def run_updates(session: Any, context: dict, settlement: dict | None, preview: Callable[[dict], Completion],
                allocate_id: Callable[[str, str], str], *, max_new_tasks: int = 32,
                progress_sink: Callable[[dict], None] | None = None) -> Completion:
    """U1→U6 using A/B preview after every stage; no commit or narration.

    time_scan=True still requires explicit U1/U2 no-change decisions and a full
    U3 scan. Its existing wire contract rejects movement/appearance candidates.
    """
    progress: dict = {"calls": [], "previews": []}
    try:
        base = deepcopy(context)
        settlement = deepcopy(settlement)
        entities, people, all_tasks = _world(base["world"])
        _require(isinstance(base.get("binding"), dict) and base["binding"], "binding required")
        pure_time = base.get("time_scan") is True
        if pure_time:
            _require(settlement is None, "time scan must not import group result candidates")
            _require(isinstance(base.get("timeFact"), dict), "time fact required")
            _text(base["timeFact"]["id"], "time fact ID")
            _require("timeAdvance" in base, "locked time advance required")
            facts, actors, group_id = [], [], None
        else:
            group = validate_group(base)
            verify_candidate_packet(settlement)
            _require(isinstance(settlement, dict) and settlement.get("inputHash") == digest(base), "stale or unrelated joint result")
            _require(settlement.get("binding") == base["binding"] and settlement.get("committed") is False, "joint result binding mismatch")
            facts, actors = settlement["facts"], group["memberIds"]
            group_id = group["groupId"]
        original_initial = digest(base["world"]["initial"])
        current = deepcopy(base["world"])
        allocated = set(entities) | set(all_tasks)
        for entity in entities.values():
            for field in ("appearanceChanges", "personalityChanges"):
                allocated.update(row["id"] for row in entity.get(field, []))
        def new_id(kind, slot):
            value = _text(allocate_id(kind, digest({"input": digest(base), "slot": slot})), "allocated ID")
            _require(value not in allocated, "allocated ID collision")
            allocated.add(value)
            return value
        def payload(**extra):
            return {"context": base, "world": current, "worldHash": digest(current), "settlement": settlement,
                    "facts": facts, "candidates": progress["calls"], **extra}
        def finish(stage, changes):
            nonlocal current
            call = {"stage": stage, "changes": changes}
            audit = _call(session, "D06.P.review", payload(stage=stage, proposed=call))
            _require(audit.get("verdict") == "pass", stage + ": semantic stage audit rejected")
            _exact_ids(audit["checkedEntityIds"], list(changes), stage + " candidate audit")
            progress["calls"].append(call)
            if progress_sink is not None:
                progress_sink(deepcopy({"status": "candidate", "binding": base["binding"], **progress}))
            request = {"binding": base["binding"], "baseWorldHash": digest(base["world"]),
                       "completedStages": deepcopy(progress["calls"]), "stage": stage}
            request["candidateHash"] = digest(request["completedStages"])
            outcome = preview(deepcopy(request))
            _require(isinstance(outcome, Completion) and outcome.status == "result", "preview incomplete: " + str(getattr(outcome, "reason", None)))
            value = outcome.value
            _require(value["binding"] == base["binding"] and value["candidateHash"] == request["candidateHash"] and value["stage"] == stage, "stale preview binding")
            _require(value["baseWorldHash"] == request["baseWorldHash"], "preview baseline mismatch")
            next_world = value["world"]
            next_entities, next_people, _ = _world(next_world)
            _require(set(next_entities) == set(entities) and set(next_people) == set(people), "preview changed fixed entity roster")
            _require(digest(next_world["initial"]) == original_initial, "preview rewrote immutable initial state")
            progress["previews"].append({"stage": stage, "candidateHash": request["candidateHash"], "worldHash": digest(next_world)})
            current = deepcopy(next_world)
            if progress_sink is not None:
                progress_sink(deepcopy({"status": "previewed", "binding": base["binding"], **progress}))
        # U1: all characters and items, then simultaneous positions.
        movable = list({**current["items"], **current["characters"]})
        decision = _call(session, "U1.1", payload(entityIds=movable))
        rows = _rows(decision["decisions"], "entityId", movable, "U1 all movable entities")
        _require(all(type(r.get("change")) is bool for r in rows.values()), "U1 change labels required")
        changed = [key for key, row in rows.items() if row["change"]]
        positions = {}
        if changed:
            choices = _call(session, "U1.2", payload(entityIds=changed, decisions=decision))
            selected = _rows(choices["positions"], "entityId", changed, "U1 destination coverage")
            positions = {key: row["position"] for key, row in selected.items()}
        _require(not pure_time or not positions, "interface_gap: pure time movement cannot be staged")
        validate_positions(current, positions)
        finish("position", {key: {"entityId": key, "positionSet": pos} for key, pos in positions.items()})
        def descriptions(kind, component, targets):
            available = _records(current, kind)
            selection = _call(session, component + ".1", payload(entityIds=targets, activeRecords=available))
            _exact_ids(selection["checkedEntityIds"], targets, component + " entity coverage")
            _exact_ids(selection["checkedRecordIds"], [rid for k in targets for rid in available[k]], component + " record coverage")
            operations = selection["operations"]
            _require(isinstance(operations, list), "description operations required")
            touched, superseded, kept, output = set(), set(), set(), {}
            for index, op in enumerate(operations):
                owner, label, old = op["entityId"], op["op"], op["recordIds"]
                _require(owner in targets and label in ("keep", "remove", "add", "replace"), "invalid description operation")
                _exact_ids(old, old, "old description references")
                _require(set(old) <= set(available[owner]), "unknown/inactive/initial description reference")
                touched.add(owner)
                if label == "keep":
                    _require(not (set(old) & (superseded | kept)), "conflicting or repeated keep/removal")
                    kept.update(old)
                    continue
                _require(not (set(old) & (superseded | kept)), "conflicting description operations; no last-write-wins")
                _require((label in ("remove", "replace")) == bool(old), "remove/replace needs old references, add cannot supersede")
                superseded.update(old)
                text = None
                if label in ("add", "replace"):
                    generated = _call(session, component + ".2", payload(operation=op, operationIndex=index, currentDescriptionCandidates=output))
                    text = _text(generated, "one local description")
                change = {"id": new_id("change", f"{component}:{index}"), "text": text, "supersedes": old}
                field = kind + "Changes"
                output.setdefault(owner, {"entityId": owner, field: []})[field].append(change)
            _require(touched == set(targets), component + ": explicit operations/keep required for every entity")
            _require(kept | superseded == {rid for key in targets for rid in available[key]},
                     component + ": record operation coverage incomplete; no implicit keep")
            return output
        appearances = descriptions("appearance", "U2", list(entities))
        _require(not pure_time or not appearances, "interface_gap: pure time appearance cannot be staged")
        finish("appearance", appearances)
        # U3: all current tasks individually; never derive parents from children.
        _, _, tasks = _world(current)
        task_decisions = _call(session, "U3.1", payload(taskIds=list(tasks), characterIds=list(people)))
        task_rows = _rows(task_decisions["decisions"], "taskId", list(tasks), "all current tasks")
        _exact_ids(task_decisions["checkedCharacterIds"], list(people), "all task owners including no-task characters")
        achieved = {}
        for key, row in task_rows.items():
            _require(row["label"] in ("pending", "achieved"), "unfinished task judgment")
            _require(tasks[key]["status"] != "achieved" or row["label"] == "achieved", "cannot undo achieved task")
            if row["label"] == "achieved" and tasks[key]["status"] == "pending":
                owner = tasks[key]["ownerId"]
                achieved.setdefault(owner, {"entityId": owner, "tasksAchieved": []})["tasksAchieved"].append(key)
        finish("tasks", achieved)
        # U4: explicit count per existing parent; each new goal remains pending.
        _, _, parents = _world(current)
        needs = _call(session, "U4.1", payload(parentTaskIds=list(parents), characterIds=list(people)))
        _exact_ids(needs["checkedParentTaskIds"], list(parents), "all potential parent tasks")
        _exact_ids(needs["checkedCharacterIds"], list(people), "subtask character coverage")
        need_rows = _rows(needs["needs"], "parentTaskId", list(parents), "parent need coverage")
        _require(type(max_new_tasks) is int and max_new_tasks >= 0, "invalid subtask resource limit")
        _require(all(type(r.get("count")) is int and r["count"] >= 0 for r in need_rows.values()), "invalid subtask count")
        _require(sum(r["count"] for r in need_rows.values()) <= max_new_tasks, "subtask_budget_pause: complete requirement exceeds budget")
        added = {}
        for parent, row in need_rows.items():
            owner = parents[parent]["ownerId"]
            for index in range(row["count"]):
                goal = _text(_call(session, "U4.2", payload(parentTaskId=parent, ownerId=owner, goalIndex=index, requiredCount=row["count"], currentSubtaskCandidates=added)), "one concrete subtask goal")
                task = {"id": new_id("task", f"{parent}:{index}"), "ownerId": owner, "parentTaskId": parent, "goal": goal, "status": "pending"}
                added.setdefault(owner, {"entityId": owner, "subtasksAdded": []})["subtasksAdded"].append(task)
        finish("subtasks", added)
        # U5 is conditional but scans EVERY person, including off-scene people.
        personalities = descriptions("personality", "U5", list(people)) if achieved else {}
        before_personality = _records(current, "personality")
        finish("personality", personalities)
        after_personality = _records(current, "personality")
        for owner in personalities:
            old = [r["text"] for r in before_personality[owner].values() if r["text"] is not None]
            new = [r["text"] for r in after_personality[owner].values() if r["text"] is not None]
            _require(old != new, "personality operation made no effective preference change; model must decide keep")
        sanities = {}
        for owner in personalities:
            value = _call(session, "U6.1", payload(entityId=owner, effectivePersonalityRecords=after_personality[owner]))
            _require(type(value) is int and 0 <= value <= 100, "sanity must be integer 0..100; no clipping")
            sanities[owner] = {"entityId": owner, "sanitySet": value}
        finish("sanity", sanities)
        mapping = _call(session, "D06.P.mapping", payload(candidateRefs=_candidate_refs(progress["calls"]), timeFact=base.get("timeFact")))
        validate_fact_mapping(mapping, facts, progress["calls"], time_fact=base.get("timeFact"))
        wire = assemble_wire(group_id, actors, progress["calls"], list(people), personality_scanned=bool(achieved))
        return result(_bind_candidate({"inputHash": digest(base), "binding": base["binding"], "updates": progress["calls"],
                       "candidates": wire, "factMapping": mapping, "previews": progress["previews"],
                       "finalPreviewHash": digest(current), "committed": False,
                       "semanticReview": "model_checked_not_human_signed"}))
    except Exception as exc:
        if progress_sink is not None:
            try:
                progress_sink(deepcopy({"status": "incomplete", "reason": str(exc), **progress}))
            except Exception:
                pass  # Original failure remains failure; no candidate is accepted.
        return incomplete("D06: " + str(exc))
