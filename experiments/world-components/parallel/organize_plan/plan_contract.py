# -*- coding: utf-8 -*-
"""c3 N3 organization-plan contract and validator.

The plan is the ONLY thing N3 hands to N4. It carries no prose, no verbs, no
punctuation. The schema is frozen here, before any run:

    {
      "groups": [
        {"facts": ["f0", "f1"], "links": ["continuation"]},
        {"facts": ["f2"], "links": []}
      ],
      "refs": {"f0": "name", "f1": "omit", "f2": "name"},
      "edges": [{"from": "f2", "to": "f3", "type": "before", "mode": "required"}]
    }

Meaning (fixed by design/world-engine-reports/components/organize-before-wording-v1.md):
- `groups` partition the selected facts in input order into contiguous chunks.
  A chunk is one expression unit. `links[i]` joins `facts[i]` and `facts[i+1]`
  INSIDE the chunk:
    * `continuation` = same entity combined into one expression;
    * `parallel`     = different entities juxtaposed, NO temporal claim.
  Neither value means "then", "at the same time", or "because".
- `refs` gives, per fact, how the entity is addressed:
    * `name` = write the display name;
    * `omit` = leave the subject out (承前省略). It is licensed only when the
      SAME entity was named earlier in the SAME group and that named entity is
      the nearest preceding named entity (no intervening other name), and the
      display name is unique across the selected set.
- `edges` carries ONLY relations that the fixture already authorized. The
  validator rejects invented, reversed, duplicated or missing-authorized
  edges. `mode=required|optional` says whether N4 must express it; it does not
  create a relation.
- Any other key, any free-text string, any other link/ref/edge enum value is
  rejected. That is how "do not add time or causal relations" is enforced at
  the plan layer: the schema has no way to say it.

The validator is deliberately strict. It answers exactly one question:
"is this plan a legal organization of THIS selected fact set under THIS
authorization record?" It does not score prose and does not call a model.
"""

from __future__ import annotations

from typing import Any, Iterable

PLAN_KEYS = {"groups", "refs", "edges"}
GROUP_KEYS = {"facts", "links"}
EDGE_KEYS = {"from", "to", "type", "mode"}

LINK_VALUES = {"continuation", "parallel"}
REF_VALUES = {"name", "omit"}
EDGE_TYPES = {"before"}
EDGE_MODES = {"required", "optional"}

# Fact kinds that name one entity and can therefore take a ref/link. Time and
# global no-change facts have no entity and are outside this round's schema;
# they are refused instead of being silently forced into a group.
ENTITY_KINDS = {
    "appearance_changed",
    "outcome",
    "moved",
    "positioned_at",
    "task_achieved",
    "personality_changed",
    "sanity_changed",
    "position_relative",
}
NON_ENTITY_KINDS = {"time", "no_change"}

# Connector words that would turn an expression plan into a temporal/causal
# claim. They are illegal anywhere in a plan value (values are enums anyway;
# this catches a future free-text field someone tries to smuggle in).
BANNED_SUBSTRINGS = (
    "随后", "同时", "与此同时", "然后", "接着", "之后", "之前",
    "因此", "因为", "所以", "导致", "于是",
)

