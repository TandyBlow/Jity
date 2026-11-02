# N3 organisation planner v3 (commit 2): ordered sentence groups with per
# group fact ids, TIME ATTRIBUTION and APPELLATION GRANTS — the structure
# the v2 N4 renderer consumes and the model is trained to use.
#
# Grouping follows the frozen rubric semantics (the D2 rule arm's R1-R6,
# reimplemented standalone so the registered module stays byte-stable):
#   R1  entity buckets in first-appearance order
#   R2  transitive merge via verbatim identical task goals
#   R2b same-name entities NEVER share a group (同名消歧: a merged group
#       would force the narration to conflate two people)
#   R3  a time fact joins the input-order predecessor's group (leading
#       time joins the first entity group)
#   R5  within-group input order; groups by minimal input index
# Appellation grants (R6, commit-2 rules):
#   - a pronoun (male→他, female→她, unknown→TA) is granted ONLY when the
#     entity has a gender hint AND its display name is unique across the
#     plan AND no other entity in the SAME group resolves to the same
#     pronoun string — otherwise the bare name (the safe fallback; a
#     granted pronoun is a capability, a name is not a failure)
#   - name-only grants emit nothing (absence of a grant = use the name)
# Time attribution: a group carrying a time fact exposes it as `time`.
#
# Hard invariants (checked by check_plan_v3): union(factIds) == selected
# ids; every refersTo anchored inside its own group; every grant's pronoun
# matches the gender table or is a name; a time fact sits in exactly one
# group and that group's `time` equals it.

PRONOUN_BY_GENDER = {"male": "他", "female": "她", "unknown": "TA"}


def _ill_formed(selected_facts: list) -> list:
    problems = []
    ids = [f.get("factId") for f in selected_facts]
    if any(not isinstance(x, str) or not x for x in ids):
        problems.append("missing or non-string factId")
    if len(set(ids)) != len(ids):
        problems.append("duplicate factId")
    return problems


def plan_v3(selected_facts: list, names: dict,
            gender_hints: dict | None = None) -> dict:
    """-> {"sentences": [...], "edges": {...}} or raises nothing; refusals
    return {"refusal": {"class", "reason"}} like the D2 rule arm."""
    problems = _ill_formed(selected_facts)
    if problems:
        return {"refusal": {"class": "ill-formed", "reason": "; ".join(problems)}}
    order = {f["factId"]: i for i, f in enumerate(selected_facts)}
    hints = gender_hints or {}

    entity_order, buckets = [], {}
    for f in selected_facts:
        e = f.get("entityId")
        if e is None:
            continue
        if e not in buckets:
            buckets[e] = []
            entity_order.append(e)
        buckets[e].append(f["factId"])
    if not entity_order:
        if any(f["kind"] == "time" for f in selected_facts) \
                and any(f["kind"] == "no_change" for f in selected_facts):
            # the no_change convention: a global no-change point with its
            # time advance forms ONE group (no grants — nobody to address)
            fids = [f["factId"] for f in selected_facts]
            t = next((f for f in selected_facts if f["kind"] == "time"), None)
            return {"sentences": [{"index": 0, "factIds": fids,
                                   "coreference": [],
                                   "time": ({"amount": t["amount"],
                                             "unit": t["unit"]} if t else None)}],
                    "edges": {"consecutive-time": False}}
        if any(f["kind"] == "time" for f in selected_facts):
            return {"refusal": {"class": "unsupported",
                                "reason": "time-orphan: a lone time fact has "
                                          "no entity group to attach to"}}
        return {"refusal": {"class": "unsupported",
                            "reason": "no-entity: an empty plan would drop "
                                      "selected facts"}}

    # display-name uniqueness across the plan (the same-name guard) —
    # counted over DISTINCT ENTITIES, not fact occurrences: one person with
    # five facts must still be pronominalisable
    name_counts = {}
    for e in entity_order:
        nm = names.get(e) or next((f.get("name") for f in selected_facts
                                   if f.get("entityId") == e), None)
        if nm:
            name_counts[nm] = name_counts.get(nm, 0) + 1

    parent = {e: e for e in entity_order}

    def find(e):
        while parent[e] != e:
            parent[e] = parent[parent[e]]
            e = parent[e]
        return e

    seen_goal = {}
    for f in selected_facts:
        if f["kind"] == "task_achieved":
            g = f["goal"]
            if g in seen_goal:
                a, b = find(seen_goal[g]), find(f["entityId"])
                if a != b:
                    parent[a] = b
            else:
                seen_goal[g] = f["entityId"]

    groups, group_of_entity = [], {}
    for e in entity_order:
        root = find(e)
        if root not in group_of_entity:
            group_of_entity[root] = len(groups)
            groups.append([])
        groups[group_of_entity[root]].extend(buckets[e])
    # R2b: same-name entities must not share a group — split the merged
    # group apart (union-find merges by goal text; two same-name people
    # reaching one goal text would otherwise be conflated)
    groups = _split_same_name(groups, selected_facts, order, names)

    entity_group_of = {}
    for gi, g in enumerate(groups):
        for fid in g:
            f = selected_facts[order[fid]]
            if f.get("entityId"):
                entity_group_of[f["entityId"]] = gi

    # R3: time facts join the input-order predecessor's group
    edges = {"consecutive-time": False}
    group_of = {fid: gi for gi, g in enumerate(groups) for fid in g}
    placed_times = {}
    for i, f in enumerate(selected_facts):
        if f["kind"] != "time":
            continue
        if i == 0:
            target = group_of[next(fid for fid in group_of
                                   if selected_facts[order[fid]].get("entityId"))]
        else:
            pred = selected_facts[i - 1]
            if pred["kind"] == "time":
                edges["consecutive-time"] = True
                target = placed_times[pred["factId"]]
            elif pred.get("entityId") and pred["entityId"] in entity_group_of:
                target = entity_group_of[pred["entityId"]]
            else:
                target = group_of[next(fid for fid in group_of
                                       if selected_facts[order[fid]].get("entityId"))]
        if target not in range(len(groups)):
            groups.append([])
            target = len(groups) - 1
        groups[target].append(f["factId"])
        placed_times[f["factId"]] = target

    groups = [sorted(g, key=lambda fid: order[fid]) for g in groups]
    groups = [g for g in groups if g]
    groups.sort(key=lambda g: min(order[fid] for fid in g))

    sentences = []
    for gi, g in enumerate(groups):
        grants = _appellation_grants(g, selected_facts, order, names, hints,
                                     name_counts)
        time_fact = next((selected_facts[order[fid]] for fid in g
                          if selected_facts[order[fid]]["kind"] == "time"), None)
        sentences.append({
            "index": gi, "factIds": g, "coreference": grants,
            "time": ({"amount": time_fact["amount"], "unit": time_fact["unit"]}
                     if time_fact else None)})
    return {"sentences": sentences, "edges": edges}


