"""Small, standard-library-only helpers for D's isolated L3 experiments.

These are experiment records and structural guards, not a second world protocol
or a semantic game engine.  No helper decides an action, target or consequence;
human semantic review and the production authority remain separate.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


class LabValidationError(ValueError):
    """Invalid experiment input/output; never convert this into a negative answer."""


TASKS = frozenset({"D02", "D03", "D04", "D05"})
CASE_KEYS = frozenset({
    "caseId", "sourceGroup", "anchorCase", "derivedFrom", "split", "purpose",
    "task", "stageCut", "input",
})
INPUT_KEYS = {
    "D02": frozenset({"world", "actorId", "protagonistId", "advance", "confirmedPrefix"}),
    "D03": frozenset({"world", "source", "candidateIds", "alreadyActedIds", "confirmedGroup", "knownPriorJudgments"}),
    "D04": frozenset({"world", "memberId", "source", "admission", "alreadyActedIds", "previouslySkippedIds", "confirmedGroup", "judgments"}),
    "D05": frozenset({"world", "group"}),
}
JUDGMENT_KEYS = frozenset({
    "sourceId", "targetId", "rollId", "ruleVersion", "value", "threshold",
    "passed", "eligible", "admitted",
})
FORBIDDEN_INPUT_KEYS = frozenset({
    "answer", "answers", "gold", "golden", "expected", "draftexpected",
    "expectedtargets", "expectedoutput", "expectedkind", "labels", "label",
    "rubric", "review", "humanreview", "coveragetags", "sourcegroup",
    "futurejudgments", "futureactions", "futureoutcomes", "futureresults",
})


def canonical_bytes(value: Any) -> bytes:
    """Deterministic UTF-8 JSON, sorted keys, no newline and no nonfinite values."""
    def check_tree(node: Any) -> None:
        if isinstance(node, dict):
            if any(not isinstance(key, str) for key in node):
                raise LabValidationError("canonical JSON requires string object keys")
            for child in node.values():
                check_tree(child)
        elif isinstance(node, list):
            for child in node:
                check_tree(child)
        elif node is not None and type(node) not in (str, bool, int, float):
            raise LabValidationError("not a JSON value")
    check_tree(value)
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True,
                          separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise LabValidationError(f"not canonical JSON: {exc}") from exc


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _reject_constant(value: str) -> None:
    raise LabValidationError(f"nonfinite JSON constant: {value}")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise LabValidationError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def _parse_json(raw: str) -> Any:
    try:
        return json.loads(raw, object_pairs_hook=_unique_object,
                          parse_constant=_reject_constant)
    except (ValueError, TypeError) as exc:
        if isinstance(exc, LabValidationError):
            raise
        raise LabValidationError(f"invalid JSON: {exc}") from exc


def load_jsonl(path: str | Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with Path(path).open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                value = _parse_json(line)
                _object(value, "row")
            except LabValidationError as exc:
                raise LabValidationError(f"{path}:{line_number}: {exc}") from exc
            rows.append(value)
    return rows


def _object(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise LabValidationError(f"{path}: expected object")
    return value


def _array(value: Any, path: str) -> list[Any]:
    if not isinstance(value, list):
        raise LabValidationError(f"{path}: expected array")
    return value


def _string(value: Any, path: str, *, nonempty: bool = True) -> str:
    if not isinstance(value, str) or (nonempty and not value.strip()):
        raise LabValidationError(f"{path}: expected {'nonempty ' if nonempty else ''}string")
    return value


def _keys(value: Any, path: str, *, required: Iterable[str],
          allowed: Iterable[str] | None = None) -> dict[str, Any]:
    obj = _object(value, path)
    required_set = set(required)
    allowed_set = set(allowed) if allowed is not None else required_set
    missing = required_set - set(obj)
    extra = set(obj) - allowed_set
    if missing:
        raise LabValidationError(f"{path}: missing fields {sorted(missing)}")
    if extra:
        raise LabValidationError(f"{path}: unexpected fields {sorted(extra)}")
    return obj


def _ids(value: Any, path: str, registered: set[str] | None = None) -> list[str]:
    values = _array(value, path)
    for index, item in enumerate(values):
        _string(item, f"{path}[{index}]")
        if registered is not None and item not in registered:
            raise LabValidationError(f"{path}[{index}]: unknown ID {item}")
    if len(set(values)) != len(values):
        raise LabValidationError(f"{path}: duplicate ID")
    return values


def _id(value: Any, path: str, registered: set[str]) -> str:
    text = _string(value, path)
    if text not in registered:
        raise LabValidationError(f"{path}: unknown ID {text}")
    return text


def _without_answers(value: Any, path: str = "input") -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            if not isinstance(key, str):
                raise LabValidationError(f"{path}: non-string key")
            normal = key.replace("_", "").replace("-", "").lower()
            if normal in FORBIDDEN_INPUT_KEYS or normal.startswith(("expected", "future", "gold")):
                raise LabValidationError(f"{path}.{key}: review/future answer in model input")
            _without_answers(nested, f"{path}.{key}")
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            _without_answers(nested, f"{path}[{index}]")


def _world(value: Any) -> set[str]:
    world = _keys(value, "input.world", required={"time", "places", "items", "characters"})
    if not isinstance(world["time"], (str, dict)) or not world["time"]:
        raise LabValidationError("input.world.time: missing time")
    entities: set[str] = set()
    people: set[str] = set()
    place_ids: set[str] = set()
    for kind in ("places", "items", "characters"):
        for index, entity in enumerate(_array(world[kind], f"input.world.{kind}")):
            path = f"input.world.{kind}[{index}]"
            if kind == "places":
                _keys(entity, path, required={"id", "name", "parentId"},
                      allowed={"id", "name", "parentId", "appearance"})
            elif kind == "items":
                _keys(entity, path, required={"id", "name", "position"},
                      allowed={"id", "name", "position", "appearance"})
            else:
                _keys(entity, path, required={"id", "name", "position", "appearance", "tasks", "personality", "sanity"})
            entity_id = _string(entity["id"], path + ".id")
            _string(entity["name"], path + ".name")
            if entity_id in entities:
                raise LabValidationError(f"{path}.id: duplicate entity ID {entity_id}")
            entities.add(entity_id)
            if kind == "places":
                place_ids.add(entity_id)
            elif kind == "characters":
                people.add(entity_id)
                if type(entity["sanity"]) is not int or not 0 <= entity["sanity"] <= 100:
                    raise LabValidationError(f"{path}.sanity: expected integer in 0..100")
                _string(entity["appearance"], path + ".appearance")
                for j, text in enumerate(_array(entity["personality"], path + ".personality")):
                    _string(text, f"{path}.personality[{j}]")
                tasks = _array(entity["tasks"], path + ".tasks")
                task_ids: set[str] = set()
                for j, task in enumerate(tasks):
                    tpath = f"{path}.tasks[{j}]"
                    _keys(task, tpath, required={"id", "text", "status", "parentId"})
                    task_id = _string(task["id"], tpath + ".id")
                    if task_id in task_ids:
                        raise LabValidationError(f"{tpath}: duplicate task ID")
                    task_ids.add(task_id)
                    _string(task["text"], tpath + ".text")
                    if task["status"] not in ("pending", "achieved"):
                        raise LabValidationError(f"{tpath}.status: invalid task status")
                parents = {task["id"]: task["parentId"] for task in tasks}
                for task_id, parent_id in parents.items():
                    if parent_id is not None and parent_id not in task_ids:
                        raise LabValidationError(f"{path}.tasks: unknown/cross-owner parent")
                    seen: set[str] = set()
                    current = task_id
                    while current is not None:
                        if current in seen:
                            raise LabValidationError(f"{path}.tasks: parent cycle")
                        seen.add(current)
                        current = parents[current]
    if not people:
        raise LabValidationError("input.world.characters: empty roster")
    for index, place in enumerate(world["places"]):
        if place["parentId"] is not None:
            _id(place["parentId"], f"input.world.places[{index}].parentId", place_ids)
    for kind in ("items", "characters"):
        for index, entity in enumerate(world[kind]):
            position = entity["position"]
            path = f"input.world.{kind}[{index}].position"
            if isinstance(position, str):
                _id(position, path, entities)
            elif isinstance(position, dict) and position:
                for key in ("containerId", "placeId", "holderId", "relativeTo"):
                    if key in position and position[key] is not None:
                        _id(position[key], f"{path}.{key}", entities)
            else:
                raise LabValidationError(f"{path}: expected registered position or object")
    return people


def _source(value: Any, path: str, people: set[str]) -> dict[str, Any]:
    # Missing/empty frozen text is representable solely as a guard probe.
    source = _keys(value, path, required={"memberId"}, allowed={"memberId", "actionText"})
    _id(source["memberId"], path + ".memberId", people)
    if "actionText" in source:
        _string(source["actionText"], path + ".actionText", nonempty=False)
    return source


def _members(value: Any, path: str, people: set[str]) -> list[dict[str, Any]]:
    members = _array(value, path)
    for index, member in enumerate(members):
        _source(member, f"{path}[{index}]", people)
    member_ids = [member["memberId"] for member in members]
    if len(set(member_ids)) != len(member_ids):
        raise LabValidationError(f"{path}: duplicate member ID")
    return members


def _judgments(value: Any, path: str, people: set[str]) -> list[dict[str, Any]]:
    judgments = _array(value, path)
    for index, item in enumerate(judgments):
        jpath = f"{path}[{index}]"
        _keys(item, jpath, required={"sourceId", "targetId"}, allowed=JUDGMENT_KEYS)
        _id(item["sourceId"], jpath + ".sourceId", people)
        _id(item["targetId"], jpath + ".targetId", people)
        for field in ("eligible", "admitted", "passed"):
            if field in item and type(item[field]) is not bool:
                raise LabValidationError(f"{jpath}.{field}: expected boolean")
        for field in ("value", "threshold"):
            if field in item and type(item[field]) is not int:
                raise LabValidationError(f"{jpath}.{field}: expected integer")
        for field in ("rollId", "ruleVersion"):
            if field in item:
                _string(item[field], jpath + "." + field)
    return judgments


def _checked_input(case: Mapping[str, Any]) -> tuple[str, dict[str, Any], set[str]]:
    _keys(case, "case", required=CASE_KEYS)
    for field in ("caseId", "sourceGroup", "split", "purpose", "stageCut"):
        _string(case[field], "case." + field)
    if type(case["anchorCase"]) is not bool:
        raise LabValidationError("case.anchorCase: expected boolean")
    if case["derivedFrom"] is not None:
        _string(case["derivedFrom"], "case.derivedFrom")
    task = case["task"]
    if task not in TASKS:
        raise LabValidationError("case.task: unsupported task")
    value = _object(case["input"], "input")
    required = INPUT_KEYS[task] - ({"previouslySkippedIds"} if task == "D04" else set())
    _keys(value, "input", required=required, allowed=INPUT_KEYS[task])
    _without_answers(value)
    canonical_bytes(value)
    people = _world(value["world"])
    if task == "D02":
        _id(value["actorId"], "input.actorId", people)
        _id(value["protagonistId"], "input.protagonistId", people)
        advance = _keys(value["advance"], "input.advance", required={"inputText", "intentStatus"})
        if advance["inputText"] is not None:
            _string(advance["inputText"], "input.advance.inputText", nonempty=False)
        if advance["intentStatus"] not in ("pending", "consumed", "expired"):
            raise LabValidationError("input.advance.intentStatus: invalid status")
        _members(value["confirmedPrefix"], "input.confirmedPrefix", people)
    elif task in ("D03", "D04"):
        source = _source(value["source"], "input.source", people)
        group = _keys(value["confirmedGroup"], "input.confirmedGroup", required={"members"})
        _members(group["members"], "input.confirmedGroup.members", people)
        _ids(value["alreadyActedIds"], "input.alreadyActedIds", people)
        if task == "D03":
            candidates = _ids(value["candidateIds"], "input.candidateIds", people)
            if set(candidates) != people:
                raise LabValidationError("input.candidateIds: incomplete candidate roster")
            prior = _judgments(value["knownPriorJudgments"], "input.knownPriorJudgments", people)
            if any(item["sourceId"] == source["memberId"] for item in prior):
                raise LabValidationError("input.knownPriorJudgments: current-source future judgment leakage")
            if prior:
                frozen_sources = {member["memberId"] for member in group["members"]
                                  if member.get("actionText", "").strip()}
                if any(item["sourceId"] not in frozen_sources for item in prior):
                    raise LabValidationError("input.knownPriorJudgments: source has no frozen action text")
                if not all(_complete_judgment(item) for item in prior):
                    raise LabValidationError("input.knownPriorJudgments: incomplete or inconsistent prior judgment")
                if not _distinct_judgment_ids(prior):
                    raise LabValidationError("input.knownPriorJudgments: duplicate roll or relation identity")
                # These checks establish a declared frozen source and internal
                # rule/identity consistency only. This input shape has no
                # confirmed-target ledger or service receipt: it cannot prove
                # that a prior relation was actually confirmed by the service.
        else:
            _id(value["memberId"], "input.memberId", people)
            _ids(value.get("previouslySkippedIds", []), "input.previouslySkippedIds", people)
            admission = _keys(value["admission"], "input.admission", required={"eligible", "admitted"})
            if any(type(admission[field]) is not bool for field in admission):
                raise LabValidationError("input.admission: expected booleans")
            _judgments(value["judgments"], "input.judgments", people)
    else:
        group_fields = {"closed", "memberIds", "members", "confirmedTargets", "judgments"}
        group = _keys(value["group"], "input.group", required=group_fields,
                      allowed=group_fields | {"alreadyActedIds"})
        if type(group["closed"]) is not bool:
            raise LabValidationError("input.group.closed: expected boolean")
        _ids(group["memberIds"], "input.group.memberIds", people)
        _ids(group.get("alreadyActedIds", []), "input.group.alreadyActedIds", people)
        _members(group["members"], "input.group.members", people)
        for index, record in enumerate(_array(group["confirmedTargets"], "input.group.confirmedTargets")):
            path = f"input.group.confirmedTargets[{index}]"
            _keys(record, path, required={"sourceId", "targetIds"})
            _id(record["sourceId"], path + ".sourceId", people)
            _ids(record["targetIds"], path + ".targetIds", people)
        _judgments(group["judgments"], "input.group.judgments", people)
    return task, value, people


def build_model_input(case: Mapping[str, Any]) -> dict[str, Any]:
    """Return the entire current-stage input, with no labels/metadata projection.

    Unknown fields are rejected rather than silently dropped.  Call guard_case
    before inference; intentionally damaged guard probes remain inspectable.
    Prior-judgment checks do not certify service confirmation of a relation;
    that provenance is a separate preflight requirement, not a model inference.
    """
    _, value, _ = _checked_input(case)
    return copy.deepcopy(value)


def _complete_judgment(item: Mapping[str, Any]) -> bool:
    return (set(item) == JUDGMENT_KEYS
            and item["ruleVersion"] == "reaction-d20-v1"
            and 1 <= item["value"] <= 20 and item["threshold"] == 11
            and item["passed"] == (item["value"] >= item["threshold"])
            and item["admitted"] == (item["passed"] and item["eligible"]))


def _distinct_judgment_ids(judgments: Sequence[Mapping[str, Any]]) -> bool:
    roll_ids = [item.get("rollId") for item in judgments]
    relations = [(item["sourceId"], item["targetId"]) for item in judgments]
    return len(set(roll_ids)) == len(roll_ids) and len(set(relations)) == len(relations)


def guard_case(case: Mapping[str, Any]) -> dict[str, Any]:
    """Only deterministic call eligibility/completeness; no semantic decisions."""
    try:
        task, value, _ = _checked_input(case)
    except (LabValidationError, TypeError) as exc:
        return {"shouldCall": False, "reason": "invalid_input", "detail": str(exc)}
    if task == "D02":
        text = value["advance"]["inputText"]
        if text is None or (value["advance"]["intentStatus"] == "pending" and not text.strip()):
            return {"shouldCall": False, "reason": "missing_input_text"}
        if value["actorId"] in {member["memberId"] for member in value["confirmedPrefix"]}:
            return {"shouldCall": False, "reason": "already_acted_reuse"}
    elif task in ("D03", "D04"):
        source = value["source"]
        if not source.get("actionText", "").strip():
            return {"shouldCall": False, "reason": "missing_frozen_source_text"}
        frozen = {member["memberId"]: member.get("actionText", "")
                  for member in value["confirmedGroup"]["members"]}
        if frozen.get(source["memberId"]) != source["actionText"]:
            return {"shouldCall": False, "reason": "source_not_frozen_or_mismatch"}
        if any(not text.strip() for text in frozen.values()):
            return {"shouldCall": False, "reason": "missing_frozen_group_text"}
        if task == "D04":
            member_id = value["memberId"]
            if member_id in value["alreadyActedIds"] or frozen.get(member_id, "").strip():
                return {"shouldCall": False, "reason": "already_acted_reuse"}
            if not value["admission"]["eligible"] or not value["admission"]["admitted"]:
                return {"shouldCall": False, "reason": "not_admitted"}
            judgments = value["judgments"]
            if not judgments or not all(_complete_judgment(item) for item in judgments):
                return {"shouldCall": False, "reason": "missing_or_invalid_judgment"}
            if not _distinct_judgment_ids(judgments):
                return {"shouldCall": False, "reason": "duplicate_judgment_identity"}
            current = [item for item in judgments
                       if item["sourceId"] == source["memberId"] and item["targetId"] == member_id]
            if len(current) != 1:
                return {"shouldCall": False, "reason": "missing_or_duplicate_current_judgment"}
            if not current[0]["eligible"] or not current[0]["admitted"]:
                return {"shouldCall": False, "reason": "admission_judgment_mismatch"}
    else:
        group = value["group"]
        if not group["closed"]:
            return {"shouldCall": False, "reason": "group_not_closed"}
        ids = set(group["memberIds"])
        members = group["members"]
        if not ids or {member["memberId"] for member in members} != ids or any(
                not member.get("actionText", "").strip() for member in members):
            return {"shouldCall": False, "reason": "missing_member_action"}
        targets = group["confirmedTargets"]
        sources = [record["sourceId"] for record in targets]
        if set(sources) != ids or len(sources) != len(ids):
            return {"shouldCall": False, "reason": "missing_or_duplicate_confirmed_targets"}
        required = {(record["sourceId"], target) for record in targets for target in record["targetIds"]}
        judgments = group["judgments"]
        observed = [(item["sourceId"], item["targetId"]) for item in judgments]
        if set(observed) != required or len(observed) != len(required):
            return {"shouldCall": False, "reason": "missing_or_duplicate_relation_judgment"}
        if not all(_complete_judgment(item) for item in judgments):
            return {"shouldCall": False, "reason": "missing_or_invalid_judgment"}
        if not _distinct_judgment_ids(judgments):
            return {"shouldCall": False, "reason": "duplicate_judgment_identity"}
        already_acted = set(group.get("alreadyActedIds", []))
        if any(item["targetId"] in already_acted and item["eligible"] for item in judgments):
            return {"shouldCall": False, "reason": "already_acted_eligibility_mismatch"}
        if any(item["admitted"] and item["targetId"] not in ids for item in judgments):
            return {"shouldCall": False, "reason": "admitted_target_missing_from_group"}
    return {"shouldCall": True, "reason": "ready"}


def validate_dataset(input_cases: Sequence[Mapping[str, Any]],
                     reviews: Sequence[Mapping[str, Any]] = ()) -> dict[str, Any]:
    """Validate mechanics/provenance shape, without certifying human truth."""
    problems: list[dict[str, Any]] = []
    cases: dict[str, Mapping[str, Any]] = {}
    groups: dict[str, set[str]] = defaultdict(set)
    anchors: Counter[tuple[str, str]] = Counter()
    tasks: Counter[str] = Counter()
    splits: Counter[str] = Counter()
    guards: Counter[str] = Counter()
    visible_hashes: dict[bytes, str] = {}

    def issue(case_id: Any, path: str, code: str, message: str) -> None:
        problems.append({"caseId": case_id, "path": path, "code": code, "message": message})

    for index, case in enumerate(input_cases):
        case_id = case.get("caseId") if isinstance(case, Mapping) else None
        try:
            task, _, _ = _checked_input(case)
        except (LabValidationError, TypeError) as exc:
            issue(case_id, f"inputs[{index}]", "invalid_case", str(exc))
            continue
        if case_id in cases:
            issue(case_id, "caseId", "duplicate_case", "caseId must be unique")
            continue
        cases[case_id] = case
        visible_hash = hashlib.sha256(canonical_bytes(case["input"])).digest()
        previous_group = visible_hashes.setdefault(visible_hash, case["sourceGroup"])
        if previous_group != case["sourceGroup"]:
            issue(case_id, "sourceGroup", "duplicate_input_across_groups", "identical visible input cannot create a new source group")
        groups[case["sourceGroup"]].add(case["split"])
        if case["anchorCase"]:
            anchors[(case["sourceGroup"], task)] += 1
            if case["derivedFrom"] is not None:
                issue(case_id, "anchorCase", "derived_anchor", "anchor cannot also be a derived case")
        elif case["derivedFrom"] is None:
            issue(case_id, "derivedFrom", "missing_origin", "non-anchor needs derivedFrom")
        tasks[task] += 1
        splits[case["split"]] += 1
        guards[guard_case(case)["reason"]] += 1
    for group, group_splits in groups.items():
        if len(group_splits) != 1:
            issue(None, "sourceGroup", "cross_split_group", f"{group}: source group crosses split")
    for case_id, case in cases.items():
        parent_id = case["derivedFrom"]
        if anchors[(case["sourceGroup"], case["task"])] != 1:
            issue(case_id, "anchorCase", "anchor_count", "each task/source group needs exactly one anchor")
        if parent_id is None:
            continue
        if parent_id not in cases:
            issue(case_id, "derivedFrom", "missing_parent", "derived parent not present")
            continue
        parent = cases[parent_id]
        if parent["sourceGroup"] != case["sourceGroup"]:
            issue(case_id, "derivedFrom", "cross_group_derivation", "derived case changed sourceGroup")
        if parent["split"] != case["split"]:
            issue(case_id, "derivedFrom", "cross_split_derivation", "derived case changed split")
        current: str | None = case_id
        seen: set[str] = set()
        while current is not None and current in cases:
            if current in seen:
                issue(case_id, "derivedFrom", "derivation_cycle", "derivedFrom cycle")
                break
            seen.add(current)
            current = cases[current]["derivedFrom"]

    review_ids: set[str] = set()
    review_states: Counter[str] = Counter()
    coverage: Counter[str] = Counter()
    for index, review in enumerate(reviews):
        case_id = review.get("caseId") if isinstance(review, Mapping) else None
        try:
            _object(review, f"reviews[{index}]")
            _string(case_id, f"reviews[{index}].caseId")
            if case_id in review_ids:
                raise LabValidationError("duplicate review caseId")
            review_ids.add(case_id)
            if case_id not in cases:
                raise LabValidationError("review does not name a valid input case")
            tags = _array(review.get("coverageTags"), f"reviews[{index}].coverageTags")
            for tag in tags:
                _string(tag, f"reviews[{index}].coverageTags")
                coverage[tag] += 1
            state = _string(review.get("humanReview"), f"reviews[{index}].humanReview")
            review_states[state] += 1
            if "draftExpected" not in review:
                raise LabValidationError("review missing draftExpected")
            canonical_bytes(review)
        except (LabValidationError, TypeError) as exc:
            issue(case_id, f"reviews[{index}]", "invalid_review", str(exc))
    for case_id in set(cases) - review_ids:
        issue(case_id, "review", "missing_review_draft", "separate review record missing")
    return {
        "valid": not problems, "problems": problems,
        "summary": {"caseCount": len(input_cases), "validCaseCount": len(cases),
                    "sourceGroupCount": len(groups), "tasks": dict(sorted(tasks.items())),
                    "splitCounts": dict(sorted(splits.items())),
                    "anchorCount": sum(anchors.values()), "guardReasons": dict(sorted(guards.items())),
                    "coverageTags": dict(sorted(coverage.items())),
                    "reviewStateClaims": dict(sorted(review_states.items())),
                    "reviewStatus": "pending_human_review", "sourceIndependence": "unverified",
                    "priorRelationConfirmation": "unverified_without_target_ledger_or_service_receipt",
                    "formalVerdict": "not_evaluated"},
    }


def decode_output(task: str, raw: str, case: Mapping[str, Any]) -> Any:
    """Decode only the task's closed experiment shape; no semantic auto-pass."""
    case_task, value, people = _checked_input(case)
    if task != case_task:
        raise LabValidationError("output task does not match case task")
    guard = guard_case(case)
    if not guard["shouldCall"]:
        raise LabValidationError(f"output for a guarded case: {guard['reason']}")
    _string(raw, "raw", nonempty=True)
    if task == "D04":
        return raw  # Preserve the original UTF-8 text rather than rewriting it.
    result = _parse_json(raw)
    if task == "D02":
        obj = _object(result, "output")
        if obj.get("kind") == "skip":
            _keys(obj, "output", required={"kind"})
        elif obj.get("kind") == "act":
            _keys(obj, "output", required={"kind", "text"})
            _string(obj["text"], "output.text")
        else:
            raise LabValidationError("output.kind: expected act or skip")
    elif task == "D03":
        _keys(result, "output", required={"targets"})
        targets = _array(result["targets"], "output.targets")
        ids: list[str] = []
        for index, target in enumerate(targets):
            _keys(target, f"output.targets[{index}]", required={"targetId"})
            ids.append(_id(target["targetId"], f"output.targets[{index}].targetId", people))
        if len(set(ids)) != len(ids):
            raise LabValidationError("output.targets: duplicate target")
    else:
        _keys(result, "output", required={"results"})
        results = _object(result["results"], "output.results")
        if set(results) != set(value["group"]["memberIds"]):
            raise LabValidationError("output.results: exact group member coverage required")
        for member_id, text in results.items():
            _string(text, "output.results." + member_id)
    return result


