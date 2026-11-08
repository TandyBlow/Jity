"""Extract auditable, ungraded delayed probes from a frozen story branch.

This module does no semantic inference. Automatic last-mention detection is a
conservative literal/alias scan and is always marked for human review. Gold and
source quotations never enter the public probe submitted to a context builder.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json


class ProbeError(ValueError):
    """A replay history, annotation, or probe is not internally consistent."""


_COLLECTIONS = (
    ("world_fact", "world_facts_upserted"),
    ("item", "items_upserted"),
    ("item", "items_removed"),
    ("npc", "npcs_upserted"),
    ("quest", "quests_upserted"),
)
_OUTPUT_COLLECTIONS = (
    ("item", "items_gained"), ("item", "items_lost"),
    ("npc", "npcs_encountered"), ("quest", "quests_updated"),
)
_FIELDS = ("description", "notes", "current_location", "location", "relationship", "objective", "status")
_LABELS = {
    "description": "具体说明", "notes": "记录的备注", "current_location": "位置",
    "location": "位置", "relationship": "关系", "objective": "目标", "status": "状态",
}
_GENERIC_VALUES = {
    "known", "suspected", "resolved", "active", "completed", "failed", "paused",
    "present", "following", "away", "unknown", "owned", "lost", "observed",
    "consumed", "destroyed", "discarded", "持有", "拥有", "未知", "在场", "死亡",
}
_PUBLIC_FIELDS = {
    "id", "fact_id", "kind", "question", "source_turn", "source_turn_id", "delay",
    "checkpoint_turn", "checkpoint_turn_id", "branch_id", "history_fingerprint",
    "mention_detection", "review_required", "answer_status",
}


def _digest(value) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _history(dataset: dict) -> list[dict]:
    if not isinstance(dataset, dict) or not isinstance(dataset.get("turns"), list):
        raise ProbeError("dataset.turns must be a list")
    turns = dataset["turns"]
    ids = set()
    for number, record in enumerate(turns, 1):
        if not isinstance(record, dict) or type(record.get("turn")) is not int or record["turn"] != number:
            raise ProbeError("Replay turns must start at 1 and remain consecutive")
        if "turn_id" not in record or record["turn_id"] is None:
            raise ProbeError("Every replay turn needs its original turn_id")
        identifier = str(record["turn_id"])
        if identifier in ids:
            raise ProbeError("Original turn_id cannot repeat within one branch")
        ids.add(identifier)
        if not isinstance(record.get("output"), dict):
            raise ProbeError("Every replay turn needs its recorded output object")
    return turns


def _entries(record: dict):
    output = record["output"]
    updates = output.get("memory_updates") or {}
    if not isinstance(updates, dict):
        updates = {}
    for kind, key in _COLLECTIONS:
        for index, item in enumerate(updates.get(key) or []):
            if isinstance(item, dict):
                yield kind, item, "output.memory_updates.%s[%s]" % (key, index)
    for kind, key in _OUTPUT_COLLECTIONS:
        for index, item in enumerate(output.get(key) or []):
            if isinstance(item, dict):
                yield kind, item, "output.%s[%s]" % (key, index)


def _string_leaves(value, path: str):
    """Yield every string value with its exact path, excluding object keys."""
    if isinstance(value, str):
        if value.strip():
            yield {"channel": path, "text": value}
    elif isinstance(value, dict):
        for key, child in value.items():
            child_path = (path + "." + key if isinstance(key, str) and key.isidentifier()
                          else path + "[" + json.dumps(key, ensure_ascii=False) + "]")
            yield from _string_leaves(child, child_path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _string_leaves(child, "%s[%s]" % (path, index))


def _public_texts(record: dict) -> list[dict]:
    """Scan all published output strings and action, never inherited state.

    Options, roll stakes, scene prompts, location fields, memory-update text and
    future output extensions can all explicitly repeat a fact. A field whitelist
    would incorrectly lengthen a fact's delay when one of those paths rementions
    it. Exact leaf paths also make each detected match independently auditable.
    """
    return [*_string_leaves(record.get("player_action", ""), "player_action"),
            *_string_leaves(record["output"], "output")]


def _collect_facts(turns: list[dict]) -> dict:
    facts = {}
    for record in turns:
        # Top-level compatibility fields and memory_updates can duplicate the
        # same disclosure. The explicit memory_updates version takes priority.
        seen = set()
        for kind, item, path in _entries(record):
            name = item.get("name")
            if not isinstance(name, str) or not name.strip():
                continue
            for field in _FIELDS:
                value = item.get(field)
                if not isinstance(value, str) or not value.strip():
                    continue
                identity = (kind, name.strip(), field)
                if identity in seen:
                    continue
                seen.add(identity)
                fact_id = "fact-" + _digest(identity)[:20]
                fact = facts.setdefault(fact_id, {
                    "fact_id": fact_id, "kind": kind, "name": name.strip(), "field": field,
                    "versions": [], "aliases": [], "first_disclosed_turn": record["turn"],
                })
                for alias in item.get("aliases") or []:
                    if isinstance(alias, str) and len(alias.strip()) >= 2 and alias.strip() not in fact["aliases"]:
                        fact["aliases"].append(alias.strip())
                fact["versions"].append({
                    "turn": record["turn"], "turn_id": record["turn_id"], "value": value.strip(),
                    "aliases": [a.strip() for a in (item.get("aliases") or [])
                                if isinstance(a, str) and len(a.strip()) >= 2],
                    "evidence": {"channel": path + "." + field, "quote": value, "turn": record["turn"]},
                })
    texts = {r["turn"]: _public_texts(r) for r in turns}
    for fact in facts.values():
        mentions = []
        evidence = []
        for record in turns:
            turn = record["turn"]
            known = [v for v in fact["versions"] if v["turn"] <= turn]
            if not known:
                continue  # Future annotations are not evidence of earlier knowledge.
            needles = {fact["name"]}
            needles.update(alias for version in known for alias in version["aliases"])
            needles.update(v["value"] for v in known if len(v["value"]) >= 2 and v["value"] not in _GENERIC_VALUES)
            found = []
            for part in texts[turn]:
                matches = sorted(needle for needle in needles if needle and needle in part["text"])
                if matches:
                    found.append({"turn": turn, "channel": part["channel"], "matches": matches,
                                  "quote": part["text"]})
            if found or any(v["turn"] == turn for v in fact["versions"]):
                mentions.append(turn)
                evidence.extend(found)
        fact["literal_mention_turns"] = mentions
        fact["literal_mention_evidence"] = evidence
    return facts


def _annotation_index(annotations, facts: dict, turns: list[dict]) -> dict:
    if annotations is None:
        return {}
    if not isinstance(annotations, list):
        raise ProbeError("annotations must be a list")
    result = {}
    public = {r["turn"]: _public_texts(r) for r in turns}
    for annotation in annotations:
        if not isinstance(annotation, dict):
            raise ProbeError("Each annotation must be an object")
        allowed = {"fact_id", "mention_turns", "reviewed_through_turn", "reviewer", "evidence"}
        if set(annotation) - allowed:
            raise ProbeError("Unknown annotation fields")
        fact_id = annotation.get("fact_id")
        if fact_id not in facts or fact_id in result:
            raise ProbeError("Annotation fact_id must exist and be unique")
        through = annotation.get("reviewed_through_turn")
        if type(through) is not int or not 1 <= through <= len(turns):
            raise ProbeError("reviewed_through_turn is outside the replay history")
        reviewer = annotation.get("reviewer")
        if not isinstance(reviewer, str) or not reviewer.strip():
            raise ProbeError("Human-reviewed annotations require a reviewer")
        mentions = annotation.get("mention_turns")
        if (not isinstance(mentions, list) or not mentions
                or any(type(t) is not int or not 1 <= t <= through for t in mentions)
                or mentions != sorted(set(mentions))):
            raise ProbeError("mention_turns must be sorted, unique, and within the reviewed range")
        automatic = {t for t in facts[fact_id]["literal_mention_turns"] if t <= through}
        if not automatic.issubset(mentions):
            raise ProbeError("An annotation cannot erase an observed literal remention")
        if any(t < facts[fact_id]["first_disclosed_turn"] for t in mentions):
            raise ProbeError("A mention cannot precede this fact's first recorded disclosure")
        evidence = annotation.get("evidence", [])
        if not isinstance(evidence, list):
            raise ProbeError("Annotation evidence must be a list")
        supported = set()
        for item in evidence:
            if not isinstance(item, dict) or set(item) != {"turn", "channel", "quote"}:
                raise ProbeError("Annotation evidence needs turn, channel, and quote")
            turn, quote = item.get("turn"), item.get("quote")
            if type(turn) is not int or turn not in mentions or not isinstance(quote, str) or not quote.strip():
                raise ProbeError("Annotation evidence must quote one of its mention turns")
            if not any(p["channel"] == item["channel"] and quote in p["text"] for p in public[turn]):
                raise ProbeError("Annotation quotation was not found in that public turn")
            supported.add(turn)
        if not (set(mentions) - automatic).issubset(supported):
            raise ProbeError("Additional semantic mentions require an exact source quotation")
        result[fact_id] = deepcopy(annotation)
    return result


def _mentions(fact: dict, annotation: dict | None) -> list[int]:
    return sorted(set(fact["literal_mention_turns"]) | set(annotation["mention_turns"] if annotation else []))


def _question(fact: dict, kind: str) -> str:
    label = _LABELS[fact["field"]]
    if kind == "recall":
        return "根据此前剧情，请回忆“%s”的%s；无法确定时说明不知道。" % (fact["name"], label)
    return "下一步行动需要用到“%s”的%s，请依据此前已知事实作出决定；信息不足时先请求补充。" % (fact["name"], label)


def extract_probes(dataset: dict, delays=(10, 20, 40), annotations=None) -> dict:
    """Return separate public probes, private gold, and reviewable candidates.

    ``annotations`` is an optional list of human-authored records with fact_id,
    mention_turns, reviewed_through_turn, reviewer, and evidence quotations for
    semantic mentions that the literal detector missed. It can add mentions,
    but cannot silently remove a known literal match. All unreviewed probes are
    candidates, never claimed as semantically verified evaluation samples.
    """
    turns = _history(dataset)
    if (not isinstance(delays, (tuple, list)) or not delays
            or any(type(d) is not int or d < 1 for d in delays) or len(delays) != len(set(delays))):
        raise ProbeError("delays must be distinct positive integers")
    facts = _collect_facts(turns)
    annotation_map = _annotation_index(annotations, facts, turns)
    fingerprint = _digest(dataset)
    probes, gold, candidates = [], [], []
    counts = {str(d): 0 for d in sorted(delays)}
    rejected_leading_questions = 0
    for fact_id, fact in sorted(facts.items()):
        annotation = annotation_map.get(fact_id)
        mentions = _mentions(fact, annotation)
        candidate = deepcopy(fact)
        candidate.update(mention_turns=mentions, review_required=annotation is None,
                         annotation=deepcopy(annotation), probe_ids=[])
        for source_turn in mentions:
            for delay in sorted(delays):
                checkpoint = source_turn + delay
                if checkpoint > len(turns) or any(source_turn < t <= checkpoint for t in mentions):
                    continue
                versions = [v for v in fact["versions"] if v["turn"] <= checkpoint]
                if not versions:
                    continue
                expected = versions[-1]
                reviewed = annotation is not None and annotation["reviewed_through_turn"] >= checkpoint
                for kind in ("recall", "action"):
                    question = _question(fact, kind)
                    if expected["value"] in question:
                        rejected_leading_questions += 1
                        continue
                    identity = [fingerprint, fact_id, source_turn, checkpoint, kind]
                    probe_id = "probe-" + _digest(identity)[:24]
                    probe = {
                        "id": probe_id, "fact_id": fact_id, "kind": kind, "question": question,
                        "source_turn": source_turn, "source_turn_id": turns[source_turn - 1]["turn_id"],
                        "delay": delay, "checkpoint_turn": checkpoint,
                        "checkpoint_turn_id": turns[checkpoint - 1]["turn_id"],
                        "branch_id": "branch-" + _digest(identity)[:24],
                        "history_fingerprint": fingerprint,
                        "mention_detection": "human_reviewed_literal_and_semantic" if reviewed else "literal_alias",
                        "review_required": not reviewed, "answer_status": "not_queried",
                    }
                    probes.append(probe)
                    gold.append({
                        "probe_id": probe_id, "fact_id": fact_id, "expected_value": expected["value"],
                        "value_disclosed_turn": expected["turn"], "evidence": deepcopy(expected["evidence"]),
                        "last_mention_turn": source_turn,
                        "mention_turns_through_checkpoint": [t for t in mentions if t <= checkpoint],
                        "review_required": not reviewed,
                    })
                    candidate["probe_ids"].append(probe_id)
                    counts[str(delay)] += 1
        candidates.append(candidate)
    probes.sort(key=lambda p: (p["checkpoint_turn"], p["fact_id"], p["kind"], p["delay"]))
    order = {p["id"]: i for i, p in enumerate(probes)}
    gold.sort(key=lambda g: order[g["probe_id"]])
    document = {
        "schema_version": 1, "kind": "jity_replay_probes", "history_fingerprint": fingerprint,
        "probes": probes, "gold": gold, "candidates": candidates,
        "coverage": {"history_turns": len(turns), "facts": len(facts), "probes": len(probes),
                     "by_delay": counts, "review_required": sum(p["review_required"] for p in probes),
                     "human_reviewed": sum(not p["review_required"] for p in probes),
                     "leading_questions_excluded": rejected_leading_questions},
        "limitations": [
            "Automatic mention detection matches literal names, aliases and recorded values; it is not semantic review.",
            "Generated questions use authored fact names and require review for answer leakage, ambiguity, and usefulness.",
            "Carried-forward state snapshots are excluded from mention counting.",
            "Probes have not been answered or scored; every branch starts from its frozen checkpoint.",
        ],
    }
    return document


def validate_probes(dataset: dict, probes: list[dict], gold: list[dict], annotations=None) -> dict:
    """Validate disclosure time, last mention, answer separation and isolation."""
    turns = _history(dataset)
    facts = _collect_facts(turns)
    annotation_map = _annotation_index(annotations, facts, turns)
    fingerprint = _digest(dataset)
    if not isinstance(probes, list) or not isinstance(gold, list):
        raise ProbeError("probes and gold must be separate lists")
    answers = {}
    for record in gold:
        if not isinstance(record, dict) or not isinstance(record.get("probe_id"), str) or record["probe_id"] in answers:
            raise ProbeError("Every gold record needs a unique probe_id")
        answers[record["probe_id"]] = record
    identifiers, branches = set(), set()
    for probe in probes:
        if not isinstance(probe, dict) or set(probe) != _PUBLIC_FIELDS:
            raise ProbeError("Public probe contains missing or forbidden fields; gold/evidence must stay separate")
        identifier, branch = probe["id"], probe["branch_id"]
        if not isinstance(identifier, str) or identifier in identifiers or not isinstance(branch, str) or branch in branches:
            raise ProbeError("Probe IDs and branch IDs must each be unique")
        identifiers.add(identifier)
        branches.add(branch)
        fact = facts.get(probe["fact_id"])
        if fact is None:
            raise ProbeError("Probe references an unknown or future-only fact")
        source, checkpoint, delay = probe["source_turn"], probe["checkpoint_turn"], probe["delay"]
        if (any(type(v) is not int for v in (source, checkpoint, delay)) or delay < 1
                or not 1 <= source < checkpoint <= len(turns) or source + delay != checkpoint):
            raise ProbeError("source_turn + delay must equal a valid later checkpoint")
        if (probe["source_turn_id"] != turns[source - 1]["turn_id"]
                or probe["checkpoint_turn_id"] != turns[checkpoint - 1]["turn_id"]
                or probe["history_fingerprint"] != fingerprint):
            raise ProbeError("Probe checkpoint identity does not match the frozen history")
        annotation = annotation_map.get(probe["fact_id"])
        mentions = [t for t in _mentions(fact, annotation) if t <= checkpoint]
        if not mentions or mentions[-1] != source:
            raise ProbeError("source_turn is not the last observed mention before the checkpoint")
        versions = [v for v in fact["versions"] if v["turn"] <= checkpoint]
        if not versions:
            raise ProbeError("Probe cannot use a fact disclosed after its checkpoint")
        answer = answers.get(identifier)
        expected = versions[-1]
        if (not answer or answer.get("fact_id") != probe["fact_id"]
                or answer.get("expected_value") != expected["value"]
                or answer.get("value_disclosed_turn") != expected["turn"]
                or answer.get("evidence") != expected["evidence"]
                or answer.get("last_mention_turn") != source
                or answer.get("mention_turns_through_checkpoint") != mentions):
            raise ProbeError("Gold must match the recorded value and evidence available at the checkpoint")
        question = probe["question"]
        if not isinstance(question, str) or not question.strip() or expected["value"] in question:
            raise ProbeError("A probe question cannot disclose its expected answer")
        if probe["kind"] not in {"recall", "action"} or probe["answer_status"] != "not_queried":
            raise ProbeError("Probe must be an unqueried independent recall/action branch")
        reviewed = annotation is not None and annotation["reviewed_through_turn"] >= checkpoint
        detection = "human_reviewed_literal_and_semantic" if reviewed else "literal_alias"
        if (type(probe["review_required"]) is not bool or probe["review_required"] != (not reviewed)
                or probe["mention_detection"] != detection or answer.get("review_required") != (not reviewed)):
            raise ProbeError("Review status cannot claim semantic confirmation without a covering annotation")
    if set(answers) != identifiers:
        raise ProbeError("Gold must cover every probe exactly once, with no extra answers")
    return {"probes": len(probes), "independent_branches": len(branches),
            "review_required": sum(p["review_required"] for p in probes)}