def _split_same_name(groups: list, selected_facts: list, order: dict,
                     names: dict) -> list:
    """Any group holding two same-name entities splits so the colliding
    entity starts a fresh group (input order kept); entities without a
    resolvable name never split anything."""
    out = []
    for g in groups:
        by_entity = {}
        for fid in g:
            eid = selected_facts[order[fid]].get("entityId")
            by_entity.setdefault(eid, []).append(fid)
        current, current_names = [], set()
        for eid, fids in by_entity.items():
            nm = names.get(eid) or next(
                (selected_facts[order[fid]].get("name") for fid in fids), None)
            if nm is not None and nm in current_names:
                out.append(current)
                current, current_names = [], set()
            current.extend(fids)
            if nm:
                current_names.add(nm)
        if current:
            out.append(current)
    return out


def _appellation_grants(group_fids: list, selected_facts: list, order: dict,
                        names: dict, hints: dict, name_counts: dict) -> list:
    """One grant per entity in the group whose PRONOUN is licensed:
    gender hint present, display name unique plan-wide, and the pronoun
    string not already granted to another entity in this group. The
    antecedent discipline lives in the COMPOSER (first mention in the text
    by name, later mentions by the granted pronoun) — a grant is a
    licence, not an obligation."""
    grants = []
    taken = set()
    for fid in group_fids:
        f = selected_facts[order[fid]]
        eid = f.get("entityId")
        if not eid or any(g["refersTo"] == eid for g in grants):
            continue
        name = names.get(eid) or f.get("name")
        hint = hints.get(eid)
        if not hint or hint not in PRONOUN_BY_GENDER:
            continue
        if name and name_counts.get(name, 0) > 1:
            continue  # 同名: never pronominalise a duplicated name
        pronoun = PRONOUN_BY_GENDER[hint]
        if pronoun in taken:
            # in-group pronoun collision: FIRST takes the pronoun, later
            # same-pronoun entities keep their names (the grant table
            # itself stays unambiguous; a wrong binding still fails G1)
            continue
        taken.add(pronoun)
        grants.append({"mention": pronoun, "refersTo": eid,
                       "pronoun": pronoun, "name": name})
    return grants


def check_plan_v3(plan: dict, selected_facts: list, names: dict,
                  gender_hints: dict | None = None) -> list:
    """Hard invariants for a v3 plan; empty list = holds."""
    problems = []
    if "refusal" in plan:
        return ["plan is a refusal"]
    hints = gender_hints or {}
    fact_ids = [f["factId"] for f in selected_facts]
    ids_in_plan = [fid for s in plan["sentences"] for fid in s["factIds"]]
    if sorted(ids_in_plan) != sorted(fact_ids):
        problems.append("plan ids != selected ids")
    by_id = {f["factId"]: f for f in selected_facts}
    for s in plan["sentences"]:
        if not s["factIds"]:
            problems.append(f"empty sentence group at index {s.get('index')}")
            continue
        group_entities = set()
        for fid in s["factIds"]:
            fact = by_id.get(fid)
            if fact is None:
                problems.append(f"unknown factId {fid} in sentence group")
                continue
            if fact.get("entityId"):
                group_entities.add(fact["entityId"])
        for ref in s.get("coreference") or []:
            if ref["refersTo"] not in group_entities:
                problems.append(f"refersTo {ref['refersTo']} not anchored in "
                                "its sentence group")
            expected_p = PRONOUN_BY_GENDER.get(hints.get(ref["refersTo"]))
            if expected_p is None or ref.get("pronoun") != expected_p:
                problems.append(f"grant {ref} does not match the gender table")
        name_to_eid = {}
        for fid in s["factIds"]:
            fact = by_id.get(fid)
            eid = fact.get("entityId") if fact else None
            nm = fact.get("name") if fact else None
            if nm and eid:
                prev = name_to_eid.get(nm)
                if prev is not None and prev != eid:
                    problems.append(f"same-name entities share group "
                                    f"{s.get('index')}: {nm}")
                name_to_eid[nm] = eid
    # time attribution: a time fact in exactly one group and that group's
    # time equals it
    for fid in fact_ids:
        f = by_id.get(fid) or {}
        if f.get("kind") != "time":
            continue
        holders = [s for s in plan["sentences"] if fid in s["factIds"]]
        if len(holders) != 1:
            problems.append(f"time fact {fid} in {len(holders)} groups")
            continue
        t = holders[0].get("time")
        if not t or t.get("amount") != f.get("amount") \
                or t.get("unit") != f.get("unit"):
            problems.append(f"time attribution mismatch for {fid}")
    return problems
