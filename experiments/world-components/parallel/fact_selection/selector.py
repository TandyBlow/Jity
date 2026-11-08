"""Selection rules and scoring for the attention-selection v2 experiment.

This module is experiment code only: it does not parse player text, call a
model, touch the backend, or change the production N2 interface. Every rule
receives a frozen case (facts, authorization, prior narration, attention
targets/focus) and returns an ordered list of fact ids.

Four rule arms are compared with the hand-written selection:

* no_attention: all must + every eligible optional, ignoring attention.
* lexical: R-attention-v1 exactly as frozen in v1, matching surface target
  strings against name/text/goal/from/to/at/scope.
* lexical_content: the same rule with at/scope removed from the match fields;
  this is a diagnostic variant, not the v1 rule.
* semantic: an intent-aware rule with a hand-provided focus (entity and
  attribute). The focus is an experimental input, not a parser output; this
  arm is an upper bound on selection given attention, not a deployable parser.

The pass metric is deliberately not the D1 `mustPrecision` (must hits /
all selected). That metric penalises any selected optional fact, which is the
subject of this experiment. The new metric keeps the hard constraints
(must recall, no forbidden/uncertain, no prior repeat) and adds optional
target quality (target selected, no unrelated optional). `related` optionals
are explicitly allowed; `strict` additionally requires that nothing beyond
the target is selected. The legacy mustPrecision is still reported, but only
as a diagnostic.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

CASE_PATH = Path(__file__).with_name("cases-v2.json")

ATTENTION_FIELDS = ("name", "text", "goal", "from", "to", "at", "scope")
CONTENT_FIELDS = ("name", "text", "goal", "from", "to")
EXCLUDED_KINDS = {"time", "no_change"}
ALLOWED_AUTHORIZATION = {"must", "optional"}
KIND_BY_ATTRIBUTE = {
    "personality": {"personality_changed"},
    "task": {"task_achieved"},
    "appearance": {"appearance_changed"},
    "sanity": {"sanity_changed"},
    "position": {"moved", "positioned_at"},
    "movement": {"moved"},
}


def load_cases(path: str | Path = CASE_PATH) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def facts_by_id(case: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {fact["factId"]: fact for fact in case["facts"]}


def must_ids(case: dict[str, Any]) -> set[str]:
    return {fact["factId"] for fact in case["facts"] if fact["authorization"] == "must"}


def eligible(fact: dict[str, Any], narrated: set[str]) -> bool:
    return (fact["authorization"] in ALLOWED_AUTHORIZATION
            and fact["factId"] not in narrated
            and fact["kind"] not in EXCLUDED_KINDS)


def in_fact_order(case: dict[str, Any], ids: Iterable[str]) -> list[str]:
    wanted = set(ids)
    known = {fact["factId"] for fact in case["facts"]}
    unknown = wanted - known
    if unknown:
        raise ValueError(f"selected ids not in case {case['caseId']}: {sorted(unknown)}")
    return [fact["factId"] for fact in case["facts"] if fact["factId"] in wanted]


def select_no_attention(case: dict[str, Any]) -> list[str]:
    """Keep all must; keep every eligible optional; read no attention at all."""
    narrated = set(case["alreadyNarratedFactIds"])
    out = []
    for fact in case["facts"]:
        if fact["authorization"] == "must":
            out.append(fact["factId"])
        elif fact["authorization"] == "optional" and eligible(fact, narrated):
            out.append(fact["factId"])
    return out


def _select_lexical(case: dict[str, Any], fields: tuple[str, ...]) -> list[str]:
    narrated = set(case["alreadyNarratedFactIds"])
    targets = [str(t) for t in case.get("attentionTargets", [])]
    out = []
    for fact in case["facts"]:
        if fact["authorization"] == "must":
            out.append(fact["factId"])
            continue
        if fact["authorization"] != "optional" or not eligible(fact, narrated):
            continue
        text = " ".join(str(fact.get(field)) for field in fields
                        if field in fact and fact[field] is not None)
        if any(target in text for target in targets):
            out.append(fact["factId"])
    return out


def select_lexical(case: dict[str, Any]) -> list[str]:
    """The v1 R-attention-v1 rule: all fields, including at and scope."""
    return _select_lexical(case, ATTENTION_FIELDS)


def select_lexical_content(case: dict[str, Any]) -> list[str]:
    """Diagnostic: drop at/scope so a shared location is not content evidence."""
    return _select_lexical(case, CONTENT_FIELDS)


def _text(fact: dict[str, Any], field: str) -> str:
    value = fact.get(field)
    return "" if value is None else str(value)


def matches_focus(fact: dict[str, Any], focus: dict[str, Any]) -> bool:
    attribute = focus.get("attribute")
    if fact["kind"] not in KIND_BY_ATTRIBUTE.get(attribute, set()):
        return False
    entity_match = (fact.get("entityId") == focus.get("entityId")
                    or fact.get("name") == focus.get("name"))
    if attribute == "appearance":
        obj = str(focus.get("objectText") or "")
        object_match = bool(obj) and (obj in _text(fact, "name") or obj in _text(fact, "text"))
        if obj:
            return entity_match and object_match
        return entity_match
    return entity_match


def select_semantic(case: dict[str, Any]) -> list[str]:
    """Intent-aware rule with hand-provided focus; no text parsing."""
    narrated = set(case["alreadyNarratedFactIds"])
    focus = case["focus"]
    out = []
    for fact in case["facts"]:
        if fact["authorization"] == "must":
            out.append(fact["factId"])
        elif fact["authorization"] == "optional" and eligible(fact, narrated) and matches_focus(fact, focus):
            out.append(fact["factId"])
    return out


ARMS = {
    "manual": lambda case: case["manualSelectedFactIds"],
    "no_attention": select_no_attention,
    "lexical": select_lexical,
    "lexical_content": select_lexical_content,
    "semantic": select_semantic,
}


def evaluate(case: dict[str, Any], selected: Iterable[str]) -> dict[str, Any]:
    facts = facts_by_id(case)
    selected_set = set(selected)
    must = must_ids(case)
    optional = selected_set - must
    target = set(case.get("targetOptionalFactIds", []))
    related = set(case.get("relatedOptionalFactIds", []))
    missing_must = sorted(must - selected_set)
    forbidden = sorted(fid for fid in selected_set
                       if facts[fid]["authorization"] == "forbidden")
    uncertain = sorted(fid for fid in selected_set
                       if facts[fid]["authorization"] == "uncertain")
    prior = sorted(fid for fid in selected_set
                   if fid in set(case["alreadyNarratedFactIds"]))
    unrelated = sorted(optional - target - related)
    related_selected = sorted(optional & related)
    target_selected = target <= selected_set
    hard_pass = not missing_must and not forbidden and not uncertain and not prior
    lenient_pass = hard_pass and target_selected and not unrelated
    strict_pass = lenient_pass and set(optional) == target
    precision = len(must & selected_set) / len(selected_set) if selected_set else None
    target_recall = (len(target & selected_set) / len(target)) if target else 1.0
    acceptable_precision = (len(optional & (target | related)) / len(optional)) if optional else 1.0
    return {
        "selected": in_fact_order(case, selected_set),
        "hardPass": hard_pass,
        "lenientPass": lenient_pass,
        "strictPass": strict_pass,
        "manualEqual": selected_set == set(case["manualSelectedFactIds"]),
        "missingMust": missing_must,
        "forbiddenSelected": forbidden,
        "uncertainSelected": uncertain,
        "priorSelected": prior,
        "targetSelected": target_selected,
        "relatedSelected": related_selected,
        "unrelatedSelected": unrelated,
        "mustPrecision": precision,
        "legacyD1Pass": precision is not None and precision >= 0.85,
        "targetRecall": target_recall,
        "acceptableOptionalPrecision": acceptable_precision,
        "selectedCount": len(selected_set),
        "optionalCount": len(optional),
    }


def run_all(cases: dict[str, Any]) -> dict[str, Any]:
    results = []
    for case in cases["cases"]:
        row = {"caseId": case["caseId"], "groupId": case["groupId"], "origin": case["origin"],
               "attentionOrigin": case["attentionOrigin"], "arms": {}}
        for name, rule in ARMS.items():
            selected = rule(case)
            row["arms"][name] = evaluate(case, selected)
        results.append(row)
    return {"protocol": cases["protocol"], "cases": results,
            "summary": summarize(cases, results)}


def summarize(cases: dict[str, Any], results: list[dict[str, Any]]) -> dict[str, Any]:
    groups = {case["caseId"]: case["groupId"] for case in cases["cases"]}
    out = {}
    for arm in ARMS:
        rows = [(groups[row["caseId"]], row["arms"][arm]) for row in results]
        summary = {}
        for label, subset in (("all", rows),
                              ("controlled", [item for item in rows if item[0] != "R"]),
                              ("coverage", [item for item in rows if item[0] == "R"])):
            cells = [cell for _, cell in subset]
            summary[label] = {
                "n": len(cells),
                "hardPass": sum(1 for cell in cells if cell["hardPass"]),
                "lenientPass": sum(1 for cell in cells if cell["lenientPass"]),
                "strictPass": sum(1 for cell in cells if cell["strictPass"]),
                "manualEqual": sum(1 for cell in cells if cell["manualEqual"]),
                "legacyD1Pass": sum(1 for cell in cells if cell["legacyD1Pass"]),
                "mustPrecisionMean": (sum(cell["mustPrecision"] for cell in cells
                                          if cell["mustPrecision"] is not None)
                                       / len([cell for cell in cells if cell["mustPrecision"] is not None])
                                       if any(cell["mustPrecision"] is not None for cell in cells) else None),
                "unrelatedSelected": sum(len(cell["unrelatedSelected"]) for cell in cells),
                "relatedSelected": sum(len(cell["relatedSelected"]) for cell in cells),
            }
        by_group = {}
        for group in sorted(set(groups.values())):
            cells = [cell for g, cell in rows if g == group]
            by_group[group] = {
                "n": len(cells),
                "lenientPass": sum(1 for cell in cells if cell["lenientPass"]),
                "strictPass": sum(1 for cell in cells if cell["strictPass"]),
                "manualEqual": sum(1 for cell in cells if cell["manualEqual"]),
            }
        summary["byGroup"] = by_group
        out[arm] = summary
    return out