# Error codes are part of the contract: tests assert on these strings.
E_PLAN_NOT_OBJECT = "plan-not-object"
E_UNKNOWN_FIELD = "unknown-field"
E_GROUPS_EMPTY = "groups-empty"
E_GROUP_NOT_OBJECT = "group-not-object"
E_GROUP_FACTS_EMPTY = "group-facts-empty"
E_FACTS_NOT_LIST = "facts-not-list"
E_LINK_COUNT = "link-count"
E_LINK_VALUE = "link-value"
E_FACT_ID_SHAPE = "fact-id-shape"
E_FACT_UNKNOWN = "fact-unknown"
E_FACT_DUPLICATE = "fact-duplicate"
E_FACT_MISSING = "fact-missing"
E_ORDER = "order-changed"
E_UNSUPPORTED_FACT_KIND = "unsupported-fact-kind"
E_LINK_ENTITY_MISMATCH = "link-entity-mismatch"
E_REFS_NOT_OBJECT = "refs-not-object"
E_REF_MISSING = "ref-missing"
E_REF_UNKNOWN = "ref-unknown"
E_REF_VALUE = "ref-value"
E_REF_FIRST_MENTION_OMIT = "ref-first-mention-omit"
E_REF_OMIT_WITHOUT_NAME = "ref-omit-without-name"
E_REF_CROSS_GROUP_OMIT = "ref-cross-group-omit"
E_REF_AMBIGUOUS_OMIT = "ref-ambiguous-omit"
E_REF_AMBIGUOUS_NAME = "ref-ambiguous-name"
E_EDGES_NOT_LIST = "edges-not-list"
E_EDGE_NOT_OBJECT = "edge-not-object"
E_EDGE_ENDPOINT_UNKNOWN = "edge-endpoint-unknown"
E_EDGE_SELF = "edge-self"
E_EDGE_ORDER = "edge-order"
E_EDGE_TYPE = "edge-type"
E_EDGE_MODE = "edge-mode"
E_EDGE_UNAUTHORIZED = "edge-unauthorized"
E_EDGE_DUPLICATE = "edge-duplicate"
E_EDGE_MISSING = "edge-missing-authorized"
E_EDGE_TARGET_NOT_ISOLATED = "edge-target-not-isolated"
E_EDGE_SAME_GROUP = "edge-same-group"
E_PLAN_FREE_TEXT = "plan-free-text"


def _err(errors: list[dict], code: str, detail: str, **extra: Any) -> None:
    item = {"code": code, "detail": detail}
    item.update(extra)
    errors.append(item)


def _is_fact_id(value: Any) -> bool:
    return isinstance(value, str) and len(value) >= 2 and value[0] == "f" and value[1:].isdigit()


def _walk_strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from _walk_strings(item)
    elif isinstance(value, dict):
        for item in value.values():
            yield from _walk_strings(item)


def _fact_index(facts: list[dict]) -> dict[str, int]:
    return {str(f.get("factId")): i for i, f in enumerate(facts)}


def _display_name(fact: dict) -> str | None:
    name = fact.get("name")
    return name if isinstance(name, str) and name else None