def _percentiles(values: Sequence[float]) -> dict[str, Any]:
    if not values:
        return {"n": 0, "p50Ms": None, "p95Ms": None, "maxMs": None}
    ordered = sorted(values)
    return {"n": len(ordered), "p50Ms": statistics.median(ordered),
            "p95Ms": ordered[math.ceil(0.95 * len(ordered)) - 1], "maxMs": ordered[-1]}


def summarize_attempts(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Keep every attempt, including incomplete callers and late engine settle.

    This report cannot sign human semantics or a formal project acceptance.
    Full-request timing remains unverified if only component/scope data exists.
    """
    counts: Counter[str] = Counter()
    elapsed_values: list[float] = []
    scopes: dict[str, list[tuple[Mapping[str, Any], float | None, float]]] = defaultdict(list)
    over_budget: list[int] = []
    missing_timing: list[int] = []
    group_counts: Counter[str] = Counter()
    complete_statuses = {"complete"}
    for index, record in enumerate(records):
        status = record.get("status", "incomplete")
        counts[str(status)] += 1
        group_counts[str(record.get("sourceGroup", "unregistered"))] += 1
        scope = str(record.get("measurementScope", "component"))
        if scope not in {"component", "range_chain", "full_request"}:
            raise LabValidationError(f"attempt {index}: unknown measurementScope")
        default_budget = 500.0 if scope in {"range_chain", "full_request"} else 50.0
        budget = record.get("budgetMs", default_budget)
        if type(budget) not in (int, float) or not math.isfinite(budget) or budget <= 0:
            raise LabValidationError(f"attempt {index}: invalid budgetMs")
        ceiling = 500.0 if scope in {"range_chain", "full_request"} else 50.0
        if budget > ceiling:
            raise LabValidationError(f"attempt {index}: budget exceeds registered scope ceiling")
        measured: list[float] = []
        for field in ("elapsedMs", "settledElapsedMs"):
            value = record.get(field)
            if value is None:
                continue
            if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
                raise LabValidationError(f"attempt {index}: invalid {field}")
            measured.append(float(value))
        elapsed = max(measured) if measured else None
        if elapsed is None:
            missing_timing.append(index)
        else:
            elapsed_values.append(elapsed)
            if elapsed > budget:
                over_budget.append(index)
        scopes[scope].append((record, elapsed, float(budget)))

    scope_reports: dict[str, Any] = {}
    for scope, attempts in sorted(scopes.items()):
        measured = [elapsed for _, elapsed, _ in attempts if elapsed is not None]
        complete = sum(record.get("status") in complete_statuses for record, _, _ in attempts)
        over = sum(elapsed is not None and elapsed > budget for _, elapsed, budget in attempts)
        missing = sum(elapsed is None for _, elapsed, _ in attempts)
        workloads: dict[str, list[tuple[Mapping[str, Any], float | None, float]]] = defaultdict(list)
        for attempt in attempts:
            workload_id = attempt[0].get("workloadId")
            workload_key = workload_id if isinstance(workload_id, str) and workload_id.strip() else "unregistered"
            workloads[workload_key].append(attempt)
        workload_reports: dict[str, Any] = {}
        for workload_id, workload_attempts in sorted(workloads.items()):
            w_complete = sum(record.get("status") in complete_statuses for record, _, _ in workload_attempts)
            w_over = sum(elapsed is not None and elapsed > budget for _, elapsed, budget in workload_attempts)
            w_missing = sum(elapsed is None for _, elapsed, _ in workload_attempts)
            if w_over:
                w_status = "latency_fail"
            elif workload_id == "unregistered" or w_missing or w_complete < 20 or w_complete != len(workload_attempts):
                w_status = "latency_unverified"
            else:
                w_status = "within_observed_budget"
            workload_reports[workload_id] = {
                "attemptCount": len(workload_attempts), "completeCount": w_complete,
                "overBudgetCount": w_over, "missingTimingCount": w_missing,
                **_percentiles([elapsed for _, elapsed, _ in workload_attempts if elapsed is not None]),
                "latencyStatus": w_status,
            }
        status = ("latency_fail" if over else
                  "latency_unverified" if any(report["latencyStatus"] == "latency_unverified"
                                              for report in workload_reports.values()) else
                  "within_observed_budget")
        scope_reports[scope] = {"attemptCount": len(attempts), "completeCount": complete,
                                "overBudgetCount": over, "missingTimingCount": missing,
                                **_percentiles(measured), "latencyStatus": status,
                                "workloads": workload_reports}
    full = scope_reports.get("full_request")
    observed_status = ("latency_fail" if over_budget else
                       "latency_unverified" if missing_timing or not records else
                       "within_observed_budget")
    all_status = ("latency_fail" if over_budget else
                  "latency_unverified" if not scope_reports or any(
                      report["latencyStatus"] == "latency_unverified" for report in scope_reports.values())
                  else "within_observed_budget")
    return {
        "attemptCount": len(records), "completeCount": counts["complete"],
        "failedCount": counts["failed"], "cancelledCount": counts["cancelled"],
        "timeoutCount": counts["timeout"], "staleCount": counts["stale"],
        "incompleteCount": sum(n for status, n in counts.items()
                               if status not in {"complete", "failed", "cancelled", "timeout", "stale", "guarded"}),
        "guardedCount": counts["guarded"], "statusCounts": dict(sorted(counts.items())),
        "timing": _percentiles(elapsed_values), "overBudgetAttemptIndices": over_budget,
        "missingTimingAttemptIndices": missing_timing,
        "observedBudgetStatus": observed_status, "scopeSummaries": scope_reports,
        "latencyStatus": all_status,
        "fullRequestLatencyStatus": full["latencyStatus"] if full else "latency_unverified",
        "groupScore": {group: {"attemptCount": n, "status": "pending_human_review"}
                       for group, n in sorted(group_counts.items())},
        "semanticStatus": "pending_human_review", "formalVerdict": "not_evaluated",
    }