def validate_plan(
    facts: list[dict],
    authorized_edges: list[dict],
    plan: Any,
    *,
    require_all_authorized: bool = True,
) -> dict:
    """Validate one plan against one selected fact set + authorization record.

    `facts`: ordered selected facts. Required keys: factId, kind, entityId,
             name. Extra world fields are ignored (the plan never sees them).
    `authorized_edges`: list of {"from": "f2", "to": "f3", ...}. Only edges
             whose BOTH endpoints are in the selected set are applicable.
    Returns {"ok": bool, "errors": [...], "stats": {...}}.
    """
    errors: list[dict] = []
    stats: dict[str, Any] = {
        "facts": len(facts),
        "groups": 0,
        "mergedGroups": 0,
        "omittedRefs": 0,
        "edges": 0,
    }

    if not isinstance(plan, dict):
        _err(errors, E_PLAN_NOT_OBJECT, f"plan is {type(plan).__name__}, expected object")
        return {"ok": False, "errors": errors, "stats": stats}

    for key in plan:
        if key not in PLAN_KEYS:
            _err(errors, E_UNKNOWN_FIELD, f"plan key {key!r} is not in {sorted(PLAN_KEYS)}", field=key)

    # Any Chinese prose anywhere is a schema escape attempt. Values are only
    # factIds and the closed enum tokens; nothing else may be a string.
    allowed_strings = set(LINK_VALUES) | set(REF_VALUES) | set(EDGE_TYPES) | set(EDGE_MODES)
    for s in _walk_strings(plan):
        if _is_fact_id(s) or s in allowed_strings:
            continue
        # Only prose-looking strings are reported here; a bare token that is
        # not an enum is caught by the link/ref/edge checks with a precise code.
        prose = any("\u4e00" <= ch <= "\u9fff" for ch in s) or any(ch.isspace() for ch in s) or any(
            ch in "，。；、！？“”‘’：（）" for ch in s)
        if not prose:
            continue
        if any(w in s for w in BANNED_SUBSTRINGS):
            _err(errors, E_PLAN_FREE_TEXT, f"banned temporal/causal wording in {s!r}", value=s)
        else:
            _err(errors, E_PLAN_FREE_TEXT, f"prose string {s!r} is not a factId or enum token", value=s)

    index = _fact_index(facts)
    ordered_ids = [str(f.get("factId")) for f in facts]
    by_id = {str(f.get("factId")): f for f in facts}

    # --- fact kinds -------------------------------------------------------
    supported_ids: list[str] = []
    for fid in ordered_ids:
        kind = by_id[fid].get("kind")
        if kind in NON_ENTITY_KINDS:
            _err(errors, E_UNSUPPORTED_FACT_KIND,
                 f"{fid} kind={kind!r} has no entity; this round's plan schema does not cover it",
                 factId=fid, kind=kind)
        elif kind not in ENTITY_KINDS:
            _err(errors, E_UNSUPPORTED_FACT_KIND, f"{fid} kind={kind!r} is not registered", factId=fid, kind=kind)
        else:
            supported_ids.append(fid)
        if not by_id[fid].get("entityId"):
            _err(errors, E_UNSUPPORTED_FACT_KIND, f"{fid} has no entityId", factId=fid)

    # --- groups -----------------------------------------------------------
    groups = plan.get("groups")
    if not isinstance(groups, list) or not groups:
        _err(errors, E_GROUPS_EMPTY, "groups must be a non-empty list")
        groups = []

    flat: list[str] = []
    group_of: dict[str, int] = {}
    group_links: list[list[str]] = []
    for gi, group in enumerate(groups):
        if not isinstance(group, dict):
            _err(errors, E_GROUP_NOT_OBJECT, f"group {gi} is {type(group).__name__}")
            group_links.append([])
            continue
        for key in group:
            if key not in GROUP_KEYS:
                _err(errors, E_UNKNOWN_FIELD, f"group {gi} key {key!r} is not allowed", group=gi, field=key)
        gfacts = group.get("facts")
        links = group.get("links", [])
        if not isinstance(gfacts, list) or not gfacts:
            _err(errors, E_GROUP_FACTS_EMPTY, f"group {gi} facts must be a non-empty list", group=gi)
            group_links.append([])
            continue
        if not isinstance(links, list):
            _err(errors, E_LINK_COUNT, f"group {gi} links must be a list", group=gi)
            links = []
        if len(links) != max(0, len(gfacts) - 1):
            _err(errors, E_LINK_COUNT,
                 f"group {gi} has {len(gfacts)} facts and {len(links)} links", group=gi)
        for link in links:
            if link not in LINK_VALUES:
                _err(errors, E_LINK_VALUE, f"group {gi} link {link!r} is not allowed", group=gi, link=link)
        group_links.append([str(x) for x in links])

        prev: str | None = None
        for fi, raw in enumerate(gfacts):
            if not _is_fact_id(raw):
                _err(errors, E_FACT_ID_SHAPE, f"group {gi} has non-factId {raw!r}", group=gi, value=raw)
                continue
            fid = str(raw)
            if fid not in index:
                _err(errors, E_FACT_UNKNOWN, f"{fid} is not in the selected set", factId=fid)
                continue
            if fid in group_of:
                _err(errors, E_FACT_DUPLICATE, f"{fid} appears more than once", factId=fid)
                continue
            group_of[fid] = gi
            flat.append(fid)
            # link entity semantics
            if prev is not None:
                a = by_id[prev].get("entityId")
                b = by_id[fid].get("entityId")
                # the link index inside this group
                li = fi - 1
                want = "continuation" if a == b else "parallel"
                got = group_links[gi][li] if li < len(group_links[gi]) else None
                if got in LINK_VALUES and got != want:
                    _err(errors, E_LINK_ENTITY_MISMATCH,
                         f"group {gi} link {li} joins {prev}({a}) and {fid}({b}); expected {want}, got {got}",
                         group=gi, linkIndex=li, expected=want, actual=got)
            prev = fid

    missing = [fid for fid in ordered_ids if fid not in group_of]
    for fid in missing:
        _err(errors, E_FACT_MISSING, f"{fid} is not covered by any group", factId=fid)
    if not missing and flat != ordered_ids:
        _err(errors, E_ORDER, "flattened groups are not the input order; groups must be contiguous chunks",
             got=flat, expected=ordered_ids)

    stats["groups"] = len(groups)
    stats["mergedGroups"] = sum(1 for g in groups if isinstance(g, dict) and isinstance(g.get("facts"), list) and len(g["facts"]) > 1)

    # --- refs -------------------------------------------------------------
    refs = plan.get("refs")
    if not isinstance(refs, dict):
        _err(errors, E_REFS_NOT_OBJECT, "refs must be an object keyed by factId")
        refs = {}

    for fid in refs:
        if fid not in index:
            _err(errors, E_REF_UNKNOWN, f"refs has unknown factId {fid!r}", factId=fid)
    for fid in ordered_ids:
        if fid not in refs:
            _err(errors, E_REF_MISSING, f"{fid} has no ref", factId=fid)
            continue
        if refs[fid] not in REF_VALUES:
            _err(errors, E_REF_VALUE, f"{fid} ref {refs[fid]!r} is not allowed", factId=fid, value=refs[fid])

    # display-name ambiguity: same name for two selected entities makes both
    # `name` and `omit` unable to identify the subject.
    name_to_entities: dict[str, set[str]] = {}
    for f in facts:
        nm = _display_name(f)
        eid = f.get("entityId")
        if nm and eid:
            name_to_entities.setdefault(nm, set()).add(str(eid))
    ambiguous_entities = {
        eid for nm, eids in name_to_entities.items() if len(eids) > 1 for eid in eids
    }
    for fid in ordered_ids:
        if by_id[fid].get("entityId") in ambiguous_entities and refs.get(fid) in REF_VALUES:
            _err(errors, E_REF_AMBIGUOUS_NAME,
                 f"{fid} belongs to an entity whose display name is shared; ref {refs.get(fid)!r} is ambiguous",
                 factId=fid)

    # first mention / nearest antecedent / cross-group omission
    seen_entities: set[str] = set()
    for gi, group in enumerate(groups):
        if not isinstance(group, dict) or not isinstance(group.get("facts"), list):
            continue
        last_named: str | None = None
        last_named_fid: str | None = None
        for raw in group["facts"]:
            fid = str(raw)
            if fid not in index or refs.get(fid) not in REF_VALUES:
                continue
            eid = by_id[fid].get("entityId")
            ref = refs[fid]
            if ref == "name":
                last_named = eid
                last_named_fid = fid
                seen_entities.add(eid)
                continue
            # ref == omit
            if eid not in seen_entities:
                _err(errors, E_REF_FIRST_MENTION_OMIT,
                     f"{fid} omits the first mention of {eid}", factId=fid, entityId=eid)
            if last_named is None:
                if eid in seen_entities:
                    _err(errors, E_REF_CROSS_GROUP_OMIT,
                         f"{fid} omits across a group boundary; the name is only in an earlier group",
                         factId=fid, entityId=eid)
                else:
                    _err(errors, E_REF_OMIT_WITHOUT_NAME,
                         f"{fid} omits but no name precedes it in the same group", factId=fid)
            elif last_named != eid:
                _err(errors, E_REF_AMBIGUOUS_OMIT,
                     f"{fid} omits {eid} but the nearest preceding name is {last_named_fid}({last_named})",
                     factId=fid, entityId=eid, nearestNamedFact=last_named_fid)
            stats["omittedRefs"] += 1

    # --- edges ------------------------------------------------------------
    edges = plan.get("edges", [])
    if not isinstance(edges, list):
        _err(errors, E_EDGES_NOT_LIST, "edges must be a list")
        edges = []

    applicable_auth = {
        (str(e.get("from")), str(e.get("to")))
        for e in authorized_edges
        if str(e.get("from")) in index and str(e.get("to")) in index
    }
    seen_edges: set[tuple[str, str]] = set()
    for ei, edge in enumerate(edges):
        if not isinstance(edge, dict):
            _err(errors, E_EDGE_NOT_OBJECT, f"edge {ei} is {type(edge).__name__}")
            continue
        for key in edge:
            if key not in EDGE_KEYS:
                _err(errors, E_UNKNOWN_FIELD, f"edge {ei} key {key!r} is not allowed", edge=ei, field=key)
        src, dst = edge.get("from"), edge.get("to")
        if not _is_fact_id(src) or not _is_fact_id(dst):
            _err(errors, E_EDGE_ENDPOINT_UNKNOWN, f"edge {ei} endpoints must be factIds", edge=ei)
            continue
        if src not in index or dst not in index:
            _err(errors, E_EDGE_ENDPOINT_UNKNOWN, f"edge {ei} references a fact outside the selected set", edge=ei)
            continue
        if src == dst:
            _err(errors, E_EDGE_SELF, f"edge {ei} is self-referential", edge=ei)
            continue
        if index[src] >= index[dst]:
            _err(errors, E_EDGE_ORDER, f"edge {ei} must go forward in input order", edge=ei)
        if edge.get("type") not in EDGE_TYPES:
            _err(errors, E_EDGE_TYPE, f"edge {ei} type {edge.get('type')!r} is not allowed", edge=ei)
        if edge.get("mode") not in EDGE_MODES:
            _err(errors, E_EDGE_MODE, f"edge {ei} mode {edge.get('mode')!r} is not allowed", edge=ei)
        key = (str(src), str(dst))
        if key in seen_edges:
            _err(errors, E_EDGE_DUPLICATE, f"edge {key} appears more than once", edge=ei)
            continue
        seen_edges.add(key)
        if key not in applicable_auth:
            _err(errors, E_EDGE_UNAUTHORIZED,
                 f"edge {key} is not in the fixture authorization record", edge=ei)
        # the authorized target endpoint must stand alone (frozen rule from
        # organize-before-wording-v1: target starts its own expression with a name)
        gsrc, gdst = group_of.get(str(src)), group_of.get(str(dst))
        if gsrc is not None and gdst is not None and gsrc == gdst:
            _err(errors, E_EDGE_SAME_GROUP, f"edge {key} endpoints share one group", edge=ei)
        if gdst is not None and gdst < len(groups) and isinstance(groups[gdst], dict):
            if len(groups[gdst].get("facts", [])) != 1:
                _err(errors, E_EDGE_TARGET_NOT_ISOLATED,
                     f"edge {key} target {dst} must be its own group", edge=ei)

    if require_all_authorized:
        for key in sorted(applicable_auth - seen_edges):
            _err(errors, E_EDGE_MISSING,
                 f"authorized relation {key} is not carried by the plan", edge=list(key))

    stats["edges"] = len(seen_edges)
    return {"ok": not errors, "errors": errors, "stats": stats}


def plan_groups(plan: dict) -> list[list[str]]:
    return [list(g.get("facts", [])) for g in plan.get("groups", []) if isinstance(g, dict)]
